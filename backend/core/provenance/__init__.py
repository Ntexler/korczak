"""On-demand provenance extraction for claims (Feature 6.5, Stage C).

Entry point:
    from backend.core.provenance import extract_claim_provenance

    result = await extract_claim_provenance(claim_id)

The extractor runs multiple sources in parallel (full-text cache,
Unpaywall, Semantic Scholar, CORE, arXiv), aggregates candidate
passages with a single Claude call, and persists the winning quote +
examples + category to the `claims` row. Subsequent calls return the
cached result for free (no network, no Claude tokens).
"""

from backend.core.provenance.extractor import extract_claim_provenance

__all__ = ["extract_claim_provenance"]
