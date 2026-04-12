"""Embedding helper — async OpenAI text-embedding-3-small calls with caching."""

import logging

import httpx

from backend.config import settings
from backend.search.cache import embedding_cache, make_key

logger = logging.getLogger(__name__)

OPENAI_EMBEDDINGS_URL = "https://api.openai.com/v1/embeddings"


async def get_embedding(text: str) -> list[float]:
    """Get embedding vector for text. Uses cache to avoid redundant API calls."""
    cache_key = make_key(text)
    if cache_key in embedding_cache:
        return embedding_cache[cache_key]

    headers = {
        "Authorization": f"Bearer {settings.openai_api_key}",
        "Content-Type": "application/json",
    }
    body = {
        "model": settings.embedding_model,
        "input": text,
        "dimensions": settings.embedding_dimensions,
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            OPENAI_EMBEDDINGS_URL, json=body, headers=headers, timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()

    embedding = data["data"][0]["embedding"]
    embedding_cache[cache_key] = embedding
    return embedding
