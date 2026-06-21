"""Score the extraction stage against hand-labeled gold.

Run from the repo root:
    python -m evals.score

Reads:
- `evals/to_label.jsonl`           (the 50-review labeling set)
- `evals/gold.jsonl`               (hand labels per `evals/rubric.md`)
- `data/extracted_issues.jsonl`    (the model's full extraction output)

Writes:
- `evals/model_subset.jsonl`       (model extractions for the 50 labeling
                                    review_ids - snapshot so the eval is
                                    self-contained from committed files alone)
- `evals/matches_for_review.jsonl` (per-review proposed model<->gold matches
                                    plus any unmatched issues on either side,
                                    for adjudication BEFORE finalizing numbers)
- `evals/results.md`               (review-level 2x2 + per-issue metrics table,
                                    plus an empty Failure modes section)

The script always (re)builds `model_subset.jsonl` if `to_label.jsonl` exists.
The metrics, matches, and results.md require `gold.jsonl`; the script exits
cleanly with guidance if it is missing. Never fabricates labels.

LOCAL ONLY. No API calls.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from extract.extractor import REPO_ROOT
from extract.sample import read_jsonl

for _stream in (sys.stdout, sys.stderr):
    _reconfigure = getattr(_stream, "reconfigure", None)
    if _reconfigure is not None:
        try:
            _reconfigure(encoding="utf-8", errors="backslashreplace")
        except (OSError, ValueError):
            pass


TO_LABEL_PATH = REPO_ROOT / "evals" / "to_label.jsonl"
GOLD_PATH = REPO_ROOT / "evals" / "gold.jsonl"
ISSUES_PATH = REPO_ROOT / "data" / "extracted_issues.jsonl"
MODEL_SUBSET_PATH = REPO_ROOT / "evals" / "model_subset.jsonl"
MATCHES_PATH = REPO_ROOT / "evals" / "matches_for_review.jsonl"
RESULTS_PATH = REPO_ROOT / "evals" / "results.md"

SEVERITY_INT = {"low": 1, "medium": 2, "high": 3}


def build_model_subset(review_ids: set[str]) -> list[dict]:
    """Filter the full extraction file to the labeling set's review_ids and
    write `evals/model_subset.jsonl`. Done unconditionally so the eval is
    reproducible from committed files alone (no need to re-run extraction).
    """
    all_extractions = read_jsonl(ISSUES_PATH)
    subset = [
        row for row in all_extractions
        if row["review"]["review_id"] in review_ids
    ]
    MODEL_SUBSET_PATH.parent.mkdir(parents=True, exist_ok=True)
    with MODEL_SUBSET_PATH.open("w", encoding="utf-8") as fh:
        for row in subset:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return subset


def pair_score(model_iss: dict, gold_iss: dict) -> float:
    """Higher = better match for the greedy matcher.

    Feature_area match outweighs severity match so two issues in the same area
    bind first; among same-area pairs, exact severity outweighs within-one.
    The cost function is intentionally loose - any positive overlap is a
    candidate, and the matcher is greedy descending so the best alignments
    bind before partial ones.
    """
    s = 0.0
    if model_iss.get("feature_area") == gold_iss.get("feature_area"):
        s += 2.0
    m_sev = model_iss.get("severity")
    g_sev = gold_iss.get("severity")
    if m_sev == g_sev:
        s += 1.0
    elif (
        m_sev in SEVERITY_INT
        and g_sev in SEVERITY_INT
        and abs(SEVERITY_INT[m_sev] - SEVERITY_INT[g_sev]) == 1
    ):
        s += 0.5
    return s


def match_issues(
    model_issues: list[dict], gold_issues: list[dict]
) -> tuple[list[tuple[int, int]], list[int], list[int]]:
    """Greedy bipartite match between model and gold issues for one review.

    Returns matched (model_idx, gold_idx) pairs ordered by descending pair_score,
    plus the indices of any model issues with no gold counterpart (candidate
    over-extraction) and gold issues with no model counterpart (candidate
    model miss). Both unmatched lists feed `matches_for_review.jsonl` so the
    labeler can adjudicate before the metrics are read as final.
    """
    candidates: list[tuple[float, int, int]] = []
    for mi, m in enumerate(model_issues):
        for gi, g in enumerate(gold_issues):
            score = pair_score(m, g)
            if score > 0:
                candidates.append((score, mi, gi))
    candidates.sort(reverse=True)

    used_m: set[int] = set()
    used_g: set[int] = set()
    matches: list[tuple[int, int]] = []
    for _, mi, gi in candidates:
        if mi in used_m or gi in used_g:
            continue
        matches.append((mi, gi))
        used_m.add(mi)
        used_g.add(gi)

    unmatched_m = [i for i in range(len(model_issues)) if i not in used_m]
    unmatched_g = [i for i in range(len(gold_issues)) if i not in used_g]
    return matches, unmatched_m, unmatched_g


@dataclass
class Scoreboard:
    n_reviews: int = 0
    # Confusion matrix keyed by (model_has_issue, gold_has_issue).
    cm: dict[tuple[bool, bool], int] = field(
        default_factory=lambda: {
            (True, True): 0,
            (True, False): 0,
            (False, True): 0,
            (False, False): 0,
        }
    )
    n_model_issues: int = 0
    n_matched: int = 0
    n_feature_area_correct: int = 0  # among matched pairs
    n_severity_exact: int = 0  # among matched pairs
    n_severity_within_one: int = 0  # among matched pairs


def render_results(board: Scoreboard) -> str:
    cm = board.cm
    n = board.n_reviews
    agree = cm[(True, True)] + cm[(False, False)]
    agree_pct = (agree / n * 100) if n else 0.0
    m = board.n_model_issues
    matched = board.n_matched

    def pct_line(num: int, den: int) -> str:
        if den == 0:
            return "n/a"
        return f"{num} / {den} = {num / den * 100:.0f}%"

    precision_line = pct_line(matched, m) if m else "n/a (no model issues)"

    lines: list[str] = []
    lines.append("# Extraction eval results")
    lines.append("")
    lines.append(
        f"_Generated {date.today().isoformat()} against {n} hand-labeled reviews._"
    )
    lines.append("")
    lines.append(f"## Review-level has_issue agreement (n = {n} reviews)")
    lines.append("")
    lines.append("|                 | gold has_issue | gold no_issue |")
    lines.append("|-----------------|---------------:|--------------:|")
    lines.append(
        f"| model has_issue | {cm[(True, True)]} | {cm[(True, False)]} |"
    )
    lines.append(
        f"| model no_issue  | {cm[(False, True)]} | {cm[(False, False)]} |"
    )
    lines.append("")
    lines.append(f"Agreement: {agree} / {n} = {agree_pct:.0f}%.")
    lines.append("")
    lines.append(
        f"## Per-issue agreement (n = {m} model issues across {n} reviews)"
    )
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(
        f"| Precision (model issues matched to a gold issue) | {precision_line} |"
    )
    lines.append(
        f"| Feature_area accuracy (of matched, n = {matched}) | "
        f"{pct_line(board.n_feature_area_correct, matched)} |"
    )
    lines.append(
        f"| Severity exact (of matched, n = {matched}) | "
        f"{pct_line(board.n_severity_exact, matched)} |"
    )
    lines.append(
        f"| Severity within-one (of matched, n = {matched}) | "
        f"{pct_line(board.n_severity_within_one, matched)} |"
    )
    lines.append("")
    lines.append(
        "_Matching is greedy by descending pair_score (feature_area match "
        "outweighs severity, exact severity outweighs within-one); see "
        "`evals/score.py:pair_score`. Adjudicate the proposed matches in "
        "`evals/matches_for_review.jsonl` before treating these numbers as "
        "final. Any correction there should be applied to `evals/gold.jsonl` "
        "and the script rerun._"
    )
    lines.append("")
    lines.append("## Failure modes")
    lines.append("")
    lines.append(
        "_To fill in from `evals/matches_for_review.jsonl` after adjudication. "
        "Categorize what the mismatches show: model over-extraction "
        "(unmatched_model_issues that are not real); model misses "
        "(unmatched_gold_issues that the model should have caught); "
        "feature_area confusions (and which directions they go); severity "
        "drift (does the model tend higher or lower than the rubric); "
        "anything systemic enough to change a prompt or schema decision._"
    )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    if not TO_LABEL_PATH.exists():
        print(
            f"{TO_LABEL_PATH.relative_to(REPO_ROOT)} not found. "
            "Run `python -m evals.sample` first to draw the labeling set."
        )
        return 1

    label_rows = read_jsonl(TO_LABEL_PATH)
    review_ids = {r["review_id"] for r in label_rows}
    text_by_id = {r["review_id"]: r["text"] for r in label_rows}

    model_subset = build_model_subset(review_ids)
    print(
        f"Snapshotted {len(model_subset)} / {len(review_ids)} model extractions "
        f"-> {MODEL_SUBSET_PATH.relative_to(REPO_ROOT)}"
    )
    if len(model_subset) != len(review_ids):
        missing = review_ids - {r["review"]["review_id"] for r in model_subset}
        print(
            f"WARNING: {len(missing)} labeling-set review_ids missing from "
            f"the model extraction file: {sorted(missing)[:5]}..."
        )

    if not GOLD_PATH.exists():
        print()
        print(
            f"{GOLD_PATH.relative_to(REPO_ROOT)} not found. Hand-label "
            f"{TO_LABEL_PATH.relative_to(REPO_ROOT)} per `evals/rubric.md` "
            "and save as `evals/gold.jsonl`, then rerun `python -m evals.score`."
        )
        return 1

    gold_rows = read_jsonl(GOLD_PATH)
    gold_by_id = {row["review_id"]: row for row in gold_rows}
    model_by_id = {row["review"]["review_id"]: row for row in model_subset}

    common_ids = set(gold_by_id) & set(model_by_id)
    only_in_gold = set(gold_by_id) - set(model_by_id)
    only_in_model_only = set(model_by_id) - set(gold_by_id)
    if only_in_gold or only_in_model_only:
        print()
        print("WARNING: review_id mismatches between gold and model snapshot:")
        if only_in_gold:
            print(
                f"  in gold but not in model snapshot "
                f"({len(only_in_gold)}): {sorted(only_in_gold)[:5]}..."
            )
        if only_in_model_only:
            print(
                f"  in model snapshot but not in gold "
                f"({len(only_in_model_only)}): {sorted(only_in_model_only)[:5]}..."
            )
        print("Scoring on the intersection only.")

    board = Scoreboard(n_reviews=len(common_ids))
    match_records: list[dict] = []

    for rid in sorted(common_ids):
        gold = gold_by_id[rid]
        model_row = model_by_id[rid]
        model_issues: list[dict] = list(model_row["extraction"]["issues"])
        gold_issues: list[dict] = list(gold.get("issues", []))

        gold_has = bool(gold.get("has_issue", bool(gold_issues)))
        model_has = bool(model_issues)
        board.cm[(model_has, gold_has)] += 1

        matches, unmatched_m, unmatched_g = match_issues(model_issues, gold_issues)
        board.n_model_issues += len(model_issues)
        board.n_matched += len(matches)

        for mi, gi in matches:
            mfa = model_issues[mi].get("feature_area")
            gfa = gold_issues[gi].get("feature_area")
            if mfa == gfa:
                board.n_feature_area_correct += 1
            msev = model_issues[mi].get("severity")
            gsev = gold_issues[gi].get("severity")
            if msev == gsev:
                board.n_severity_exact += 1
                board.n_severity_within_one += 1
            elif (
                msev in SEVERITY_INT
                and gsev in SEVERITY_INT
                and abs(SEVERITY_INT[msev] - SEVERITY_INT[gsev]) <= 1
            ):
                board.n_severity_within_one += 1

        match_records.append(
            {
                "review_id": rid,
                "review_text": text_by_id.get(rid, ""),
                "gold_has_issue": gold_has,
                "model_has_issue": model_has,
                "matches": [
                    {
                        "model": {
                            "theme": model_issues[mi].get("theme"),
                            "feature_area": model_issues[mi].get("feature_area"),
                            "severity": model_issues[mi].get("severity"),
                        },
                        "gold": {
                            "desc": gold_issues[gi].get("desc"),
                            "feature_area": gold_issues[gi].get("feature_area"),
                            "severity": gold_issues[gi].get("severity"),
                        },
                        "feature_area_match": (
                            model_issues[mi].get("feature_area")
                            == gold_issues[gi].get("feature_area")
                        ),
                        "severity_match": (
                            model_issues[mi].get("severity")
                            == gold_issues[gi].get("severity")
                        ),
                    }
                    for mi, gi in matches
                ],
                "unmatched_model_issues": [
                    {
                        "theme": model_issues[i].get("theme"),
                        "feature_area": model_issues[i].get("feature_area"),
                        "severity": model_issues[i].get("severity"),
                    }
                    for i in unmatched_m
                ],
                "unmatched_gold_issues": [
                    {
                        "desc": gold_issues[i].get("desc"),
                        "feature_area": gold_issues[i].get("feature_area"),
                        "severity": gold_issues[i].get("severity"),
                    }
                    for i in unmatched_g
                ],
            }
        )

    MATCHES_PATH.parent.mkdir(parents=True, exist_ok=True)
    with MATCHES_PATH.open("w", encoding="utf-8") as fh:
        for rec in match_records:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(
        f"Wrote {len(match_records)} per-review match records "
        f"-> {MATCHES_PATH.relative_to(REPO_ROOT)}"
    )

    RESULTS_PATH.write_text(render_results(board), encoding="utf-8")
    print(f"Wrote {RESULTS_PATH.relative_to(REPO_ROOT)}")
    print()
    print(
        "Adjudicate matches_for_review.jsonl before treating the results "
        "numbers as final."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
