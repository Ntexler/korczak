"""Knowledge Tree engine — builds and manages personal knowledge trees for each user."""

import logging
from datetime import datetime

from backend.integrations.supabase_client import get_client
from backend.core.centrality import compute_concept_centrality, detect_branch_points

logger = logging.getLogger(__name__)

# Relationship types for tree building
PREREQUISITE_TYPES = {"BUILDS_ON", "PREREQUISITE_FOR"}
FLOW_TYPES = {"BUILDS_ON", "PREREQUISITE_FOR", "RELATES", "REFINES"}


async def build_user_tree(user_id: str, root_domain: str | None = None) -> dict:
    """Generate a knowledge tree for a user from the knowledge graph.

    Steps:
    1. Find high-centrality concepts → trunk nodes
    2. Compute prerequisite chains via relationships
    3. Detect branch points (where 2+ paths diverge)
    4. Map user's progress onto the tree
    5. Cache result in knowledge_tree_nodes

    Returns {nodes: [...], edges: [...], stats: {...}}
    """
    client = get_client()

    # 1. Get concept centrality
    centrality = await compute_concept_centrality()
    if not centrality:
        return {"nodes": [], "edges": [], "stats": {}}

    # 2. Get relationships for tree structure
    rels = (
        client.table("relationships")
        .select("source_id, target_id, relationship_type")
        .execute()
    )

    # Build parent→children map (BUILDS_ON: source builds on target → target is parent)
    children_of: dict[str, list[str]] = {}
    parent_of: dict[str, str | None] = {}

    for r in (rels.data or []):
        if r["relationship_type"] in PREREQUISITE_TYPES:
            parent = r["target_id"]  # target is the prerequisite (foundation)
            child = r["source_id"]   # source builds on it
            children_of.setdefault(parent, []).append(child)
            # Only set if not already set (first parent wins)
            if child not in parent_of:
                parent_of[child] = parent

    # 3. Find trunk (highest centrality concepts with no parents or very high centrality)
    sorted_concepts = sorted(
        centrality.items(),
        key=lambda x: x[1]["centrality"],
        reverse=True,
    )

    # Top 10% centrality = trunk candidates
    trunk_count = max(3, len(sorted_concepts) // 10)
    trunk_ids = set()
    for cid, data in sorted_concepts[:trunk_count]:
        trunk_ids.add(cid)

    # Also include concepts with no parents (true roots)
    for cid in centrality:
        if cid not in parent_of:
            trunk_ids.add(cid)

    # 4. Get user's knowledge state
    user_knowledge = (
        client.table("user_knowledge")
        .select("concept_id, understanding_level")
        .eq("user_id", user_id)
        .execute()
    )
    knowledge_map = {
        uk["concept_id"]: uk["understanding_level"]
        for uk in (user_knowledge.data or [])
    }

    # 5. Build tree nodes with depth and status
    nodes = []
    edges = []
    visited = set()

    def compute_status(concept_id: str, depth: int) -> str:
        level = knowledge_map.get(concept_id, 0)
        if level >= 3:
            return "completed"
        elif level >= 1:
            return "in_progress"
        elif depth == 0:
            return "available"  # Trunk is always available
        else:
            # Check if parent is completed
            parent = parent_of.get(concept_id)
            if parent and knowledge_map.get(parent, 0) >= 2:
                return "available"
            return "locked"

    def traverse(concept_id: str, depth: int, parent_id: str | None = None):
        if concept_id in visited or concept_id not in centrality:
            return
        visited.add(concept_id)

        data = centrality[concept_id]
        status = compute_status(concept_id, depth)
        is_branch_point = len(children_of.get(concept_id, [])) >= 2

        node = {
            "concept_id": concept_id,
            "name": data["name"],
            "type": data["type"],
            "depth": depth,
            "status": status,
            "centrality": round(data["centrality"], 3),
            "is_branch_point": is_branch_point,
            "parent_id": parent_id,
            "child_count": len(children_of.get(concept_id, [])),
        }
        nodes.append(node)

        if parent_id:
            edges.append({"source": parent_id, "target": concept_id})

        # Traverse children
        for child_id in children_of.get(concept_id, []):
            traverse(child_id, depth + 1, concept_id)

    # Start from trunk concepts
    for trunk_id in trunk_ids:
        traverse(trunk_id, 0)

    # 6. Cache to DB (clear old, insert new)
    try:
        client.table("knowledge_tree_nodes").delete().eq("user_id", user_id).execute()
        for node in nodes:
            client.table("knowledge_tree_nodes").upsert({
                "user_id": user_id,
                "concept_id": node["concept_id"],
                "parent_node_id": None,  # Simplified — using concept-level parent
                "depth": node["depth"],
                "status": node["status"],
                "branch_label": node["name"] if node["is_branch_point"] else None,
            }, on_conflict="user_id,concept_id").execute()
    except Exception as e:
        logger.warning(f"Tree cache update failed: {e}")

    # Stats
    stats = {
        "total_nodes": len(nodes),
        "trunk_nodes": sum(1 for n in nodes if n["depth"] == 0),
        "branch_points": sum(1 for n in nodes if n["is_branch_point"]),
        "completed": sum(1 for n in nodes if n["status"] == "completed"),
        "available": sum(1 for n in nodes if n["status"] == "available"),
        "locked": sum(1 for n in nodes if n["status"] == "locked"),
        "max_depth": max((n["depth"] for n in nodes), default=0),
    }

    return {"nodes": nodes, "edges": edges, "stats": stats}


async def get_available_branches(user_id: str, concept_id: str) -> list[dict]:
    """At a branch point, what paths can the user take?"""
    client = get_client()

    # Get children of this concept
    rels = (
        client.table("relationships")
        .select("source_id, target_id, relationship_type")
        .eq("target_id", concept_id)
        .in_("relationship_type", list(PREREQUISITE_TYPES))
        .execute()
    )

    child_ids = [r["source_id"] for r in (rels.data or [])]
    if not child_ids:
        return []

    # Get concept details for children
    concepts = (
        client.table("concepts")
        .select("id, name, type, definition, paper_count")
        .in_("id", child_ids)
        .execute()
    )

    # Count sub-concepts for each branch
    branches = []
    for c in (concepts.data or []):
        # Count how many concepts are downstream of this one
        downstream = (
            client.table("relationships")
            .select("source_id", count="exact")
            .eq("target_id", c["id"])
            .in_("relationship_type", list(PREREQUISITE_TYPES))
            .execute()
        )

        # Check if already chosen
        chosen = (
            client.table("branch_choices")
            .select("id")
            .eq("user_id", user_id)
            .eq("branch_point_concept_id", concept_id)
            .eq("chosen_branch_concept_id", c["id"])
            .limit(1)
            .execute()
        )

        branches.append({
            "concept_id": c["id"],
            "name": c["name"],
            "type": c["type"],
            "definition": c.get("definition", ""),
            "paper_count": c.get("paper_count", 0),
            "downstream_count": downstream.count or 0,
            "is_chosen": bool(chosen.data),
        })

    return branches


async def choose_branch(user_id: str, branch_point_id: str, chosen_concept_id: str) -> dict:
    """Record the user's choice at a branch point and unlock that branch."""
    client = get_client()

    # Record choice
    client.table("branch_choices").upsert({
        "user_id": user_id,
        "branch_point_concept_id": branch_point_id,
        "chosen_branch_concept_id": chosen_concept_id,
        "chosen_at": datetime.utcnow().isoformat(),
    }, on_conflict="user_id,branch_point_concept_id").execute()

    # Unlock the chosen branch nodes
    # Get downstream concepts
    rels = (
        client.table("relationships")
        .select("source_id")
        .eq("target_id", chosen_concept_id)
        .in_("relationship_type", list(PREREQUISITE_TYPES))
        .execute()
    )
    unlock_ids = [chosen_concept_id] + [r["source_id"] for r in (rels.data or [])]

    # Update tree nodes to 'available'
    for cid in unlock_ids:
        client.table("knowledge_tree_nodes").update({
            "status": "available",
            "unlocked_at": datetime.utcnow().isoformat(),
        }).eq("user_id", user_id).eq("concept_id", cid).eq("status", "locked").execute()

    return {"status": "chosen", "unlocked": len(unlock_ids)}


async def get_tree_progress(user_id: str) -> dict:
    """Get summary of user's knowledge tree progress."""
    client = get_client()

    nodes = (
        client.table("knowledge_tree_nodes")
        .select("status, depth")
        .eq("user_id", user_id)
        .execute()
    )
    if not nodes.data:
        return {
            "total_nodes": 0,
            "trunk_completion_pct": 0,
            "branches_explored": 0,
            "max_depth_reached": 0,
        }

    data = nodes.data
    total = len(data)
    completed = sum(1 for n in data if n["status"] == "completed")
    trunk = [n for n in data if n["depth"] == 0]
    trunk_completed = sum(1 for n in trunk if n["status"] == "completed")

    # Count unique branches explored (depth > 0, status != locked)
    explored = sum(1 for n in data if n["depth"] > 0 and n["status"] != "locked")

    return {
        "total_nodes": total,
        "completed_nodes": completed,
        "completion_pct": round(completed / total * 100, 1) if total > 0 else 0,
        "trunk_completion_pct": round(trunk_completed / len(trunk) * 100, 1) if trunk else 0,
        "branches_explored": explored,
        "max_depth_reached": max((n["depth"] for n in data if n["status"] in ("completed", "in_progress")), default=0),
    }


async def refresh_tree(user_id: str) -> dict:
    """Rebuild tree when syllabus changes or new concepts discovered."""
    return await build_user_tree(user_id)
