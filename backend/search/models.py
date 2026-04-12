"""Pydantic models for search pipeline stages."""

from enum import Enum
from pydantic import BaseModel, Field


class QueryIntent(str, Enum):
    FACTUAL = "factual"
    COMPARISON = "comparison"
    CONTROVERSY = "controversy"
    EXPLORATION = "exploration"


class QueryAnalysis(BaseModel):
    """Output of Stage 1: Query Analysis."""
    intent: QueryIntent = QueryIntent.FACTUAL
    concepts: list[str] = Field(default_factory=list)
    sub_queries: list[str] = Field(default_factory=list, max_length=4)
    requires_recency: bool = False
    requires_controversy: bool = False


class RetrievalItem(BaseModel):
    """Single retrieved chunk from any retriever."""
    id: str
    type: str  # concept, paper, claim, controversy, user_note
    title: str
    content: str
    score: float = 0.0
    metadata: dict = Field(default_factory=dict)


class RetrievalResult(BaseModel):
    """Output of a single retriever."""
    source: str  # semantic, graph, citation, user, controversy
    items: list[RetrievalItem] = Field(default_factory=list)
    token_estimate: int = 0


class RetrievalBundle(BaseModel):
    """Combined output of all retrievers for synthesis."""
    results: list[RetrievalResult] = Field(default_factory=list)
    user_context: str = ""
    level_description: str = ""
    mode: str = "navigator"
    socratic_level: int = 0
    total_items: int = 0
    source_count: int = 0

    def all_items(self) -> list[RetrievalItem]:
        items = []
        for r in self.results:
            items.extend(r.items)
        return items

    def format_for_prompt(self, max_chars: int = 14000) -> str:
        """Format all retrieved items into a context string for Claude."""
        sections = []
        for result in self.results:
            if not result.items:
                continue
            section_lines = [f"=== Source: {result.source.upper()} ==="]
            for item in result.items:
                section_lines.append(
                    f"[{item.id}] ({item.type}) {item.title}\n{item.content}"
                )
            sections.append("\n".join(section_lines))

        text = "\n\n".join(sections)
        if len(text) > max_chars:
            text = text[:max_chars] + "\n... (truncated)"
        return text


class CoverageVerdict(BaseModel):
    """Output of Stage 3: Coverage Check."""
    complete: bool = True
    missing_aspects: list[str] = Field(default_factory=list)
    retry_queries: list[str] = Field(default_factory=list)
    attempt: int = 0


class SourceCitation(BaseModel):
    """A cited source in the synthesis."""
    id: str
    title: str
    type: str


class SynthesisOutput(BaseModel):
    """Output of Stage 4: Synthesis."""
    response_text: str
    sources_cited: list[SourceCitation] = Field(default_factory=list)
    confidence: float = 0.8
    knowledge_gaps: list[str] = Field(default_factory=list)
    token_count: int = 0


class SkepticIssue(BaseModel):
    """A single issue found by the skeptic."""
    type: str  # missing_perspective, overconfident, source_bias, scope_creep
    detail: str


class SkepticVerdict(BaseModel):
    """Output of Stage 5: Skeptic Review."""
    approved: bool = True
    issues: list[SkepticIssue] = Field(default_factory=list)
    suggested_additions: list[str] = Field(default_factory=list)
    confidence_adjustment: float = 0.0  # negative = lower confidence
    token_count: int = 0


class TokenUsage(BaseModel):
    """Aggregated token usage across all stages."""
    query_analysis: int = 0
    coverage_check: int = 0
    synthesis: int = 0
    skeptic_review: int = 0
    total: int = 0


class PipelineResult(BaseModel):
    """Final output of the search pipeline."""
    response_text: str
    concepts_referenced: list[dict] = Field(default_factory=list)
    sources_cited: list[dict] = Field(default_factory=list)
    insight: dict | None = None
    mode: str = "navigator"
    confidence: float = 0.8
    knowledge_gaps: list[str] = Field(default_factory=list)
    skeptic_warnings: list[str] = Field(default_factory=list)
    token_usage: TokenUsage = Field(default_factory=TokenUsage)
    stages_completed: list[str] = Field(default_factory=list)
    used_fallback: bool = False
