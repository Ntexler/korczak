"""Concept Enricher — generate rich descriptions for concepts using their graph context."""

import logging

from backend.integrations.supabase_client import get_client, get_papers_for_concept

logger = logging.getLogger(__name__)


async def get_concept_with_context(concept_id: str) -> dict | None:
    """Get a concept with its definition, key papers, and connection explanations."""
    client = get_client()

    # Get the concept
    concept_result = (
        client.table("concepts")
        .select("id, name, type, definition, paper_count, trend, confidence, controversy_score, interdisciplinarity")
        .eq("id", concept_id)
        .execute()
    )
    if not concept_result.data:
        return None

    concept = concept_result.data[0]

    # Get key papers (top 5 by relevance)
    papers = await get_papers_for_concept(concept_id, limit=5)
    import json as _json
    concept["key_papers"] = [
        {
            "id": str(p["id"]),
            "title": p.get("title", ""),
            "authors": _json.loads(p["authors"]) if isinstance(p.get("authors"), str) else (p.get("authors") or []),
            "publication_year": p.get("publication_year"),
            "cited_by_count": p.get("cited_by_count", 0),
            "doi": p.get("doi"),
            "openalex_id": p.get("openalex_id"),
        }
        for p in papers
    ]

    # Get claims related to this concept's papers
    if papers:
        paper_ids = [str(p["id"]) for p in papers]
        claims_result = (
            client.table("claims")
            .select("claim_text, evidence_type, strength, confidence")
            .in_("paper_id", paper_ids)
            .order("confidence", desc=True)
            .limit(5)
            .execute()
        )
        concept["key_claims"] = claims_result.data or []
    else:
        concept["key_claims"] = []

    return concept


async def get_enriched_neighbors(concept_id: str, depth: int = 1) -> list[dict]:
    """Get neighbors with full relationship explanations and source papers."""
    client = get_client()

    # Use the existing RPC which already returns explanations
    result = client.rpc(
        "get_concept_neighborhood",
        {"p_concept_id": concept_id, "p_depth": depth},
    ).execute()

    neighbors = []
    for n in (result.data or []):
        neighbor = {
            "concept": {
                "id": str(n.get("concept_id", "")),
                "name": n.get("concept_name", "Unknown"),
                "type": n.get("concept_type", "concept"),
                "definition": n.get("concept_definition"),
                "confidence": n.get("concept_confidence", 0.5),
            },
            "relationship_type": n.get("relationship_type", "related"),
            "confidence": n.get("relationship_confidence", 0.5),
            "explanation": n.get("relationship_explanation"),
            "depth": n.get("depth", 1),
        }
        neighbors.append(neighbor)

    return neighbors


async def get_enriched_graph_data(limit: int = 100) -> dict:
    """Get full graph visualization data with definitions and connection explanations."""
    client = get_client()

    # Get concepts with definitions
    concepts = (
        client.table("concepts")
        .select("id, name, type, definition, confidence, paper_count")
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )

    concept_ids = {c["id"] for c in concepts.data}

    # Get relationships with explanations and source paper
    relationships = (
        client.table("relationships")
        .select("id, source_id, target_id, relationship_type, confidence, explanation, paper_id")
        .execute()
    )

    # For edges with paper_id, fetch paper titles
    paper_ids_needed = {
        r["paper_id"] for r in relationships.data
        if r.get("paper_id") and r["source_id"] in concept_ids and r["target_id"] in concept_ids
    }

    paper_titles = {}
    if paper_ids_needed:
        papers_result = (
            client.table("papers")
            .select("id, title")
            .in_("id", list(paper_ids_needed))
            .execute()
        )
        paper_titles = {p["id"]: p["title"] for p in (papers_result.data or [])}

    type_colors = {
        "theory": "#E8B931",
        "method": "#58A6FF",
        "framework": "#3FB950",
        "phenomenon": "#D29922",
        "tool": "#BC8CFF",
        "metric": "#F78166",
        "critique": "#F85149",
        "paradigm": "#E8B931",
    }

    nodes = [
        {
            "id": c["id"],
            "name": c["name"],
            "type": c.get("type", "concept"),
            "definition": c.get("definition"),
            "confidence": c.get("confidence", 0.5),
            "paper_count": c.get("paper_count", 0),
            "color": type_colors.get(c.get("type", "concept"), "#8B949E"),
        }
        for c in concepts.data
    ]

    edges = [
        {
            "id": r["id"],
            "source": r["source_id"],
            "target": r["target_id"],
            "type": r["relationship_type"],
            "confidence": r.get("confidence", 0.5),
            "explanation": r.get("explanation"),
            "source_paper": paper_titles.get(r.get("paper_id")) if r.get("paper_id") else None,
        }
        for r in relationships.data
        if r["source_id"] in concept_ids and r["target_id"] in concept_ids
    ]

    return {
        "nodes": nodes,
        "edges": edges,
        "node_count": len(nodes),
        "edge_count": len(edges),
    }
