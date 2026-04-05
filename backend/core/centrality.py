"""Centrality analysis — compute concept importance and detect branch points."""

import logging
from collections import Counter

from backend.integrations.supabase_client import get_client

logger = logging.getLogger(__name__)

# Relationship types that indicate knowledge flow
FLOW_TYPES = {"BUILDS_ON", "PREREQUISITE_FOR", "RELATES", "REFINES"}


async def compute_concept_centrality(concept_ids: list[str] | None = None) -> dict[str, dict]:
    """Compute in-degree centrality for concepts.

    Returns {concept_id: {in_degree, out_degree, centrality, name, type}}
    """
    client = get_client()

    # Get all relationships
    query = (
        client.table("relationships")
        .select("source_id, target_id, relationship_type")
    )
    result = query.execute()

    in_degree: Counter = Counter()
    out_degree: Counter = Counter()

    for r in (result.data or []):
        if r["relationship_type"] in FLOW_TYPES:
            in_degree[r["target_id"]] += 1
            out_degree[r["source_id"]] += 1

    # Get concept details
    if concept_ids:
        concepts = (
            client.table("concepts")
            .select("id, name, type")
            .in_("id", concept_ids)
            .execute()
        )
    else:
        concepts = client.table("concepts").select("id, name, type").execute()

    all_ids = {c["id"] for c in (concepts.data or [])}
    max_in = max(in_degree.values()) if in_degree else 1

    centrality = {}
    for c in (concepts.data or []):
        cid = c["id"]
        in_d = in_degree.get(cid, 0)
        out_d = out_degree.get(cid, 0)
        centrality[cid] = {
            "in_degree": in_d,
            "out_degree": out_d,
            "centrality": in_d / max_in if max_in > 0 else 0,
            "name": c["name"],
            "type": c["type"],
        }

    return centrality


async def detect_branch_points(domain: str | None = None) -> list[dict]:
    """Find concepts where the graph naturally forks into specialization clusters.

    A branch point is a concept that:
    1. Has high in-degree (many things build on it)
    2. Its children form distinct clusters (few cross-edges between them)
    """
    client = get_client()

    # Get all edges
    rels = (
        client.table("relationships")
        .select("source_id, target_id, relationship_type")
        .execute()
    )

    # Build adjacency
    children: dict[str, list[str]] = {}
    for r in (rels.data or []):
        if r["relationship_type"] in FLOW_TYPES:
            src = r["source_id"]
            children.setdefault(src, []).append(r["target_id"])

    # Find nodes with 2+ children
    branch_points = []
    for parent, kids in children.items():
        if len(kids) >= 2:
            # Check if children are in different clusters (few edges between them)
            kid_set = set(kids)
            cross_edges = 0
            for r in (rels.data or []):
                if r["source_id"] in kid_set and r["target_id"] in kid_set:
                    cross_edges += 1

            # Low cross-connectivity = good branch point
            max_possible = len(kids) * (len(kids) - 1)
            connectivity = cross_edges / max_possible if max_possible > 0 else 0

            if connectivity < 0.3:  # Less than 30% connected = distinct branches
                branch_points.append({
                    "concept_id": parent,
                    "branch_count": len(kids),
                    "branch_ids": kids[:5],
                    "connectivity": round(connectivity, 2),
                })

    # Get concept names for branch points
    bp_ids = [bp["concept_id"] for bp in branch_points]
    if bp_ids:
        concepts = (
            client.table("concepts")
            .select("id, name, type")
            .in_("id", bp_ids)
            .execute()
        )
        name_map = {c["id"]: c for c in (concepts.data or [])}
        for bp in branch_points:
            info = name_map.get(bp["concept_id"], {})
            bp["name"] = info.get("name", "Unknown")
            bp["type"] = info.get("type", "concept")

    # Sort by branch count (most branches first)
    branch_points.sort(key=lambda x: x["branch_count"], reverse=True)
    return branch_points


async def classify_pillar_vs_niche(concept_ids: list[str] | None = None) -> dict[str, str]:
    """Classify concepts as 'pillar' (high centrality) or 'niche' (low centrality).

    Returns {concept_id: 'pillar' | 'niche' | 'standard'}
    """
    centrality = await compute_concept_centrality(concept_ids)

    if not centrality:
        return {}

    # Compute thresholds
    values = [c["centrality"] for c in centrality.values()]
    avg = sum(values) / len(values) if values else 0

    classifications = {}
    for cid, data in centrality.items():
        if data["centrality"] > avg * 2:
            classifications[cid] = "pillar"
        elif data["centrality"] < avg * 0.3:
            classifications[cid] = "niche"
        else:
            classifications[cid] = "standard"

    return classifications
