"""Caching layer for search pipeline — in-memory TTL caches."""

import hashlib
from cachetools import TTLCache

# Embedding cache: avoid re-embedding the same text within 1 hour
embedding_cache: TTLCache = TTLCache(maxsize=256, ttl=3600)

# Query analysis cache: same query within 5 minutes gets cached result
analysis_cache: TTLCache = TTLCache(maxsize=64, ttl=300)

# Full pipeline result cache: identical query+user within 2 minutes
pipeline_cache: TTLCache = TTLCache(maxsize=32, ttl=120)


def make_key(*parts: str) -> str:
    """Create a cache key from multiple string parts."""
    raw = ":".join(parts)
    return hashlib.sha256(raw.encode()).hexdigest()
