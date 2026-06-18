"""Pull and normalize SoundCloud Android reviews from Google Play.

Run from the repo root:
    python -m ingest.soundcloud --count 3000

Output: data/soundcloud_reviews.jsonl (one normalized review per line),
followed by a printed summary (total, rating distribution, date range) and
three sample records.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, Iterator

import yaml
from google_play_scraper import Sort, reviews

REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = REPO_ROOT / "config" / "run.yaml"
PAGE_SIZE = 200


@dataclass(frozen=True)
class IngestConfig:
    app_id: str
    default_count: int
    page_delay_seconds: float
    lang: str
    country: str
    output_path: Path


def load_config(path: Path = CONFIG_PATH) -> IngestConfig:
    with path.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    ing = raw["ingest"]
    return IngestConfig(
        app_id=ing["app_id"],
        default_count=int(ing["default_count"]),
        page_delay_seconds=float(ing["page_delay_seconds"]),
        lang=ing["lang"],
        country=ing["country"],
        output_path=REPO_ROOT / ing["output_path"],
    )


def normalize(raw: dict) -> dict | None:
    """Map a raw scraper record to our schema, or None if it should be dropped."""
    text = (raw.get("content") or "").strip()
    if not text:
        return None
    at = raw.get("at")
    timestamp = at.isoformat() if isinstance(at, datetime) else (at or "")
    return {
        "review_id": raw.get("reviewId"),
        "rating": raw.get("score"),
        "text": text,
        "timestamp": timestamp,
        "app_version": raw.get("reviewCreatedVersion") or raw.get("appVersion") or "",
    }


def fetch(config: IngestConfig, target_count: int) -> Iterator[dict]:
    """Yield normalized, deduped reviews until target_count or the feed runs out."""
    seen: set[str] = set()
    token = None
    page = 0
    yielded = 0
    while yielded < target_count:
        page += 1
        request_size = min(PAGE_SIZE, target_count - yielded)
        batch, token = reviews(
            config.app_id,
            lang=config.lang,
            country=config.country,
            sort=Sort.NEWEST,
            count=request_size,
            continuation_token=token,
        )
        if not batch:
            print(f"  page {page}: empty batch, stopping")
            break
        kept = 0
        for raw in batch:
            rid = raw.get("reviewId")
            if not rid or rid in seen:
                continue
            normalized = normalize(raw)
            if normalized is None:
                continue
            seen.add(rid)
            yielded += 1
            kept += 1
            yield normalized
            if yielded >= target_count:
                break
        print(f"  page {page}: pulled {len(batch)}, kept {kept}, total {yielded}/{target_count}")
        if token is None:
            print("  no continuation token returned - feed exhausted")
            break
        if yielded < target_count:
            time.sleep(config.page_delay_seconds)


def write_jsonl(records: Iterable[dict], path: Path) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with path.open("w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            written += 1
    return written


def read_jsonl(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def summarize(records: list[dict]) -> None:
    if not records:
        print("\nNo records written - nothing to summarize.")
        return
    ratings = Counter(r.get("rating") for r in records)
    timestamps = [r["timestamp"] for r in records if r.get("timestamp")]
    earliest = min(timestamps) if timestamps else "(none)"
    latest = max(timestamps) if timestamps else "(none)"
    total = sum(ratings.values())
    print("\n=== Pull summary ===")
    print(f"Total reviews: {len(records)}")
    print("Rating distribution:")
    for stars in (1, 2, 3, 4, 5):
        count = ratings.get(stars, 0)
        pct = (count / total * 100) if total else 0.0
        bar = "#" * int(round(pct / 2))
        print(f"  {stars} star: {count:>5}  {pct:5.1f}%  {bar}")
    missing = sum(c for r, c in ratings.items() if r not in (1, 2, 3, 4, 5))
    if missing:
        print(f"  (unrated/other: {missing})")
    print(f"Date range: {earliest}  ->  {latest}")


def print_samples(records: list[dict], n: int = 3) -> None:
    print(f"\n=== {n} sample records ===")
    for i, rec in enumerate(records[:n], start=1):
        print(f"\n--- sample {i} ---")
        text = rec.get("text", "")
        if len(text) > 400:
            text = text[:400].rstrip() + "..."
        printable = {**rec, "text": text}
        print(json.dumps(printable, ensure_ascii=False, indent=2))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--count",
        type=int,
        default=None,
        help="target review count (overrides ingest.default_count in run.yaml)",
    )
    args = parser.parse_args(argv)

    config = load_config()
    target = args.count if args.count is not None else config.default_count

    print(f"Pulling up to {target} reviews for {config.app_id} (sort=newest)...")
    print(f"  lang={config.lang}  country={config.country}  delay={config.page_delay_seconds}s")
    written = write_jsonl(fetch(config, target), config.output_path)
    print(f"\nWrote {written} reviews to {config.output_path.relative_to(REPO_ROOT)}")

    records = read_jsonl(config.output_path)
    summarize(records)
    print_samples(records, n=3)
    return 0


if __name__ == "__main__":
    sys.exit(main())
