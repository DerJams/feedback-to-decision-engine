"""Pull and normalize SoundCloud Android reviews from Google Play.

Run from the repo root:
    python -m ingest.soundcloud

Date-bounded: pages newest-first and stops once a review crosses the
`ingest.lookback_days` cutoff in config/run.yaml (no fixed count cap). Each
record is tagged `platform: "android"` so the downstream combined file can
report per-platform counts.

Output: data/soundcloud_reviews_android.jsonl (per-platform), then
`python -m ingest.combine` merges it with the iOS pull into
data/soundcloud_reviews.jsonl.
"""
from __future__ import annotations

import json
import sys
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Iterator

import yaml
from google_play_scraper import Sort, reviews

REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = REPO_ROOT / "config" / "run.yaml"
PAGE_SIZE = 200

for _stream in (sys.stdout, sys.stderr):
    _reconfigure = getattr(_stream, "reconfigure", None)
    if _reconfigure is not None:
        try:
            _reconfigure(encoding="utf-8", errors="backslashreplace")
        except (OSError, ValueError):
            pass


@dataclass(frozen=True)
class AndroidIngestConfig:
    app_id: str
    lang: str
    country: str
    output_path: Path
    page_delay_seconds: float
    lookback_days: int


def load_config(path: Path = CONFIG_PATH) -> AndroidIngestConfig:
    with path.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    ing = raw["ingest"]
    android = ing["android"]
    return AndroidIngestConfig(
        app_id=android["app_id"],
        lang=android["lang"],
        country=android["country"],
        output_path=REPO_ROOT / android["output_path"],
        page_delay_seconds=float(ing["page_delay_seconds"]),
        lookback_days=int(ing["lookback_days"]),
    )


def to_utc(at) -> datetime | None:
    """google-play-scraper's `at` is a naive datetime (UTC). Make it
    timezone-aware so it can be compared against an aware cutoff. Returns
    None if the value is missing or the wrong type.
    """
    if not isinstance(at, datetime):
        return None
    if at.tzinfo is None:
        return at.replace(tzinfo=timezone.utc)
    return at.astimezone(timezone.utc)


def normalize(raw: dict, country: str) -> dict | None:
    """Map a raw scraper record to the project schema. Returns None if it
    should be dropped (no text, no timestamp).

    `platform` and `country` are added so the combined file can report
    per-platform / per-market volumes without an extra join.
    """
    text = (raw.get("content") or "").strip()
    if not text:
        return None
    at = to_utc(raw.get("at"))
    if at is None:
        return None
    return {
        "review_id": raw.get("reviewId"),
        "rating": raw.get("score"),
        "text": text,
        "timestamp": at.isoformat(),
        "app_version": raw.get("reviewCreatedVersion") or raw.get("appVersion") or "",
        "platform": "android",
        "country": country,
    }


def fetch(config: AndroidIngestConfig, cutoff: datetime) -> Iterator[dict]:
    """Yield normalized reviews newest-first, stopping when any review's
    timestamp drops below `cutoff`. Within a page we keep yielding the
    in-window records and break as soon as we see an out-of-window one,
    since `Sort.NEWEST` is monotonically decreasing in timestamp.
    """
    seen: set[str] = set()
    token = None
    page = 0
    yielded = 0
    while True:
        page += 1
        batch, token = reviews(
            config.app_id,
            lang=config.lang,
            country=config.country,
            sort=Sort.NEWEST,
            count=PAGE_SIZE,
            continuation_token=token,
        )
        if not batch:
            print(f"  page {page}: empty batch, stopping")
            break
        kept = 0
        crossed_cutoff = False
        for raw in batch:
            rid = raw.get("reviewId")
            if not rid or rid in seen:
                continue
            at = to_utc(raw.get("at"))
            if at is None:
                continue
            if at < cutoff:
                crossed_cutoff = True
                break
            normalized = normalize(raw, country=config.country)
            if normalized is None:
                continue
            seen.add(rid)
            yielded += 1
            kept += 1
            yield normalized
        print(
            f"  page {page}: pulled {len(batch)}, kept {kept}, "
            f"total {yielded}{' (cutoff reached)' if crossed_cutoff else ''}"
        )
        if crossed_cutoff:
            break
        if token is None:
            print("  no continuation token returned - feed exhausted")
            break
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
    print("\n=== Android pull summary ===")
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


def main() -> int:
    config = load_config()
    cutoff = datetime.now(timezone.utc) - timedelta(days=config.lookback_days)
    print(
        f"Pulling SoundCloud Android reviews newest-first until cutoff "
        f"{cutoff.isoformat()} (lookback_days={config.lookback_days})..."
    )
    print(
        f"  app_id={config.app_id}  lang={config.lang}  country={config.country}  "
        f"delay={config.page_delay_seconds}s"
    )
    written = write_jsonl(fetch(config, cutoff), config.output_path)
    print(
        f"\nWrote {written} reviews to {config.output_path.relative_to(REPO_ROOT)}"
    )

    records = read_jsonl(config.output_path)
    summarize(records)
    return 0


if __name__ == "__main__":
    sys.exit(main())
