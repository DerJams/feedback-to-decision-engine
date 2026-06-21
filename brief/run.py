"""Render the markdown opportunity brief from scored themes.

Run from the repo root:
    python -m brief.run

Reads:
- data/scored_themes.jsonl   (ranked themes + per-component score breakdown)
- data/clusters.jsonl        (cluster members -> review_ids)
- data/extracted_issues.jsonl (review text + rating, keyed by review_id)
- data/soundcloud_reviews.jsonl, data/soundcloud_reviews_en.jsonl
  (for the dataset stats block; sourced live, not hardcoded)

Writes brief/opportunity_brief.md.

Quotes are pulled verbatim from review text and cited by review_id. Every
quote traces to a real review - no invented quotes. The brief opens with the
divergence between prevalence (the most-mentioned complaint) and priority
(what the weighted scoring elevates); that gap is the product insight.

LOCAL ONLY. No API calls.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import yaml

from extract.extractor import REPO_ROOT
from extract.sample import read_jsonl

for _stream in (sys.stdout, sys.stderr):
    _reconfigure = getattr(_stream, "reconfigure", None)
    if _reconfigure is not None:
        try:
            _reconfigure(encoding="utf-8", errors="backslashreplace")
        except (OSError, ValueError):
            pass


RUN_CONFIG_PATH = REPO_ROOT / "config" / "run.yaml"
WEIGHTS_CONFIG_PATH = REPO_ROOT / "config" / "weights.yaml"

# Reviews shorter than this are usually low-signal ("ads", "ok", "trash") and
# longer than this don't read in a brief block. Quotes longer than DISPLAY_TRIM
# get an ellipsis tail so we can include a slightly longer source while keeping
# the rendered block scannable.
QUOTE_MIN_LEN = 30
QUOTE_MAX_LEN = 320
DISPLAY_TRIM = 240
QUOTES_PER_THEME = 3

# Display-only floor on centroid_sim for quotes. Members below this still
# contribute to the cluster's score (their issue is real signal), but their
# host review is less likely to read on-theme in a brief block. Tuned to drop
# residual off-direction quotes in mixed clusters (themes 13 / 18) without
# losing the medoid of any ranked theme - the lowest ranked medoid sim is
# 0.833, so the floor stays comfortably below it. Below-floor themes show
# whatever survives (1, or even 0) rather than backfilling with weaker
# candidates; this is documented as a known limitation in the brief itself.
QUOTE_SIM_FLOOR = 0.82


# One-line PM-style recommendations, keyed by the cluster's medoid label.
# Labels are more semantically stable than cluster_ids across reruns. Missing
# entries render as "(recommendation pending)" so a regenerated brief surfaces
# the gap rather than silently dropping a theme.
RECOMMENDATIONS: dict[str, str] = {
    "playback pauses during songs":
        "Instrument session-level playback events (buffer stalls, decoder errors, "
        "route changes) and correlate with device, OS, and network to isolate the top "
        "contributor before shipping a fix.",
    "songs unavailable in user's country":
        "Replace the silent dead-end with clear regional-availability messaging at the "
        "moment of attempted play, plus an inline \"similar available now\" "
        "recommendation row to redirect the session.",
    "excessive ads":
        "Run a controlled experiment on slightly reduced ad load for long-tenured free "
        "users (e.g. >90 days retained), measuring net revenue including any uplift in "
        "premium conversion. Do not change ad load without that test.",
    "offline playback unavailable":
        "Audit failed-download attempts to separate rights-flagged tracks from "
        "cache/storage failures; ship the dominant pattern's fix and surface the "
        "rights case as a clear in-app message.",
    "playlist not playing":
        "Likely shares root cause with playback pauses; bundle both into a single "
        "playback-reliability workstream and instrument the two surfaces together.",
    "app crashes":
        "Pull Crashlytics top stack signatures by OS / device combo and fix the three "
        "with the highest crashes-per-DAU. Standard work, but unblocks every other "
        "theme above it.",
    "liked songs disappearing from playlist":
        "Separate rights-removal (track left the catalog) from data-loss (sync bug). "
        "Harden the sync flow if data-loss; add a visible \"no longer available\" "
        "marker if rights, so users aren't blindsided.",
    "sign in or login fails":
        "Segment auth-funnel telemetry by provider (Google / Apple / email) and OS "
        "version. The cluster size suggests one provider regressed recently.",
    "missing download feature":
        "Split complaints by tier. Free users asking for downloads = paywall-"
        "expectation issue (better premium-badging); premium users asking = feature "
        "exists but isn't discoverable enough.",
    "songs behind premium paywall":
        "Move the premium-only indicator upstream from play attempt to search and "
        "browse, so users self-select before hitting a wall - the surprise is the "
        "source of the complaint, not the paywall itself.",
    "subscription cancellation not working":
        "Audit the cancel flow end-to-end for steps that aren't legally required "
        "(retention prompts, multi-confirmation). Compliance and brand-trust risk "
        "make this worth a fast fix.",
    "sound quality is poor":
        "Correlate complaints with upload bitrate, network conditions, and device "
        "audio output. High strategic fit but ambiguous root cause - diagnose before "
        "prescribing.",
    "same songs repeat frequently":
        "Check recommendation-diversity metrics on the personalized queue, especially "
        "for free users; the model may be overfitting on a narrow signal (recent "
        "likes? short history?).",
    "app performance degradation over time":
        "Profile memory and cache behavior over long-running sessions and across cold "
        "starts. Classic leak / cache-bloat shape worth ruling out first.",
    "account creation fails":
        "Audit signup conversion by referrer, provider, and OS version. New-user "
        "failure is disproportionately costly to growth, so worth a dedicated review.",
    "low quality songs in catalog":
        "Catalog quality is largely outside the app team's lane (rights, labels, "
        "creators). Flag to content/partnerships rather than treating as a product "
        "defect.",
    "customer support unresponsive to concerns":
        "Sample these reviews into the support team's QA queue; the action is "
        "operational (response SLA, routing), not a product change.",
    "missing original artist information":
        "Audit metadata coverage on the most-played long-tail tracks; if the gap is "
        "user-uploaded content, add an artist-tag prompt at upload to push correction "
        "upstream.",
    "price increase":
        "Watch retention by cohort post-increase. Price is a strategy call, not a "
        "product fix; the brief's job is to surface that the complaint exists and is "
        "growing.",
    "lack of support for paid features":
        "Triage premium-tier support tickets separately; paying users hitting friction "
        "is a higher-cost churn signal than free-tier complaints. Tighten the SLA on "
        "this segment.",
    "absence of ads":
        "Positive-signal cluster (subscriber praise). Not an action item - useful as "
        "marketing/retention proof that the premium tier delivers on its core promise.",
}


@dataclass(frozen=True)
class BriefConfig:
    scored_path: Path
    clusters_path: Path
    issues_path: Path
    raw_reviews_path: Path
    en_reviews_path: Path
    brief_output: Path
    prd_output: Path
    llm_model: str
    cluster_threshold: float
    cluster_min_size: int
    ranking_min_size: int
    weights: dict[str, float]


def load_brief_config(
    run_path: Path = RUN_CONFIG_PATH,
    weights_path: Path = WEIGHTS_CONFIG_PATH,
) -> BriefConfig:
    raw = yaml.safe_load(run_path.read_text(encoding="utf-8"))
    w_raw = yaml.safe_load(weights_path.read_text(encoding="utf-8"))
    return BriefConfig(
        scored_path=REPO_ROOT / raw["score"]["output_path"],
        clusters_path=REPO_ROOT / raw["cluster"]["output_path"],
        issues_path=REPO_ROOT / raw["extract"]["output_path"],
        raw_reviews_path=REPO_ROOT / raw["ingest"]["output_path"],
        en_reviews_path=REPO_ROOT / raw["language_filter"]["output_path"],
        brief_output=REPO_ROOT / raw["brief"]["output_path"],
        prd_output=REPO_ROOT / raw["brief"]["prd_output_path"],
        llm_model=raw["extract"]["model"],
        cluster_threshold=float(raw["cluster"]["similarity_threshold"]),
        cluster_min_size=int(raw["cluster"]["min_cluster_size"]),
        ranking_min_size=int(raw["score"]["ranking_min_size"]),
        weights={k: float(v) for k, v in w_raw["weights"].items()},
    )


def count_lines(path: Path) -> int:
    with path.open("r", encoding="utf-8") as fh:
        return sum(1 for line in fh if line.strip())


def count_issues(issue_rows: list[dict]) -> int:
    return sum(len(r["extraction"]["issues"]) for r in issue_rows)


def index_clusters(clusters: list[dict]) -> dict[str, dict]:
    return {c["cluster_id"]: c for c in clusters}


def index_reviews(issue_rows: list[dict]) -> dict[str, dict]:
    return {row["review"]["review_id"]: row["review"] for row in issue_rows}


def select_quotes(
    members: list[dict],
    reviews_by_id: dict[str, dict],
    sentiment: str,
) -> list[dict]:
    """Pick up to QUOTES_PER_THEME quotes ranked by representativeness.

    Primary sort: centroid_sim DESC. A high centroid_sim means the member's
    extracted issue sits at the cluster's semantic center, so its host
    review is the most likely to read on-theme. This replaces the previous
    severity-first ordering, which pulled in reviews where the cluster's
    issue was tangential to the reviewer's main complaint.

    Tiebreakers: shorter review text first (the most focused quote at the
    same centroid_sim wins), then lower star rating as a late tiebreaker.

    Severity filter: negative-sentiment clusters keep only high/medium
    members; positive-sentiment clusters allow low too, because positive
    extractions naturally land at severity=low and would otherwise be
    filtered to zero quotes.
    """
    if sentiment == "positive":
        allowed_severities = {"high", "medium", "low"}
    else:
        allowed_severities = {"high", "medium"}

    candidates: list[dict] = []
    seen_ids: set[str] = set()
    for m in members:
        rid = m["review_id"]
        if rid in seen_ids:
            continue
        seen_ids.add(rid)
        review = reviews_by_id.get(rid)
        if review is None:
            continue
        text = (review.get("text") or "").strip()
        if len(text) < QUOTE_MIN_LEN or len(text) > QUOTE_MAX_LEN:
            continue
        if m.get("severity") not in allowed_severities:
            continue
        candidates.append(
            {
                "review_id": rid,
                "rating": review.get("rating"),
                "text": text,
                "severity": m["severity"],
                "theme": m["theme"],
                "centroid_sim": float(m.get("centroid_sim", 0.0)),
            }
        )

    candidates = [c for c in candidates if c["centroid_sim"] >= QUOTE_SIM_FLOOR]

    candidates.sort(
        key=lambda x: (
            -x["centroid_sim"],
            len(x["text"]),
            x["rating"] if x["rating"] is not None else 99,
        )
    )

    return candidates[:QUOTES_PER_THEME]


def format_quote_text(text: str) -> str:
    """Collapse newlines + trim for display. Source is preserved in the JSONL.

    The brief is a markdown blockquote, so internal newlines would split the
    block. The trim threshold is short enough that 2-3 quotes per theme stay
    readable at a glance.
    """
    flat = " ".join(text.split())
    if len(flat) > DISPLAY_TRIM:
        flat = flat[: DISPLAY_TRIM - 1].rstrip() + "..."
    return flat


def format_score_breakdown(theme: dict) -> str:
    b = theme["breakdown"]
    return (
        f"freq +{b['frequency']['contribution']:.3f} | "
        f"severity +{b['severity']['contribution']:.3f} | "
        f"fit +{b['strategic_fit']['contribution']:.3f}"
    )


def feature_area_summary(theme: dict) -> str:
    """Top 2 feature areas as 'core_listening x72, other x3'."""
    fa = theme["feature_area_breakdown"]
    parts = sorted(fa.items(), key=lambda kv: kv[1], reverse=True)[:2]
    return ", ".join(f"{area} x{n}" for area, n in parts)


def render_brief(
    themes: list[dict],
    clusters_by_id: dict[str, dict],
    reviews_by_id: dict[str, dict],
    config: BriefConfig,
    dataset_stats: dict,
) -> str:
    today = date.today().isoformat()
    n_themes = len(themes)
    top = themes[0]
    largest = max(themes, key=lambda t: t["size"])

    w = config.weights

    lines: list[str] = []
    lines.append("# Opportunity Brief - SoundCloud Android")
    lines.append("")
    lines.append(
        f"_Generated {today} from {dataset_stats['raw_reviews']:,} app store reviews "
        f"({dataset_stats['en_reviews']:,} English after filter, "
        f"{dataset_stats['issues']:,} issues extracted, "
        f"{dataset_stats['clusters']:,} clusters, "
        f"{n_themes} ranked themes above size {config.ranking_min_size})._"
    )
    lines.append("")

    lines.append("## Headline")
    lines.append("")
    lines.append("Two findings, and they do not agree:")
    lines.append("")
    lines.append(
        f"- **Prevalence:** `{largest['label']}` is the single most-mentioned "
        f"complaint by a wide margin - **{largest['size']} reviews** raise it, "
        f"the next-largest theme is roughly 70% as common."
    )
    lines.append(
        f"- **Priority:** when reach is combined with severity and strategic fit, "
        f"`{top['label']}` ranks **#1**, and `{largest['label']}` drops to "
        f"**#{themes.index(largest) + 1}**."
    )
    lines.append("")
    lines.append(
        "Why the divergence is the headline insight: reviewers complain about ads "
        "more often than anything else, but they describe ads as repeated friction "
        "(\"medium\" severity), not as something that breaks the product. Playback "
        "pauses and country-availability gaps appear less often but reviewers describe "
        "them at higher severity and they hit core_listening - the part of SoundCloud "
        "that actually has to work. Acting on ad load is also a lower-confidence "
        "opportunity (see the strategic_fit rationale in `config/weights.yaml`): "
        "reducing ads is a direct revenue lever, not a defect fix, and the retention "
        "gains it might produce are hard to attribute. So the brief reads the way a "
        "priorities argument actually goes in a room: yes, ads are the loudest "
        "complaint; no, ads are not the highest-leverage thing to do this quarter."
    )
    lines.append("")

    lines.append("## Method & limitations")
    lines.append("")
    lines.append(
        f"Extraction uses Anthropic `{config.llm_model}` against a neutral schema "
        f"(no specific complaints named in the prompt, so themes surface from "
        f"reviewer language). Clustering is local: sentence-transformers embeddings, "
        f"sentiment-partitioned agglomerative at cosine threshold "
        f"{config.cluster_threshold}, medoid labels. Scoring weights are auditable - "
        f"frequency {w['frequency']}, severity {w['severity']}, "
        f"strategic_fit {w['strategic_fit']}; per-feature-area fit values and the "
        f"severity scale live in `config/weights.yaml`. Frequency is "
        f"log-scaled so the heavy-tailed size distribution does not collapse "
        f"mid-tier themes to near-zero. Volume floor: clusters with fewer than "
        f"{config.ranking_min_size} issues are excluded from this ranked output."
    )
    lines.append("")
    lines.append(
        "**Limitations.** A single similarity threshold cannot fit every concept's "
        "natural granularity. A few low-rank clusters - notably theme 13 "
        "(_same songs repeat frequently_) and theme 18 (_missing original artist "
        "information_) - blend two related but directionally different concerns "
        "(\"songs auto-repeating\" vs. \"can't manually repeat\"; missing metadata "
        "vs. obscure-artist catalog complaints). A centroid_sim display floor "
        f"({QUOTE_SIM_FLOOR:.2f}) drops the worst off-theme quotes from the render, "
        "but cannot rewrite the cluster boundary itself - so a residual quote that "
        "leans the other direction may still surface in those two blocks."
    )
    lines.append("")

    lines.append("## Ranked opportunities")
    lines.append("")

    for rank, theme in enumerate(themes, start=1):
        cluster = clusters_by_id.get(theme["cluster_id"])
        if cluster is None:
            members: list[dict] = []
        else:
            members = cluster.get("members", [])
        quotes = select_quotes(members, reviews_by_id, theme["sentiment"])
        rec = RECOMMENDATIONS.get(theme["label"], "_(recommendation pending)_")

        lines.append(
            f"### {rank}. {theme['label']} - score {theme['score']:.3f}"
        )
        lines.append("")
        lines.append(
            f"**Reach:** {theme['size']} reviews &nbsp;|&nbsp; "
            f"**Mean severity:** "
            f"{theme['breakdown']['severity']['raw_mean']:.2f} / 3.00 &nbsp;|&nbsp; "
            f"**Sentiment:** {theme['sentiment']} &nbsp;|&nbsp; "
            f"**Feature areas:** {feature_area_summary(theme)}"
        )
        lines.append("")
        lines.append(f"**Score breakdown:** {format_score_breakdown(theme)}")
        lines.append("")

        if quotes:
            for q in quotes:
                rating = q["rating"]
                star = f" ({rating}★)" if isinstance(rating, int) else ""
                lines.append(
                    f"> \"{format_quote_text(q['text'])}\" "
                    f"- review `{q['review_id']}`{star}"
                )
                lines.append(">")
            # Drop the trailing empty blockquote line
            if lines[-1] == ">":
                lines.pop()
        else:
            lines.append(
                "_No quote met the length / severity filter and the "
                f"centroid_sim floor ({QUOTE_SIM_FLOOR:.2f}). The cluster is "
                "real signal but does not contain a sharp, on-theme review to quote._"
            )
        lines.append("")
        lines.append(f"**What I'd do:** {rec}")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(
        "_Generated by the local pipeline. All quotes verbatim from "
        "`data/extracted_issues.jsonl`; the review_id values trace back to the "
        "original Google Play scrape in `data/soundcloud_reviews.jsonl`._"
    )
    lines.append("")

    return "\n".join(lines)


def main() -> int:
    config = load_brief_config()

    themes = read_jsonl(config.scored_path)
    clusters = read_jsonl(config.clusters_path)
    issue_rows = read_jsonl(config.issues_path)

    clusters_by_id = index_clusters(clusters)
    reviews_by_id = index_reviews(issue_rows)

    dataset_stats = {
        "raw_reviews": count_lines(config.raw_reviews_path),
        "en_reviews": count_lines(config.en_reviews_path),
        "issues": count_issues(issue_rows),
        "clusters": len(clusters),
    }

    markdown = render_brief(
        themes,
        clusters_by_id=clusters_by_id,
        reviews_by_id=reviews_by_id,
        config=config,
        dataset_stats=dataset_stats,
    )

    config.brief_output.parent.mkdir(parents=True, exist_ok=True)
    config.brief_output.write_text(markdown, encoding="utf-8")

    print(f"Wrote {len(themes)} ranked themes")
    print(f"  -> {config.brief_output.relative_to(REPO_ROOT)}")
    print()
    print(f"Dataset: {dataset_stats['raw_reviews']:,} raw -> "
          f"{dataset_stats['en_reviews']:,} en -> "
          f"{dataset_stats['issues']:,} issues -> "
          f"{dataset_stats['clusters']:,} clusters -> {len(themes)} ranked")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
