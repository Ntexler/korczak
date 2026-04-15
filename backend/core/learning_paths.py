"""Learning-Path Generator — teaching as pathfinding.

Given (user, goal_concept), find an ordered sequence of concepts to
study. The path respects:
  - prerequisites (inferred from the concept relationship graph)
  - what the user has already mastered (skip those)
  - citation depth (simpler/older concepts first)
  - canonical anchoring (prefer concepts that belong to canonical papers)

Produces a learning_paths + learning_path_steps record.

This is NOT a replacement for a teacher — it's a starting trajectory the
learner can follow, revise, or ignore. Each step points at a canonical
paper when possible so the learner reads the real text.
"""

from __future__ import annotations

import logging
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Optional

import psycopg2
import psycopg2.extras

logger = logging.getLogger(__name__)

DB_PARAMS = {
    "host": "db.bgrdmydbrtnucunbpobl.supabase.co",
    "port": 5432,
    "user": "postgres",
    "password": "KOR@9876CZAK",
    "database": "postgres",
}

# Edge types that indicate "A depends on B" when source=A, target=B
PREREQ_TYPES = {"BUILDS_ON", "EXTENDS", "APPLIES"}
# Edge types that indicate lateral / peer relationships (not prereqs)
LATERAL_TYPES = {"ANALOGOUS_TO", "CONTRADICTS", "RESPONDS_TO"}


# ---------------------------------------------------------------------------
# Graph helpers
# ---------------------------------------------------------------------------

def _fetch_concept_graph(conn, field_filter: Optional[str] = None) -> dict:
    """Load a subgraph of concept→concept edges.

    Returns:
      {
        "nodes": {concept_id: {id, name, type, definition, paper_count, canonical_count}},
        "incoming": {concept_id: [{from, edge_type}]},   # who I depend on
        "outgoing": {concept_id: [{to, edge_type}]},     # who depends on me
      }
    """
    nodes: dict = {}
    incoming: dict = defaultdict(list)
    outgoing: dict = defaultdict(list)

    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        # Nodes — every concept with usage stats
        cur.execute(
            """
            SELECT c.id, c.name, c.type, c.definition,
                   (SELECT COUNT(*) FROM paper_concepts pc WHERE pc.concept_id = c.id) as paper_count,
                   (SELECT COUNT(*) FROM paper_concepts pc
                      JOIN papers p ON p.id = pc.paper_id
                      WHERE pc.concept_id = c.id AND p.canonical = TRUE) as canonical_count
            FROM concepts c
            """
        )
        for r in cur.fetchall():
            nodes[str(r["id"])] = dict(r)

        # Edges — only concept-to-concept
        cur.execute(
            """
            SELECT source_id, target_id, relationship_type
            FROM relationships
            WHERE source_type = 'concept' AND target_type = 'concept'
            """
        )
        for r in cur.fetchall():
            src = str(r["source_id"])
            tgt = str(r["target_id"])
            et = r["relationship_type"]
            # In our schema, source BUILDS_ON target means source depends on target.
            # So: edge A -[BUILDS_ON]-> B  means A depends on B, i.e. B is prereq of A.
            if et in PREREQ_TYPES:
                incoming[src].append({"from": tgt, "edge_type": et})
                outgoing[tgt].append({"to": src, "edge_type": et})
            elif et in LATERAL_TYPES:
                # Don't treat as prereq, but we still remember the link
                pass

    return {"nodes": nodes, "incoming": incoming, "outgoing": outgoing}


def _known_concepts(conn, user_id: str, mastery_threshold: float = 0.7) -> set:
    """Concept IDs the learner already has at or above the mastery threshold."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT concept_id
            FROM user_concept_mastery
            WHERE user_id = %s AND mastery_score >= %s
            """,
            (user_id, mastery_threshold),
        )
        return {str(r[0]) for r in cur.fetchall()}


# ---------------------------------------------------------------------------
# Path construction
# ---------------------------------------------------------------------------

def _reverse_topo_sort(goal_id: str, graph: dict, already_known: set,
                       max_depth: int = 6) -> list:
    """Walk backward from goal through prereqs; return topo-sorted list.

    Uses Kahn's algorithm on the subgraph reachable within max_depth.
    """
    nodes = graph["nodes"]
    incoming = graph["incoming"]

    # BFS backward to collect the relevant subgraph
    collected: set = set()
    q = deque([(goal_id, 0)])
    while q:
        cid, depth = q.popleft()
        if cid in collected or cid not in nodes:
            continue
        collected.add(cid)
        if cid in already_known:
            # Known concepts form the frontier — don't expand past them
            continue
        if depth >= max_depth:
            continue
        for edge in incoming.get(cid, []):
            if edge["from"] not in collected:
                q.append((edge["from"], depth + 1))

    # Drop known concepts from the subgraph (skip what the learner has)
    subgraph = {c for c in collected if c not in already_known}

    # Kahn's algorithm: start with nodes whose prereqs (within the subgraph)
    # are all satisfied.
    in_degree: dict = {c: 0 for c in subgraph}
    for c in subgraph:
        for edge in incoming.get(c, []):
            if edge["from"] in subgraph:
                in_degree[c] += 1

    queue = deque([c for c, d in in_degree.items() if d == 0])
    ordered: list = []
    while queue:
        # Deterministic-ish ordering: prefer concepts with more canonical papers
        # (they're more foundational and usually clearer teaching material).
        cands = list(queue)
        cands.sort(
            key=lambda c: (
                -nodes[c].get("canonical_count", 0),
                -nodes[c].get("paper_count", 0),
                nodes[c].get("name", ""),
            )
        )
        queue.clear()
        for c in cands:
            ordered.append(c)
            for edge in graph["outgoing"].get(c, []):
                t = edge["to"]
                if t in in_degree:
                    in_degree[t] -= 1
                    if in_degree[t] == 0:
                        queue.append(t)

    # If cycles remain (leftovers with nonzero degree), append them by
    # canonical-count heuristic so we don't silently drop them.
    leftovers = [c for c, d in in_degree.items() if d > 0 and c not in ordered]
    leftovers.sort(
        key=lambda c: (
            -nodes[c].get("canonical_count", 0),
            -nodes[c].get("paper_count", 0),
        )
    )
    ordered.extend(leftovers)

    return ordered


def _anchor_paper(conn, concept_id: str) -> Optional[str]:
    """Pick the best paper to read for a concept.

    Preference: canonical paper that uses the concept, otherwise the
    highest-cited paper that uses it.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT p.id
            FROM paper_concepts pc
            JOIN papers p ON p.id = pc.paper_id
            WHERE pc.concept_id = %s
            ORDER BY p.canonical DESC NULLS LAST,
                     p.cited_by_count DESC NULLS LAST
            LIMIT 1
            """,
            (concept_id,),
        )
        r = cur.fetchone()
        return str(r[0]) if r else None


def _build_instruction(concept: dict, anchor_paper_title: Optional[str]) -> str:
    base = f"Study the concept '{concept['name']}'"
    if concept.get("definition"):
        base += f" — {concept['definition'][:160]}"
    if anchor_paper_title:
        base += f". Anchor reading: \"{anchor_paper_title[:80]}\"."
    return base


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_learning_path(
    user_id: str,
    goal_concept_id: str,
    name: Optional[str] = None,
    description: Optional[str] = None,
    max_depth: int = 6,
    max_steps: int = 20,
    mastery_threshold: float = 0.7,
    save: bool = True,
) -> dict:
    """Build a concrete learning path toward goal_concept_id for user_id.

    Returns the full path (concepts + anchor papers + instructions), and
    if save=True, persists it to learning_paths + learning_path_steps.
    """
    conn = psycopg2.connect(**DB_PARAMS)
    try:
        if goal_concept_id not in _nodes_index(conn):
            raise ValueError(f"Goal concept {goal_concept_id} not found")

        graph = _fetch_concept_graph(conn)
        known = _known_concepts(conn, user_id, mastery_threshold)
        ordered = _reverse_topo_sort(goal_concept_id, graph, known, max_depth=max_depth)

        # Trim to max_steps (end of list is the goal)
        if len(ordered) > max_steps:
            # Keep the last step (the goal) + the most canonical prereqs
            goal_idx = ordered.index(goal_concept_id) if goal_concept_id in ordered else len(ordered) - 1
            head = [c for c in ordered[:goal_idx] if graph["nodes"][c].get("canonical_count", 0) > 0]
            if len(head) < max_steps - 1:
                # pad with high paper_count concepts
                remaining = [c for c in ordered[:goal_idx] if c not in head]
                remaining.sort(key=lambda c: -graph["nodes"][c].get("paper_count", 0))
                head.extend(remaining[: max_steps - 1 - len(head)])
            ordered = head + [goal_concept_id]

        # Attach anchor papers + titles
        steps: list = []
        paper_title_cache: dict = {}
        with conn.cursor() as cur:
            for pos, cid in enumerate(ordered, 1):
                node = graph["nodes"][cid]
                anchor = _anchor_paper(conn, cid)
                title = None
                if anchor:
                    if anchor not in paper_title_cache:
                        cur.execute("SELECT title FROM papers WHERE id = %s", (anchor,))
                        r = cur.fetchone()
                        paper_title_cache[anchor] = r[0] if r else None
                    title = paper_title_cache[anchor]
                steps.append(
                    {
                        "position": pos,
                        "concept_id": cid,
                        "concept_name": node["name"],
                        "paper_id": anchor,
                        "paper_title": title,
                        "instruction": _build_instruction(node, title),
                    }
                )

        path: dict = {
            "user_id": user_id,
            "goal_concept_id": goal_concept_id,
            "goal_concept_name": graph["nodes"][goal_concept_id]["name"],
            "known_prereqs_skipped": len(known),
            "steps": steps,
        }

        if save:
            path_id = _persist_path(conn, user_id, goal_concept_id, name, description, steps)
            path["path_id"] = path_id

        return path
    finally:
        conn.close()


def _nodes_index(conn) -> set:
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM concepts")
        return {str(r[0]) for r in cur.fetchall()}


def _persist_path(conn, user_id, goal_concept_id, name, description, steps) -> str:
    name = name or f"Path to concept {goal_concept_id[:8]}"
    description = description or f"Auto-generated learning path in {len(steps)} steps"
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO learning_paths (user_id, name, description, goal_concept_ids, generated_by)
            VALUES (%s, %s, %s, ARRAY[%s]::uuid[], 'korczak')
            RETURNING id
            """,
            (user_id, name, description, goal_concept_id),
        )
        path_id = cur.fetchone()[0]

        for step in steps:
            cur.execute(
                """
                INSERT INTO learning_path_steps
                    (path_id, concept_id, paper_id, position, instruction, status)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    path_id,
                    step["concept_id"],
                    step["paper_id"],
                    step["position"],
                    step["instruction"],
                    "current" if step["position"] == 1 else "pending",
                ),
            )
        conn.commit()
        return str(path_id)


# ---------------------------------------------------------------------------
# Convenience: find goal by name
# ---------------------------------------------------------------------------

def find_concept_by_name(name: str) -> Optional[str]:
    """Lookup a concept id by (fuzzy) name. Used by API and CLI."""
    conn = psycopg2.connect(**DB_PARAMS)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id FROM concepts
                WHERE lower(name) = lower(%s)
                   OR normalized_name = lower(%s)
                LIMIT 1
                """,
                (name, name),
            )
            r = cur.fetchone()
            return str(r[0]) if r else None
    finally:
        conn.close()


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser()
    parser.add_argument("--user", required=True)
    parser.add_argument("--goal", required=True, help="Goal concept name")
    parser.add_argument("--max-steps", type=int, default=20)
    parser.add_argument("--save", action="store_true")
    parser.add_argument("--name", default=None)
    args = parser.parse_args()

    goal_id = find_concept_by_name(args.goal)
    if not goal_id:
        print(f"No concept found matching '{args.goal}'")
        raise SystemExit(1)
    path = generate_learning_path(
        user_id=args.user,
        goal_concept_id=goal_id,
        name=args.name,
        max_steps=args.max_steps,
        save=args.save,
    )
    print(json.dumps(path, indent=2, ensure_ascii=False, default=str))
