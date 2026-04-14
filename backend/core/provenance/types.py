"""Shared data types for the provenance extractor."""

from dataclasses import dataclass, field
from typing import Literal


SourceName = Literal["full_text", "unpaywall", "semantic_scholar", "core", "arxiv"]

Status = Literal["hit", "miss", "error", "skipped"]


@dataclass
class ExtractionContext:
    """Input bundle passed to every source."""
    claim_id: str
    claim_text: str
    paper_id: str
    doi: str | None
    title: str
    full_text: str | None
    full_text_source: str | None


@dataclass
class SourceResult:
    """What a single source returns to the aggregator."""
    source: SourceName
    status: Status
    # `passages`: candidate verbatim passages the source believes are relevant.
    # Aggregator (Claude) picks the best one and decides the authoritative quote.
    passages: list[str] = field(default_factory=list)
    # `location_hint`: optional structured location (e.g., "section 3.2") for
    # a passage, aligned by index with `passages`.
    location_hints: list[str | None] = field(default_factory=list)
    # `url`: where the reader can verify — open-access PDF, citation-context
    # page, arXiv listing, etc.
    url: str | None = None
    error: str | None = None
    # Metadata returned by the source that the aggregator or UI may use.
    extra: dict = field(default_factory=dict)


@dataclass
class ExtractionResult:
    """Final result persisted to the `claims` row."""
    claim_id: str
    verbatim_quote: str | None
    quote_location: str | None
    claim_category: str | None  # 'main' | 'supporting' | 'background' | 'limitation' | None
    examples: list[dict]
    provenance_sources: list[dict]  # One entry per source that was attempted
    extracted_at: str  # ISO timestamp
    cached: bool = False
