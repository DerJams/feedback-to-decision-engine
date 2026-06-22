"""Build a balanced down-sample of the language-filtered review corpus.

Run from the repo root:
    python -m ingest.balance

Reads `data/soundcloud_reviews_en.jsonl`, draws ~500 reviews from each
platform (android, iOS) stratified by star rating in proportion to that
platform's natural distribution, then force-includes any review_id in
`evals/gold.jsonl` that is present in the corpus so the extraction eval
still has gold overlap. Writes the result to
`data/soundcloud_reviews_en_balanced.jsonl`, preserving every original
field (platform, country, timestamp, app_version, ...).

The point of the down-sample is to fit one full extraction pass under the
Cerebras free-tier daily token budget (~1M tokens/day). The Android subset
is ~2.8k of the EN corpus and the iOS subset is ~1k; keeping each at ~500
keeps the comparison balanced rather than letting Android dominate, while
the gold-id pin keeps `evals/score.py` reproducible.

LOCAL ONLY. No API calls.
"""
from __future__ import annotations

import json
import random
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = REPO_ROOT / "config" / "run.yaml"
GOLD_PATH = REPO_ROOT / "evals" / "gold.jsonl"
OUTPUT_PATH = REPO_ROOT / "data" / "soundcloud_reviews_en_balanced.jsonl"

SEED = 42
TARGET_PER_PLATFORM = 500
PLATFORMS = ("android", "ios")

for _stream in (sys.stdout, sys.stderr):
    _reconfigure = getattr(_stream, "reconfigure", None)
    if _reconfigure is not None:
        try:
            _reconfigure(encoding="utf-8", errors="backslashreplace")
        except (OSError, ValueError):
            pass


def read_jsonl(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def proportional_strata(
    pool_by_rating: dict[int, list[dict]],
    target: int,
) -> dict[int, int]:
    """Allocate `target` reviews across ratings in proportion to natural rate.

    Largest-remainder rounding so the per-rating counts sum exactly to target.
    """
    total = sum(len(v) for v in pool_by_rating.values())
    if total == 0:
        return {}
    raw = {r: target * len(v) / total for r, v in pool_by_rating.items()}
    floors = {r: int(x) for r, x in raw.items()}
    used = sum(floors.values())
    remainders = sorted(
        ((raw[r] - floors[r], r) for r in raw), reverse=True
    )
    # Distribute the residual to ratings with the largest fractional remainders.
    for _, r in remainders[: target - used]:
        floors[r] += 1
    # Never request more than the pool can supply.
    for r, pool in pool_by_rating.items():
        floors[r] = min(floors[r], len(pool))
    return floors


def main() -> int:
    raw_config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    en_path = REPO_ROOT / raw_config["language_filter"]["output_path"]
    reviews = read_jsonl(en_path)
    print(f"Loaded {len(reviews)} reviews from {en_path.relative_to(REPO_ROOT)}")

    by_id: dict[str, dict] = {r["review_id"]: r for r in reviews}

    # Group per (platform, rating) for stratified sampling within platform.
    by_plat_rating: dict[str, dict[int, list[dict]]] = {
        p: defaultdict(list) for p in PLATFORMS
    }
    for r in reviews:
        plat = r.get("platform")
        rating = r.get("rating")
        if plat in PLATFORMS and isinstance(rating, int):
            by_plat_rating[plat][rating].append(r)

    rng = random.Random(SEED)
    picked: dict[str, dict] = {}  # review_id -> review, dedup by id

    print()
    print(f"Stratified sample (target {TARGET_PER_PLATFORM} per platform):")
    for plat in PLATFORMS:
        pool_by_rating = dict(by_plat_rating[plat])
        target = min(TARGET_PER_PLATFORM, sum(len(v) for v in pool_by_rating.values()))
        strata = proportional_strata(pool_by_rating, target)
        for rating in sorted(strata):
            n = strata[rating]
            pool = pool_by_rating[rating]
            available = len(pool)
            chosen = rng.sample(pool, n) if n <= available else pool
            for r in chosen:
                picked[r["review_id"]] = r
            print(
                f"  {plat:<8} {rating}-star: target={n:>3} / pool={available:>4}  picked={len(chosen)}"
            )

    # Force-include gold review_ids that exist in the corpus, so evals/score.py
    # has the same labeling-set IDs to join against.
    gold_ids: set[str] = set()
    if GOLD_PATH.exists():
        for row in read_jsonl(GOLD_PATH):
            rid = row.get("review_id")
            if rid:
                gold_ids.add(rid)
    gold_in_corpus = gold_ids & set(by_id)
    gold_not_in_picked = gold_in_corpus - set(picked)
    for rid in sorted(gold_not_in_picked):
        picked[rid] = by_id[rid]

    print()
    print(f"Gold review_ids: {len(gold_ids)} in gold.jsonl")
    print(f"  {len(gold_in_corpus)} present in current corpus")
    print(f"  {len(gold_in_corpus & set(picked) - gold_not_in_picked)} already covered by stratified pick")
    print(f"  {len(gold_not_in_picked)} force-added on top")

    out = list(picked.values())
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", encoding="utf-8") as fh:
        for r in out:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    # Summary
    plat_counts = Counter(r.get("platform") for r in out)
    us_count = sum(1 for r in out if r.get("country") == "us")
    rating_by_plat = {p: Counter() for p in PLATFORMS}
    for r in out:
        plat = r.get("platform")
        if plat in rating_by_plat and isinstance(r.get("rating"), int):
            rating_by_plat[plat][r["rating"]] += 1

    print()
    print(f"Wrote {len(out)} balanced reviews -> {OUTPUT_PATH.relative_to(REPO_ROOT)}")
    print()
    print("Per-platform counts:")
    for p in PLATFORMS:
        print(f"  {p:<8}: {plat_counts.get(p, 0):>4}")
    print(f"  US country tag (across both platforms): {us_count}")
    print()
    print("Rating distribution within each platform:")
    print(f"  {'platform':<8} {'1*':>4} {'2*':>4} {'3*':>4} {'4*':>4} {'5*':>4}  total")
    for p in PLATFORMS:
        counts = rating_by_plat[p]
        row = " ".join(f"{counts.get(s, 0):>4}" for s in (1, 2, 3, 4, 5))
        total = sum(counts.values())
        print(f"  {p:<8} {row}  {total:>5}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
