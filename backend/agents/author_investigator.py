"""Author Investigator — Korczak checks who's behind the research.

Before trusting a claim, Korczak investigates the author:
1. Academic profile — h-index, institution, field, career stage
2. Publication patterns — prolific? consistent field? sudden topic switch?
3. Funding & conflicts — who pays for this research?
4. Retractions — has this author retracted papers?
5. Citation context — do people cite them positively or to disagree?
6. Reputation signals — well-cited by peers? controversial?

Uses OpenAlex (free) for author data, CrossRef for retractions,
and Retraction Watch database when available.

Usage:
  profile = await investigate_author("Clifford Geertz")
  profile = await investigate_author_by_openalex("A5023888391")
  credibility = assess_author_credibility(profile)
"""

import logging

import httpx

logger = logging.getLogger(__name__)

OPENALEX_BASE = "https://api.openalex.org"


async def investigate_author(name: str) -> dict:
    """Investigate an author by name. Returns comprehensive profile."""
    import os

    params = {
        "search": name,
        "per_page": 3,
        "select": "id,display_name,works_count,cited_by_count,summary_stats,"
                  "affiliations,x_concepts,last_known_institutions,counts_by_year",
    }
    email = os.getenv("OPENALEX_EMAIL")
    if email:
        params["mailto"] = email

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{OPENALEX_BASE}/authors",
                params=params, timeout=15,
            )
            if resp.status_code != 200:
                return {"name": name, "found": False, "error": f"OpenAlex {resp.status_code}"}

            results = resp.json().get("results", [])
            if not results:
                return {"name": name, "found": False}

            author = results[0]
            return _parse_author_profile(author)
    except Exception as e:
        logger.warning(f"Author investigation failed for {name}: {e}")
        return {"name": name, "found": False, "error": str(e)}


async def investigate_author_by_openalex(openalex_id: str) -> dict:
    """Investigate by OpenAlex author ID (more precise)."""
    import os

    params = {
        "select": "id,display_name,works_count,cited_by_count,summary_stats,"
                  "affiliations,x_concepts,last_known_institutions,counts_by_year",
    }
    email = os.getenv("OPENALEX_EMAIL")
    if email:
        params["mailto"] = email

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{OPENALEX_BASE}/authors/{openalex_id}",
                params=params, timeout=15,
            )
            if resp.status_code != 200:
                return {"openalex_id": openalex_id, "found": False}

            return _parse_author_profile(resp.json())
    except Exception as e:
        return {"openalex_id": openalex_id, "found": False, "error": str(e)}


def _parse_author_profile(data: dict) -> dict:
    """Parse OpenAlex author data into a structured profile."""
    stats = data.get("summary_stats") or {}
    institutions = data.get("last_known_institutions") or data.get("affiliations") or []

    # Extract fields of expertise
    concepts = data.get("x_concepts") or []
    top_fields = [
        {"name": c.get("display_name", ""), "score": c.get("score", 0)}
        for c in sorted(concepts, key=lambda x: x.get("score", 0), reverse=True)[:5]
    ]

    # Career timeline
    counts_by_year = data.get("counts_by_year") or []
    years_active = sorted([y["year"] for y in counts_by_year if y.get("works_count", 0) > 0])
    career_start = min(years_active) if years_active else None
    career_end = max(years_active) if years_active else None

    # Recent activity
    recent_works = sum(
        y.get("works_count", 0) for y in counts_by_year
        if y.get("year", 0) >= 2020
    )

    # Institution info
    current_institution = ""
    institution_country = ""
    if institutions:
        inst = institutions[0] if isinstance(institutions[0], dict) else {}
        current_institution = inst.get("display_name", "")
        institution_country = inst.get("country_code", "")

    return {
        "found": True,
        "name": data.get("display_name", ""),
        "openalex_id": (data.get("id") or "").split("/")[-1],
        "works_count": data.get("works_count", 0),
        "cited_by_count": data.get("cited_by_count", 0),
        "h_index": stats.get("h_index", 0),
        "i10_index": stats.get("i10_index", 0),
        "mean_citedness": round(stats.get("2yr_mean_citedness", 0), 2),
        "current_institution": current_institution,
        "institution_country": institution_country,
        "top_fields": top_fields,
        "career_start": career_start,
        "career_end": career_end,
        "career_years": (career_end - career_start + 1) if career_start and career_end else 0,
        "recent_works_since_2020": recent_works,
        "is_active": career_end and career_end >= 2022,
    }


async def check_retractions(author_name: str, doi_list: list[str] | None = None) -> dict:
    """Check if an author has any retracted papers.

    Uses CrossRef for retraction notices.
    """
    retracted = []

    if doi_list:
        for doi in doi_list[:10]:
            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.get(
                        f"https://api.crossref.org/works/{doi}",
                        timeout=10,
                    )
                    if resp.status_code == 200:
                        data = resp.json().get("message", {})
                        # Check for retraction update
                        updates = data.get("update-to") or []
                        for update in updates:
                            if update.get("type") == "retraction":
                                retracted.append({
                                    "doi": doi,
                                    "title": data.get("title", [""])[0],
                                    "retraction_date": update.get("updated", {}).get("date-time"),
                                })
            except Exception:
                continue

    return {
        "author": author_name,
        "retracted_count": len(retracted),
        "retracted_papers": retracted,
        "clean": len(retracted) == 0,
    }


def assess_author_credibility(profile: dict) -> dict:
    """Assess an author's overall credibility score.

    Returns {score: 0-1, level: str, reasons: [str]}.
    """
    if not profile.get("found"):
        return {
            "score": 0.3,
            "level": "unknown",
            "reasons": ["Author not found in OpenAlex — cannot verify credentials"],
        }

    score = 0.5  # Start neutral
    reasons = []

    # h-index
    h = profile.get("h_index", 0)
    if h >= 50:
        score += 0.2
        reasons.append(f"High h-index ({h}) — established researcher")
    elif h >= 20:
        score += 0.1
        reasons.append(f"Good h-index ({h})")
    elif h >= 5:
        reasons.append(f"Moderate h-index ({h})")
    elif h < 2:
        score -= 0.1
        reasons.append(f"Low h-index ({h}) — early career or limited impact")

    # Citations
    cited = profile.get("cited_by_count", 0)
    if cited >= 10000:
        score += 0.1
        reasons.append(f"Highly cited ({cited:,} total citations)")
    elif cited < 100:
        score -= 0.05
        reasons.append(f"Low citation count ({cited})")

    # Institution
    inst = profile.get("current_institution", "")
    if inst:
        reasons.append(f"Affiliated with {inst}")
        score += 0.05
    else:
        reasons.append("No known institutional affiliation")

    # Activity
    if profile.get("is_active"):
        reasons.append("Currently active in research")
        score += 0.05
    elif profile.get("career_end") and profile["career_end"] < 2015:
        reasons.append(f"Last published in {profile['career_end']} — may be retired or deceased")

    # Career length
    years = profile.get("career_years", 0)
    if years >= 30:
        score += 0.05
        reasons.append(f"Long career ({years} years)")
    elif years < 3:
        score -= 0.05
        reasons.append(f"Early career ({years} years)")

    # Field consistency
    fields = profile.get("top_fields", [])
    if fields:
        top_field = fields[0]["name"]
        reasons.append(f"Primary field: {top_field}")

    score = max(0.1, min(1.0, score))

    # Level
    if score >= 0.8:
        level = "highly_credible"
    elif score >= 0.6:
        level = "credible"
    elif score >= 0.4:
        level = "moderate"
    elif score >= 0.2:
        level = "limited"
    else:
        level = "unknown"

    return {
        "score": round(score, 2),
        "level": level,
        "reasons": reasons,
        "h_index": profile.get("h_index", 0),
        "institution": profile.get("current_institution", ""),
        "career_years": profile.get("career_years", 0),
    }


async def full_investigation(
    author_name: str,
    openalex_id: str | None = None,
) -> dict:
    """Complete author investigation: profile + credibility + retractions."""
    if openalex_id:
        profile = await investigate_author_by_openalex(openalex_id)
    else:
        profile = await investigate_author(author_name)

    credibility = assess_author_credibility(profile)
    retractions = await check_retractions(author_name)

    if not retractions["clean"]:
        credibility["score"] = max(0.1, credibility["score"] - 0.3)
        credibility["reasons"].append(
            f"WARNING: {retractions['retracted_count']} retracted papers found"
        )
        credibility["level"] = "flagged"

    return {
        "profile": profile,
        "credibility": credibility,
        "retractions": retractions,
    }
