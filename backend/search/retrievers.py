"""Retriever functions — each returns a RetrievalResult, all run in parallel."""

import asyncio
import logging
from datetime import datetime

from backend.integrations import supabase_client as db
from backend.integrations.openalex_client import search_papers_by_keyword
from backend.core.context_builder import (
    get_library_context,
    get_highlight_context,
    get_reading_behavior_context,
    get_syllabus_context,
)
from backend.user.profile_builder import get_user_context_string
from backend.user.behavior_tracker import get_behavior_context_string
from backend.core.controversy_mapper import map_debate_landscape
from backend.search.embeddings import get_embedding
from backend.search.models import RetrievalItem, RetrievalResult

logger = logging.getLogger(__name__)


async def retrieve_semantic(sub_queries: list[str]) -> RetrievalResult:
    """Semantic retrieval: embed queries → pgvector search on concepts + claims."""
    items: list[RetrievalItem] = []
    seen_ids: set[str] = set()

    for query in sub_queries[:3]:  # max 3 sub-queries
        try:
            embedding = await get_embedding(query)

            # Search concepts
            concepts = await db.semantic_search_concepts(
                embedding, threshold=0.65, limit=8,
            )
            for c in concepts:
                cid = str(c["id"])
                if cid in seen_ids:
                    continue
                seen_ids.add(cid)
                items.append(RetrievalItem(
                    id=cid,
                    type="concept",
                    title=c.get("name", ""),
                    content=c.get("definition", "") or f"{c.get('name', '')} ({c.get('type', '')})",
                    score=c.get("similarity", 0.0),
                    metadata={
                        "concept_type": c.get("type"),
                        "confidence": c.get("confidence"),
                        "paper_count": c.get("paper_count"),
                        "trend": c.get("trend"),
                    },
                ))

            # Search claims
            claims = await db.semantic_search_claims(
                embedding, threshold=0.55, limit=5,
            )
            for cl in claims:
                clid = str(cl["id"])
                if clid in seen_ids:
                    continue
                seen_ids.add(clid)
                items.append(RetrievalItem(
                    id=clid,
                    type="claim",
                    title=cl.get("claim_text", "")[:80],
                    content=cl.get("claim_text", ""),
                    score=cl.get("similarity", 0.0),
                    metadata={
                        "paper_id": str(cl.get("paper_id", "")),
                        "evidence_type": cl.get("evidence_type"),
                        "strength": cl.get("strength"),
                        "confidence": cl.get("confidence"),
                    },
                ))
        except Exception as e:
            logger.warning(f"Semantic retrieval failed for query '{query}': {e}")

    # Sort by score descending
    items.sort(key=lambda x: x.score, reverse=True)
    return RetrievalResult(
        source="semantic",
        items=items[:15],
        token_estimate=sum(len(i.content) // 4 for i in items[:15]),
    )


async def retrieve_graph(concepts: list[str]) -> RetrievalResult:
    """Graph retrieval: ILIKE concept search → neighborhood + papers + claims."""
    items: list[RetrievalItem] = []
    seen_ids: set[str] = set()

    for concept_name in concepts[:5]:
        try:
            # Find matching concepts via ILIKE
            matches = await db.search_concepts(concept_name, limit=3)
            for concept in matches:
                cid = str(concept["id"])
                if cid in seen_ids:
                    continue
                seen_ids.add(cid)

                items.append(RetrievalItem(
                    id=cid,
                    type="concept",
                    title=concept.get("name", ""),
                    content=concept.get("definition", "") or concept.get("name", ""),
                    score=1.0,
                    metadata={
                        "concept_type": concept.get("type"),
                        "confidence": concept.get("confidence"),
                        "paper_count": concept.get("paper_count"),
                    },
                ))

                # Get neighborhood (depth 1)
                neighbors = await db.get_concept_neighborhood(cid, depth=1)
                if neighbors:
                    for n in neighbors[:5]:
                        nid = str(n.get("concept_id", ""))
                        if nid and nid not in seen_ids:
                            seen_ids.add(nid)
                            items.append(RetrievalItem(
                                id=nid,
                                type="concept",
                                title=n.get("concept_name", ""),
                                content=(
                                    f"{n.get('concept_name', '')} ({n.get('concept_type', '')}): "
                                    f"{n.get('concept_definition', '') or ''} "
                                    f"[{n.get('relationship_type', '')} — {n.get('relationship_explanation', '') or ''}]"
                                ),
                                score=n.get("relationship_confidence", 0.5),
                                metadata={
                                    "relationship_type": n.get("relationship_type"),
                                    "depth": n.get("depth", 1),
                                },
                            ))

                # Get papers for this concept
                papers = await db.get_papers_for_concept(cid, limit=3)
                paper_ids = []
                for p in papers:
                    pid = str(p["id"])
                    if pid not in seen_ids:
                        seen_ids.add(pid)
                        paper_ids.append(pid)
                        authors_str = ", ".join(
                            a.get("name", "") for a in (p.get("authors") or [])[:3]
                        )
                        items.append(RetrievalItem(
                            id=pid,
                            type="paper",
                            title=p.get("title", ""),
                            content=(
                                f"{p.get('title', '')} ({p.get('publication_year', '')}) "
                                f"by {authors_str}. "
                                f"Citations: {p.get('cited_by_count', 0)}."
                            ),
                            score=p.get("relevance", 0.5),
                            metadata={
                                "publication_year": p.get("publication_year"),
                                "cited_by_count": p.get("cited_by_count"),
                                "doi": p.get("doi"),
                            },
                        ))

                # Get claims for those papers
                if paper_ids:
                    claims = await db.get_claims_for_papers(paper_ids, limit=5)
                    for cl in claims:
                        clid = str(cl["id"])
                        if clid not in seen_ids:
                            seen_ids.add(clid)
                            items.append(RetrievalItem(
                                id=clid,
                                type="claim",
                                title=cl.get("claim_text", "")[:80],
                                content=cl.get("claim_text", ""),
                                score=cl.get("confidence", 0.5),
                                metadata={
                                    "evidence_type": cl.get("evidence_type"),
                                    "strength": cl.get("strength"),
                                },
                            ))
        except Exception as e:
            logger.warning(f"Graph retrieval failed for concept '{concept_name}': {e}")

    return RetrievalResult(
        source="graph",
        items=items[:20],
        token_estimate=sum(len(i.content) // 4 for i in items[:20]),
    )


async def retrieve_citations(concepts: list[str], requires_recency: bool = False) -> RetrievalResult:
    """Citation retrieval: OpenAlex keyword search for relevant papers."""
    items: list[RetrievalItem] = []
    seen_titles: set[str] = set()

    from_year = datetime.now().year - 2 if requires_recency else None

    for concept in concepts[:3]:
        try:
            papers = await search_papers_by_keyword(
                keyword=concept, from_year=from_year, limit=5,
            )
            for p in papers:
                title = p.get("title", "")
                if title.lower() in seen_titles:
                    continue
                seen_titles.add(title.lower())

                authors_str = ", ".join(
                    a.get("name", "") for a in (p.get("authors") or [])[:3]
                )
                items.append(RetrievalItem(
                    id=p.get("openalex_id", ""),
                    type="paper",
                    title=title,
                    content=(
                        f"{title} ({p.get('publication_year', '')}) by {authors_str}. "
                        f"Citations: {p.get('cited_by_count', 0)}. "
                        f"Abstract: {(p.get('abstract', '') or '')[:300]}"
                    ),
                    score=0.7,  # OpenAlex relevance not directly available
                    metadata={
                        "openalex_id": p.get("openalex_id"),
                        "publication_year": p.get("publication_year"),
                        "cited_by_count": p.get("cited_by_count"),
                        "doi": p.get("doi"),
                        "source": "openalex",
                    },
                ))
            # Rate-limit politeness: small pause between concept searches
            await asyncio.sleep(0.2)
        except Exception as e:
            logger.warning(f"Citation retrieval failed for '{concept}': {e}")

    items.sort(key=lambda x: x.metadata.get("cited_by_count", 0), reverse=True)
    return RetrievalResult(
        source="citation",
        items=items[:10],
        token_estimate=sum(len(i.content) // 4 for i in items[:10]),
    )


async def retrieve_user_context(user_id: str) -> RetrievalResult:
    """User context retrieval: bundle all 6 user context layers into one result."""
    if not user_id:
        return RetrievalResult(source="user", items=[], token_estimate=0)

    context_parts = []
    try:
        # Layer 1: Knowledge profile
        profile = await get_user_context_string(user_id)
        if profile:
            context_parts.append(f"Knowledge Profile:\n{profile}")

        # Layer 3a: Behavioral patterns
        behavior = await get_behavior_context_string(user_id)
        if behavior:
            context_parts.append(f"Behavioral Patterns:\n{behavior}")

        # Library context
        library = await get_library_context(user_id)
        if library:
            context_parts.append(f"Library:\n{library}")

        # Highlights
        highlights = await get_highlight_context(user_id)
        if highlights:
            context_parts.append(f"Highlights:\n{highlights}")

        # Reading behavior
        reading = await get_reading_behavior_context(user_id)
        if reading:
            context_parts.append(f"Reading Focus:\n{reading}")

        # Syllabus progress
        syllabus = await get_syllabus_context(user_id)
        if syllabus:
            context_parts.append(f"Curriculum:\n{syllabus}")
    except Exception as e:
        logger.warning(f"User context retrieval failed: {e}")

    combined = "\n\n".join(context_parts)
    items = []
    if combined:
        items.append(RetrievalItem(
            id=f"user-{user_id}",
            type="user_note",
            title="User Context",
            content=combined,
            score=1.0,
        ))

    return RetrievalResult(
        source="user",
        items=items,
        token_estimate=len(combined) // 4,
    )


async def retrieve_controversies(concepts: list[str]) -> RetrievalResult:
    """Controversy retrieval: search debates related to query concepts."""
    items: list[RetrievalItem] = []
    seen_ids: set[str] = set()

    for concept in concepts[:3]:
        try:
            # Direct controversy search
            controversies = await db.search_controversies(concept, limit=3)
            for c in controversies:
                cid = str(c["id"])
                if cid in seen_ids:
                    continue
                seen_ids.add(cid)
                sides_str = ""
                if c.get("sides"):
                    sides_str = " vs ".join(
                        s.get("label", "") for s in c["sides"][:3]
                    )
                items.append(RetrievalItem(
                    id=cid,
                    type="controversy",
                    title=c.get("title", ""),
                    content=(
                        f"{c.get('title', '')}: {c.get('description', '')} "
                        f"Sides: {sides_str}. Status: {c.get('status', 'unknown')}."
                    ),
                    score=c.get("intensity", 0.5),
                    metadata={
                        "status": c.get("status"),
                        "intensity": c.get("intensity"),
                    },
                ))

            # Debate landscape mapping
            landscape = await map_debate_landscape(concept)
            if landscape and landscape.get("contradicting_pairs"):
                for pair in landscape["contradicting_pairs"][:3]:
                    items.append(RetrievalItem(
                        id=str(pair.get("id", "")),
                        type="controversy",
                        title=f"Contradiction: {pair.get('explanation', '')[:60]}",
                        content=(
                            f"Contradiction between concepts: {pair.get('explanation', '')}. "
                            f"Confidence: {pair.get('confidence', 'unknown')}."
                        ),
                        score=0.6,
                    ))
        except Exception as e:
            logger.warning(f"Controversy retrieval failed for '{concept}': {e}")

    return RetrievalResult(
        source="controversy",
        items=items[:8],
        token_estimate=sum(len(i.content) // 4 for i in items[:8]),
    )
