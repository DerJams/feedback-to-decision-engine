# Feedback-to-Decision Engine

A pipeline that turns public app-store reviews into a ranked, evidence-traced product-discovery synthesis - with a validated extraction step so the synthesis is trustworthy, not just plausible.

## Why this exists

Review volume is huge and unstructured, and the loudest complaint isn't always the highest-priority one - a fact that's easy to assert and easy to lose in a spreadsheet. This project makes the prioritization explicit and contestable: every theme is ranked from a documented weighted score, every claim traces to a verbatim review.

## Key findings (SoundCloud iOS + Android, 90-day window, 3,846 reviews)

- **The most-mentioned theme is not the #1 priority.** `excessive ads` is mentioned **316 times** (3x the next theme) but ranks **#4** on priority. `app crashes` ranks **#1** - lower volume but higher severity, in a feature area weighted as core-product hygiene.
- **A taxonomy fix surfaced the #1 priority theme.** The extraction schema initially had no `stability` or `downloads` category; "the app keeps crashing" was getting bucketed into a generic `other`. Adding those two enums made the top-priority theme on the entire corpus (`app crashes`) visible for the first time.
- **iOS-vs-Android was compared on a matched US-only window** (2026-06-03 → 2026-06-20, 17 days, US-only on both sides) to avoid confounding platform with country. An apparent Android skew on `app crashes` (1.5x in the unmatched view) **dissolved under the control** (1.1x matched). A real Android skew on `playback stops unexpectedly` **held and got stronger** (2.8x → 4.5x). The iOS ads-skew held at similar magnitude in both views.

**Full findings:** [`synthesis/discovery_synthesis.md`](synthesis/discovery_synthesis.md)

## How it works

```
ingest -> language filter -> LLM extraction -> clustering -> scoring -> synthesis
```

1. **Ingest** - pull newest reviews per app from the iOS App Store + Google Play, normalized JSONL.
2. **Language filter** - drop non-English reviews via lingua-py; dropped reviews kept for audit.
3. **LLM issue extraction** - per-review, Anthropic Claude Haiku 4.5, structured/tool-calling so enum compliance is enforced at the API boundary. Per-review cache keyed on provider + model + prompt + schema, so any change invalidates prior extractions.
4. **Clustering** - local sentence-transformer embeddings (`all-MiniLM-L6-v2`), sentiment-partitioned agglomerative clustering at cosine 0.45, medoid labels.
5. **Scoring** - `0.40 * normalized_frequency + 0.40 * normalized_severity + 0.20 * strategic_fit`. Frequency is log-scaled to handle the heavy-tail cluster size distribution; a volume floor keeps tiny clusters out of the ranking.
6. **Synthesis** - human-readable deliverable: ranked themes, verbatim quotes, prevalence-vs-priority breakdown, platform comparison.

## Validation

The extraction step was measured against a 50-review hand-labeled gold set, before any synthesis was written:

- **Review-level detection: 94%** (45 / 48)
- **0 missed reviews**, **3 false positives** flagged on benign text
- **Feature_area accuracy: 57% strict / 83% hierarchical** (same-parent)
- Gold n = 48 (intersection with the current corpus; 2 reviews aged out of the 90-day ingest window)

Full numbers: [`evals/results.md`](evals/results.md). This matters because the synthesis is only as trustworthy as the extraction - it was measured, not assumed.

## Design choices worth noting

- **Scoring weights are documented product priors, not magic numbers.** Every `strategic_fit` value in [`config/weights.yaml`](config/weights.yaml) carries a one-line rationale. If a recruiter disagrees with the ranking, the weight that produced it is one file away. The ranking is contestable by design.
- **One model, one schema across the whole corpus.** The full 3,846-review extraction was re-run end-to-end after the schema added `stability` and `downloads`, so the eval numbers actually describe what's in the synthesis. No mixed-provenance results.
- **Smaller clean sample over larger confounded sample.** The iOS-vs-Android comparison is built on a 17-day US-only matched window even though a larger 88-day cross-platform sample exists - because the larger sample conflates platform with country (Android in this corpus is 100% US, iOS is multi-country). A deliberate analytical trade.
- **What this is NOT.** Public reviews self-select to extremes, so this is **directional pain signal, not representative prevalence**. There is no telemetry, no internal ticket overlay, no funnel data. This is discovery: it surfaces *where* users hurt; it does not prescribe fixes or set product targets.

## Run it

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env   # then set ANTHROPIC_API_KEY
```

```powershell
python -m ingest.soundcloud      # Android pull (Google Play)
python -m ingest.appstore        # iOS pull (App Store, multi-country to dodge per-country caps)
python -m ingest.combine         # merge per-platform files into one platform-tagged JSONL
python -m ingest.language_filter # drop non-English reviews (kept for audit)
python -m extract.run            # only stage that calls an API
python -m cluster.run
python -m score.run
python -m evals.score            # validation against evals/gold.jsonl
```

Intermediate artifacts land in `data/` (gitignored). The extract stage caches per-review results on disk, so a reproduction run is cheap unless the model, prompt, or schema changes.

## Repo structure

- `ingest/` - per-platform review scrapers + language filter
- `extract/` - LLM extraction backends (Anthropic, Cerebras, Groq) + per-review cache
- `cluster/` - local-embedding clustering of extracted issue themes
- `score/` - transparent weighted scoring of clusters
- `synthesis/` - human-readable deliverable, the headline finding lives here
- `evals/` - hand-labeled gold set + scorer for extraction validation
- `config/` - runtime config (`run.yaml`, `extraction_schema.yaml`) and scoring weights (`weights.yaml`)
