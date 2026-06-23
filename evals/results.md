# Extraction eval results

_Generated 2026-06-22 against 48 hand-labeled reviews (gold set size: 50; 2 aged out of the current 90-day ingest window and are not in the extraction snapshot)._

Aged-out gold review_ids (excluded from scoring):
- `68b5998a-3205-48db-83a7-a4d990db2b23`
- `89ac06eb-5fc0-4435-86cf-bcf53f582758`

## Review-level has_issue agreement (n = 48 reviews)

|                 | gold has_issue | gold no_issue |
|-----------------|---------------:|--------------:|
| model has_issue | 35 | 3 |
| model no_issue  | 0 | 10 |

Agreement: 45 / 48 = 94%.

## Per-issue agreement (n = 56 model issues across 48 reviews)

| Metric | Value |
|--------|-------|
| Precision (model issues matched to a gold issue) | 35 / 56 = 62% |
| Feature_area accuracy - strict, exact enum (of matched, n = 35) | 20 / 35 = 57% |
| Feature_area accuracy - hierarchical, same parent (of matched, n = 35) | 29 / 35 = 83% |
| Severity exact (of matched, n = 35) | 17 / 35 = 49% |
| Severity within-one (of matched, n = 35) | 29 / 35 = 83% |

_The gap between strict and hierarchical feature_area accuracy is driven by reviews whose original gold label was bucketed into other/"App functionality" - the model resolved many of those to the finer `stability` and `downloads` categories that were added to the schema after the gold was written. Parent map: `app_functionality` = {stability, downloads, core_listening, account, other}; `monetization`, `social`, `discovery` stand alone (see `evals/score.py:FEATURE_AREA_PARENT`)._

_Matching is greedy by descending pair_score (feature_area match outweighs severity, exact severity outweighs within-one); see `evals/score.py:pair_score`. Adjudicate the proposed matches in `evals/matches_for_review.jsonl` before treating these numbers as final. Any correction there should be applied to `evals/gold.jsonl` and the script rerun._

## Failure modes

_To fill in from `evals/matches_for_review.jsonl` after adjudication. Categorize what the mismatches show: model over-extraction (unmatched_model_issues that are not real); model misses (unmatched_gold_issues that the model should have caught); feature_area confusions (and which directions they go); severity drift (does the model tend higher or lower than the rubric); anything systemic enough to change a prompt or schema decision._
