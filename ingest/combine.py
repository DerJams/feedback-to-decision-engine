"""Combine per-platform review files into one platform-tagged JSONL.

Run from the repo root, after both `ingest.soundcloud` (Android) and
`ingest.appstore` (iOS) have written their per-platform files:

    python -m ingest.combine

Reads:
- `ingest.android.output_path` (data/soundcloud_reviews_android.jsonl)
- `ingest.ios.output_path`     (data/soundcloud_reviews_ios.jsonl)

Writes:
- `ingest.output_path`         (data/soundcloud_reviews.jsonl)

Each record carries a `platform` field ("android" | "ios") set by the
per-platform ingest. This combined file is what `ingest.language_filter`
and the brief dataset stats read downstream.

Prints counts per platform and the actual date range each platform ended
up covering, so the labeling decision (which lookback window is right)
can be informed by what landed, not what was requested.

LOCAL ONLY. No API calls.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = REPO_ROOT / "config" / "run.yaml"

for _stream in (sys.stdout, sys.stderr):
    _reconfigure = getattr(_stream, "reconfigure", None)
    if _reconfigure is not None:
        try:
            _reconfigure(encoding="utf-8", errors="backslashreplace")
        except (OSError, ValueError):
            pass


@dataclass(frozen=True)
class CombineConfig:
    android_input: Path
    ios_input: Path
    combined_output: Path


def load_config(path: Path = CONFIG_PATH) -> CombineConfig:
    with path.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    ing = raw["ingest"]
    return CombineConfig(
        android_input=REPO_ROOT / ing["android"]["output_path"],
        ios_input=REPO_ROOT / ing["ios"]["output_path"],
        combined_output=REPO_ROOT / ing["output_path"],
    )


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def write_jsonl(records: list[dict], path: Path) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return len(records)


def summarize_platform(label: str, records: list[dict]) -> None:
    if not records:
        print(f"  {label:<8}: 0 reviews")
        return
    timestamps = [r["timestamp"] for r in records if r.get("timestamp")]
    earliest = min(timestamps) if timestamps else "(none)"
    latest = max(timestamps) if timestamps else "(none)"
    by_country = Counter(r.get("country") for r in records if r.get("country"))
    country_str = (
        ", ".join(f"{c}={n}" for c, n in by_country.most_common())
        if by_country
        else "(no country tag)"
    )
    print(
        f"  {label:<8}: {len(records):>5} reviews  "
        f"date range {earliest}  ->  {latest}  "
        f"[{country_str}]"
    )


def main() -> int:
    config = load_config()

    android_records = read_jsonl(config.android_input)
    ios_records = read_jsonl(config.ios_input)
    if not android_records:
        print(
            f"WARNING: {config.android_input.relative_to(REPO_ROOT)} is "
            "missing or empty. Run `python -m ingest.soundcloud` first."
        )
    if not ios_records:
        print(
            f"WARNING: {config.ios_input.relative_to(REPO_ROOT)} is missing "
            "or empty. Run `python -m ingest.appstore` first."
        )

    combined = android_records + ios_records
    written = write_jsonl(combined, config.combined_output)
    print(
        f"Wrote {written} combined reviews -> "
        f"{config.combined_output.relative_to(REPO_ROOT)}"
    )

    print("\n=== Per-platform actuals ===")
    summarize_platform("android", android_records)
    summarize_platform("ios", ios_records)

    by_platform = Counter(r.get("platform") for r in combined)
    print("\nCombined platform breakdown:")
    for plat, n in by_platform.most_common():
        share = n / len(combined) * 100 if combined else 0.0
        print(f"  {plat or '(untagged)':<8}: {n:>5}  ({share:5.1f}%)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
