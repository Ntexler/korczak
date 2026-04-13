"""Search pipeline orchestrator — wires all stages together."""

import asyncio
import logging
import time

from backend.search.models import (
    PipelineResult,
    QueryIntent,
    RetrievalBundle,
    TokenUsage,
)
from backend.search.cache import pipeline_cache, make_key
from backend.search.stages import analyze_query, check_coverage, synthesize, skeptic_review
from backend.search.retrievers import (
    retrieve_semantic,
    retrieve_graph,
    retrieve_citations,
    retrieve_user_context,
    retrieve_controversies,
    retrieve_perplexity,
)

logger = logging.getLogger(__name__)

MAX_COVERAGE_RETRIES = 2
MAX_SKEPTIC_RETRIES = 1


async def run_search_pipeline(
    user_message: str,
    conversation_history: list[dict] | None = None,
    user_id: str | None = None,
    mode: str = "navigator",
    level_description: str = "",
    socratic_level: int = 0,
    locale: str = "en",
) -> PipelineResult:
    """Main entry point: run the full 5-stage search pipeline.

    Falls back to a minimal result if early stages fail.
    """
    start_time = time.time()
    token_usage = TokenUsage()
    stages_completed = []

    # Check cache
    cache_key = make_key(user_message, user_id or "", mode)
    if cache_key in pipeline_cache:
        cached = pipeline_cache[cache_key]
        cached.stages_completed = ["cache_hit"]
        return cached

    # ── Stage 1: Query Analysis ──
    try:
        analysis, tokens = await analyze_query(user_message, conversation_history)
        token_usage.query_analysis = tokens
        stages_completed.append("query_analysis")
        logger.info(
            f"Query analysis: intent={analysis.intent}, "
            f"concepts={analysis.concepts}, sub_queries={analysis.sub_queries}"
        )
    except Exception as e:
        logger.error(f"Query analysis failed: {e}")
        # Fallback: use raw message as both concept and sub-query
        from backend.search.models import QueryAnalysis
        analysis = QueryAnalysis(
            intent=QueryIntent.FACTUAL,
            concepts=[user_message[:100]],
            sub_queries=[user_message],
        )
        stages_completed.append("query_analysis_fallback")

    # ── Stage 2: Parallel Retrieval ──
    retrieval_tasks = [
        retrieve_semantic(analysis.sub_queries),
        retrieve_graph(analysis.concepts),
        retrieve_user_context(user_id or ""),
    ]
    # Conditional retrievers
    if analysis.requires_recency or analysis.concepts:
        retrieval_tasks.append(
            retrieve_citations(analysis.concepts, analysis.requires_recency)
        )
    # Perplexity web search — always runs if API key is configured
    retrieval_tasks.append(
        retrieve_perplexity(user_message, analysis.concepts)
    )
    if analysis.requires_controversy:
        retrieval_tasks.append(retrieve_controversies(analysis.concepts))

    raw_results = await asyncio.gather(*retrieval_tasks, return_exceptions=True)

    # Filter out exceptions
    results = []
    for r in raw_results:
        if isinstance(r, Exception):
            logger.warning(f"Retriever failed: {r}")
        else:
            results.append(r)

    # Extract user context text
    user_context_text = ""
    for r in results:
        if r.source == "user" and r.items:
            user_context_text = r.items[0].content

    # Build bundle
    bundle = RetrievalBundle(
        results=results,
        user_context=user_context_text,
        level_description=level_description,
        mode=mode,
        socratic_level=socratic_level,
        total_items=sum(len(r.items) for r in results),
        source_count=len([r for r in results if r.items]),
    )
    stages_completed.append("retrieval")
    logger.info(f"Retrieval: {bundle.total_items} items from {bundle.source_count} sources")

    # ── Stage 3: Coverage Check (with retry) ──
    retry_count = 0
    # Skip coverage check if we have enough items from diverse sources
    should_check_coverage = bundle.total_items < 20 or bundle.source_count < 3

    while should_check_coverage and retry_count < MAX_COVERAGE_RETRIES:
        try:
            verdict, tokens = await check_coverage(user_message, bundle)
            token_usage.coverage_check += tokens

            if verdict.complete:
                stages_completed.append("coverage_pass")
                break

            # Retry with gap-filling queries
            logger.info(f"Coverage gap: {verdict.missing_aspects}. Retry queries: {verdict.retry_queries}")
            gap_tasks = []
            if verdict.retry_queries:
                gap_tasks.append(retrieve_semantic(verdict.retry_queries))
                gap_tasks.append(retrieve_graph(verdict.retry_queries))

            if gap_tasks:
                gap_results = await asyncio.gather(*gap_tasks, return_exceptions=True)
                for r in gap_results:
                    if not isinstance(r, Exception) and r.items:
                        bundle.results.append(r)
                        bundle.total_items += len(r.items)

            retry_count += 1
            stages_completed.append(f"coverage_retry_{retry_count}")
        except Exception as e:
            logger.warning(f"Coverage check failed: {e}")
            stages_completed.append("coverage_skip")
            break

    if not should_check_coverage:
        stages_completed.append("coverage_skip_rich")

    # ── Stage 3.5: Build pedagogical context + user preferences ──
    teaching_context = None
    if user_id:
        try:
            # User's explicit teaching preferences (always inject if set)
            from backend.core.teaching_preferences import get_user_preferences, preferences_to_prompt
            prefs = await get_user_preferences(user_id)
            prefs_block = preferences_to_prompt(prefs)

            # Pedagogical strategy (only if concepts detected)
            pedagogy_block = ""
            if analysis.concepts:
                from backend.core.pedagogy import (
                    build_teaching_context,
                    detect_student_profile,
                    get_student_knowledge,
                )
                student_profile = await detect_student_profile(user_id)
                student_knows = await get_student_knowledge(user_id, limit=15)
                primary_concept_type = None
                for r in bundle.results:
                    for item in r.items:
                        if item.type == "concept" and hasattr(item, "metadata"):
                            primary_concept_type = (item.metadata or {}).get("concept_type")
                            break
                    if primary_concept_type:
                        break

                pedagogy_block = build_teaching_context(
                    concept_type=primary_concept_type or "theory",
                    student_profile=student_profile,
                    concept_name=analysis.concepts[0] if analysis.concepts else "",
                    related_concepts=analysis.concepts[1:5] if len(analysis.concepts) > 1 else None,
                    student_knows=student_knows if student_knows else None,
                )

            # Combine: preferences override pedagogy defaults
            parts = [p for p in [prefs_block, pedagogy_block] if p]
            if parts:
                teaching_context = "\n\n".join(parts)
                stages_completed.append("pedagogy")
        except Exception as e:
            logger.debug(f"Pedagogy context skipped: {e}")

    # ── Stage 4: Synthesis (smart model routing) ──
    try:
        synthesis_output, tokens = await synthesize(
            user_message, bundle, locale, intent=analysis.intent,
            teaching_context=teaching_context,
        )
        token_usage.synthesis = tokens
        stages_completed.append(f"synthesis_{analysis.intent.value}")
    except Exception as e:
        logger.error(f"Synthesis failed: {e}")
        return PipelineResult(
            response_text=_fallback_response(locale),
            mode=mode,
            confidence=0.0,
            stages_completed=stages_completed + ["synthesis_failed"],
            token_usage=token_usage,
            used_fallback=True,
        )

    # ── Stage 5: Skeptic Review ──
    # Skip for: tutor mode at high Socratic, AND simple factual/exploration queries
    skeptic_warnings = []
    is_complex = analysis.intent in (QueryIntent.CONTROVERSY, QueryIntent.COMPARISON)
    should_run_skeptic = is_complex and not (mode == "tutor" and socratic_level >= 2)

    if should_run_skeptic:
        skeptic_retries = 0
        try:
            verdict, tokens = await skeptic_review(user_message, synthesis_output, bundle)
            token_usage.skeptic_review += tokens

            if not verdict.approved and skeptic_retries < MAX_SKEPTIC_RETRIES:
                # Re-synthesize with skeptic feedback
                feedback = "\n".join(
                    f"- {i.type}: {i.detail}" for i in verdict.issues
                )
                if verdict.suggested_additions:
                    feedback += "\nSuggested additions: " + ", ".join(verdict.suggested_additions)

                synthesis_output, tokens = await synthesize(
                    user_message, bundle, locale, skeptic_feedback=feedback,
                    intent=analysis.intent,
                )
                token_usage.synthesis += tokens
                skeptic_retries += 1

                # Re-run skeptic on revised synthesis
                verdict, tokens = await skeptic_review(user_message, synthesis_output, bundle)
                token_usage.skeptic_review += tokens

            # Apply confidence adjustment
            synthesis_output.confidence = max(
                0.1,
                synthesis_output.confidence + verdict.confidence_adjustment,
            )

            # Collect warnings
            for issue in verdict.issues:
                skeptic_warnings.append(f"[{issue.type}] {issue.detail}")

            stages_completed.append("skeptic_review")
        except Exception as e:
            logger.warning(f"Skeptic review failed: {e}")
            stages_completed.append("skeptic_skip")
    else:
        stages_completed.append("skeptic_skip_tutor")

    # ── Stage 6: Build final result ──
    token_usage.total = (
        token_usage.query_analysis
        + token_usage.coverage_check
        + token_usage.synthesis
        + token_usage.skeptic_review
    )

    # Extract concepts referenced from retrieval items
    concepts_referenced = []
    seen_concept_ids = set()
    for r in bundle.results:
        for item in r.items:
            if item.type == "concept" and item.id not in seen_concept_ids:
                seen_concept_ids.add(item.id)
                concepts_referenced.append({
                    "concept_id": item.id,
                    "name": item.title,
                })

    # Build sources list
    sources_cited = [
        {"id": s.id, "title": s.title, "type": s.type}
        for s in synthesis_output.sources_cited
    ]

    result = PipelineResult(
        response_text=synthesis_output.response_text,
        concepts_referenced=concepts_referenced,
        sources_cited=sources_cited,
        mode=mode,
        confidence=synthesis_output.confidence,
        knowledge_gaps=synthesis_output.knowledge_gaps,
        skeptic_warnings=skeptic_warnings,
        token_usage=token_usage,
        stages_completed=stages_completed,
    )

    elapsed_ms = (time.time() - start_time) * 1000
    logger.info(
        f"Pipeline complete in {elapsed_ms:.0f}ms — "
        f"{len(stages_completed)} stages, "
        f"{token_usage.total} tokens, "
        f"confidence={result.confidence:.2f}"
    )

    # Cache result
    pipeline_cache[cache_key] = result

    return result


def _fallback_response(locale: str) -> str:
    """Graceful error message when pipeline fails."""
    if locale == "he":
        return "אירעה שגיאה בעיבוד השאלה. אנא נסה שוב."
    return "An error occurred while processing your question. Please try again."
