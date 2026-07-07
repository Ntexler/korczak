"""Trusted sources registry — the user-approved anchor list.

Tier 1: peer-reviewed anchors — one witness counts as two in the court,
        and papers published there get a credibility boost.
Tier 2: verified institutional data (facts, not interpretation).
Tier 3: quality knowledge journalism + primary-text archives —
        validation only, never the academic base.

Loaded once, cached 10 minutes. Matching is normalized-substring so
"The Lancet Psychiatry" matches the "The Lancet" entry.
"""

import logging
import re
import time

logger = logging.getLogger(__name__)

_cache: dict = {"loaded_at": 0.0, "by_name": {}}
_TTL = 600


def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", (name or "").lower()).strip()


def _load() -> dict[str, int]:
    now = time.monotonic()
    if _cache["by_name"] and now - _cache["loaded_at"] < _TTL:
        return _cache["by_name"]
    try:
        from backend.integrations.supabase_client import get_client
        client = get_client()
        rows = client.table("trusted_sources").select("name, tier").execute()
        _cache["by_name"] = {_norm(r["name"]): r["tier"] for r in (rows.data or [])}
        _cache["loaded_at"] = now
    except Exception as e:
        logger.debug(f"Trusted sources load failed (empty registry): {e}")
    return _cache["by_name"]


def trust_tier(source_name: str | None) -> int | None:
    """Tier (1/2/3) if the source matches the registry, else None."""
    if not source_name:
        return None
    n = _norm(source_name)
    if not n:
        return None
    registry = _load()
    if n in registry:
        return registry[n]
    # substring both ways: "the lancet psychiatry" ⊃ "the lancet"
    for trusted_name, tier in registry.items():
        if len(trusted_name) >= 6 and (trusted_name in n or n in trusted_name):
            return tier
    return None


def invalidate_cache() -> None:
    _cache["loaded_at"] = 0.0
    _cache["by_name"] = {}
