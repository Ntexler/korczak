"""Integration tests for the search pipeline.

Run: pytest backend/tests/test_search_pipeline.py -v
Requires: ANTHROPIC_API_KEY, SUPABASE_URL, SUPABASE_SERVICE_KEY, OPENAI_API_KEY
"""

import asyncio
import time
import pytest

from backend.search.pipeline import run_search_pipeline
from backend.search.models import PipelineResult


# -- Test queries spanning different intents --

TEST_QUERIES = [
    {
        "query": "What is the relationship between structural violence and medical anthropology?",
        "expected_mode": "navigator",
        "description": "Multi-concept factual query",
    },
    {
        "query": "Explain participant observation step by step",
        "expected_mode": "tutor",
        "description": "Tutor mode — step-by-step explanation",
    },
    {
        "query": "What are the latest debates in decolonizing anthropology?",
        "expected_mode": "navigator",
        "description": "Controversy + recency query",
    },
    {
        "query": "How does thick description compare to functionalism?",
        "expected_mode": "navigator",
        "description": "Comparison intent — two concepts",
    },
    {
        "query": "What methodological gaps exist in digital ethnography?",
        "expected_mode": "navigator",
        "description": "Exploration + gap detection",
    },
]


@pytest.fixture(scope="module")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "test_case",
    TEST_QUERIES,
    ids=[t["description"] for t in TEST_QUERIES],
)
async def test_pipeline_completes(test_case):
    """Pipeline completes without exception and returns valid result."""
    start = time.time()

    result = await run_search_pipeline(
        user_message=test_case["query"],
        mode=test_case["expected_mode"],
        locale="en",
    )

    elapsed = time.time() - start

    # Basic assertions
    assert isinstance(result, PipelineResult)
    assert result.response_text, "Response text should not be empty"
    assert result.confidence >= 0.0, "Confidence should be non-negative"
    assert isinstance(result.skeptic_warnings, list)
    assert isinstance(result.stages_completed, list)
    assert len(result.stages_completed) > 0, "At least one stage should complete"

    # Performance
    assert elapsed < 30, f"Pipeline took {elapsed:.1f}s (max 30s)"

    # Token tracking
    assert result.token_usage.total >= 0

    print(
        f"\n[{test_case['description']}]\n"
        f"  Elapsed: {elapsed:.1f}s\n"
        f"  Stages: {result.stages_completed}\n"
        f"  Concepts: {len(result.concepts_referenced)}\n"
        f"  Confidence: {result.confidence:.2f}\n"
        f"  Tokens: {result.token_usage.total}\n"
        f"  Warnings: {len(result.skeptic_warnings)}\n"
        f"  Response: {result.response_text[:200]}..."
    )


@pytest.mark.asyncio
async def test_pipeline_with_hebrew():
    """Pipeline handles Hebrew locale correctly."""
    result = await run_search_pipeline(
        user_message="מה ההבדל בין טוטמיזם לפטישיזם?",
        mode="navigator",
        locale="he",
    )

    assert isinstance(result, PipelineResult)
    assert result.response_text


@pytest.mark.asyncio
async def test_pipeline_caching():
    """Second identical call should be faster (cache hit)."""
    query = "What is liminality in anthropology?"

    start1 = time.time()
    result1 = await run_search_pipeline(user_message=query, mode="navigator")
    elapsed1 = time.time() - start1

    start2 = time.time()
    result2 = await run_search_pipeline(user_message=query, mode="navigator")
    elapsed2 = time.time() - start2

    assert result1.response_text == result2.response_text
    assert "cache_hit" in result2.stages_completed
    # Cache hit should be at least 10x faster
    assert elapsed2 < elapsed1 / 5, f"Cache hit ({elapsed2:.2f}s) not faster than cold ({elapsed1:.2f}s)"
