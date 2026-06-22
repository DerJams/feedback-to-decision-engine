"""Smoke-test the extractor on a 20-review stratified, platform-mixed sample.

Run from the repo root:
    python -m extract.run_sample

Draws 10 Android + 10 iOS reviews stratified by star rating (5/2/2/1/0 each
side), so the smoke test exercises both platforms AND the false-positive
end (high-rating reviews that should yield 0 issues). Uses the SAME
extractor backend, concurrency, and retry path as the full corpus run; the
only difference is the corpus size. Output is NOT written to the full-corpus
output path - extractions land in `data/extracted_issues_sample.jsonl` so the
real run's output is never polluted.

Prints:
- provider/model in use
- a per-review one-line trace
- 3 full sample extractions (JSON) so you can read the schema landing
- observed throughput (rev/sec and req/min)
- a retry/backoff summary if any 429/5xx events fired
"""
from __future__ import annotations

import json
import random
import sys
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from extract.extractor import REPO_ROOT, Extractor, load_extract_config
from extract.run import RetryStats, extract_with_retry
from extract.sample import read_jsonl

for _stream in (sys.stdout, sys.stderr):
    _reconfigure = getattr(_stream, "reconfigure", None)
    if _reconfigure is not None:
        try:
            _reconfigure(encoding="utf-8", errors="backslashreplace")
        except (OSError, ValueError):
            pass


SAMPLE_OUTPUT_PATH = REPO_ROOT / "data" / "extracted_issues_sample.jsonl"
SEED = 42

# Per-platform mini-strata. Sums to 10 per platform = 20 total. Heavy on the
# 1-3 star end where complaints concentrate; a single 4-star slot in each
# platform serves as a false-positive control.
PER_PLATFORM_STRATA: dict[int, int] = {
    1: 5,
    2: 2,
    3: 2,
    4: 1,
    5: 0,
}


def stratified_by_platform(
    reviews: list[dict],
    seed: int = SEED,
) -> list[dict]:
    """Return a 20-review sample: 10 from each platform, star-stratified within."""
    by_plat_rating: dict[tuple[str, int], list[dict]] = defaultdict(list)
    for r in reviews:
        plat = r.get("platform")
        rating = r.get("rating")
        if plat not in ("android", "ios") or not isinstance(rating, int):
            continue
        by_plat_rating[(plat, rating)].append(r)

    rng = random.Random(seed)
    picked: list[dict] = []
    for plat in ("android", "ios"):
        for rating, n in PER_PLATFORM_STRATA.items():
            if n == 0:
                continue
            pool = by_plat_rating.get((plat, rating), [])
            if len(pool) < n:
                raise ValueError(
                    f"Stratum {plat}/{rating}-star has only {len(pool)} reviews, "
                    f"need {n}. Re-pull or rebalance the strata."
                )
            picked.extend(rng.sample(pool, n))

    rng.shuffle(picked)
    return picked


def main() -> int:
    config = load_extract_config()
    reviews = read_jsonl(config.input_path)
    sample = stratified_by_platform(reviews)

    extractor = Extractor(config)
    print(
        f"Smoke test on {len(sample)} reviews "
        f"({sum(1 for r in sample if r.get('platform') == 'android')} android + "
        f"{sum(1 for r in sample if r.get('platform') == 'ios')} ios)"
    )
    print(f"  provider:        {extractor.config.provider}")
    print(f"  model:           {extractor.config.model}")
    print(f"  max_concurrency: {extractor.config.max_concurrency}")
    print(f"  max_retries:     {extractor.config.max_retries}")
    print(f"  cache key:       {extractor.cache_key}")
    print()

    results: list[dict | None] = [None] * len(sample)
    stats = RetryStats()
    stop_event = threading.Event()
    cached_total = 0
    api_total = 0
    issues_total = 0
    start = time.perf_counter()

    with ThreadPoolExecutor(max_workers=extractor.config.max_concurrency) as pool:
        futures = {
            pool.submit(
                extract_with_retry,
                extractor,
                review,
                extractor.config.max_retries,
                extractor.config.backoff_base_seconds,
                extractor.config.backoff_max_seconds,
                stats,
                stop_event,
            ): i
            for i, review in enumerate(sample)
        }
        for fut in as_completed(futures):
            i = futures[fut]
            try:
                record = fut.result()
            except Exception as exc:
                print(
                    f"  [{i + 1:>2}] FAILED: {type(exc).__name__}: {exc}"
                )
                continue
            results[i] = {"review": sample[i], "extraction": record}
            if record.get("cached"):
                cached_total += 1
            else:
                api_total += 1
            issues_total += len(record["issues"])
            review = sample[i]
            snippet = (review["text"] or "").replace("\n", " ")
            if len(snippet) > 60:
                snippet = snippet[:60] + "..."
            cached_marker = " (cached)" if record.get("cached") else ""
            print(
                f"  [{i + 1:>2}/{len(sample)}]  {review.get('platform', '?'):<7} "
                f"{review.get('rating', '?')}*  {len(record['issues'])} issue(s)"
                f"{cached_marker}  | {snippet!r}"
            )

    elapsed = time.perf_counter() - start

    SAMPLE_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    final = [r for r in results if r is not None]
    with SAMPLE_OUTPUT_PATH.open("w", encoding="utf-8") as fh:
        for row in final:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(
        f"\nWrote {len(final)} extractions ({issues_total} issues total) "
        f"-> {SAMPLE_OUTPUT_PATH.relative_to(REPO_ROOT)}"
    )

    print()
    print("=== Throughput ===")
    rate = len(final) / max(1e-9, elapsed)
    api_rate = api_total / max(1e-9, elapsed)
    print(f"Wallclock:           {elapsed:.1f}s")
    print(f"Throughput:          {rate:.2f} rev/s")
    print(f"Effective req rate:  {api_rate * 60:.0f} req/min ({api_total} fresh API calls)")
    print(f"Cache hits:          {cached_total}")

    # If the backend captured rate-limit headers from a real response (Groq
    # does this via with_raw_response), surface them so the actual account
    # limits are visible without consulting docs.
    last_headers = getattr(extractor.backend, "last_headers", None)
    if last_headers:
        print()
        print("=== Provider rate-limit headers (last successful response) ===")
        for k in sorted(last_headers):
            print(f"  {k}: {last_headers[k]}")

    print()
    print("=== Retry / backoff events ===")
    if stats.retries:
        print(
            f"{stats.retries} retries total "
            f"(rate-limit: {stats.rate_limit_events}, server: {stats.server_error_events})"
        )
        print(f"{stats.failures} hard failures after exhausting retries")
        print(f"Last {min(len(stats.events), 5)} retry events:")
        for ev in stats.events[-5:]:
            print(
                f"  review {ev['review_id'][:8]}...  attempt {ev['attempt']}  "
                f"{ev['error_type']}  waited {ev['wait_seconds']}s  "
                f"msg={ev['msg']!r}"
            )
    else:
        print("none (no 429 / 5xx fired in the smoke test)")

    print()
    print(f"=== {min(3, len(final))} sample extractions ===")
    shown = 0
    # Prefer to show extractions with issues, so you can see the schema land.
    by_issues_desc = sorted(
        final,
        key=lambda r: -len(r["extraction"]["issues"]),
    )
    for row in by_issues_desc:
        if shown >= 3:
            break
        print()
        print(json.dumps(row, ensure_ascii=False, indent=2))
        shown += 1
    if shown == 0:
        print("(no review produced any issues - investigate the prompt or schema)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
