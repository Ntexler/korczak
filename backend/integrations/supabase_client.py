"""Supabase client wrapper for Knowledge Graph operations."""

from supabase import create_client, Client

from backend.config import settings

_client: Client | None = None


def get_client() -> Client:
    """Get or create Supabase client (singleton)."""
    global _client
    if _client is None:
        _client = create_client(settings.supabase_url, settings.supabase_service_key)
    return _client


# -- Papers --

async def insert_paper(paper: dict) -> dict:
    """Insert a paper into the database."""
    client = get_client()
    result = client.table("papers").insert(paper).execute()
    return result.data[0]


async def get_paper_by_openalex_id(openalex_id: str) -> dict | None:
    """Check if a paper already exists."""
    client = get_client()
    result = client.table("papers").select("*").eq("openalex_id", openalex_id).execute()
    return result.data[0] if result.data else None


# -- Concepts --

async def upsert_concept(concept: dict) -> dict:
    """Insert or update a concept."""
    client = get_client()
    result = client.table("concepts").upsert(
        concept, on_conflict="normalized_name"
    ).execute()
    return result.data[0]


async def search_concepts(query: str, limit: int = 20) -> list[dict]:
    """Search concepts by name."""
    client = get_client()
    result = (
        client.table("concepts")
        .select("*")
        .ilike("name", f"%{query}%")
        .limit(limit)
        .execute()
    )
    return result.data


async def find_similar_concepts(embedding: list[float], threshold: float = 0.9, limit: int = 5) -> list[dict]:
    """Find concepts with similar embeddings (for entity resolution)."""
    client = get_client()
    result = client.rpc(
        "match_concepts",
        {"query_embedding": embedding, "match_threshold": threshold, "match_count": limit},
    ).execute()
    return result.data


# -- Relationships --

async def insert_relationship(rel: dict) -> dict:
    """Insert a relationship between graph nodes."""
    client = get_client()
    result = client.table("relationships").insert(rel).execute()
    return result.data[0]


# -- Graph queries --

async def get_concept_neighborhood(concept_id: str, depth: int = 1) -> dict:
    """Get concept and its neighbors using recursive query."""
    client = get_client()
    # For depth > 1, use RPC with recursive CTE
    result = client.rpc(
        "get_concept_neighborhood",
        {"p_concept_id": concept_id, "p_depth": depth},
    ).execute()
    return result.data


async def get_graph_stats() -> dict:
    """Get counts of all graph node types."""
    client = get_client()
    papers = client.table("papers").select("id", count="exact").execute()
    concepts = client.table("concepts").select("id", count="exact").execute()
    relationships = client.table("relationships").select("id", count="exact").execute()
    claims = client.table("claims").select("id", count="exact").execute()
    entities = client.table("entities").select("id", count="exact").execute()
    return {
        "total_papers": papers.count or 0,
        "total_concepts": concepts.count or 0,
        "total_relationships": relationships.count or 0,
        "total_claims": claims.count or 0,
        "total_entities": entities.count or 0,
    }


# -- Navigator helpers --

async def get_concept_by_id(concept_id: str) -> dict | None:
    """Get a single concept by ID."""
    client = get_client()
    result = client.table("concepts").select("*").eq("id", concept_id).execute()
    return result.data[0] if result.data else None


async def get_papers_for_concept(concept_id: str, limit: int = 5) -> list[dict]:
    """Get papers linked to a concept via paper_concepts join."""
    client = get_client()
    result = (
        client.table("paper_concepts")
        .select("paper_id, relevance, papers(id, title, authors, publication_year, cited_by_count, abstract, doi, openalex_id)")
        .eq("concept_id", concept_id)
        .order("relevance", desc=True)
        .limit(limit)
        .execute()
    )
    papers = []
    for row in result.data:
        paper = row.get("papers")
        if paper:
            paper["relevance"] = row.get("relevance")
            papers.append(paper)
    return papers


async def get_claims_for_papers(paper_ids: list[str], limit: int = 10) -> list[dict]:
    """Get claims by paper IDs (batched to avoid Supabase URL limits)."""
    if not paper_ids:
        return []
    client = get_client()
    all_claims = []
    for i in range(0, len(paper_ids), 30):
        batch = paper_ids[i:i + 30]
        result = (
            client.table("claims")
            .select(
                # Feature 6.5: include provenance fields (usually NULL until
                # on-demand extractor runs; UI renders them gracefully).
                "id, paper_id, claim_text, evidence_type, strength, confidence, "
                "verbatim_quote, quote_location, claim_category, examples, "
                "provenance_extracted_at"
            )
            .in_("paper_id", batch)
            .order("confidence", desc=True)
            .limit(limit)
            .execute()
        )
        all_claims.extend(result.data or [])
    all_claims.sort(key=lambda c: c.get("confidence", 0), reverse=True)
    return all_claims[:limit]


async def search_controversies(keyword: str, limit: int = 3) -> list[dict]:
    """Search controversies by keyword ILIKE on title."""
    client = get_client()
    result = (
        client.table("controversies")
        .select("*")
        .ilike("title", f"%{keyword}%")
        .limit(limit)
        .execute()
    )
    return result.data


async def list_concepts(
    search: str | None = None,
    type_filter: str | None = None,
    trend_filter: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> list[dict]:
    """List/search concepts with optional filters."""
    client = get_client()
    query = client.table("concepts").select("id, name, type, definition, paper_count, trend, confidence")
    if search:
        query = query.ilike("name", f"%{search}%")
    if type_filter:
        query = query.eq("type", type_filter)
    if trend_filter:
        query = query.eq("trend", trend_filter)
    query = query.order("paper_count", desc=True).range(offset, offset + limit - 1)
    result = query.execute()
    return result.data


# -- Search pipeline helpers --

async def semantic_search_concepts(query_embedding: list[float], threshold: float = 0.7, limit: int = 10) -> list[dict]:
    """Semantic search on concepts via pgvector embedding similarity."""
    client = get_client()
    result = client.rpc(
        "search_concepts_by_embedding",
        {"query_embedding": query_embedding, "match_threshold": threshold, "match_count": limit},
    ).execute()
    return result.data


async def semantic_search_claims(query_embedding: list[float], threshold: float = 0.6, limit: int = 10) -> list[dict]:
    """Semantic search on claims via pgvector embedding similarity."""
    client = get_client()
    result = client.rpc(
        "search_claims_by_embedding",
        {"query_embedding": query_embedding, "match_threshold": threshold, "match_count": limit},
    ).execute()
    return result.data


async def fulltext_search_papers(query: str, limit: int = 10) -> list[dict]:
    """Full-text search on papers using tsvector + websearch_to_tsquery."""
    client = get_client()
    result = client.rpc(
        "fulltext_search_papers",
        {"search_query": query, "match_count": limit},
    ).execute()
    return result.data


async def create_conversation(mode: str = "navigator", user_id: str | None = None) -> dict:
    """Create a new conversation."""
    client = get_client()
    data = {"mode": mode}
    if user_id:
        data["user_id"] = user_id
    result = client.table("conversations").insert(data).execute()
    return result.data[0]


async def save_message(
    conversation_id: str,
    role: str,
    content: str,
    graph_context: dict | None = None,
    concepts_referenced: list | None = None,
) -> dict:
    """Save a message to a conversation."""
    client = get_client()
    data = {
        "conversation_id": conversation_id,
        "role": role,
        "content": content,
    }
    if graph_context:
        data["graph_context"] = graph_context
    if concepts_referenced:
        data["concepts_referenced"] = concepts_referenced
    result = client.table("messages").insert(data).execute()
    return result.data[0]


async def get_conversation_messages(conversation_id: str, limit: int = 50) -> list[dict]:
    """Get messages for a conversation."""
    client = get_client()
    result = (
        client.table("messages")
        .select("id, role, content, concepts_referenced, created_at")
        .eq("conversation_id", conversation_id)
        .order("created_at", desc=False)
        .limit(limit)
        .execute()
    )
    return result.data
