"""Smoke-test the extractor on a 20-review stratified dev sample.

Run from the repo root:
    python -m extract.run_sample

Writes the per-review extractions to the path in config/run.yaml
(extract.output_path), prints a one-line-per-review trace, and finally prints
one full extraction so you can read a real structured result.
"""
from __future__ import annotations

import json

from extract.extractor import REPO_ROOT, Extractor, load_extract_config
from extract.sample import DEFAULT_STRATA, read_jsonl, stratified_sample


def main() -> int:
    config = load_extract_config()
    reviews = read_jsonl(config.input_path)
    sample = stratified_sample(reviews)

    print(f"Sampled {len(sample)} reviews from {config.input_path.relative_to(REPO_ROOT)}")
    print(f"  strata (1-5 stars): {dict(DEFAULT_STRATA)}")

    extractor = Extractor(config)
    print(f"  model: {extractor.config.model}")
    print(f"  cache key: {extractor.cache_key}")
    print()

    results: list[dict] = []
    issues_total = 0
    cached_total = 0
    for i, review in enumerate(sample, start=1):
        record = extractor.extract(review)
        results.append({"review": review, "extraction": record})
        n = len(record["issues"])
        issues_total += n
        if record.get("cached"):
            cached_total += 1
        cached_marker = " (cached)" if record.get("cached") else ""
        snippet = review["text"].replace("\n", " ")
        if len(snippet) > 60:
            snippet = snippet[:60] + "..."
        print(
            f"  [{i:>2}/{len(sample)}] {review['rating']}*  "
            f"{n} issue(s){cached_marker}  | {snippet!r}"
        )

    output_path = config.output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as fh:
        for row in results:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(
        f"\nWrote {len(results)} extractions ({issues_total} issues total, "
        f"{cached_total} from cache) to {output_path.relative_to(REPO_ROOT)}"
    )

    print("\n=== one detailed extraction ===")
    for row in results:
        if row["extraction"]["issues"]:
            print(json.dumps(row, ensure_ascii=False, indent=2))
            break
    else:
        print("(no review produced any issues - investigate the prompt or schema)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
