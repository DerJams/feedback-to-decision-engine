"""Filter ingested reviews by detected language; auditable, non-destructive.

Run from the repo root:
    python -m ingest.language_filter

Reads `language_filter.input_path` (raw ingest), runs lingua-py detection on
each review's text, and writes two files:
- `output_path`   : reviews whose top detected language matches the target
                    at or above min_confidence (kept reviews, schema unchanged
                    so the downstream extractor consumes them transparently).
- `dropped_path`  : reviews that didn't make the bar, with `detected_language`
                    and `confidence` appended so the filter is auditable.

Prints before/after counts and the language breakdown of the dropped set.

Country='us' in the ingest pull is intentionally unchanged - that's the
US-storefront scope. This step is only about the language of the review text.
"""
from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import yaml
from lingua import Language, LanguageDetectorBuilder

REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = REPO_ROOT / "config" / "run.yaml"

# Map ISO 639-1 codes onto lingua's Language enum. Extend as needed - kept
# narrow so an unsupported code in run.yaml fails loudly rather than silently.
ISO_TO_LANGUAGE: dict[str, Language] = {
    "en": Language.ENGLISH,
}


@dataclass(frozen=True)
class FilterConfig:
    language: str
    min_confidence: float
    input_path: Path
    output_path: Path
    dropped_path: Path

    @property
    def target_language(self) -> Language:
        try:
            return ISO_TO_LANGUAGE[self.language]
        except KeyError as exc:
            raise ValueError(
                f"Unsupported language code {self.language!r}. "
                f"Add it to ISO_TO_LANGUAGE in ingest/language_filter.py."
            ) from exc


def load_filter_config(path: Path = CONFIG_PATH) -> FilterConfig:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    f = raw["language_filter"]
    return FilterConfig(
        language=f["language"],
        min_confidence=float(f["min_confidence"]),
        input_path=REPO_ROOT / f["input_path"],
        output_path=REPO_ROOT / f["output_path"],
        dropped_path=REPO_ROOT / f["dropped_path"],
    )


def read_jsonl(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def write_jsonl(records: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.parse_args(argv)
    config = load_filter_config()

    reviews = read_jsonl(config.input_path)
    print(f"Loaded {len(reviews)} reviews from {config.input_path.relative_to(REPO_ROOT)}")
    print(f"  target: {config.language!r}, min confidence: {config.min_confidence:.2f}")

    print("Building lingua detector...")
    t0 = time.perf_counter()
    detector = LanguageDetectorBuilder.from_all_languages().build()
    target = config.target_language
    print(f"  detector ready ({time.perf_counter() - t0:.1f}s)")

    kept: list[dict] = []
    dropped: list[dict] = []
    drop_breakdown: Counter[str] = Counter()

    t0 = time.perf_counter()
    for review in reviews:
        text = review.get("text", "")
        ranked = detector.compute_language_confidence_values(text)
        if ranked:
            top = ranked[0]
            top_lang_name = top.language.name.lower()
            top_conf = float(top.value)
            # Default to keep. Drop only when lingua is at least min_confidence
            # sure the top language is non-target. Lingua's confidence on 1-5
            # word reviews is often 0.05-0.20 even when it correctly identifies
            # English ("not bad", "better than Spotify"). Treating low-confidence
            # detections as "drop unless target" would filter out exactly the
            # short reviews we most want to keep. Confident non-English
            # detections (Portuguese, Vietnamese, etc. at 0.8-1.0) still get
            # dropped as intended.
            # `==` not `is`: lingua-py 2.x is a Rust port (PyO3) and its
            # Language type does not preserve Python's singleton-enum identity
            # across instantiations.
            is_target = top.language == target
            keep = is_target or top_conf < config.min_confidence
        else:
            top_lang_name = "unknown"
            top_conf = 0.0
            keep = False

        if keep:
            kept.append(review)
        else:
            drop_breakdown[top_lang_name] += 1
            dropped.append({
                **review,
                "detected_language": top_lang_name,
                "confidence": round(top_conf, 4),
            })
    print(f"  detection ran in {time.perf_counter() - t0:.1f}s")

    write_jsonl(kept, config.output_path)
    write_jsonl(dropped, config.dropped_path)

    print()
    print(f"Wrote {len(kept):>5} kept    -> {config.output_path.relative_to(REPO_ROOT)}")
    print(f"Wrote {len(dropped):>5} dropped -> {config.dropped_path.relative_to(REPO_ROOT)}")

    print("\n=== Filter summary ===")
    print(f"Before:  {len(reviews)}")
    pct_kept = (len(kept) / len(reviews) * 100) if reviews else 0.0
    print(f"After:   {len(kept)}  ({pct_kept:.1f}% kept)")
    print(f"Dropped: {len(dropped)}")

    if dropped:
        print("\nTop detected languages in the dropped set:")
        for lang, count in drop_breakdown.most_common(15):
            pct = count / len(dropped) * 100
            bar = "#" * int(round(pct / 2))
            print(f"  {lang:>22}  {count:>5}  {pct:5.1f}%  {bar}")
        remainder = sum(c for _, c in drop_breakdown.most_common()[15:])
        if remainder:
            print(f"  {'(other languages)':>22}  {remainder:>5}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
