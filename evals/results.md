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

Precision understates the model: all 61 extracted issues trace to real review text (zero hallucinations); the gap is labeling granularity. See Failure mode 3.

_Matching is greedy by descending pair_score (feature_area match outweighs severity, exact severity outweighs within-one); see `evals/score.py:pair_score`. Adjudicate the proposed matches in `evals/matches_for_review.jsonl` before treating these numbers as final. Any correction there should be applied to `evals/gold.jsonl` and the script rerun._

## Failure modes (n = 50 blind-labeled reviews)

1. Severity calibration is loose. Direction is reliable (86% within one level) but the
   exact level lands less than half the time (46%). The three borderline over-extractions
   were all tagged "high," hinting at a mild upward skew, though n is small. This is the
   largest open calibration question the eval surfaces.

2. Two real complaint types have no feature_area. Downloads/offline and app-stability
   (crashes, freezes, force-closes) have no dedicated category, so they scatter between
   "other" and core_listening. This is most of the residual feature_area disagreement
   (12 of 37 matched pairs) and aligns with the 19.4% of all extracted issues the model
   tags "other." Adding a stability and a downloads category is the clear next schema step.

3. Extra model issues are granularity, not hallucination. The model extracts ~1.6 issues
   per review to the gold's 1.0. All 24 unmatched model issues trace to real review text;
   none are invented. The 61% precision understates the model; the true false-positive
   surface is only the 3 borderline review-level extractions (a "used to be free" gripe, a
   logo-change complaint) where a vague remark was treated as an issue.

4. Detection skews permissive. Zero misses across 50 reviews; the only review-level errors
   are the 3 over-extractions on praise or borderline reviews.

Method note: gold labeled the primary issue per review, so strict precision-as-overlap
understates a model that decomposes multi-issue reviews. A future pass would use
multi-issue blind labeling for a clean precision figure.
