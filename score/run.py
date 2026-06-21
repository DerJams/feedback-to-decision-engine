"""Theme scoring over clustered issues.

Run from the repo root:
    python -m score.run

Reads `data/clusters.jsonl` and `config/weights.yaml`, scores each cluster as
a weighted sum of three normalized components, and writes a ranked JSONL with
a per-cluster BREAKDOWN so the ranking is auditable: the reader can see
exactly how much frequency, severity, and strategic fit each contributed.

Score formula (per config/weights.yaml):
    score = w_freq * frequency_norm
          + w_sev  * severity_norm
          + w_fit  * strategic_fit

where:
- frequency_norm  = log(1 + cluster.size) / log(1 + max_size_among_ranked)  in [0, 1]
- severity_norm   = mean(severity_scale[m.severity] for m in members) / max(severity_scale)  in [~1/3, 1]
- strategic_fit   = sum(count_in_area * strategic_fit[area]) / cluster.size  in [0, 1]

Frequency is log-scaled because cluster sizes are heavy-tailed (the top cluster
is ~3x the next and the floor is ~7-70x smaller). Linear min-max squashes the
mid-tier near zero and lets severity dominate every rank below #1; the log
compresses the head and spreads the body so volume actually differentiates.

The severity numeric scale is read from config/weights.yaml (`severity_scale`)
- NOT hardcoded - so adjusting how harshly "high" is weighted vs "medium" is a
config edit, not a code change.

Volume floor: clusters below `score.ranking_min_size` (config/run.yaml) are
excluded from the ranked output entirely. Clustering still keeps min_cluster_size
at 3 so small clusters are visible in clusters.jsonl for inspection, but a
3-member cluster floating into a "top opportunity" rank would sink the brief's
credibility. Normalization happens AFTER the floor so a single huge cluster
beyond the rest doesn't crush the ranked tier on the way back down.

LOCAL ONLY. No API calls.
"""
from __future__ import annotations

import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

from extract.extractor import REPO_ROOT
from extract.sample import read_jsonl

RUN_CONFIG_PATH = REPO_ROOT / "config" / "run.yaml"
WEIGHTS_CONFIG_PATH = REPO_ROOT / "config" / "weights.yaml"

# Match the UTF-8 stdout hardening the other stages use - medoid labels include
# strings that can carry non-cp1252 characters.
for _stream in (sys.stdout, sys.stderr):
    _reconfigure = getattr(_stream, "reconfigure", None)
    if _reconfigure is not None:
        try:
            _reconfigure(encoding="utf-8", errors="backslashreplace")
        except (OSError, ValueError):
            pass


@dataclass(frozen=True)
class ScoreConfig:
    input_path: Path
    output_path: Path
    ranking_min_size: int
    weights: dict[str, float]
    severity_scale: dict[str, float]
    strategic_fit: dict[str, float]


def load_score_config(
    run_path: Path = RUN_CONFIG_PATH,
    weights_path: Path = WEIGHTS_CONFIG_PATH,
) -> ScoreConfig:
    run_raw = yaml.safe_load(run_path.read_text(encoding="utf-8"))
    w_raw = yaml.safe_load(weights_path.read_text(encoding="utf-8"))
    sc = run_raw["score"]
    return ScoreConfig(
        input_path=REPO_ROOT / sc["input_path"],
        output_path=REPO_ROOT / sc["output_path"],
        ranking_min_size=int(sc["ranking_min_size"]),
        weights={k: float(v) for k, v in w_raw["weights"].items()},
        severity_scale={k: float(v) for k, v in w_raw["severity_scale"].items()},
        strategic_fit={k: float(v) for k, v in w_raw["strategic_fit"].items()},
    )


def mean_severity(cluster: dict, severity_scale: dict[str, float]) -> float:
    """Weighted mean of numeric severity over all member issues."""
    total = 0.0
    count = 0
    for sev_label, n in cluster["severity_breakdown"].items():
        if sev_label not in severity_scale:
            # Unknown enum value means the schema changed or the extractor
            # produced something out-of-spec - fail loudly rather than silently
            # zeroing it.
            raise ValueError(
                f"cluster {cluster['cluster_id']} has unknown severity "
                f"label {sev_label!r}; expected one of {sorted(severity_scale)}"
            )
        total += severity_scale[sev_label] * n
        count += n
    if count == 0:
        return 0.0
    return total / count


def strategic_fit_for_cluster(
    cluster: dict, strategic_fit: dict[str, float]
) -> float:
    """Weighted mean of per-feature-area strategic fit over members.

    A cluster usually spans multiple feature areas (a "playback" cluster will
    have most members in core_listening but some in discovery, etc.), so we
    weight each area's fit value by how many members fell in it.
    """
    total = 0.0
    count = 0
    for area, n in cluster["feature_area_breakdown"].items():
        if area not in strategic_fit:
            raise ValueError(
                f"cluster {cluster['cluster_id']} has unknown feature_area "
                f"{area!r}; expected one of {sorted(strategic_fit)}"
            )
        total += strategic_fit[area] * n
        count += n
    if count == 0:
        return 0.0
    return total / count


def score_clusters(
    clusters: list[dict],
    weights: dict[str, float],
    severity_scale: dict[str, float],
    strategic_fit: dict[str, float],
    ranking_min_size: int = 1,
) -> list[dict]:
    """Return ranked clusters annotated with a score + per-component breakdown.

    All three components are normalized into [0, 1] before weighting so the
    weights in weights.yaml mean what they read like - "frequency is worth 40%
    of the score" actually corresponds to a 0.40 max contribution. Frequency
    uses log normalization (see module docstring) so the heavy-tailed cluster
    size distribution doesn't collapse mid-tier frequencies to ~0.

    Clusters with size < ranking_min_size are dropped before normalization, so
    a single outsized cluster beyond the floor doesn't drag the ranked-tier
    frequency norm back down toward zero.
    """
    eligible = [c for c in clusters if c["size"] >= ranking_min_size]
    if not eligible:
        return []

    max_size = max(c["size"] for c in eligible)
    max_severity = max(severity_scale.values())
    log_denom = math.log(1 + max_size)

    w_freq = weights["frequency"]
    w_sev = weights["severity"]
    w_fit = weights["strategic_fit"]

    scored: list[dict] = []
    for c in eligible:
        freq_raw = math.log(1 + c["size"]) / log_denom if log_denom > 0 else 0.0
        sev_raw = mean_severity(c, severity_scale)
        sev_norm = sev_raw / max_severity if max_severity else 0.0
        fit_raw = strategic_fit_for_cluster(c, strategic_fit)

        freq_contrib = w_freq * freq_raw
        sev_contrib = w_sev * sev_norm
        fit_contrib = w_fit * fit_raw
        total = freq_contrib + sev_contrib + fit_contrib

        scored.append(
            {
                "cluster_id": c["cluster_id"],
                "label": c["label"],
                "sentiment": c["sentiment"],
                "size": c["size"],
                "score": total,
                "breakdown": {
                    "frequency": {
                        "normalized": freq_raw,
                        "weight": w_freq,
                        "contribution": freq_contrib,
                    },
                    "severity": {
                        "raw_mean": sev_raw,
                        "normalized": sev_norm,
                        "weight": w_sev,
                        "contribution": sev_contrib,
                    },
                    "strategic_fit": {
                        "raw": fit_raw,
                        "weight": w_fit,
                        "contribution": fit_contrib,
                    },
                },
                "severity_breakdown": c["severity_breakdown"],
                "feature_area_breakdown": c["feature_area_breakdown"],
            }
        )

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored


def print_top(scored: list[dict], n: int = 15) -> None:
    print(f"\n=== Top {n} themes (audit view) ===")
    print(
        f"{'rank':>4}  {'id':<8}{'size':>5}  "
        f"{'score':>6}   {'freq':>13}   {'sev':>20}   {'fit':>13}   label"
    )
    print(
        f"{'-' * 4}  {'-' * 8}{'-' * 5}  {'-' * 6}   "
        f"{'-' * 13}   {'-' * 20}   {'-' * 13}   {'-' * 30}"
    )
    for i, t in enumerate(scored[:n], start=1):
        b = t["breakdown"]
        freq_cell = f"{b['frequency']['normalized']:.2f}->{b['frequency']['contribution']:+.3f}"
        sev_cell = (
            f"{b['severity']['raw_mean']:.2f}"
            f"({b['severity']['normalized']:.2f})"
            f"->{b['severity']['contribution']:+.3f}"
        )
        fit_cell = f"{b['strategic_fit']['raw']:.2f}->{b['strategic_fit']['contribution']:+.3f}"
        print(
            f"{i:>4}  {t['cluster_id']:<8}{t['size']:>5}  "
            f"{t['score']:>6.3f}   {freq_cell:>13}   {sev_cell:>20}   "
            f"{fit_cell:>13}   {t['label']!r}"
        )
    print(
        "\nLegend: freq = log(1+size)/log(1+max_size) -> weighted contribution; "
        "sev = mean_raw(scale)(normalized_to_max_scale) -> weighted contribution; "
        "fit = weighted_mean_of_per_area_strategic_fit -> weighted contribution."
    )


def main() -> int:
    config = load_score_config()
    clusters = read_jsonl(config.input_path)
    print(f"Loaded {len(clusters)} clusters from {config.input_path.relative_to(REPO_ROOT)}")
    print(f"Ranking floor (score.ranking_min_size): size >= {config.ranking_min_size}")
    print("Weights (config/weights.yaml):")
    for k, v in config.weights.items():
        print(f"  {k:<15} {v}")
    print("Severity scale:", config.severity_scale)
    print("Strategic fit :", config.strategic_fit)

    scored = score_clusters(
        clusters,
        weights=config.weights,
        severity_scale=config.severity_scale,
        strategic_fit=config.strategic_fit,
        ranking_min_size=config.ranking_min_size,
    )

    dropped = len(clusters) - len(scored)
    config.output_path.parent.mkdir(parents=True, exist_ok=True)
    with config.output_path.open("w", encoding="utf-8") as fh:
        for row in scored:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(
        f"\nWrote {len(scored)} ranked themes "
        f"({dropped} excluded by ranking_min_size) "
        f"-> {config.output_path.relative_to(REPO_ROOT)}"
    )

    print_top(scored, n=15)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
