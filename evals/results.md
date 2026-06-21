# Extraction eval results

_Generated 2026-06-21 against 50 hand-labeled reviews._

## Review-level has_issue agreement (n = 50 reviews)

|                 | gold has_issue | gold no_issue |
|-----------------|---------------:|--------------:|
| model has_issue | 37 | 3 |
| model no_issue  | 0 | 10 |

Agreement: 47 / 50 = 94%.

## Per-issue agreement (n = 61 model issues across 50 reviews)

| Metric | Value |
|--------|-------|
| Precision (model issues matched to a gold issue) | 37 / 61 = 61% |
| Feature_area accuracy (of matched, n = 37) | 25 / 37 = 68% |
| Severity exact (of matched, n = 37) | 17 / 37 = 46% |
| Severity within-one (of matched, n = 37) | 32 / 37 = 86% |

_Matching is greedy by descending pair_score (feature_area match outweighs severity, exact severity outweighs within-one); see `evals/score.py:pair_score`. Adjudicate the proposed matches in `evals/matches_for_review.jsonl` before treating these numbers as final. Any correction there should be applied to `evals/gold.jsonl` and the script rerun._

## Failure modes

_To fill in from `evals/matches_for_review.jsonl` after adjudication. Categorize what the mismatches show: model over-extraction (unmatched_model_issues that are not real); model misses (unmatched_gold_issues that the model should have caught); feature_area confusions (and which directions they go); severity drift (does the model tend higher or lower than the rubric); anything systemic enough to change a prompt or schema decision._
