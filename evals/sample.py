"""Draw a stratified blind-labeling sample for the extraction eval.

Run from the repo root:
    python -m evals.sample

Reads:
- `data/soundcloud_reviews_en.jsonl` (language-filtered review corpus)

Writes:
- `evals/to_label.jsonl` with `{review_id, text}` only - no rating, no model
  output, nothing that could bias a blind hand-label. Star-stratum is logged
  to stdout for the eval harness, not written into the file.

Strata are weighted toward 1-3 star reviews (where complaints concentrate) but
keep 10 of the 50 reviews in the 4-5 star band so the eval can score the
extractor's ZERO-issue calls too. The seed is fixed for reproducibility - the
labeling set should not move under the labeler's feet between runs.

LOCAL ONLY. No API calls.
"""
from __future__ import annotations

import json
import random
import sys
from collections import Counter
from pathlib import Path

import yaml

from extract.extractor import REPO_ROOT
from extract.sample import read_jsonl

for _stream in (sys.stdout, sys.stderr):
    _reconfigure = getattr(_stream, "reconfigure", None)
    if _reconfigure is not None:
        try:
            _reconfigure(encoding="utf-8", errors="backslashreplace")
        except (OSError, ValueError):
            pass


RUN_CONFIG_PATH = REPO_ROOT / "config" / "run.yaml"
OUTPUT_PATH = REPO_ROOT / "evals" / "to_label.jsonl"

SEED = 42

# Per-star allocation. Sums to 50. Heavy on 1-3 stars where complaints
# concentrate; 5 reviews each at 4 and 5 stars so the eval covers zero-issue
# calls (high-rated reviews are mostly praise and should return `issues: []`).
STRATA: dict[int, int] = {
    1: 18,
    2: 12,
    3: 10,
    4: 5,
    5: 5,
}


def main() -> int:
    raw = yaml.safe_load(RUN_CONFIG_PATH.read_text(encoding="utf-8"))
    en_path = REPO_ROOT / raw["language_filter"]["output_path"]
    reviews = read_jsonl(en_path)

    by_rating: dict[int, list[dict]] = {}
    for r in reviews:
        rating = r.get("rating")
        if rating is None:
            continue
        by_rating.setdefault(int(rating), []).append(r)

    rng = random.Random(SEED)
    picked: list[dict] = []
    for star, n_target in sorted(STRATA.items()):
        pool = by_rating.get(star, [])
        if len(pool) < n_target:
            print(
                f"WARNING: only {len(pool)} reviews available for {star}-star "
                f"stratum (target {n_target}); taking all."
            )
            picked.extend(pool)
        else:
            picked.extend(rng.sample(pool, n_target))

    # Shuffle the final order so the labeler does not see strata in blocks.
    # Same RNG so the order is reproducible under the fixed seed.
    rng.shuffle(picked)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", encoding="utf-8") as fh:
        for r in picked:
            fh.write(
                json.dumps(
                    {"review_id": r["review_id"], "text": r["text"]},
                    ensure_ascii=False,
                )
                + "\n"
            )

    breakdown = Counter(int(r["rating"]) for r in picked)
    print(f"Wrote {len(picked)} reviews -> {OUTPUT_PATH.relative_to(REPO_ROOT)}")
    print(f"Seed: {SEED}")
    print("Star-stratum breakdown:")
    for star in sorted(breakdown):
        print(f"  {star}-star : {breakdown[star]:>2}")
    print()
    print(
        "Next step: hand-label evals/gold.jsonl from to_label.jsonl using "
        "evals/rubric.md. Each line: "
        '{"review_id": ..., "has_issue": bool, "issues": [{"feature_area": ..., '
        '"severity": ...}, ...]}.'
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
