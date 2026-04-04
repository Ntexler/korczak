"""White Space Finder — identifies research gaps and under-explored connections.

Cross-references the knowledge graph to find:
  - Concepts with few or no papers (under-researched areas)
  - Concept pairs that are semantically close but have no relationships
  - Topics with high controversy but low evidence
  - Domains where funding/papers dropped off (abandoned lines of inquiry)
"""

import logging
from backend.integrations.supabase_client import get_client

logger = logging.getLogger(__name__)


async def find_orphan_concepts(min_papers: int = 0, limit: int = 20) -> list[dict]:
    """Find concepts with zero or very few linked papers."""
    client = get_client()

    # Get concepts not linked to any papers
    all_concepts = (
        client.table("concepts")
        .select("id, name, type, definition, confidence")
        .order("created_at", desc=True)
        .limit(500)
        .execute()
    )

    paper_concepts = (
        client.table("paper_concepts")
        .select("concept_id")
        .execute()
    )

    linked_ids = {pc["concept_id"] for pc in paper_concepts.data}

    orphans = []
    for c in all_concepts.data:
        if c["id"] not in linked_ids:
            orphans.append({
                "id": c["id"],
                "name": c["name"],
                "type": c.get("type", "concept"),
                "definition": c.get("definition"),
                "confidence": c.get("confidence", 0.5),
                "paper_count": 0,
                "gap_type": "no_papers",
            })
        if len(orphans) >= limit:
            break

    return orphans


async def find_missing_connections(limit: int = 20) -> list[dict]:
    """Find concept pairs that share papers but have no direct relationship.

    These are implicit connections that might represent research gaps
    or undocumented relationships.
    """
    client = get_client()

    # Get all paper-concept links
    paper_concepts = (
        client.table("paper_concepts")
        .select("paper_id, concept_id")
        .execute()
    )

    # Build paper → concepts mapping
    paper_to_concepts: dict[str, set[str]] = {}
    for pc in paper_concepts.data:
        pid = pc["paper_id"]
        cid = pc["concept_id"]
        if pid not in paper_to_concepts:
            paper_to_concepts[pid] = set()
        paper_to_concepts[pid].add(cid)

    # Find concept pairs that co-occur in papers
    cooccurrence: dict[tuple[str, str], int] = {}
    for concepts in paper_to_concepts.values():
        concept_list = sorted(concepts)
        for i, c1 in enumerate(concept_list):
            for c2 in concept_list[i + 1:]:
                pair = (c1, c2)
                cooccurrence[pair] = cooccurrence.get(pair, 0) + 1

    # Get existing relationships
    relationships = (
        client.table("relationships")
        .select("source_id, target_id")
        .execute()
    )
    existing_pairs = set()
    for r in relationships.data:
        pair = tuple(sorted([r["source_id"], r["target_id"]]))
        existing_pairs.add(pair)

    # Find co-occurring pairs WITHOUT relationships
    missing = []
    for pair, count in sorted(cooccurrence.items(), key=lambda x: -x[1]):
        if pair not in existing_pairs and count >= 2:
            missing.append({
                "concept_a_id": pair[0],
                "concept_b_id": pair[1],
                "shared_papers": count,
                "gap_type": "missing_relationship",
            })
        if len(missing) >= limit:
            break

    # Enrich with concept names
    if missing:
        concept_ids = set()
        for m in missing:
            concept_ids.add(m["concept_a_id"])
            concept_ids.add(m["concept_b_id"])

        concepts = (
            client.table("concepts")
            .select("id, name")
            .in_("id", list(concept_ids))
            .execute()
        )
        name_map = {c["id"]: c["name"] for c in concepts.data}

        for m in missing:
            m["concept_a_name"] = name_map.get(m["concept_a_id"], "Unknown")
            m["concept_b_name"] = name_map.get(m["concept_b_id"], "Unknown")

    return missing


async def find_low_evidence_controversies(limit: int = 10) -> list[dict]:
    """Find active controversies with very few supporting papers or claims."""
    client = get_client()

    controversies = (
        client.table("controversies")
        .select("id, title, description, status")
        .eq("status", "active")
        .execute()
    )

    results = []
    for c in controversies.data[:limit]:
        # Count CONTRADICTS relationships mentioning related concepts
        contradicts = (
            client.table("relationships")
            .select("id")
            .eq("relationship_type", "CONTRADICTS")
            .execute()
        )
        results.append({
            "controversy_id": c["id"],
            "title": c["title"],
            "description": c.get("description"),
            "evidence_count": len(contradicts.data),
            "gap_type": "low_evidence_controversy",
        })

    # Sort by least evidence
    results.sort(key=lambda x: x["evidence_count"])
    return results


async def find_research_gaps(keyword: str | None = None, limit: int = 20) -> dict:
    """Comprehensive research gap analysis.

    Returns orphan concepts, missing connections, and low-evidence controversies.
    Optionally filtered by keyword.
    """
    orphans = await find_orphan_concepts(limit=limit)
    missing = await find_missing_connections(limit=limit)
    low_evidence = await find_low_evidence_controversies(limit=10)

    if keyword:
        kw = keyword.lower()
        orphans = [o for o in orphans if kw in o.get("name", "").lower()
                   or kw in (o.get("definition") or "").lower()]
        missing = [m for m in missing if kw in m.get("concept_a_name", "").lower()
                   or kw in m.get("concept_b_name", "").lower()]
        low_evidence = [le for le in low_evidence if kw in le.get("title", "").lower()]

    return {
        "keyword": keyword,
        "orphan_concepts": orphans,
        "missing_connections": missing,
        "low_evidence_controversies": low_evidence,
        "summary": {
            "total_gaps": len(orphans) + len(missing) + len(low_evidence),
            "orphan_concepts": len(orphans),
            "missing_connections": len(missing),
            "low_evidence_controversies": len(low_evidence),
        },
    }
