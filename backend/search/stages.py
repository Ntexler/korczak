"""Pipeline stages — Claude-calling functions for analysis, coverage, synthesis, skeptic."""

import json
import logging

from backend.config import settings
from backend.integrations.claude_client import _call_claude, _parse_json_response
from backend.search.models import (
    QueryAnalysis,
    QueryIntent,
    RetrievalBundle,
    CoverageVerdict,
    SynthesisOutput,
    SourceCitation,
    SkepticVerdict,
    SkepticIssue,
)
from backend.search.prompts import (
    QUERY_ANALYSIS_PROMPT,
    COVERAGE_CHECK_PROMPT,
    SYNTHESIS_NAVIGATOR_PROMPT,
    SYNTHESIS_TUTOR_PROMPT,
    SYNTHESIS_BRIEFING_PROMPT,
    SKEPTIC_REVIEW_PROMPT,
)

logger = logging.getLogger(__name__)


async def analyze_query(
    query: str,
    history: list[dict] | None = None,
) -> tuple[QueryAnalysis, int]:
    """Stage 1: Analyze query intent, extract concepts, generate sub-queries.
    Returns (QueryAnalysis, total_tokens).
    """
    history_text = ""
    if history:
        history_text = "\n".join(
            f"{m['role']}: {m['content'][:200]}" for m in history[-6:]
        )

    prompt = QUERY_ANALYSIS_PROMPT.format(
        history=history_text or "(no prior conversation)",
        query=query,
    )

    response = await _call_claude(
        prompt,
        model=settings.haiku_model,
        max_tokens=500,
        temperature=0.1,
    )

    parsed = _parse_json_response(response.text)
    if parsed.get("parse_error"):
        logger.warning(f"Query analysis parse failed, using defaults: {response.text[:200]}")
        return QueryAnalysis(
            intent=QueryIntent.FACTUAL,
            concepts=[query],
            sub_queries=[query],
        ), response.total_tokens

    # Map intent string to enum
    intent_map = {
        "factual": QueryIntent.FACTUAL,
        "comparison": QueryIntent.COMPARISON,
        "controversy": QueryIntent.CONTROVERSY,
        "exploration": QueryIntent.EXPLORATION,
    }

    analysis = QueryAnalysis(
        intent=intent_map.get(parsed.get("intent", ""), QueryIntent.FACTUAL),
        concepts=parsed.get("concepts", [query])[:6],
        sub_queries=parsed.get("sub_queries", [query])[:4],
        requires_recency=parsed.get("requires_recency", False),
        requires_controversy=parsed.get("requires_controversy", False),
    )

    return analysis, response.total_tokens


async def check_coverage(
    query: str,
    bundle: RetrievalBundle,
) -> tuple[CoverageVerdict, int]:
    """Stage 3: Check if retrieval covers the query adequately.
    Returns (CoverageVerdict, total_tokens).
    """
    # Build summary of what was retrieved
    source_names = [r.source for r in bundle.results if r.items]
    item_types = {}
    for r in bundle.results:
        for item in r.items:
            item_types[item.type] = item_types.get(item.type, 0) + 1

    summary_lines = []
    for r in bundle.results:
        if r.items:
            top_titles = [i.title[:60] for i in r.items[:5]]
            summary_lines.append(f"- {r.source}: {len(r.items)} items — {', '.join(top_titles)}")

    prompt = COVERAGE_CHECK_PROMPT.format(
        query=query,
        item_count=bundle.total_items,
        source_count=bundle.source_count,
        retrieval_summary="\n".join(summary_lines) or "(no items retrieved)",
    )

    response = await _call_claude(
        prompt,
        model=settings.haiku_model,
        max_tokens=300,
        temperature=0.0,
    )

    parsed = _parse_json_response(response.text)
    if parsed.get("parse_error"):
        return CoverageVerdict(complete=True), response.total_tokens

    return CoverageVerdict(
        complete=parsed.get("complete", True),
        missing_aspects=parsed.get("missing_aspects", []),
        retry_queries=parsed.get("retry_queries", [])[:2],
    ), response.total_tokens


def _pick_synthesis_model(intent: QueryIntent) -> str:
    """Smart routing: Haiku for simple factual queries, Sonnet for complex ones."""
    if intent in (QueryIntent.CONTROVERSY, QueryIntent.COMPARISON):
        return settings.sonnet_model
    return settings.haiku_model


async def synthesize(
    query: str,
    bundle: RetrievalBundle,
    locale: str = "en",
    skeptic_feedback: str | None = None,
    intent: QueryIntent = QueryIntent.FACTUAL,
    teaching_context: str | None = None,
) -> tuple[SynthesisOutput, int]:
    """Stage 4: Synthesize retrieved knowledge into a coherent response.
    Returns (SynthesisOutput, total_tokens).
    Uses Haiku for factual/exploration queries, Sonnet for comparison/controversy.
    Optionally includes pedagogical teaching instructions.
    """
    language_instruction = (
        "Respond in Hebrew. Use Hebrew for all text except technical/academic terms."
        if locale == "he"
        else "Respond in English."
    )

    retrieval_context = bundle.format_for_prompt(max_chars=12000)

    # Select mode-appropriate prompt
    if bundle.mode == "tutor":
        prompt_template = SYNTHESIS_TUTOR_PROMPT
        prompt = prompt_template.format(
            socratic_level=bundle.socratic_level,
            user_context=bundle.user_context or "(no user context)",
            level_description=bundle.level_description or "standard",
            retrieval_context=retrieval_context,
            language_instruction=language_instruction,
            query=query,
        )
    elif bundle.mode == "briefing":
        prompt_template = SYNTHESIS_BRIEFING_PROMPT
        prompt = prompt_template.format(
            user_context=bundle.user_context or "(no user context)",
            retrieval_context=retrieval_context,
            language_instruction=language_instruction,
            query=query,
        )
    else:
        prompt_template = SYNTHESIS_NAVIGATOR_PROMPT
        prompt = prompt_template.format(
            user_context=bundle.user_context or "(no user context)",
            level_description=bundle.level_description or "standard",
            retrieval_context=retrieval_context,
            language_instruction=language_instruction,
            query=query,
        )

    if teaching_context:
        prompt += f"\n\n{teaching_context}"

    if skeptic_feedback:
        prompt += f"\n\nIMPORTANT — Skeptic feedback from prior attempt (address these issues):\n{skeptic_feedback}"

    model = _pick_synthesis_model(intent)
    response = await _call_claude(
        prompt,
        model=model,
        max_tokens=1500,
        temperature=0.3,
    )

    parsed = _parse_json_response(response.text)
    if parsed.get("parse_error"):
        # Fallback: use raw text as response
        return SynthesisOutput(
            response_text=response.text,
            confidence=0.6,
            token_count=response.total_tokens,
        ), response.total_tokens

    sources = []
    for s in parsed.get("sources_cited", []):
        sources.append(SourceCitation(
            id=s.get("id", ""),
            title=s.get("title", ""),
            type=s.get("type", "unknown"),
        ))

    return SynthesisOutput(
        response_text=parsed.get("response", response.text),
        sources_cited=sources,
        confidence=parsed.get("confidence", 0.7),
        knowledge_gaps=parsed.get("knowledge_gaps", []),
        token_count=response.total_tokens,
    ), response.total_tokens


async def skeptic_review(
    query: str,
    synthesis: SynthesisOutput,
    bundle: RetrievalBundle,
) -> tuple[SkepticVerdict, int]:
    """Stage 5: Adversarial review of synthesis output.
    Returns (SkepticVerdict, total_tokens).
    """
    # Build evidence summary for the skeptic
    evidence_lines = []
    for r in bundle.results:
        for item in r.items[:3]:
            evidence_lines.append(f"[{item.id}] ({item.type}) {item.title}: {item.content[:150]}")

    prompt = SKEPTIC_REVIEW_PROMPT.format(
        synthesis=synthesis.response_text,
        evidence_summary="\n".join(evidence_lines[:15]) or "(no evidence provided)",
        query=query,
    )

    response = await _call_claude(
        prompt,
        model=settings.haiku_model,
        max_tokens=800,
        temperature=0.2,
    )

    parsed = _parse_json_response(response.text)
    if parsed.get("parse_error"):
        return SkepticVerdict(approved=True), response.total_tokens

    issues = []
    for issue in parsed.get("issues", []):
        issues.append(SkepticIssue(
            type=issue.get("type", "unknown"),
            detail=issue.get("detail", ""),
        ))

    return SkepticVerdict(
        approved=parsed.get("approved", True),
        issues=issues,
        suggested_additions=parsed.get("suggested_additions", []),
        confidence_adjustment=parsed.get("confidence_adjustment", 0.0),
        token_count=response.total_tokens,
    ), response.total_tokens
