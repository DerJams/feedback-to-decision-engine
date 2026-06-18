"""Stratified sampling for the extraction dev smoke test.

This is a dev-only sampler. It oversamples low-rating reviews because the goal
of the 20-review sample is to stress-test extraction quality on the dense-signal
end, not to mirror the natural rating distribution. The two 4-star and one
5-star slots serve as false-positive controls: a good extractor should mostly
return no issues for "love it" reviews, and we want to see that on real data
before scaling up.
"""
from __future__ import annotations

import json
import random
from collections import defaultdict
from pathlib import Path

# Stratification for the 20-review dev sample, agreed at the stage-3 design
# step. Edit here if the philosophy changes; don't quietly skew at the call site.
DEFAULT_STRATA: dict[int, int] = {
    1: 10,
    2: 4,
    3: 3,
    4: 2,
    5: 1,
}

DEFAULT_SEED = 42


def read_jsonl(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def stratified_sample(
    reviews: list[dict],
    strata: dict[int, int] = DEFAULT_STRATA,
    seed: int = DEFAULT_SEED,
) -> list[dict]:
    """Return one review list, sampled per-rating per `strata`, then shuffled.

    Shuffling at the end means the extractor sees a mix in run order, not a
    block of 1-stars followed by a block of 5-stars. That matters if you ever
    eyeball partial output mid-run.
    """
    by_rating: dict[int, list[dict]] = defaultdict(list)
    for r in reviews:
        rating = r.get("rating")
        if isinstance(rating, int):
            by_rating[rating].append(r)

    rng = random.Random(seed)
    picked: list[dict] = []
    for rating, n in strata.items():
        pool = by_rating.get(rating, [])
        if len(pool) < n:
            raise ValueError(
                f"Stratum {rating}-star has only {len(pool)} reviews available, "
                f"need {n}. Pull more reviews or adjust the stratification."
            )
        picked.extend(rng.sample(pool, n))

    rng.shuffle(picked)
    return picked
