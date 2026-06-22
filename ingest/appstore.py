"""Pull and normalize SoundCloud iOS reviews from the App Store.

Run from the repo root:
    python -m ingest.appstore

Parallel to `ingest/soundcloud.py` for Android. Resolves SoundCloud's iOS
trackId at runtime via the iTunes Search API (no hardcoded guessed id),
verifies the seller name to skip copycat hits ("Soundloud", etc.), then
pulls reviews across the markets listed in `ingest.ios.countries`. Within
each market, pagination is newest-first and stops once a review crosses the
`ingest.lookback_days` cutoff in config/run.yaml.

The trackId is a global identifier, so we resolve it ONCE in the US store
and reuse it across all markets - what changes per market is the storefront
the library hits, not the app id.

The library `app-store-web-scraper` caps each (app, country) pull at ~500
reviews; pulling across multiple English-language markets gives more recent
volume and broader geographic coverage.

Output: data/soundcloud_reviews_ios.jsonl (per-platform), then
`python -m ingest.combine` merges it with the Android pull into
data/soundcloud_reviews.jsonl.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Iterator

import yaml
from app_store_web_scraper import AppStoreEntry

REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = REPO_ROOT / "config" / "run.yaml"

# iTunes Search API. Public, no auth. Used only to resolve app_name -> trackId.
ITUNES_SEARCH_URL = "https://itunes.apple.com/search"

for _stream in (sys.stdout, sys.stderr):
    _reconfigure = getattr(_stream, "reconfigure", None)
    if _reconfigure is not None:
        try:
            _reconfigure(encoding="utf-8", errors="backslashreplace")
        except (OSError, ValueError):
            pass


@dataclass(frozen=True)
class IosIngestConfig:
    app_name: str
    expected_seller_prefix: str
    countries: list[str]
    output_path: Path
    page_delay_seconds: float
    lookback_days: int


def load_config(path: Path = CONFIG_PATH) -> IosIngestConfig:
    with path.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    ing = raw["ingest"]
    ios = ing["ios"]
    return IosIngestConfig(
        app_name=ios["app_name"],
        expected_seller_prefix=ios["expected_seller_prefix"],
        countries=list(ios["countries"]),
        output_path=REPO_ROOT / ios["output_path"],
        page_delay_seconds=float(ing["page_delay_seconds"]),
        lookback_days=int(ing["lookback_days"]),
    )


def resolve_app_id(
    app_name: str,
    expected_seller_prefix: str,
    country: str = "us",
    timeout: float = 20.0,
) -> int:
    """Resolve the App Store trackId for `app_name` via the iTunes Search API.

    Filters by `expected_seller_prefix` on `sellerName` to skip copycat hits
    that crowd the search results. Raises if no matching app is found.
    """
    params = {
        "term": app_name,
        "country": country,
        "entity": "software",
        "limit": "10",
    }
    url = f"{ITUNES_SEARCH_URL}?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(url, timeout=timeout) as r:
        data = json.load(r)
    hits = data.get("results", [])
    for h in hits:
        seller = h.get("sellerName", "")
        if seller.startswith(expected_seller_prefix):
            return int(h["trackId"])
    raise RuntimeError(
        f"Could not resolve {app_name!r} via iTunes Search: no hit had "
        f"sellerName starting with {expected_seller_prefix!r}. "
        f"Got sellers: {[h.get('sellerName') for h in hits]}"
    )


def normalize(review, country: str) -> dict | None:
    """Map an app-store-web-scraper AppReview to the project schema.

    iOS exposes `title` and `country` as extra metadata beyond the Android
    schema; both are preserved. Returns None if the review has no text
    content.
    """
    text = (review.content or "").strip()
    if not text:
        return None
    date = review.date
    if date.tzinfo is None:
        date = date.replace(tzinfo=timezone.utc)
    return {
        "review_id": f"ios-{country}-{review.id}",
        "rating": review.rating,
        "text": text,
        "timestamp": date.astimezone(timezone.utc).isoformat(),
        "app_version": review.app_version or "",
        "platform": "ios",
        "country": country,
        "title": review.title or "",
    }


def fetch_country(
    app_id: int,
    country: str,
    cutoff: datetime,
) -> Iterator[dict]:
    """Yield in-window reviews from one App Store storefront.

    Iterates the library's reviews() iterator (newest-first) and stops as
    soon as a review's date drops below `cutoff`. The library caps each
    storefront at MAX_REVIEWS_LIMIT (~500) regardless.
    """
    entry = AppStoreEntry(app_id=app_id, country=country)
    page_yield = 0
    for review in entry.reviews(limit=AppStoreEntry.MAX_REVIEWS_LIMIT):
        review_date = review.date
        if review_date.tzinfo is None:
            review_date = review_date.replace(tzinfo=timezone.utc)
        if review_date < cutoff:
            print(
                f"  country={country}: reached cutoff after {page_yield} "
                "reviews, stopping"
            )
            return
        normalized = normalize(review, country=country)
        if normalized is None:
            continue
        page_yield += 1
        yield normalized
    print(f"  country={country}: yielded {page_yield} (library cap or feed end)")


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
    by_country = Counter(r.get("country") for r in records)
    ratings = Counter(r.get("rating") for r in records)
    timestamps = [r["timestamp"] for r in records if r.get("timestamp")]
    earliest = min(timestamps) if timestamps else "(none)"
    latest = max(timestamps) if timestamps else "(none)"
    total = sum(ratings.values())

    print("\n=== iOS pull summary ===")
    print(f"Total reviews: {len(records)}")
    print("Per-country counts:")
    for c, n in by_country.most_common():
        print(f"  {c:<4} : {n}")
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
        f"Resolving {config.app_name!r} App Store trackId via iTunes Search "
        f"(seller must start with {config.expected_seller_prefix!r})..."
    )
    app_id = resolve_app_id(
        config.app_name,
        config.expected_seller_prefix,
        country="us",
    )
    print(f"  resolved: trackId={app_id}")
    print(
        f"Pulling iOS reviews newest-first until cutoff "
        f"{cutoff.isoformat()} (lookback_days={config.lookback_days})..."
    )
    print(f"  countries={config.countries}  delay={config.page_delay_seconds}s")

    all_records: list[dict] = []
    for i, country in enumerate(config.countries):
        if i > 0:
            time.sleep(config.page_delay_seconds)
        print(f"\n  country={country}: fetching...")
        all_records.extend(fetch_country(app_id, country, cutoff))

    written = write_jsonl(all_records, config.output_path)
    print(
        f"\nWrote {written} reviews to {config.output_path.relative_to(REPO_ROOT)}"
    )

    records = read_jsonl(config.output_path)
    summarize(records)
    return 0


if __name__ == "__main__":
    sys.exit(main())
