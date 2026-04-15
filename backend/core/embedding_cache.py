"""Embedding Cache — avoid recalculating embeddings for repeated text.

Saves ~$0.00001 per cached hit, but more importantly saves ~200ms latency per call.
Uses SHA256 hash of input text as cache key.

Two layers:
1. In-memory LRU (fast, lost on restart)
2. DB table embedding_cache (persistent, shared across instances)
"""

import hashlib
import logging
from functools import lru_cache

from backend.integrations.supabase_client import get_client

logger = logging.getLogger(__name__)

# In-memory LRU cache (max 2000 embeddings ≈ ~25MB RAM)
_memory_cache: dict[str, list[float]] = {}
MAX_MEMORY_CACHE = 2000


def _hash_text(text: str, model: str = "text-embedding-3-small") -> str:
    """Generate a stable hash for cache lookup."""
    key = f"{model}:{text}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


async def get_cached_embedding(
    text: str,
    model: str = "text-embedding-3-small",
) -> list[float] | None:
    """Try to get embedding from cache (memory → DB).

    Returns embedding vector or None if not cached.
    """
    text_hash = _hash_text(text, model)

    # Layer 1: Memory
    if text_hash in _memory_cache:
        return _memory_cache[text_hash]

    # Layer 2: DB
    try:
        client = get_client()
        result = client.table("embedding_cache").select(
            "embedding"
        ).eq("text_hash", text_hash).execute()

        if result.data and result.data[0].get("embedding"):
            embedding = result.data[0]["embedding"]
            # Warm memory cache
            if len(_memory_cache) < MAX_MEMORY_CACHE:
                _memory_cache[text_hash] = embedding
            return embedding
    except Exception as e:
        logger.debug(f"Embedding cache DB lookup failed: {e}")

    return None


async def cache_embedding(
    text: str,
    embedding: list[float],
    model: str = "text-embedding-3-small",
    token_count: int = 0,
) -> None:
    """Store embedding in both memory and DB cache."""
    text_hash = _hash_text(text, model)

    # Memory cache
    if len(_memory_cache) >= MAX_MEMORY_CACHE:
        # Evict oldest (simple FIFO — good enough)
        oldest_key = next(iter(_memory_cache))
        del _memory_cache[oldest_key]
    _memory_cache[text_hash] = embedding

    # DB cache (async, non-blocking — failure is OK)
    try:
        client = get_client()
        client.table("embedding_cache").upsert({
            "text_hash": text_hash,
            "model": model,
            "embedding": embedding,
            "token_count": token_count,
        }, on_conflict="text_hash").execute()
    except Exception as e:
        logger.debug(f"Embedding cache DB write failed: {e}")


async def get_or_create_embedding(
    text: str,
    model: str = "text-embedding-3-small",
) -> list[float]:
    """Get embedding from cache, or generate and cache it.

    This is the main function to use — drop-in replacement for direct OpenAI calls.
    """
    # Try cache first
    cached = await get_cached_embedding(text, model)
    if cached:
        return cached

    # Generate new embedding
    from backend.integrations.openai_client import get_embedding
    embedding = await get_embedding(text)

    # Cache it
    token_count = len(text.split()) * 2  # rough estimate
    await cache_embedding(text, embedding, model, token_count)

    return embedding


def get_cache_stats() -> dict:
    """Get cache statistics."""
    return {
        "memory_entries": len(_memory_cache),
        "memory_max": MAX_MEMORY_CACHE,
        "memory_pct": round(len(_memory_cache) / MAX_MEMORY_CACHE * 100, 1),
    }
