"""Authentication & authorization — nobody gets trusted from a query param.

Two layers:
1. get_current_user — verifies a Supabase Auth JWT (Authorization: Bearer).
   Returns the verified user id. In dev (ALLOW_ANON=true, the default until
   the login UI ships) an unauthenticated caller gets "anon:<ip>" so nothing
   breaks locally — but verified identity always wins when present.
2. require_admin — admin surface protection via X-Admin-Key header matching
   ADMIN_API_KEY env. If ADMIN_API_KEY is unset AND allow_anon is true we
   permit with a loud log warning (local dev); in production set both
   ADMIN_API_KEY and ALLOW_ANON=false.

Usage:
    from backend.auth import get_current_user, require_admin

    @router.get("/me")
    async def me(user_id: str = Depends(get_current_user)): ...

    router = APIRouter(dependencies=[Depends(require_admin)])
"""

import logging
import secrets

import httpx
from fastapi import Depends, HTTPException, Request

from backend.config import settings

logger = logging.getLogger(__name__)

# Small verified-token cache: token -> user_id (avoids re-verifying every request)
_token_cache: dict[str, str] = {}
_TOKEN_CACHE_MAX = 500


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def verify_supabase_token(token: str) -> str | None:
    """Verify a Supabase Auth JWT against the auth server. Returns user id or None."""
    if not token or not settings.supabase_url:
        return None
    if token in _token_cache:
        return _token_cache[token]
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{settings.supabase_url}/auth/v1/user",
                headers={
                    "apikey": settings.supabase_key or settings.supabase_service_key,
                    "Authorization": f"Bearer {token}",
                },
                timeout=8,
            )
            if resp.status_code == 200:
                user_id = resp.json().get("id")
                if user_id:
                    if len(_token_cache) >= _TOKEN_CACHE_MAX:
                        _token_cache.pop(next(iter(_token_cache)))
                    _token_cache[token] = user_id
                    return user_id
    except Exception as e:
        logger.warning(f"Token verification failed: {e}")
    return None


async def get_current_user(request: Request) -> str:
    """Resolve the caller's identity. Verified JWT > anon fallback (dev only)."""
    auth_header = request.headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        token = auth_header[7:].strip()
        user_id = await verify_supabase_token(token)
        if user_id:
            return user_id
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    if settings.allow_anon:
        # Dev mode: identity is the client IP, NOT a caller-chosen string
        return f"anon:{_client_ip(request)}"

    raise HTTPException(status_code=401, detail="Authentication required")


async def require_admin(request: Request) -> None:
    """Gate for the admin surface. X-Admin-Key must match ADMIN_API_KEY."""
    provided = request.headers.get("x-admin-key", "")

    if settings.admin_api_key:
        if provided and secrets.compare_digest(provided, settings.admin_api_key):
            return
        raise HTTPException(status_code=403, detail="Admin access denied")

    if settings.allow_anon:
        logger.warning("Admin endpoint accessed with NO ADMIN_API_KEY configured (dev mode)")
        return

    raise HTTPException(status_code=403, detail="Admin access not configured")
