"""Draft PRD for the top-ranked theme in the opportunity brief.

Run from the repo root:
    python -m brief.prd

Reads the same artifacts the opportunity brief uses (scored_themes.jsonl,
clusters.jsonl, extracted_issues.jsonl), picks themes[0] - the top-ranked
cluster - and renders a Lenny-style one-page PRD to
`config.brief.prd_output_path`. Quote selection reuses brief.run.select_quotes
so the same centroid_sim floor (0.82) applies; quotes are verbatim and cited
by review_id.

Discipline of the rendering:
- Factual lines trace to the data (reach, severity, feature areas, quotes).
- Judgment lines (success-metric targets, solution direction, the
  draft-overlap non-goals) are visibly marked DRAFT.
- No invented numeric targets. No invented quotes. No solution claimed.

LOCAL ONLY. No API calls.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

from brief.run import (
    QUOTE_SIM_FLOOR,
    format_quote_text,
    index_clusters,
    index_reviews,
    load_brief_config,
    select_quotes,
)
from extract.extractor import REPO_ROOT
from extract.sample import read_jsonl

for _stream in (sys.stdout, sys.stderr):
    _reconfigure = getattr(_stream, "reconfigure", None)
    if _reconfigure is not None:
        try:
            _reconfigure(encoding="utf-8", errors="backslashreplace")
        except (OSError, ValueError):
            pass


def rank_of(theme: dict, themes: list[dict]) -> int:
    """1-based rank of theme in the scored list."""
    for i, t in enumerate(themes, 1):
        if t["cluster_id"] == theme["cluster_id"]:
            return i
    raise ValueError(f"theme {theme['cluster_id']} not found in scored list")


def feature_area_summary(theme: dict) -> str:
    """All feature areas with counts, e.g. 'core_listening x72'."""
    items = sorted(
        theme["feature_area_breakdown"].items(),
        key=lambda kv: kv[1],
        reverse=True,
    )
    return ", ".join(f"{area} x{n}" for area, n in items)


def severity_dist_summary(theme: dict) -> str:
    items = sorted(
        theme["severity_breakdown"].items(),
        key=lambda kv: kv[1],
        reverse=True,
    )
    return ", ".join(f"{k}={v}" for k, v in items)


def find_theme_by_label(themes: list[dict], label: str) -> dict | None:
    for t in themes:
        if t["label"] == label:
            return t
    return None


def render_prd(
    theme: dict,
    cluster: dict,
    reviews_by_id: dict[str, dict],
    themes: list[dict],
) -> str:
    rank = rank_of(theme, themes)
    n_themes = len(themes)
    largest = max(themes, key=lambda t: t["size"])
    largest_rank = rank_of(largest, themes)
    b = theme["breakdown"]
    today = date.today().isoformat()

    quotes = select_quotes(cluster["members"], reviews_by_id, theme["sentiment"])

    # Cross-references for the non-goals section. Looked up by label so a
    # rerun with shifted IDs still cites the right rank. Missing themes
    # render as a clearly-marked fallback rather than crashing.
    def cite(label: str) -> str:
        t = find_theme_by_label(themes, label)
        if t is None:
            return f"`{label}` _(not in this brief's ranked set)_"
        return f"`{label}` (theme #{rank_of(t, themes)})"

    lines: list[str] = []
    lines.append(f"# PRD (draft): {theme['label']}")
    lines.append("")
    lines.append(
        f"_Draft, {today}. Source theme: cluster `{theme['cluster_id']}`, "
        f"ranked **#{rank} of {n_themes}** in the current opportunity brief._"
    )
    lines.append("")

    # 1. Problem statement
    lines.append("## 1. Problem statement")
    lines.append("")
    lines.append(
        "On SoundCloud Android, playback is frequently interrupted mid-song "
        "without user input - unprompted pauses, stalls, drops, and unexpected "
        "skips. Reviewers describe sessions broken by these interruptions in "
        "the part of the product where reliability is non-negotiable - actually "
        "listening to music."
    )
    lines.append("")

    # 2. Evidence
    lines.append("## 2. Evidence")
    lines.append("")
    lines.append(
        f"- **Reach:** {theme['size']} reviews carry this theme "
        f"(cluster `{theme['cluster_id']}`, sentiment {theme['sentiment']})."
    )
    lines.append(
        f"- **Mean severity:** {b['severity']['raw_mean']:.2f} / 3.00 "
        f"(distribution: {severity_dist_summary(theme)})."
    )
    lines.append(
        f"- **Feature areas:** {feature_area_summary(theme)} - this cluster is "
        "concentrated in core_listening, not spread across surfaces."
    )
    lines.append("")
    lines.append(
        f"**Representative verbatim quotes** "
        f"(centroid_sim &ge; {QUOTE_SIM_FLOOR:.2f}, cited by review_id):"
    )
    lines.append("")
    if quotes:
        for q in quotes:
            rating = q["rating"]
            star = f" ({rating}★)" if isinstance(rating, int) else ""
            lines.append(
                f"> \"{format_quote_text(q['text'])}\" "
                f"- review `{q['review_id']}`{star} "
                f"_(sim {q['centroid_sim']:.2f})_"
            )
            lines.append(">")
        if lines[-1] == ">":
            lines.pop()
    else:
        lines.append(
            f"_No member cleared the centroid_sim floor ({QUOTE_SIM_FLOOR:.2f})._"
        )
    lines.append("")

    # 3. Why now
    lines.append("## 3. Why now")
    lines.append("")
    lines.append(
        f"- **Top weighted score.** Ranks **#{rank} of {n_themes}** at score "
        f"{theme['score']:.3f} "
        f"(freq +{b['frequency']['contribution']:.3f} | "
        f"severity +{b['severity']['contribution']:.3f} | "
        f"fit +{b['strategic_fit']['contribution']:.3f}). "
        f"See `config/weights.yaml` for the weight rationale."
    )
    lines.append(
        "- **Sits entirely in core_listening**, the feature area with the "
        "highest strategic_fit weight (1.0) - the explicit reasoning in "
        "`config/weights.yaml` is that playback IS the product."
    )
    lines.append(
        f"- **Prevalence-vs-priority.** `{largest['label']}` is the most-mentioned "
        f"theme overall ({largest['size']} reviews vs. {theme['size']} here) but "
        f"ranks **#{largest_rank}** because reviewers describe it as repeated "
        f"friction (mean severity "
        f"{largest['breakdown']['severity']['raw_mean']:.2f}) rather than as "
        "something that breaks the product, and its strategic_fit is lower "
        "(monetization weight 0.5). Playback reliability is the higher-leverage "
        "place to spend this quarter's cycles."
    )
    lines.append("")

    # 4. Goals & success metrics
    lines.append(
        "## 4. Goals &amp; success metrics _(DRAFT - all targets TBD with data/eng)_"
    )
    lines.append("")
    lines.append(
        "Candidate metrics to instrument and baseline. No numeric targets are "
        "asserted here; each must be set after a baseline read with data and eng."
    )
    lines.append("")
    lines.append(
        "- **Playback completion rate.** Share of playback sessions that finish "
        "the intended track without an unprompted pause/stall event. "
        "_Target: TBD (set with data/eng after baseline)._"
    )
    lines.append(
        "- **Mean uninterrupted-play minutes per session.** Time between "
        "playback start and first unprompted pause/stall. "
        "_Target: TBD (set with data/eng after baseline)._"
    )
    lines.append(
        "- **Pause-language review mention rate.** Weekly share of new reviews "
        "matching playback-pause language (pause / stall / stop / interrupt) - "
        "the metric this brief actually surfaces. "
        "_Target: TBD (set with data/eng after baseline)._"
    )
    lines.append(
        f"- **Cluster reach in the next quarterly refresh.** Size of cluster "
        f"`{theme['cluster_id']}` on a re-pulled review set (currently "
        f"{theme['size']} reviews). "
        f"_Target: TBD (set with data/eng after baseline)._"
    )
    lines.append("")

    # 5. Non-goals
    lines.append("## 5. Non-goals")
    lines.append("")
    lines.append("**Explicit out of scope** (own clusters; addressed separately):")
    lines.append("")
    ads_cite = cite("excessive ads")
    country_cite = cite("songs unavailable in user's country")
    login_cite = cite("sign in or login fails")
    catalog_cite = cite("low quality songs in catalog")
    artist_cite = cite("missing original artist information")
    lines.append(f"- {ads_cite} - distinct cluster, distinct driver.")
    lines.append(
        f"- {country_cite} - rights / geo gating, "
        "not playback-engine reliability."
    )
    lines.append(f"- {login_cite} - auth flow, separate workstream.")
    lines.append(
        f"- {catalog_cite} and {artist_cite} - catalog quality, "
        "outside the app team's lane."
    )
    lines.append("")
    lines.append(
        "**(Draft)** overlap clusters that may share root cause and should be "
        "re-scoped during discovery rather than carved off here:"
    )
    lines.append("")
    lines.append(
        f"- {cite('playlist not playing')} - the brief's recommendation already "
        "calls out a likely shared root cause; eng discovery should confirm "
        "and either bundle or split."
    )
    lines.append(
        f"- {cite('app crashes')} - distinct symptom, but a crash-induced "
        "playback halt may be reported by users as a \"pause\"; need to "
        "disambiguate in instrumentation."
    )
    lines.append("")

    # 6. Solution direction
    lines.append(
        "## 6. Solution direction _(DRAFT - hypotheses to investigate, not chosen)_"
    )
    lines.append("")
    lines.append(
        "No solution committed. The cluster's text suggests four hypotheses worth "
        "ruling in or out before any design work:"
    )
    lines.append("")
    lines.append(
        "- **(Draft, needs eng discovery)** Network / buffer-triggered stalls. "
        "Pauses concentrated under poor connectivity. Reproduce on throttled "
        "networks and instrument buffer-underrun events."
    )
    lines.append(
        "- **(Draft, needs eng discovery)** Background / lifecycle pauses. "
        "Backgrounding, audio-route change (BT or wired headphone connect / "
        "disconnect), or OS interruption mishandled. Reproduce via state "
        "transitions on the top device classes."
    )
    lines.append(
        "- **(Draft, needs eng discovery)** Ad-insertion transition artefacts. "
        "Mid-roll insertion failing to resume playback cleanly; some "
        "\"pause\" reports may be ad-transition bugs - which would also lower "
        "the perceived severity of the `excessive ads` cluster if fixed."
    )
    lines.append(
        "- **(Draft, needs eng discovery)** Decoder / codec edge cases. Specific "
        "track formats failing decode mid-play on particular device families."
    )
    lines.append("")

    # 7. Open questions
    lines.append("## 7. Open questions")
    lines.append("")
    lines.append("Questions the review data does not answer; instrumentation or eng input required:")
    lines.append("")
    lines.append(
        "- Are pauses concentrated on specific OS versions, device classes, or markets?"
    )
    lines.append(
        "- Do they correlate with ad-insertion points (i.e. is this a transition "
        "bug masquerading as a playback bug)?"
    )
    lines.append(
        "- Are they whole-session breaks or sub-second micro-stutters? Reviewer "
        "language conflates the two."
    )
    lines.append(
        f"- What is the relationship to `playlist not playing` (theme "
        f"#{rank_of(find_theme_by_label(themes, 'playlist not playing'), themes) if find_theme_by_label(themes, 'playlist not playing') else '?'})? "
        "Shared root cause or independent symptoms?"
    )
    lines.append(
        "- How does cluster reach trend across review timestamps and app_version "
        "bands? (Both fields are in the raw scrape and not yet analyzed.)"
    )
    lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(
        f"_Draft PRD, generated locally from `data/scored_themes.jsonl`, "
        f"`data/clusters.jsonl`, and `data/extracted_issues.jsonl`. "
        f"All quotes verbatim and cited by review_id; representativeness "
        f"floor `centroid_sim >= {QUOTE_SIM_FLOOR:.2f}` applied. "
        f"See `brief/opportunity_brief.md` for the full ranked set and the "
        f"Method &amp; limitations note._"
    )

    return "\n".join(lines)


def main() -> int:
    config = load_brief_config()
    themes = read_jsonl(config.scored_path)
    if not themes:
        print("No ranked themes found in scored_themes.jsonl - run scoring first.")
        return 1

    top_theme = themes[0]
    clusters_by_id = index_clusters(read_jsonl(config.clusters_path))
    cluster = clusters_by_id.get(top_theme["cluster_id"])
    if cluster is None:
        print(
            f"Top theme {top_theme['cluster_id']} not found in clusters.jsonl - "
            "rerun the cluster stage and try again."
        )
        return 1

    reviews_by_id = index_reviews(read_jsonl(config.issues_path))
    markdown = render_prd(top_theme, cluster, reviews_by_id, themes)

    config.prd_output.parent.mkdir(parents=True, exist_ok=True)
    config.prd_output.write_text(markdown, encoding="utf-8")
    print(
        f"Wrote draft PRD for theme {top_theme['cluster_id']} "
        f"({top_theme['label']!r}) -> {config.prd_output.relative_to(REPO_ROOT)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
