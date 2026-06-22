"""Full-corpus extraction with bounded concurrency + retry/backoff.

Run from the repo root:
    python -m extract.run

Iterates every review in `extract.input_path` (the language-filtered file),
runs the extractor on each through a thread pool of `extract.max_concurrency`
workers, and writes per-review extractions to `extract.output_path` as JSONL
of {"review": {...}, "extraction": {...}}.

Retry/backoff: on 429 / 5xx / connection-style errors the per-review task
sleeps with exponentially growing jitter and retries up to
`extract.max_retries` times. The thread pool keeps making progress on other
reviews in the meantime, so a sustained rate limit slows the run rather
than killing it. Per-review cache files are still atomic (one file per
review_id under the provider+model+schema cache key), so a hard-killed run
resumes cleanly without re-spending tokens on already-extracted reviews.
"""
from __future__ import annotations

import json
import random
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

from extract.extractor import REPO_ROOT, Extractor, load_extract_config
from extract.sample import read_jsonl

for _stream in (sys.stdout, sys.stderr):
    _reconfigure = getattr(_stream, "reconfigure", None)
    if _reconfigure is not None:
        try:
            _reconfigure(encoding="utf-8", errors="backslashreplace")
        except (OSError, ValueError):
            pass


# Substrings that mark a retryable error when status codes are not exposed.
# We match on both the SDK exception text and the underlying provider message
# so the same handler works across Anthropic, Cerebras, and SDK swaps.
RETRYABLE_MARKERS = (
    "rate limit",
    "rate_limit",
    "rate-limit",
    "too many requests",
    "quota",
    "timeout",
    "timed out",
    "connection",
    "temporarily unavailable",
    "503",
    "502",
    "504",
)

# Daily-cap detection. A per-minute 429 retries cleanly via backoff; a
# daily-cap 429 would burn the whole retry budget on every concurrent worker
# without ever recovering. When we see one of these markers we set a stop
# event and abort the pool early so we do not keep hammering 429s.
DAILY_CAP_MARKERS = (
    "per day",
    "per-day",
    "tokens per day",
    "tokens-per-day",
    "requests per day",
    "requests-per-day",
    "daily limit",
    "daily rate limit",
    "daily quota",
    "daily token",
    "reached your daily",
    "reset-day",
)


def is_daily_limit(exc: BaseException) -> bool:
    msg = str(exc).lower()
    return any(marker in msg for marker in DAILY_CAP_MARKERS)


@dataclass
class RetryStats:
    """Thread-shared counters/log for the retry/backoff path."""

    retries: int = 0
    rate_limit_events: int = 0
    server_error_events: int = 0
    failures: int = 0
    daily_cap_hit: bool = False
    daily_cap_msg: str = ""
    events: list[dict] = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def record(
        self,
        review_id: str,
        attempt: int,
        exc: BaseException,
        wait_seconds: float,
    ) -> None:
        msg = str(exc)
        is_429 = (
            getattr(exc, "status_code", None) == 429
            or "rate limit" in msg.lower()
            or "too many requests" in msg.lower()
            or "quota" in msg.lower()
        )
        with self.lock:
            self.retries += 1
            if is_429:
                self.rate_limit_events += 1
            else:
                self.server_error_events += 1
            # Keep the last 50 events to bound memory on long runs.
            self.events.append(
                {
                    "review_id": review_id,
                    "attempt": attempt,
                    "error_type": type(exc).__name__,
                    "msg": msg[:160],
                    "wait_seconds": round(wait_seconds, 2),
                }
            )
            if len(self.events) > 50:
                self.events.pop(0)


def is_retryable(exc: BaseException) -> bool:
    status = getattr(exc, "status_code", None)
    if status in (408, 425, 429, 500, 502, 503, 504):
        return True
    msg = str(exc).lower()
    return any(marker in msg for marker in RETRYABLE_MARKERS)


def extract_with_retry(
    extractor: Extractor,
    review: dict,
    max_retries: int,
    backoff_base: float,
    backoff_max: float,
    stats: RetryStats,
    stop_event: threading.Event,
) -> dict:
    """Call extractor.extract with exponential backoff + jitter on retryable errors.

    Aborts immediately (no retry, no further sleep) if the error looks like a
    daily cap; the stop_event is set so peer workers also bail out instead of
    each burning their own retry budget.
    """
    if stop_event.is_set():
        raise RuntimeError("aborting: daily cap detected")
    delay = backoff_base
    for attempt in range(1, max_retries + 2):
        try:
            return extractor.extract(review)
        except Exception as exc:
            if is_daily_limit(exc):
                with stats.lock:
                    if not stats.daily_cap_hit:
                        stats.daily_cap_hit = True
                        stats.daily_cap_msg = str(exc)[:400]
                stop_event.set()
                raise
            if attempt > max_retries or not is_retryable(exc):
                with stats.lock:
                    stats.failures += 1
                raise
            jitter = random.uniform(0.5, 1.5)
            wait = min(backoff_max, delay) * jitter
            stats.record(review["review_id"], attempt, exc, wait)
            time.sleep(wait)
            delay = min(backoff_max, delay * 2)
    # Unreachable: the loop either returns or raises.
    raise RuntimeError("extract_with_retry exhausted retries without raising")


def write_results(results: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in results:
            if row is None:
                continue
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> int:
    config = load_extract_config()
    reviews = read_jsonl(config.input_path)
    print(f"Loaded {len(reviews)} reviews from {config.input_path.relative_to(REPO_ROOT)}")

    extractor = Extractor(config)
    print(f"  provider:       {extractor.config.provider}")
    print(f"  model:          {extractor.config.model}")
    print(f"  max_concurrency: {extractor.config.max_concurrency}")
    print(f"  max_retries:    {extractor.config.max_retries}")
    print(f"  cache key:      {extractor.cache_key}")
    print()

    results: list[dict | None] = [None] * len(reviews)
    stats = RetryStats()
    stop_event = threading.Event()
    cached_total = 0
    api_total = 0
    issues_total = 0
    done = 0
    last_headers_snapshot: dict[str, str] | None = None

    def headers_summary() -> str:
        h = getattr(extractor.backend, "last_headers", None)
        if not h:
            return ""
        req_rem = h.get("x-ratelimit-remaining-requests", "?")
        tok_rem = h.get("x-ratelimit-remaining-tokens", "?")
        parts = [f"req_rem={req_rem}", f"tok_rem={tok_rem}"]
        # Surface any "day"-scoped fields immediately if Groq adds them.
        for k, v in sorted(h.items()):
            if "day" in k.lower():
                parts.append(f"{k}={v}")
        return "  hdrs[" + " ".join(parts) + "]"

    start = time.perf_counter()
    last_print = start

    try:
        with ThreadPoolExecutor(max_workers=config.max_concurrency) as pool:
            futures = {
                pool.submit(
                    extract_with_retry,
                    extractor,
                    review,
                    config.max_retries,
                    config.backoff_base_seconds,
                    config.backoff_max_seconds,
                    stats,
                    stop_event,
                ): i
                for i, review in enumerate(reviews)
            }
            for fut in as_completed(futures):
                i = futures[fut]
                try:
                    record = fut.result()
                except Exception as exc:
                    if stats.daily_cap_hit:
                        # First daily-cap error; report it once. Peer workers
                        # will all see stop_event and bail out without further
                        # API calls. Skip the per-review failure spam.
                        continue
                    print(f"  [{i:>5}] FAILED after retries: {type(exc).__name__}: {exc}")
                    continue
                results[i] = {"review": reviews[i], "extraction": record}
                if record.get("cached"):
                    cached_total += 1
                else:
                    api_total += 1
                    last_headers_snapshot = getattr(
                        extractor.backend, "last_headers", None
                    ) or last_headers_snapshot
                issues_total += len(record["issues"])
                done += 1
                now = time.perf_counter()
                if now - last_print > 5 or done == len(reviews):
                    elapsed = max(1e-9, now - start)
                    rate = done / elapsed
                    api_rate = api_total / elapsed
                    eta = (len(reviews) - done) / rate if rate > 0 else 0
                    print(
                        f"  [{done:>5}/{len(reviews)}]  cached={cached_total}  "
                        f"api={api_total}  issues={issues_total}  "
                        f"{rate:.1f} rev/s  ({api_rate * 60:.0f} req/min)  "
                        f"retries={stats.retries}  eta {eta:.0f}s"
                        f"{headers_summary()}",
                        flush=True,
                    )
                    last_print = now
                if stop_event.is_set():
                    # Cancel pending futures rather than queue more API attempts.
                    for f in futures:
                        if not f.done():
                            f.cancel()
                    break
    finally:
        write_results(results, config.output_path)

    final = [r for r in results if r is not None]
    n = len(final)
    elapsed = time.perf_counter() - start
    print()
    print("=== Extraction summary ===")
    print(f"Reviews processed:        {n} / {len(reviews)}")
    print(f"Total issues extracted:   {issues_total}")
    if n:
        zero_issue = sum(1 for r in final if len(r["extraction"]["issues"]) == 0)
        print(f"Reviews with 0 issues:    {zero_issue}  ({zero_issue / n * 100:.1f}%)")
        print(f"Avg issues per review:    {issues_total / n:.2f}")
    print(f"Cache hits / new API:     {cached_total} / {api_total}")
    print(
        f"Throughput:               {n / max(1e-9, elapsed):.1f} rev/s "
        f"({api_total / max(1e-9, elapsed) * 60:.0f} req/min over the whole run)"
    )
    print(
        f"Retries:                  {stats.retries} "
        f"(rate-limit: {stats.rate_limit_events}, server: {stats.server_error_events})"
    )
    if stats.failures:
        print(f"Hard failures:            {stats.failures}")
    if stats.daily_cap_hit:
        print()
        print("=== Daily cap detected, aborted early ===")
        print(f"Reviews completed before stop: {n} / {len(reviews)}")
        last_h = getattr(extractor.backend, "last_headers", None) or {}
        if last_h:
            print("Last rate-limit headers:")
            for k in sorted(last_h):
                print(f"  {k}: {last_h[k]}")
        else:
            print("(no rate-limit headers captured; provider may not expose them)")
        print(f"Error message excerpt: {stats.daily_cap_msg}")
        print("Resume with another `python -m extract.run` after the reset window;")
        print("per-review cache means already-extracted reviews will not re-spend tokens.")
    print(f"Output:                   {config.output_path.relative_to(REPO_ROOT)}")
    return 2 if stats.daily_cap_hit else 0


if __name__ == "__main__":
    raise SystemExit(main())
