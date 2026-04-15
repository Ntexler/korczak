"""Shared helper for building claim insertion rows.

All seeder pipelines (seed_optimized, seed_deep, seed_foreign, seed_citations,
seed_from_training, seed_gutenberg, mark_canonical_foreign) call this so that
the set of fields persisted on `claims` stays consistent — in particular, the
Feature 6.5 provenance fields (migration 024) are included whenever Claude
provides them, and silently omitted when it does not.

Expected shape of `claim_dict` from Claude's analysis output:
  {
    "claim": str,                                   # required
    "evidence_type": str | None,
    "strength": "strong" | "moderate" | "weak",
    "testable": bool,

    # v3 / Feature 6.5 additions — all optional:
    "category": "main" | "supporting" | "background" | "limitation",
    "verbatim_quote": str,
    "quote_location": str,
    "examples": [{"text": str, "kind": str, "location": str}, ...],
  }
"""

from typing import Any


_ALLOWED_CATEGORIES = {"main", "supporting", "background", "limitation"}


def build_claim_row(
    paper_id: str,
    claim_dict: dict,
    *,
    default_strength: str = "moderate",
    claim_text_override: str | None = None,
) -> dict[str, Any]:
    """Assemble a `claims` table row from a Claude analysis claim dict.

    `claim_text_override` lets callers (e.g. seed_deep, seed_foreign) that
    normalize the claim text beforehand pass the normalized value. If omitted,
    the raw `claim_dict["claim"]` is used.
    """
    row: dict[str, Any] = {
        "paper_id": paper_id,
        "claim_text": claim_text_override if claim_text_override is not None else claim_dict["claim"],
        "evidence_type": claim_dict.get("evidence_type"),
        "strength": claim_dict.get("strength", default_strength),
        "testable": claim_dict.get("testable", False),
    }

    category = claim_dict.get("category")
    if category in _ALLOWED_CATEGORIES:
        row["claim_category"] = category

    quote = claim_dict.get("verbatim_quote")
    if quote:
        row["verbatim_quote"] = quote

    location = claim_dict.get("quote_location")
    if location:
        row["quote_location"] = location

    examples = claim_dict.get("examples") or []
    if examples:
        row["examples"] = examples

    return row
