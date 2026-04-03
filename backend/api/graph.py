"""Knowledge Graph API endpoints."""

from fastapi import APIRouter, Query
from pydantic import BaseModel

router = APIRouter()


class ConceptOut(BaseModel):
    id: str
    name: str
    type: str
    definition: str | None = None
    paper_count: int = 0
    trend: str = "stable"
    confidence: float = 0.5


class GraphNeighbors(BaseModel):
    concept: ConceptOut
    related: list[dict] = []
    # [{concept, relationship_type, confidence}]


@router.get("/concepts", response_model=list[ConceptOut])
async def list_concepts(
    search: str | None = None,
    type: str | None = None,
    trend: str | None = None,
    limit: int = Query(default=20, le=100),
    offset: int = 0,
):
    """Search/list concepts in the knowledge graph."""
    # TODO: Wire to Supabase
    return []


@router.get("/concepts/{concept_id}", response_model=ConceptOut)
async def get_concept(concept_id: str):
    """Get a single concept with its details."""
    # TODO: Wire to Supabase
    return ConceptOut(id=concept_id, name="placeholder", type="concept")


@router.get("/concepts/{concept_id}/neighbors", response_model=GraphNeighbors)
async def get_neighbors(concept_id: str, depth: int = Query(default=1, le=3)):
    """Get neighboring concepts in the graph."""
    # TODO: Wire to Supabase with recursive CTE
    return GraphNeighbors(
        concept=ConceptOut(id=concept_id, name="placeholder", type="concept"),
    )


@router.get("/stats")
async def graph_stats():
    """Get knowledge graph statistics."""
    # TODO: Wire to Supabase
    return {
        "total_papers": 0,
        "total_concepts": 0,
        "total_relationships": 0,
        "total_claims": 0,
        "total_entities": 0,
    }
