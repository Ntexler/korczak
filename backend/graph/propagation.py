"""Belief Propagation — the graph stops being storage and starts thinking.

The audit's core inference finding: consensus was a per-node counter.
If A contradicts B, and C BUILDS_ON B — nothing ever touched C.

This module propagates trust along the edges Korczak already has:

- CONTRADICTS / WEAKENS edges push a penalty onto both endpoints,
  weighted by edge confidence.
- A node's penalty flows FORWARD along BUILDS_ON / EXTENDS / PART_OF /
  PREREQUISITE_FOR edges: whatever is built on shaky ground becomes
  shaky itself (damped per hop).
- SUPPORTS edges lift their endpoints slightly.

K damped iterations (default 3) — enough for penalties to reach
grandchildren without oscillating. Pure Python, no LLM calls, runs in
milliseconds on thousands of edges.

Output per concept: propagated_penalty / propagated_support, folded into
consensus_score, with demotion of 'consensus' nodes whose foundations
are contested ('emerging' + reason).

Wire-in: consensus.compute_consensus(propagate=True) and Chappie's
nightly_run. CLI: python -m backend.graph.propagation --apply
"""

import logging
from collections import defaultdict

logger = logging.getLogger(__name__)

DAMPING = 0.5          # how much of a node's penalty flows one hop forward
ITERATIONS = 3
CONTRADICTION_HIT = 0.3   # direct penalty per contradicting edge (× edge confidence)
SUPPORT_LIFT = 0.05       # direct lift per supporting edge (× edge confidence)
DEMOTION_THRESHOLD = 0.15  # inherited penalty that demotes 'consensus'

FORWARD_EDGES = {"BUILDS_ON", "EXTENDS", "PART_OF", "PREREQUISITE_FOR", "APPLIES"}
CONFLICT_EDGES = {"CONTRADICTS", "WEAKENS"}
SUPPORT_EDGES = {"SUPPORTS"}


def propagate(
    edges: list[dict],
    iterations: int = ITERATIONS,
    damping: float = DAMPING,
) -> dict[str, dict]:
    """Run belief propagation over concept-concept edges.

    edges: [{source_id, target_id, relationship_type, confidence}]
    Returns {concept_id: {"penalty": float, "support": float}}.
    """
    # Direct signals
    penalty: dict[str, float] = defaultdict(float)
    support: dict[str, float] = defaultdict(float)

    # source BUILDS_ON target => target's trouble flows TO source
    depends_on: dict[str, list[tuple[str, float]]] = defaultdict(list)

    for e in edges:
        rel = e.get("relationship_type", "")
        src, tgt = e.get("source_id"), e.get("target_id")
        conf = float(e.get("confidence") or 0.5)
        if not src or not tgt or src == tgt:
            continue

        if rel in CONFLICT_EDGES:
            penalty[src] += CONTRADICTION_HIT * conf
            penalty[tgt] += CONTRADICTION_HIT * conf
        elif rel in SUPPORT_EDGES:
            support[src] += SUPPORT_LIFT * conf
            support[tgt] += SUPPORT_LIFT * conf
        elif rel in FORWARD_EDGES:
            depends_on[src].append((tgt, conf))

    # Damped forward propagation: my foundations' penalties become mine
    current = dict(penalty)
    for _ in range(iterations):
        nxt: dict[str, float] = defaultdict(float)
        for node, foundations in depends_on.items():
            inherited = sum(current.get(f, 0.0) * conf for f, conf in foundations)
            if inherited > 0:
                nxt[node] = inherited * damping
        if not nxt:
            break
        for node, val in nxt.items():
            current[node] = max(current.get(node, 0.0), penalty.get(node, 0.0) + val)

    all_nodes = set(current) | set(support)
    return {
        n: {
            "penalty": round(min(current.get(n, 0.0), 1.0), 3),
            "support": round(min(support.get(n, 0.0), 0.3), 3),
        }
        for n in all_nodes
    }


async def run_propagation(apply: bool = True, limit: int = 2000) -> dict:
    """Load concept edges, propagate, and (optionally) fold into consensus."""
    from backend.integrations.supabase_client import get_client
    client = get_client()

    rels = client.table("relationships").select(
        "source_id, target_id, relationship_type, confidence"
    ).eq("source_type", "concept").eq("target_type", "concept").limit(10000).execute()
    edges = rels.data or []
    if not edges:
        return {"status": "no_edges"}

    scores = propagate(edges)
    logger.info(f"Propagation: {len(edges)} edges → {len(scores)} affected concepts")

    demoted = 0
    adjusted = 0
    if apply and scores:
        ids = list(scores.keys())[:limit]
        for i in range(0, len(ids), 50):
            batch = ids[i:i + 50]
            rows = client.table("concepts").select(
                "id, consensus_status, consensus_score"
            ).in_("id", batch).execute()
            for c in (rows.data or []):
                s = scores[c["id"]]
                net = s["support"] - s["penalty"]
                new_score = round(min(1.0, max(0.0, (c.get("consensus_score") or 0) + net)), 2)
                patch = {"consensus_score": new_score}
                # A "consensus" node standing on contested foundations is demoted
                if (c.get("consensus_status") == "consensus"
                        and s["penalty"] >= DEMOTION_THRESHOLD):
                    patch["consensus_status"] = "emerging"
                    demoted += 1
                client.table("concepts").update(patch).eq("id", c["id"]).execute()
                adjusted += 1

    top = sorted(scores.items(), key=lambda kv: -kv[1]["penalty"])[:10]
    return {
        "status": "ok",
        "edges": len(edges),
        "affected": len(scores),
        "adjusted": adjusted,
        "demoted_from_consensus": demoted,
        "most_contested": [{"concept_id": k, **v} for k, v in top],
    }


if __name__ == "__main__":
    import argparse
    import asyncio
    import json
    import sys
    from dotenv import load_dotenv

    load_dotenv()
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Belief propagation over the knowledge graph")
    parser.add_argument("--apply", action="store_true", help="Write adjusted scores back")
    args = parser.parse_args()
    result = asyncio.run(run_propagation(apply=args.apply))
    print(json.dumps(result, indent=2, default=str))
