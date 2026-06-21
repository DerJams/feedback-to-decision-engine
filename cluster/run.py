"""Local-embedding clustering over extracted issues.

Run from the repo root:
    python -m cluster.run

Reads the per-review issues written by `extract.run`, embeds each issue's
theme string with a small local sentence-transformers model, partitions by
sentiment so positive and negative concerns can't merge, and runs
agglomerative clustering with cosine distance within each partition. The
distance is cut at `1 - similarity_threshold` (config), and clusters smaller
than `min_cluster_size` (config) are dropped from the main output to noise.

Every cluster keeps the full per-issue records of its members (review_id,
severity, sentiment, feature_area, segment_hint, original theme) so the
scoring stage can read all the source fields back without rejoining against
extracted_issues.jsonl. Each cluster is labeled with its medoid theme - the
member theme string whose embedding is closest to the cluster centroid - so
labels reflect the cluster's semantic center rather than rewarding cosmetic
phrasing collisions. No LLM call.

LOCAL ONLY. No API calls. The embedding model is downloaded from HuggingFace
on first use and cached under ~/.cache/huggingface; subsequent runs are
fully offline.
"""
from __future__ import annotations

import json
import sys
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import yaml
from sklearn.cluster import AgglomerativeClustering

from extract.extractor import REPO_ROOT
from extract.sample import read_jsonl

RUN_CONFIG_PATH = REPO_ROOT / "config" / "run.yaml"

# Same UTF-8 stdout hardening as extract/run.py - the labels we print include
# theme strings the model produced, which can contain emoji or other
# non-cp1252 characters on Windows.
for _stream in (sys.stdout, sys.stderr):
    _reconfigure = getattr(_stream, "reconfigure", None)
    if _reconfigure is not None:
        try:
            _reconfigure(encoding="utf-8", errors="backslashreplace")
        except (OSError, ValueError):
            pass


@dataclass(frozen=True)
class ClusterConfig:
    embedding_model: str
    similarity_threshold: float
    min_cluster_size: int
    input_path: Path
    output_path: Path


def load_cluster_config(path: Path = RUN_CONFIG_PATH) -> ClusterConfig:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    cl = raw["cluster"]
    return ClusterConfig(
        embedding_model=cl["embedding_model"],
        similarity_threshold=float(cl["similarity_threshold"]),
        min_cluster_size=int(cl["min_cluster_size"]),
        input_path=REPO_ROOT / cl["input_path"],
        output_path=REPO_ROOT / cl["output_path"],
    )


def flatten_issues(rows: Iterable[dict]) -> list[dict]:
    """Expand per-review extractions into one record per issue.

    The source `review_id` is carried onto each issue so a downstream consumer
    of clusters.jsonl never has to rejoin against extracted_issues.jsonl.
    """
    out: list[dict] = []
    for row in rows:
        review_id = row["review"]["review_id"]
        for issue in row["extraction"]["issues"]:
            theme = (issue.get("theme") or "").strip()
            if not theme:
                continue
            out.append(
                {
                    "review_id": review_id,
                    "theme": theme,
                    "severity": issue.get("severity"),
                    "sentiment": issue.get("sentiment"),
                    "feature_area": issue.get("feature_area"),
                    "segment_hint": issue.get("segment_hint", ""),
                }
            )
    return out


def cluster_partition(
    issues: list[dict],
    embeddings: np.ndarray,
    distance_threshold: float,
) -> list[list[int]]:
    """Return a list of clusters (each is a list of issue indices).

    A single-issue partition can't run sklearn's agglomerative model
    (needs >= 2 samples), so we short-circuit that case as one singleton
    cluster. Same for empty partitions.
    """
    n = len(issues)
    if n == 0:
        return []
    if n == 1:
        return [[0]]

    model = AgglomerativeClustering(
        n_clusters=None,
        distance_threshold=distance_threshold,
        metric="cosine",
        linkage="average",
    )
    labels = model.fit_predict(embeddings)

    buckets: dict[int, list[int]] = {}
    for idx, lbl in enumerate(labels):
        buckets.setdefault(int(lbl), []).append(idx)
    return list(buckets.values())


def medoid_label(members: list[dict], member_embeddings: np.ndarray) -> str:
    """Return the theme string of the member closest to the cluster centroid.

    Normalize first so a plain dot product gives cosine similarity, matching
    the metric used for clustering. The medoid is the member with the highest
    cosine similarity to the (normalized) centroid - i.e. the theme phrasing
    that best represents the cluster's semantic center. Ties (rare with
    float32) break on input order via argmax.
    """
    norms = np.linalg.norm(member_embeddings, axis=1, keepdims=True)
    normed = member_embeddings / np.clip(norms, 1e-12, None)
    centroid = normed.mean(axis=0)
    centroid /= max(float(np.linalg.norm(centroid)), 1e-12)
    sims = normed @ centroid
    return members[int(np.argmax(sims))]["theme"]


def build_cluster_record(
    cluster_id: str,
    sentiment: str,
    members: list[dict],
    member_embeddings: np.ndarray,
) -> dict:
    """One JSONL record per cluster. Members carry full per-issue context."""
    theme_counts = Counter(m["theme"] for m in members)
    label = medoid_label(members, member_embeddings)

    severity_breakdown = dict(Counter(m["severity"] for m in members))
    feature_area_breakdown = dict(Counter(m["feature_area"] for m in members))
    # Trivially 100% one bucket because of the sentiment partition; reported
    # anyway as confirmation that the constraint held end-to-end.
    sentiment_breakdown = dict(Counter(m["sentiment"] for m in members))

    return {
        "cluster_id": cluster_id,
        "label": label,
        "sentiment": sentiment,
        "size": len(members),
        "unique_themes": len(theme_counts),
        "sentiment_breakdown": sentiment_breakdown,
        "severity_breakdown": severity_breakdown,
        "feature_area_breakdown": feature_area_breakdown,
        "members": members,
    }


def main() -> int:
    config = load_cluster_config()
    rows = read_jsonl(config.input_path)
    issues = flatten_issues(rows)

    print(f"Loaded {len(rows)} review rows -> {len(issues)} issues")
    print(f"  embedding model:      {config.embedding_model}")
    print(f"  similarity threshold: {config.similarity_threshold}")
    print(f"  min cluster size:     {config.min_cluster_size}")

    # Heavy import deferred until after the config is read, so a typo in
    # config fails fast without paying torch's startup cost.
    from sentence_transformers import SentenceTransformer

    print("\nEmbedding...")
    t0 = time.perf_counter()
    model = SentenceTransformer(config.embedding_model)
    themes = [iss["theme"] for iss in issues]
    embeddings = model.encode(
        themes,
        batch_size=64,
        show_progress_bar=False,
        normalize_embeddings=False,
    )
    embeddings = np.asarray(embeddings, dtype=np.float32)
    print(f"  embeddings: {embeddings.shape}  ({time.perf_counter() - t0:.1f}s)")

    distance_threshold = 1.0 - config.similarity_threshold

    # Partition by sentiment so opposite-sentiment issues can never merge.
    by_sentiment: dict[str, list[int]] = {}
    for idx, iss in enumerate(issues):
        by_sentiment.setdefault(iss["sentiment"] or "unknown", []).append(idx)

    print("\nClustering within sentiment partitions...")
    all_clusters: list[dict] = []
    for sentiment, idxs in sorted(by_sentiment.items()):
        partition_issues = [issues[i] for i in idxs]
        partition_emb = embeddings[idxs]
        grouped_idxs = cluster_partition(partition_issues, partition_emb, distance_threshold)
        print(
            f"  {sentiment:>10}  issues={len(partition_issues):>4}  "
            f"raw_clusters={len(grouped_idxs)}"
        )
        for local_idxs in grouped_idxs:
            members = [partition_issues[i] for i in local_idxs]
            member_emb = partition_emb[local_idxs]
            all_clusters.append(
                build_cluster_record(
                    cluster_id="",  # assigned after global size sort
                    sentiment=sentiment,
                    members=members,
                    member_embeddings=member_emb,
                )
            )

    # Split into kept vs noise by min_cluster_size, sort kept by size,
    # then assign global cluster_ids.
    kept = [c for c in all_clusters if c["size"] >= config.min_cluster_size]
    noise = [c for c in all_clusters if c["size"] < config.min_cluster_size]
    kept.sort(key=lambda c: c["size"], reverse=True)
    for i, c in enumerate(kept, start=1):
        c["cluster_id"] = f"c_{i:04d}"

    config.output_path.parent.mkdir(parents=True, exist_ok=True)
    with config.output_path.open("w", encoding="utf-8") as fh:
        for c in kept:
            fh.write(json.dumps(c, ensure_ascii=False) + "\n")

    noise_issue_count = sum(c["size"] for c in noise)

    print("\n=== Clustering summary ===")
    print(f"Issues clustered:                {len(issues)}")
    print(f"Clusters kept (size >= {config.min_cluster_size}):       {len(kept)}")
    print(
        f"Noise / small clusters:          {len(noise)}  "
        f"({noise_issue_count} issues, "
        f"{noise_issue_count / max(1, len(issues)) * 100:.1f}%)"
    )
    if kept:
        kept_count = sum(c["size"] for c in kept)
        print(
            f"Coverage in kept clusters:       {kept_count}/{len(issues)}  "
            f"({kept_count / len(issues) * 100:.1f}%)"
        )
    print(f"Output:                          {config.output_path.relative_to(REPO_ROOT)}")

    print("\n=== Top 15 clusters by size ===")
    for c in kept[:15]:
        sb = c["sentiment_breakdown"]
        parts = "  ".join(f"{k}={v}" for k, v in sorted(sb.items()))
        print(
            f"  {c['cluster_id']}  size={c['size']:>4}  "
            f"sentiment[{parts}]  unique_themes={c['unique_themes']:>3}  "
            f"label={c['label']!r}"
        )
        sample = Counter(m["theme"] for m in c["members"]).most_common(8)
        for theme, n in sample:
            print(f"        {n:>3}x  {theme}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
