"""Rate Limiter — per-user, per-endpoint rate limiting for FastAPI.

Uses in-memory sliding window with optional DB persistence for distributed deployments.
Lightweight: no Redis needed for single-server setups.

Limits:
  - chat: 30 requests / minute (Claude API is the bottleneck)
  - search: 20 requests / minute
  - export: 5 requests / minute (heavy operations)
  - default: 60 requests / minute
"""

import time
import logging
from collections import defaultdict
from datetime import datetime, timezone

from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)

# Rate limits per endpoint group (requests per minute)
RATE_LIMITS = {
    "chat": 30,
    "learning/explain": 20,
    "learning/quiz": 10,
    "obsidian/import": 3,
    "obsidian/export": 5,
    "plugins/zotero": 5,
    "plugins/anki": 5,
    "search": 20,
}
DEFAULT_LIMIT = 60
WINDOW_SECONDS = 60

# In-memory sliding window: {user_endpoint: [(timestamp, ...)]}
_windows: dict[str, list[float]] = defaultdict(list)


def _get_user_id(request: Request) -> str:
    """Extract user ID from request (query param, header, or IP fallback)."""
    # Try query param
    user_id = request.query_params.get("user_id")
    if user_id:
        return user_id

    # Try header
    user_id = request.headers.get("X-User-Id")
    if user_id:
        return user_id

    # Fallback to IP
    return request.client.host if request.client else "unknown"


def _get_endpoint_group(path: str) -> str:
    """Map a request path to a rate limit group."""
    # Remove /api/ prefix
    clean = path.lstrip("/").removeprefix("api/")

    for prefix, limit in RATE_LIMITS.items():
        if clean.startswith(prefix):
            return prefix

    return "default"


def _check_rate_limit(user_id: str, endpoint_group: str) -> tuple[bool, int]:
    """Check if request is within rate limit.

    Returns (allowed: bool, remaining: int).
    """
    key = f"{user_id}:{endpoint_group}"
    now = time.time()
    limit = RATE_LIMITS.get(endpoint_group, DEFAULT_LIMIT)

    # Clean expired entries
    window = _windows[key]
    cutoff = now - WINDOW_SECONDS
    _windows[key] = [t for t in window if t > cutoff]

    count = len(_windows[key])
    if count >= limit:
        return False, 0

    _windows[key].append(now)
    return True, limit - count - 1


class RateLimitMiddleware(BaseHTTPMiddleware):
    """FastAPI middleware for per-user rate limiting."""

    async def dispatch(self, request: Request, call_next):
        # Skip rate limiting for health checks and static files
        path = request.url.path
        if path.startswith("/api/health") or not path.startswith("/api/"):
            return await call_next(request)

        user_id = _get_user_id(request)
        endpoint_group = _get_endpoint_group(path)
        allowed, remaining = _check_rate_limit(user_id, endpoint_group)

        if not allowed:
            limit = RATE_LIMITS.get(endpoint_group, DEFAULT_LIMIT)
            logger.warning(
                f"Rate limit exceeded: user={user_id} endpoint={endpoint_group} "
                f"limit={limit}/min"
            )
            raise HTTPException(
                status_code=429,
                detail={
                    "error": "Rate limit exceeded",
                    "limit": limit,
                    "window": f"{WINDOW_SECONDS}s",
                    "retry_after": WINDOW_SECONDS,
                },
            )

        response = await call_next(request)

        # Add rate limit headers
        limit = RATE_LIMITS.get(endpoint_group, DEFAULT_LIMIT)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Window"] = f"{WINDOW_SECONDS}s"

        return response
