"""Author profile enrichment service (Feature 6.5, Stage B-2).

Two responsibilities:
  1. `ensure_author_profile(...)` — given an author identifier (openalex_id /
      orcid / name + institution), return the matching `author_profiles` row,
      creating a stub if needed.
  2. `enrich_author_profile(profile_id)` — populate a stub from OpenAlex's
      author endpoint (works_count, h_index, institution history, x_concepts)
      and generate a short Claude-written bio.

The two are deliberately separate so the API layer can lazily ensure a
profile exists when surfacing a claim, then trigger enrichment in the
background. The backfill script in
`backend/pipeline/backfill_author_profiles.py` runs both eagerly.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

from backend.integrations.claude_client import _call_claude
from backend.integrations.openalex_client import fetch_author_by_id
from backend.integrations.supabase_client import get_client

logger = logging.getLogger(__name__)


_BIO_MODEL = "claude-haiku-4-5-20251001"  # Cheap; bios are short.

_BIO_PROMPT = """Write a 1-2 sentence learner-friendly background blurb for this academic author. Focus on: their primary field of study, their main institutional context, and any especially notable scholarly contribution. Do NOT speculate. Use only the facts given.

NAME: {name}
PRIMARY FIELD: {primary_field}
PRIMARY INSTITUTION: {primary_institution} ({country})
WORKS COUNT: {works_count}
CITED BY: {cited_by_count}
H-INDEX: {h_index}
TOP CONCEPTS: {top_concepts}
INSTITUTION HISTORY (most recent first): {institution_history}

Write the blurb directly, no preamble. If the data is too sparse to write something honest, return the literal string: INSUFFICIENT_DATA"""


def _normalize_name(name: str) -> str:
    return re.sub(r"\s+", " ", (name or "").strip().lower())


# -------------------- ensure / lookup --------------------


def ensure_author_profile(
    *,
    openalex_id: str | None = None,
    orcid: str | None = None,
    name: str | None = None,
    primary_institution: str | None = None,
) -> dict | None:
    """Return the author_profiles row for this author, creating a stub if missing.

    Match priority: openalex_id > orcid > normalized_name. Returns the row dict
    (with `id`, `enriched_at`, `bio`, etc.) or None if we have no identifying
    info at all.
    """
    if not (openalex_id or orcid or name):
        return None

    client = get_client()

    # 1. Lookup by strongest identifier first
    if openalex_id:
        existing = client.table("author_profiles").select("*").eq("openalex_id", openalex_id).execute()
        if existing.data:
            return existing.data[0]
    if orcid:
        existing = client.table("author_profiles").select("*").eq("orcid", orcid).execute()
        if existing.data:
            return existing.data[0]
    if name:
        normalized = _normalize_name(name)
        existing = (
            client.table("author_profiles")
            .select("*")
            .eq("normalized_name", normalized)
            .execute()
        )
        if existing.data:
            return existing.data[0]

    # 2. Create a stub row
    row = {
        "openalex_id": openalex_id,
        "orcid": orcid,
        "name": name or "Unknown",
        "normalized_name": _normalize_name(name or "Unknown"),
        "primary_institution": primary_institution,
    }
    row = {k: v for k, v in row.items() if v is not None or k == "name"}
    inserted = client.table("author_profiles").insert(row).execute()
    return inserted.data[0] if inserted.data else None


# -------------------- enrichment from OpenAlex --------------------


async def enrich_from_openalex(profile: dict) -> dict | None:
    """Populate enrichment fields on an author_profiles row from OpenAlex.

    Returns the updated row, or None if the OpenAlex fetch failed.
    Idempotent: only fills fields that are currently NULL/empty unless the
    OpenAlex data is materially fresher.
    """
    if not profile.get("openalex_id"):
        # Nothing to enrich without an OpenAlex ID; could try ORCID lookup later.
        return profile

    raw = await fetch_author_by_id(profile["openalex_id"])
    if not raw:
        return None

    # Extract fields safely
    summary_stats = raw.get("summary_stats") or {}
    last_known = raw.get("last_known_institutions") or []
    primary_inst = last_known[0] if last_known else {}

    institution_history = []
    for aff in raw.get("affiliations") or []:
        inst = aff.get("institution") or {}
        institution_history.append({
            "institution": inst.get("display_name"),
            "ror_id": inst.get("ror"),
            "country": inst.get("country_code"),
            "years": aff.get("years") or [],
        })

    top_concepts = []
    for c in (raw.get("x_concepts") or [])[:6]:
        top_concepts.append({
            "id": c.get("id"),
            "name": c.get("display_name"),
            "level": c.get("level"),
            "score": c.get("score"),
        })

    primary_field = top_concepts[0]["name"] if top_concepts else None

    update: dict = {
        "name": raw.get("display_name") or profile.get("name"),
        "normalized_name": _normalize_name(raw.get("display_name") or profile.get("name") or ""),
        "orcid": (raw.get("orcid") or profile.get("orcid")),
        "primary_institution": primary_inst.get("display_name") or profile.get("primary_institution"),
        "primary_institution_ror_id": primary_inst.get("ror") or profile.get("primary_institution_ror_id"),
        "country": primary_inst.get("country_code") or profile.get("country"),
        "institution_history": institution_history,
        "primary_field": primary_field or profile.get("primary_field"),
        "concepts": top_concepts,
        "works_count": raw.get("works_count") or 0,
        "cited_by_count": raw.get("cited_by_count") or 0,
        "h_index": summary_stats.get("h_index"),
        "enriched_at": datetime.now(timezone.utc).isoformat(),
        "enrichment_source": "openalex",
    }
    update = {k: v for k, v in update.items() if v is not None}

    client = get_client()
    result = client.table("author_profiles").update(update).eq("id", profile["id"]).execute()
    return result.data[0] if result.data else profile


# -------------------- bio generation via Claude --------------------


async def generate_bio(profile: dict) -> dict | None:
    """Generate a short bio with Claude and persist it to author_profiles.

    Skips profiles that already have a bio. Returns the updated row, or the
    same row if generation was skipped or yielded INSUFFICIENT_DATA.
    """
    if profile.get("bio"):
        return profile

    # Refuse to bio without minimum signal
    if not (profile.get("primary_field") or profile.get("primary_institution") or profile.get("works_count")):
        return profile

    prompt = _BIO_PROMPT.format(
        name=profile.get("name") or "Unknown",
        primary_field=profile.get("primary_field") or "Unknown field",
        primary_institution=profile.get("primary_institution") or "Unknown institution",
        country=profile.get("country") or "Unknown country",
        works_count=profile.get("works_count") or 0,
        cited_by_count=profile.get("cited_by_count") or 0,
        h_index=profile.get("h_index") if profile.get("h_index") is not None else "n/a",
        top_concepts=", ".join(c.get("name", "") for c in (profile.get("concepts") or [])[:5]),
        institution_history=" -> ".join(
            f"{h.get('institution', '?')} ({h.get('country', '?')})"
            for h in (profile.get("institution_history") or [])[:3]
        ) or "n/a",
    )

    try:
        response = await _call_claude(prompt, model=_BIO_MODEL, max_tokens=300, temperature=0.2)
    except Exception as e:
        logger.warning(f"Bio generation failed for {profile.get('name')}: {e}")
        return profile

    bio_text = (response.text or "").strip()
    if not bio_text or bio_text == "INSUFFICIENT_DATA":
        return profile

    client = get_client()
    update = {
        "bio": bio_text,
        "bio_model": _BIO_MODEL,
        "bio_generated_at": datetime.now(timezone.utc).isoformat(),
    }
    result = client.table("author_profiles").update(update).eq("id", profile["id"]).execute()
    return result.data[0] if result.data else profile
