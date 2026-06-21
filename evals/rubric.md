# Extraction labeling rubric

You are labeling a blind sample of reviews to score the extraction stage. For each review in `evals/to_label.jsonl`, write one JSON line to `evals/gold.jsonl`:

```json
{"review_id": "...", "has_issue": true, "issues": [{"feature_area": "core_listening", "severity": "high", "desc": "playback pauses mid-song"}, {"feature_area": "monetization", "severity": "medium", "desc": "too many ads"}]}
```

For reviews with no extractable issue, write:

```json
{"review_id": "...", "has_issue": false, "issues": []}
```

**Fields per issue:**

- `feature_area` (required) - one of the six values listed under "Feature areas" below.
- `severity` (required) - one of `low`, `medium`, `high`. See "Severity scale" below.
- `desc` (required, 3-5 words) - a short noun-phrase description of what the complaint actually is, in your own words. Examples: `"playback pauses mid-song"`, `"too many ads"`, `"google login broken"`, `"cannot cancel subscription"`. This field is NOT used by the auto-matcher; it is carried into `evals/matches_for_review.jsonl` next to the matched model theme so adjudication can tell whether the model found the same complaint or just landed in the same feature_area by accident.

Label only from the review text. Do not look at the model's extraction output (`data/extracted_issues.jsonl`) before finalizing the gold set, or the agreement numbers will be optimistic.

## What counts as an issue

An issue is a **specific, actionable** product-side concern. To count, the review must:

- Name a concrete problem (something the product does or fails to do), not just generic affect.
- Be product-side, not user-side. (A track being slow on the user's own network is not an issue; the app failing to buffer gracefully is.)
- Be roughly clusterable across reviews. "It's broken" alone is too generic; "songs pause mid-play" is specific enough.

**Not an issue:**

- Generic praise or complaint without a target ("garbage app", "fire", "10/10").
- User-side problems (their phone, their network, their headphones).
- Off-topic content (reviewer's life story, plug for their own music).
- Pure feature requests that aren't framed as a current pain ("would be nice to have X").

If a review contains both signal and noise, label only the signal portions.

## Multiple issues per review

If a review names more than one distinct concern (e.g. ads AND playback failures), emit one entry per concern in the `issues` array. There is no fixed cap, but for very long ranty reviews label the issues a PM would actually find load-bearing, not every passing aside.

## Reviews where the reviewer praises the product

Label `has_issue: false, issues: []`. Praise is not an issue; the eval is checking whether the extractor correctly returns zero issues for high-rated, praise-only reviews. (Some of the labeling set is intentionally 4-5 star for exactly this test.)

## Severity scale

Lifted directly from `config/extraction_schema.yaml`. Severity describes how much THIS review describes the issue degrading the user's experience, not the absolute severity of the underlying bug.

- **`high`** = blocks core use, or causes the user to consider leaving.
- **`medium`** = repeated friction.
- **`low`** = minor annoyance.

When in doubt between two levels, pick the lower one. The threshold for `high` is "user is or would be leaving."

## Feature areas

Lifted directly from `config/extraction_schema.yaml`. Use `other` rather than forcing a fit.

- **`core_listening`** - playback, audio, music selection, pause/play, queue, downloads for offline listen, the basic listen flow.
- **`discovery`** - search, recommendations, feed, browsing, finding new tracks or artists.
- **`social`** - likes, reposts, follows, comments, sharing, profile-to-profile interaction.
- **`monetization`** - ads, subscriptions, pricing, paywalls, billing, premium features.
- **`account`** - sign-in, sign-up, profile, password reset, auth flows in general.
- **`other`** - anything that does not fit the above. Use this freely; do not force a fit.

If a review names problems on multiple surfaces, emit one issue per surface.

## After labeling

Save the file as `evals/gold.jsonl` (one JSON object per line, same review_ids as `evals/to_label.jsonl`). Then `evals/score.py` will join your gold labels to the model's extractions for those same review_ids and report agreement.
