"""Aggregate candidate passages from multiple sources into a final provenance record.

A single Claude call receives (claim text, title, year, and a labelled list
of candidate passages from each source) and picks the best verbatim quote,
assigns a category, and extracts examples. This is the one LLM call in the
entire extraction flow — everything else is deterministic.
"""

import logging

from backend.integrations.claude_client import _call_claude, _parse_json_response
from backend.core.provenance.types import ExtractionContext, ExtractionResult, SourceResult


logger = logging.getLogger(__name__)

_MODEL = "claude-haiku-4-5-20251001"  # Cheap + fast; the task is focused.


_AGGREGATOR_PROMPT = """You are helping to ground a specific claim from an academic paper in verbatim source material. You have candidate passages from multiple sources; pick the best evidence for the claim.

PAPER TITLE: {title}
PAPER YEAR: {year}
CLAIM: {claim}

CANDIDATE PASSAGES (from multiple sources, each labelled):
{candidates}

Return ONLY valid JSON with these fields:
{{
  "verbatim_quote": str | null,     // The single best supporting passage, quoted verbatim (max ~300 chars). Use null if no candidate passage actually supports the claim.
  "quote_source": str | null,       // Which source the chosen quote came from: "full_text" | "unpaywall" | "semantic_scholar" | "core" | "arxiv" | null. Use null when verbatim_quote is null.
  "quote_location": str | null,     // A location hint for the quote (e.g., "Results, para 3", "Citation context from influential citing paper", "CORE abstract", "arXiv abstract"). Use null when verbatim_quote is null.
  "claim_category": "main" | "supporting" | "background" | "limitation" | null,
  "examples": [                      // Concrete examples the paper uses to illustrate or test this specific claim, if surfaced in the candidate passages. Empty list when none apparent.
    {{"text": str, "kind": "case|dataset|figure|table", "location": str | null}}
  ],
  "notes": str                       // Short (<= 2 sentences) rationale — why you chose this quote, or why none fit.
}}

Rules:
- NEVER paraphrase. `verbatim_quote` must be a literal substring of one of the candidate passages.
- Prefer passages from the paper itself (`full_text`) over citation contexts from other papers.
- If the only supporting text is a citation-context from another paper, you MAY still use it, but say so in `quote_location` (e.g., "Paraphrased in a citing paper — see Semantic Scholar citation context") and acknowledge the limitation in `notes`.
- `claim_category`:
    - "main" = primary finding / central contribution of the paper
    - "supporting" = secondary evidence or sub-claim
    - "background" = prior-literature claim the author is restating
    - "limitation" = acknowledged caveat
    - null = insufficient evidence to categorize
- If NO candidate passage actually supports the claim, return verbatim_quote=null, quote_source=null, quote_location=null, and explain in `notes`."""


def _format_candidates(results: list[SourceResult]) -> str:
    blocks = []
    for r in results:
        if r.status != "hit" or not r.passages:
            continue
        for idx, passage in enumerate(r.passages):
            hint = ""
            if idx < len(r.location_hints) and r.location_hints[idx]:
                hint = f" [hint: {r.location_hints[idx]}]"
            blocks.append(f"--- Source: {r.source}{hint} ---\n{passage.strip()}")
    if not blocks:
        return "(no candidate passages from any source)"
    return "\n\n".join(blocks)


def _summarize_sources(results: list[SourceResult], chosen_quote: str | None, chosen_source: str | None) -> list[dict]:
    """Build the `provenance_sources` JSONB array for the claims row."""
    out = []
    for r in results:
        entry: dict = {
            "source": r.source,
            "status": r.status,
        }
        if r.error:
            entry["error"] = r.error
        if r.url:
            entry["url"] = r.url
        if r.extra:
            entry["extra"] = r.extra
        # Record what passage (if any) this source provided that got chosen.
        if chosen_quote and chosen_source == r.source:
            entry["quote"] = chosen_quote
        elif r.passages:
            # First candidate as a preview so the UI can show secondary options.
            first = r.passages[0]
            entry["preview"] = first[:200] + ("…" if len(first) > 200 else "")
        out.append(entry)
    return out


async def aggregate(
    ctx: ExtractionContext,
    source_results: list[SourceResult],
    year: int | None,
) -> dict:
    """Run the Claude aggregator. Returns a dict with keys:
        verbatim_quote, quote_source, quote_location, claim_category,
        examples, provenance_sources
    Never raises — on Claude error, returns a result with verbatim_quote=None
    and the error recorded in provenance_sources.
    """
    prompt = _AGGREGATOR_PROMPT.format(
        title=ctx.title or "(untitled)",
        year=year if year is not None else "(unknown)",
        claim=ctx.claim_text,
        candidates=_format_candidates(source_results),
    )

    try:
        response = await _call_claude(prompt, model=_MODEL, max_tokens=800, temperature=0.1)
    except Exception as e:
        logger.warning(f"Aggregator Claude call failed for claim {ctx.claim_id}: {e}")
        return {
            "verbatim_quote": None,
            "quote_source": None,
            "quote_location": None,
            "claim_category": None,
            "examples": [],
            "provenance_sources": _summarize_sources(source_results, None, None) + [
                {"source": "aggregator", "status": "error", "error": str(e)}
            ],
        }

    parsed = _parse_json_response(response.text)

    # Validate the aggregator output defensively.
    quote = parsed.get("verbatim_quote") if isinstance(parsed, dict) else None
    quote_source = parsed.get("quote_source") if isinstance(parsed, dict) else None
    quote_location = parsed.get("quote_location") if isinstance(parsed, dict) else None
    category = parsed.get("claim_category") if isinstance(parsed, dict) else None
    if category not in ("main", "supporting", "background", "limitation"):
        category = None
    examples = parsed.get("examples") or [] if isinstance(parsed, dict) else []
    if not isinstance(examples, list):
        examples = []

    return {
        "verbatim_quote": quote,
        "quote_source": quote_source,
        "quote_location": quote_location,
        "claim_category": category,
        "examples": examples,
        "provenance_sources": _summarize_sources(source_results, quote, quote_source),
    }
