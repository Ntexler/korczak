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
