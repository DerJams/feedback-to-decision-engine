# Feedback-to-Decision Engine

Turns app store reviews into a ranked opportunity brief and a draft PRD &mdash;
using an LLM as the structuring layer, but keeping prioritization, evidence,
and judgment in code you can audit.

> **Status:** scaffolding. A worked example using a real SoundCloud Android
> pull will lead this README once the pipeline is end-to-end.

## What it does

1. **Ingest** &mdash; pulls newest reviews for a target app (default: SoundCloud
   Android) into normalized JSONL.
2. **Extract** &mdash; runs each review through an LLM (Cerebras-hosted
   `gpt-oss-120b`) against a neutral schema (`theme`, `severity`, `sentiment`,
   `feature_area`, `segment_hint`). Schema validation happens at the API
   boundary via tool-calling, so enum compliance is free. Results are cached
   on disk so scoring can be iterated without re-spending API calls.
3. **Cluster** &mdash; dedupes and groups extracted issues into themes.
4. **Score** &mdash; ranks themes by a config-driven weighting (frequency,
   severity, strategic fit). The weights live in `config/weights.yaml` so the
   prioritization logic is legible, not hidden in code.
5. **Brief** &mdash; renders a markdown opportunity brief: ranked themes,
   verbatim quotes cited to source review IDs, estimated reach, and a short
   "what I'd do about it." Auto-drafts a one-page PRD for the top theme; every
   claim traces back to real review evidence.
6. **Eval** &mdash; hand-labeled test set plus scripts measuring extraction
   accuracy and cluster coherence; results written to a run log.

## Why neutral extraction matters

The extractor sees only the schema &mdash; no hints, no priors about what to
look for. If the top opportunity turns out to be, say, podcast playback bugs or
offline sync, that's because reviewers said so, not because the prompt led the
witness. This is the part of the system that deserves the most scrutiny in
review, so the prompt and the schema both live in version control and are short
enough to read in one sitting.

## Repo layout

```
config/   weighting, extraction schema, run settings (all YAML)
ingest/   pull reviews -> normalized JSONL
extract/  Claude call with schema validation + on-disk cache
cluster/  dedupe + theme grouping
score/    rank themes via config weights
brief/    markdown opportunity brief + auto-drafted PRD
evals/    hand-labeled set + extraction/cluster eval scripts
data/     gitignored - reviews, cached extractions, run outputs
```

## Setup

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env   # then set CEREBRAS_API_KEY
```

## Worked example

*Coming once the pipeline runs end-to-end. Will use the real SoundCloud
Android pull so you can read the brief alongside the source reviews and judge
the reasoning for yourself.*
