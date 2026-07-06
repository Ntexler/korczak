"""Atlas API — one continuous knowledge universe, not siloed fields.

The map the whole interface stands on:
- Fields are gravitational REGIONS on one map, not separate pages
- Border concepts (papers spanning 2+ fields) sit on the seams —
  that's where interdisciplinary work lives, and the map shows it
- Fog of war is an overlay across the WHOLE universe
- Thinker constellations: deep-dive a researcher's way of thinking
"""

import logging

from fastapi import APIRouter, HTTPException, Query

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("")
async def get_atlas(
    limit: int = Query(default=250, le=600),
    user_id: str | None = None,
):
    """The unified map: concepts across ALL fields with border detection.

    Returns nodes (concept + field_span + consensus), edges, and an
    optional per-user fog overlay. Border concepts have len(fields) >= 2.
    """
    try:
        from backend.integrations.supabase_client import get_client
        client = get_client()

        concepts = client.table("concepts").select(
            "id, name, type, paper_count, consensus_status, consensus_score, field_span"
        ).order("paper_count", desc=True).limit(limit).execute()
        nodes = concepts.data or []
        node_ids = {n["id"] for n in nodes}

        # Concept-concept edges within the visible set
        rels = client.table("relationships").select(
            "source_id, target_id, relationship_type, confidence"
        ).eq("source_type", "concept").eq("target_type", "concept").limit(5000).execute()
        edges = [
            r for r in (rels.data or [])
            if r["source_id"] in node_ids and r["target_id"] in node_ids
        ]

        # Fog overlay
        fog = {}
        if user_id:
            knowledge = client.table("user_knowledge").select(
                "concept_id, understanding_level"
            ).eq("user_id", user_id).limit(2000).execute()
            for k in (knowledge.data or []):
                lvl = k.get("understanding_level", 0)
                fog[k["concept_id"]] = (
                    "explored" if lvl > 0.3 else "in_progress" if lvl >= 0.1 else "unexplored"
                )

        # Field regions summary + borders
        field_counts: dict[str, int] = {}
        borders = []
        for n in nodes:
            span = n.get("field_span") or []
            for f in span:
                field_counts[f] = field_counts.get(f, 0) + 1
            if len(span) >= 2:
                borders.append({"id": n["id"], "name": n["name"], "fields": span})

        return {
            "nodes": [
                {**n, "is_border": len(n.get("field_span") or []) >= 2,
                 "fog": fog.get(n["id"], "unexplored") if user_id else None}
                for n in nodes
            ],
            "edges": edges,
            "regions": [{"field": f, "concepts": c} for f, c in
                        sorted(field_counts.items(), key=lambda kv: -kv[1])],
            "borders": borders[:50],
            "stats": {"nodes": len(nodes), "edges": len(edges), "border_concepts": len(borders)},
        }
    except Exception as e:
        logger.error(f"Atlas error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/spans/recompute")
async def recompute_field_spans(limit: int = Query(default=1000, le=5000)):
    """Recompute concepts.field_span from their papers' fields.

    Run after seeding. A concept whose papers span 2+ fields is a border
    concept — it sits on the seam between regions on the map.
    """
    try:
        from backend.integrations.supabase_client import get_client
        client = get_client()

        concepts = client.table("concepts").select("id").order(
            "paper_count", desc=True
        ).limit(limit).execute()

        updated = 0
        borders = 0
        for c in (concepts.data or []):
            pc = client.table("paper_concepts").select("paper_id").eq(
                "concept_id", c["id"]
            ).limit(50).execute()
            pids = [r["paper_id"] for r in (pc.data or [])]
            if not pids:
                continue

            fields: set[str] = set()
            for i in range(0, len(pids), 40):
                papers = client.table("papers").select("field").in_(
                    "id", pids[i:i + 40]
                ).not_.is_("field", "null").execute()
                for p in (papers.data or []):
                    if p.get("field"):
                        fields.add(p["field"])

            if fields:
                client.table("concepts").update(
                    {"field_span": sorted(fields)}
                ).eq("id", c["id"]).execute()
                updated += 1
                if len(fields) >= 2:
                    borders += 1

        return {"updated": updated, "border_concepts": borders}
    except Exception as e:
        logger.error(f"Field span recompute error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/thinker/{name}")
async def thinker_constellation(name: str):
    """Deep-dive a researcher: their constellation and way of thinking.

    Profile + credibility (author_investigator) + which of their works
    live in our graph + the concepts they shaped + what they built on.
    """
    try:
        from backend.agents.author_investigator import full_investigation
        investigation = await full_investigation(author_name=name)
        profile = investigation.get("profile", {})

        matched_papers = []
        shaped_concepts = []
        built_on = []

        openalex_id = profile.get("openalex_id")
        if openalex_id:
            # Their top works from OpenAlex (free, author-indexed)
            import os
            import httpx
            params = {
                "filter": f"authorships.author.id:A{openalex_id.lstrip('A')}",
                "sort": "cited_by_count:desc",
                "per_page": 25,
                "select": "id,title,publication_year,cited_by_count,doi",
            }
            email = os.getenv("OPENALEX_EMAIL")
            if email:
                params["mailto"] = email
            async with httpx.AsyncClient() as hclient:
                resp = await hclient.get("https://api.openalex.org/works", params=params, timeout=15)
                works = resp.json().get("results", []) if resp.status_code == 200 else []

            # Which of their works are in OUR graph?
            from backend.integrations.supabase_client import get_client
            client = get_client()
            oa_ids = [w["id"].split("/")[-1] for w in works]
            ours = []
            for i in range(0, len(oa_ids), 40):
                rows = client.table("papers").select("id, openalex_id, title").in_(
                    "openalex_id", oa_ids[i:i + 40]
                ).execute()
                ours.extend(rows.data or [])
            ours_by_oa = {p["openalex_id"]: p for p in ours}

            for w in works:
                oa = w["id"].split("/")[-1]
                matched_papers.append({
                    "title": w.get("title"),
                    "year": w.get("publication_year"),
                    "cited_by": w.get("cited_by_count", 0),
                    "in_graph": oa in ours_by_oa,
                    "paper_id": ours_by_oa.get(oa, {}).get("id"),
                })

            # Concepts they shaped (via their in-graph papers)
            in_graph_ids = [p["id"] for p in ours]
            concept_ids: set[str] = set()
            for i in range(0, len(in_graph_ids), 40):
                pc = client.table("paper_concepts").select("concept_id").in_(
                    "paper_id", in_graph_ids[i:i + 40]
                ).execute()
                for r in (pc.data or []):
                    concept_ids.add(r["concept_id"])
            cid_list = list(concept_ids)[:30]
            for i in range(0, len(cid_list), 40):
                rows = client.table("concepts").select(
                    "id, name, type, consensus_status, field_span"
                ).in_("id", cid_list[i:i + 40]).execute()
                shaped_concepts.extend(rows.data or [])

            # Who they build on: CITES targets of their in-graph papers
            if in_graph_ids:
                cites = client.table("relationships").select(
                    "target_id"
                ).eq("relationship_type", "CITES").in_(
                    "source_id", in_graph_ids[:40]
                ).limit(20).execute()
                tgt_ids = [c["target_id"] for c in (cites.data or [])]
                for i in range(0, len(tgt_ids), 40):
                    rows = client.table("papers").select("title, publication_year").in_(
                        "id", tgt_ids[i:i + 40]
                    ).execute()
                    built_on.extend(rows.data or [])

        return {
            "profile": profile,
            "credibility": investigation.get("credibility"),
            "retractions": investigation.get("retractions"),
            "works": matched_papers,
            "shaped_concepts": shaped_concepts,
            "builds_on": built_on[:15],
            "constellation_summary": {
                "works_found": len(matched_papers),
                "works_in_graph": sum(1 for p in matched_papers if p["in_graph"]),
                "concepts_shaped": len(shaped_concepts),
            },
        }
    except Exception as e:
        logger.error(f"Thinker constellation error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
