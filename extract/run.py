"""Full-corpus extraction over the filtered review set.

Run from the repo root:
    python -m extract.run

Iterates every review in extract.input_path (the language-filtered file),
runs the extractor on each, and writes the per-review extractions to
extract.output_path as JSONL of {"review": {...}, "extraction": {...}}.

Cached extractions skip the API. If the Anthropic API raises a rate-limit
error mid-run, the script saves the partial results and exits cleanly so a
later rerun resumes from the cache without re-spending tokens.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from extract.extractor import REPO_ROOT, Extractor, load_extract_config
from extract.sample import read_jsonl

# Reviews contain emoji and other non-cp1252 characters; Python's default Windows
# console encoding crashes printing them mid-run. Switch to utf-8 with
# backslashreplace so any unencodable char falls back to \uXXXX instead of raising.
for _stream in (sys.stdout, sys.stderr):
    _reconfigure = getattr(_stream, "reconfigure", None)
    if _reconfigure is not None:
        try:
            _reconfigure(encoding="utf-8", errors="backslashreplace")
        except (OSError, ValueError):
            pass

# Words that, when present in an exception, indicate the backend is rate
# limiting us. We match on status code + message text rather than catching the
# SDK's specific exception classes so the same handler works across SDK swaps.
RATE_LIMIT_MARKERS = (
    "rate limit",
    "rate_limit",
    "rate-limit",
    "quota",
    "tokens per",
    "too many requests",
    "daily",
    "limit exceeded",
)


def is_rate_limit_error(exc: BaseException) -> bool:
    if getattr(exc, "status_code", None) == 429:
        return True
    msg = str(exc).lower()
    return any(marker in msg for marker in RATE_LIMIT_MARKERS)


def write_results(results: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in results:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> int:
    config = load_extract_config()
    reviews = read_jsonl(config.input_path)
    print(f"Loaded {len(reviews)} reviews from {config.input_path.relative_to(REPO_ROOT)}")

    extractor = Extractor(config)
    print(f"  model:     {extractor.config.model}")
    print(f"  cache key: {extractor.cache_key}")
    print()

    results: list[dict] = []
    cached_total = 0
    api_total = 0
    issues_total = 0
    rate_limit_hit = False
    failure_msg = ""

    start = time.perf_counter()
    last_print = start
    try:
        for i, review in enumerate(reviews, start=1):
            try:
                record = extractor.extract(review)
            except Exception as e:
                if is_rate_limit_error(e):
                    rate_limit_hit = True
                    failure_msg = f"{type(e).__name__}: {e}"
                    print(f"\nRate limit hit at review {i}/{len(reviews)}: {failure_msg}")
                    break
                raise

            results.append({"review": review, "extraction": record})
            if record.get("cached"):
                cached_total += 1
            else:
                api_total += 1
            issues_total += len(record["issues"])

            now = time.perf_counter()
            if now - last_print > 5 or i == len(reviews):
                rate = i / (now - start) if now > start else 0
                eta = (len(reviews) - i) / rate if rate > 0 else 0
                print(
                    f"  [{i:>5}/{len(reviews)}]  cached={cached_total}  api={api_total}  "
                    f"issues={issues_total}  {rate:.1f} rev/s  eta {eta:.0f}s"
                )
                last_print = now
    finally:
        write_results(results, config.output_path)

    n = len(results)
    print()
    print("=== Extraction summary ===")
    print(f"Reviews processed:        {n}")
    print(f"Total issues extracted:   {issues_total}")
    if n:
        zero_issue = sum(1 for r in results if len(r["extraction"]["issues"]) == 0)
        print(f"Reviews with 0 issues:    {zero_issue}  ({zero_issue / n * 100:.1f}%)")
        print(f"Avg issues per review:    {issues_total / n:.2f}")
    print(f"Cache hits / new API:     {cached_total} / {api_total}")
    print(f"Output:                   {config.output_path.relative_to(REPO_ROOT)}")

    if rate_limit_hit:
        print()
        print("RATE LIMIT HIT - stopped cleanly. Partial extractions on disk + cache.")
        print(f"Next run will skip the {n} already-extracted reviews and continue.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
