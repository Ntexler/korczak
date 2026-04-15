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
        all_claims = []
        for ci in range(0, len(paper_ids), 30):
            batch = paper_ids[ci:ci + 30]
            claims_result = (
                client.table("claims")
                .select(
                    # Feature 6.5: provenance fields surfaced with every claim.
                    # verbatim_quote / quote_location / examples / claim_category
                    # are usually NULL until the on-demand extractor runs;
                    # returning them anyway lets the UI render "pending" vs
                    # "grounded" states without a second round-trip.
                    "id, paper_id, claim_text, evidence_type, strength, confidence, "
                    "verbatim_quote, quote_location, claim_category, examples, "
                    "provenance_extracted_at"
                )
                .in_("paper_id", batch)
                .order("confidence", desc=True)
                .limit(5)
                .execute()
            )
            all_claims.extend(claims_result.data or [])
        all_claims.sort(key=lambda c: c.get("confidence", 0), reverse=True)
        concept["key_claims"] = all_claims[:5]
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


async def get_enriched_graph_data(limit: int = 100, include_lens_data: bool = False) -> dict:
    """Get full graph visualization data with definitions and connection explanations.

    When include_lens_data=True, also fetches:
    - controversy_score per concept
    - max_publication_year per concept (from linked papers)
    - community_activity per concept (discussions + summaries count)
    - disagree_count per relationship (from connection_feedback)
    """
    client = get_client()

    # Get concepts with definitions + controversy_score
    concepts = (
        client.table("concepts")
        .select("id, name, type, definition, confidence, paper_count, controversy_score")
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )

    concept_ids = {c["id"] for c in concepts.data}
    concept_id_list = list(concept_ids)

    # Get relationships with explanations and source paper
    relationships = (
        client.table("relationships")
        .select("id, source_id, target_id, relationship_type, confidence, explanation, paper_id")
        .execute()
    )

    # Filter to relevant edges
    relevant_rels = [
        r for r in relationships.data
        if r["source_id"] in concept_ids and r["target_id"] in concept_ids
    ]

    # For edges with paper_id, fetch paper titles
    paper_ids_needed = {r["paper_id"] for r in relevant_rels if r.get("paper_id")}

    paper_titles = {}
    if paper_ids_needed:
        papers_result = (
            client.table("papers")
            .select("id, title")
            .in_("id", list(paper_ids_needed))
            .execute()
        )
        paper_titles = {p["id"]: p["title"] for p in (papers_result.data or [])}

    # --- Lens data (optional) ---
    max_pub_year: dict[str, int] = {}
    community_activity: dict[str, int] = {}
    disagree_counts: dict[str, int] = {}

    if include_lens_data:
        # Max publication year per concept via paper_concepts → papers
        try:
            pc_data = []
            for ci in range(0, len(concept_id_list), 50):
                batch = concept_id_list[ci:ci + 50]
                pc_batch = (
                    client.table("paper_concepts")
                    .select("concept_id, papers(publication_year)")
                    .in_("concept_id", batch)
                    .execute()
                )
                pc_data.extend(pc_batch.data or [])
            pc_result_data = pc_data
            for row in pc_result_data:
                cid = row["concept_id"]
                year = row.get("papers", {}).get("publication_year")
                if year and (cid not in max_pub_year or year > max_pub_year[cid]):
                    max_pub_year[cid] = year
        except Exception as e:
            logger.warning(f"Failed to fetch publication years for lenses: {e}")

        # Community activity: discussions + concept_summaries
        try:
            disc_data = []
            for ci in range(0, len(concept_id_list), 50):
                batch = concept_id_list[ci:ci + 50]
                disc_batch = client.table("discussions").select("target_id").eq(
                    "target_type", "concept"
                ).in_("target_id", batch).execute()
                disc_data.extend(disc_batch.data or [])
            for row in disc_data:
                tid = row["target_id"]
                community_activity[tid] = community_activity.get(tid, 0) + 1
        except Exception as e:
            logger.warning(f"Failed to fetch discussions for lenses: {e}")

        try:
            summ_data = []
            for ci in range(0, len(concept_id_list), 50):
                batch = concept_id_list[ci:ci + 50]
                summ_batch = client.table("concept_summaries").select(
                    "concept_id"
                ).in_("concept_id", batch).execute()
                summ_data.extend(summ_batch.data or [])
            for row in summ_data:
                cid = row["concept_id"]
                community_activity[cid] = community_activity.get(cid, 0) + 1
        except Exception as e:
            logger.warning(f"Failed to fetch summaries for lenses: {e}")

        # Disagree count per relationship
        rel_ids = [r["id"] for r in relevant_rels]
        if rel_ids:
            try:
                feedback_result = (
                    client.table("connection_feedback")
                    .select("relationship_id")
                    .eq("feedback_type", "disagree")
                    .in_("relationship_id", rel_ids)
                    .execute()
                )
                for row in (feedback_result.data or []):
                    rid = row["relationship_id"]
                    disagree_counts[rid] = disagree_counts.get(rid, 0) + 1
            except Exception as e:
                logger.warning(f"Failed to fetch feedback for lenses: {e}")

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

    nodes = []
    for c in concepts.data:
        node = {
            "id": c["id"],
            "name": c["name"],
            "type": c.get("type", "concept"),
            "definition": c.get("definition"),
            "confidence": c.get("confidence", 0.5),
            "paper_count": c.get("paper_count", 0),
            "color": type_colors.get(c.get("type", "concept"), "#8B949E"),
        }
        if include_lens_data:
            node["controversy_score"] = c.get("controversy_score", 0)
            node["max_publication_year"] = max_pub_year.get(c["id"])
            node["community_activity"] = community_activity.get(c["id"], 0)
        nodes.append(node)

    edges = []
    for r in relevant_rels:
        edge = {
            "id": r["id"],
            "source": r["source_id"],
            "target": r["target_id"],
            "type": r["relationship_type"],
            "confidence": r.get("confidence", 0.5),
            "explanation": r.get("explanation"),
            "source_paper": paper_titles.get(r.get("paper_id")) if r.get("paper_id") else None,
        }
        if include_lens_data:
            edge["disagree_count"] = disagree_counts.get(r["id"], 0)
        edges.append(edge)

    return {
        "nodes": nodes,
        "edges": edges,
        "node_count": len(nodes),
        "edge_count": len(edges),
    }


async def get_geographic_data() -> dict:
    """Get institution locations with paper counts for geographic visualization."""
    client = get_client()
    try:
        result = (
            client.table("entities")
            .select("id, name, metadata")
            .eq("type", "institution")
            .execute()
        )
        locations = []
        for entity in (result.data or []):
            meta = entity.get("metadata") or {}
            if meta.get("lat") and meta.get("lng"):
                locations.append({
                    "id": entity["id"],
                    "name": entity["name"],
                    "lat": meta["lat"],
                    "lng": meta["lng"],
                    "paper_count": meta.get("paper_count", 0),
                    "country": meta.get("country", ""),
                })
        return {"locations": locations, "total": len(locations)}
    except Exception as e:
        logger.warning(f"Failed to fetch geographic data: {e}")
        return {"locations": [], "total": 0}


async def get_sankey_flow_data() -> dict:
    """Get relationship counts between concept types for Sankey visualization."""
    client = get_client()

    # Build concept_id → type map
    concepts = client.table("concepts").select("id, type").execute()
    type_map = {c["id"]: c.get("type", "concept") for c in (concepts.data or [])}

    # Aggregate relationships by (source_type, target_type, rel_type)
    relationships = (
        client.table("relationships")
        .select("source_id, target_id, relationship_type")
        .execute()
    )

    flows: dict[tuple[str, str, str], int] = {}
    for r in (relationships.data or []):
        src_type = type_map.get(r["source_id"], "other")
        tgt_type = type_map.get(r["target_id"], "other")
        rel_type = r["relationship_type"]
        key = (src_type, tgt_type, rel_type)
        flows[key] = flows.get(key, 0) + 1

    flow_list = [
        {"source_type": k[0], "target_type": k[1], "relationship_type": k[2], "count": v}
        for k, v in flows.items()
        if v > 0
    ]
    flow_list.sort(key=lambda x: x["count"], reverse=True)

    unique_types = sorted(set(type_map.values()))
    return {"flows": flow_list, "types": unique_types}


# In-memory explanation cache {concept_id:locale -> explanation_dict}
_explanation_cache: dict[str, dict] = {}


async def get_simple_explanation(concept_id: str, locale: str = "en") -> dict | None:
    """Generate a simple explanation — cached in memory + DB for instant loading.

    First call: generates via Claude (~3s), saves to concepts.definition if empty.
    Subsequent calls: instant from cache (<1ms).
    """
    cache_key = f"{concept_id}:{locale}"

    # Layer 1: Memory cache
    if cache_key in _explanation_cache:
        return _explanation_cache[cache_key]

    client = get_client()

    concept = client.table("concepts").select(
        "id, name, type, definition, paper_count"
    ).eq("id", concept_id).execute()

    if not concept.data:
        return None

    c = concept.data[0]
    definition = c.get("definition") or ""

    # Layer 2: If definition is rich enough (>100 chars), use it directly — no Claude needed
    if definition and len(definition) > 100:
        result = {
            "concept_id": c["id"],
            "name": c["name"],
            "type": c.get("type"),
            "simple_explanation": definition,
            "definition": definition,
            "paper_count": c.get("paper_count", 0),
            "explain_simpler_prompt": f"Explain {c['name']} like I'm in high school",
            "go_deeper_prompt": f"Give me the full academic analysis of {c['name']}",
        }
        _explanation_cache[cache_key] = result
        return result

    # Layer 3: Generate via Claude (only if definition is short/empty)
    papers = await get_papers_for_concept(concept_id, limit=2)
    paper_context = ""
    if papers:
        paper_context = " Key works: " + ", ".join(
            f"{p.get('title', '')} ({p.get('publication_year', '')})"
            for p in papers[:2]
        )

    try:
        from backend.config import settings
        from backend.integrations.claude_client import _call_claude

        lang = "Hebrew" if locale == "he" else "English"
        prompt = (
            f"Explain the academic concept \"{c['name']}\" ({c.get('type', 'concept')}) "
            f"in 3-5 clear sentences. Be direct and informative — like a knowledgeable colleague "
            f"explaining to someone new to the topic. "
            f"Context: {definition[:200]}.{paper_context}\n"
            f"Respond in {lang}. No hollow praise. No jargon without explanation."
        )

        response = await _call_claude(
            prompt,
            model=settings.haiku_model,
            max_tokens=400,
            temperature=0.4,
        )

        explanation = response.text

        # Save back to DB so we never need to regenerate
        try:
            if not definition or len(definition) < 50:
                client.table("concepts").update(
                    {"definition": explanation}
                ).eq("id", concept_id).execute()
        except Exception:
            pass  # non-critical

        result = {
            "concept_id": c["id"],
            "name": c["name"],
            "type": c.get("type"),
            "simple_explanation": explanation,
            "definition": definition or explanation,
            "paper_count": c.get("paper_count", 0),
            "explain_simpler_prompt": f"Explain {c['name']} like I'm in high school",
            "go_deeper_prompt": f"Give me the full academic analysis of {c['name']}",
        }
        _explanation_cache[cache_key] = result
        return result

    except Exception as e:
        logger.warning(f"Simple explanation failed: {e}")
        return {
            "concept_id": c["id"],
            "name": c["name"],
            "type": c.get("type"),
            "simple_explanation": definition or f"{c['name']} is a concept in academic research.",
            "definition": definition,
            "paper_count": c.get("paper_count", 0),
        }


async def get_personal_overlay(user_id: str, limit: int = 100) -> dict:
    """Get personal knowledge overlay — fog of war data for the graph.

    Returns each concept's status for this user:
    - explored: understanding_level > 0.3 (green)
    - in_progress: understanding_level 0.1-0.3 (amber)
    - unexplored: no entry or understanding_level < 0.1 (gray/fog)
    Plus misconceptions and blind spots for explored concepts.
    """
    client = get_client()

    # Get graph concepts
    concepts = (
        client.table("concepts")
        .select("id, name, type, paper_count")
        .order("paper_count", desc=True)
        .limit(limit)
        .execute()
    )
    concept_ids = [c["id"] for c in concepts.data]

    if not concept_ids:
        return {"overlay": [], "stats": {}}

    # Get user's knowledge state for these concepts
    knowledge_data = []
    for ci in range(0, len(concept_ids), 50):
        batch = concept_ids[ci:ci + 50]
        kn_batch = (
            client.table("user_knowledge")
            .select("concept_id, understanding_level, misconceptions, blind_spots, interaction_count, last_interaction")
            .eq("user_id", user_id)
            .in_("concept_id", batch)
            .execute()
        )
        knowledge_data.extend(kn_batch.data or [])
    knowledge = type("R", (), {"data": knowledge_data})()
    knowledge_map = {k["concept_id"]: k for k in (knowledge.data or [])}

    # Build overlay
    overlay = []
    explored = 0
    in_progress = 0
    unexplored = 0

    for concept in concepts.data:
        cid = concept["id"]
        k = knowledge_map.get(cid)

        if k and k.get("understanding_level", 0) > 0.3:
            status = "explored"
            explored += 1
        elif k and k.get("understanding_level", 0) >= 0.1:
            status = "in_progress"
            in_progress += 1
        else:
            status = "unexplored"
            unexplored += 1

        entry = {
            "concept_id": cid,
            "concept_name": concept["name"],
            "status": status,
            "understanding_level": k.get("understanding_level", 0) if k else 0,
            "interaction_count": k.get("interaction_count", 0) if k else 0,
        }

        if k and status == "explored":
            misconceptions = k.get("misconceptions") or []
            blind_spots = k.get("blind_spots") or []
            if misconceptions:
                entry["misconceptions"] = len(misconceptions)
            if blind_spots:
                entry["blind_spots"] = len(blind_spots)

        overlay.append(entry)

    total = explored + in_progress + unexplored
    return {
        "overlay": overlay,
        "stats": {
            "total_concepts": total,
            "explored": explored,
            "explored_pct": round(explored / total * 100, 1) if total else 0,
            "in_progress": in_progress,
            "in_progress_pct": round(in_progress / total * 100, 1) if total else 0,
            "unexplored": unexplored,
            "unexplored_pct": round(unexplored / total * 100, 1) if total else 0,
        },
    }
