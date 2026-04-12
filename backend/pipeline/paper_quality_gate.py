"""
Paper quality gate — DOI verification, journal reputation check,
Claude-based quality assessment, duplicate detection, and orchestration.

Usage:
    from backend.pipeline.paper_quality_gate import process_upload
    result = await process_upload("upload-uuid-here")
"""

import json
import os
import re
import time
from datetime import datetime, timezone

import httpx
from dotenv import load_dotenv

load_dotenv()

# --- Config ---

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
ANTHROPIC_API = "https://api.anthropic.com/v1/messages"

HEADERS = {
    "apikey": SUPABASE_SERVICE_KEY,
    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}

# --- Known predatory / problematic publisher patterns ---

PREDATORY_PATTERNS = {
    "OMICS International",
    "OMICS Group",
    "Juniper Publishers",
    "SciDoc Publishers",
    "Science Domain International",
    "International Research Journals",
    "Academic Journals Inc",
    "Herald Scholarly Open Access",
    "Insight Medical Publishing",
    "iMedPub",
    "Longdom Publishing",
    "Pulsus Group",
    "Gavin Publishers",
    "Crimson Publishers",
    "Medwin Publishers",
    "Biomedgrid",
    "SciFed Publishers",
    "Annex Publishers",
    "Jacobs Publishers",
}

# Patterns that trigger closer inspection (not automatic rejection)
SUSPICIOUS_PATTERNS = [
    r"predatory",
    r"pay.to.publish",
    r"vanity\s+press",
    r"mega.?journal",
]

# Hindawi journals retracted en masse in 2023-2024
HINDAWI_WARNING = "Hindawi"

# MDPI is controversial — flag for review but don't auto-reject
MDPI_WARNING = "MDPI"


# --- Supabase helpers (mirroring seed_graph.py pattern) ---

def _supabase_post(table: str, data: dict) -> dict | list | None:
    """Insert into Supabase via REST API."""
    resp = httpx.post(
        f"{SUPABASE_URL}/rest/v1/{table}",
        json=data,
        headers=HEADERS,
        timeout=15,
    )
    if resp.status_code in (200, 201):
        return resp.json()
    elif resp.status_code == 409:
        return None
    else:
        print(f"  Supabase POST error ({table}): {resp.status_code} {resp.text[:300]}")
        return None


def _supabase_get(table: str, params: dict) -> list:
    """Query Supabase via REST API."""
    resp = httpx.get(
        f"{SUPABASE_URL}/rest/v1/{table}",
        params=params,
        headers={**HEADERS, "Prefer": ""},
        timeout=15,
    )
    if resp.status_code == 200:
        return resp.json()
    return []


def _supabase_patch(table: str, match_params: dict, data: dict) -> dict | list | None:
    """Update rows in Supabase via REST API."""
    resp = httpx.patch(
        f"{SUPABASE_URL}/rest/v1/{table}",
        params=match_params,
        json=data,
        headers=HEADERS,
        timeout=15,
    )
    if resp.status_code in (200, 204):
        try:
            return resp.json()
        except Exception:
            return {}
    else:
        print(f"  Supabase PATCH error ({table}): {resp.status_code} {resp.text[:300]}")
        return None


# ============================================================
# 1. DOI Verification via CrossRef
# ============================================================

def verify_doi(doi: str) -> dict:
    """Verify a DOI against the CrossRef API.

    Args:
        doi: The DOI string (e.g. '10.1234/example').

    Returns:
        Dict with verified status and metadata from CrossRef.
    """
    default = {
        "verified": False,
        "title": "",
        "journal": "",
        "publisher": "",
        "type": "",
        "crossref_data": {},
    }

    if not doi:
        return default

    # Normalize DOI — strip URL prefix if present
    doi_clean = doi.strip()
    if doi_clean.startswith("http"):
        doi_clean = re.sub(r"^https?://doi\.org/", "", doi_clean)

    try:
        resp = httpx.get(
            f"https://api.crossref.org/works/{doi_clean}",
            headers={"User-Agent": "KorczakAI/1.0 (mailto:ntexler87@gmail.com)"},
            timeout=15,
        )
        if resp.status_code != 200:
            return default

        data = resp.json().get("message", {})
        title_parts = data.get("title", [])
        container = data.get("container-title", [])

        return {
            "verified": True,
            "title": title_parts[0] if title_parts else "",
            "journal": container[0] if container else "",
            "publisher": data.get("publisher", ""),
            "type": data.get("type", ""),
            "crossref_data": data,
        }
    except Exception as e:
        print(f"  DOI verification error: {e}")
        return default


# ============================================================
# 2. Journal Reputation Check
# ============================================================

def check_journal_reputation(journal_name: str) -> dict:
    """Check if a journal name matches known predatory or suspicious patterns.

    Args:
        journal_name: Name of the journal/publisher.

    Returns:
        Dict with flagged status and reason.
    """
    if not journal_name or not journal_name.strip():
        return {"flagged": True, "reason": "Journal name is empty or missing"}

    name_lower = journal_name.lower().strip()

    # Check against known predatory publishers
    for predatory in PREDATORY_PATTERNS:
        if predatory.lower() in name_lower:
            return {
                "flagged": True,
                "reason": f"Matches known predatory publisher: {predatory}",
            }

    # Check Hindawi (mass retractions)
    if HINDAWI_WARNING.lower() in name_lower:
        return {
            "flagged": True,
            "reason": "Hindawi journal — many titles retracted in 2023-2024 wave; requires manual review",
        }

    # Check MDPI (controversial but not auto-reject)
    if MDPI_WARNING.lower() in name_lower:
        return {
            "flagged": True,
            "reason": "MDPI journal — quality varies significantly by title; flagged for review",
        }

    # Check suspicious patterns
    for pattern in SUSPICIOUS_PATTERNS:
        if re.search(pattern, name_lower):
            return {
                "flagged": True,
                "reason": f"Journal name matches suspicious pattern: {pattern}",
            }

    # Suspiciously generic names
    generic_names = [
        "international journal",
        "global journal",
        "world journal",
        "open journal",
        "universal journal",
    ]
    word_count = len(name_lower.split())
    if word_count <= 3 and any(g in name_lower for g in generic_names):
        return {
            "flagged": True,
            "reason": "Suspiciously generic journal name",
        }

    return {"flagged": False, "reason": None}


# ============================================================
# 3. Claude Quality Assessment
# ============================================================

QUALITY_ASSESSMENT_PROMPT = """You are an academic quality assessor for a knowledge graph platform. Evaluate this paper submission for quality and authenticity.

TITLE: {title}
DOI VERIFIED: {doi_verified}
JOURNAL FLAGGED: {journal_flagged}

TEXT (first 8000 chars):
{text}

Evaluate on a 0-1 scale for each criterion. Be rigorous but fair — many legitimate papers from smaller journals may not score perfectly on every metric.

Return ONLY valid JSON:
{{
  "methodology_described": <0-1 float>,
  "claims_supported": <0-1 float>,
  "writing_quality": <0-1 float>,
  "references_present": <0-1 float>,
  "academic_rigor": <0-1 float>,
  "overall_quality": <0-1 float>,
  "is_likely_genuine": <true/false>,
  "concerns": [<list of specific concern strings, or empty list>],
  "recommendation": "<approve|quarantine|reject>"
}}

Scoring guidance:
- methodology_described: Is there a clear research methodology or theoretical framework?
- claims_supported: Are claims backed by evidence, citations, or logical argument?
- writing_quality: Is the writing clear, well-structured, and free of major errors?
- references_present: Does the text reference other scholarly works?
- academic_rigor: Overall scholarly quality — depth of analysis, appropriate caveats, etc.
- overall_quality: Your holistic assessment combining all factors.
- is_likely_genuine: Is this a real academic paper (vs. AI-generated fluff, spam, or nonsense)?
- recommendation: "approve" for solid papers, "quarantine" for borderline/uncertain, "reject" for clearly inadequate.

If DOI is not verified or journal is flagged, factor that into your assessment but don't auto-reject — the paper content matters most."""


def assess_quality_with_claude(
    text: str,
    title: str,
    doi_verified: bool,
    journal_flagged: bool,
) -> dict:
    """Use Claude to assess paper quality.

    Args:
        text: Paper text (will be truncated to first 8000 chars).
        title: Paper title.
        doi_verified: Whether the DOI was verified via CrossRef.
        journal_flagged: Whether the journal was flagged for reputation issues.

    Returns:
        Quality assessment dict with scores and recommendation.
    """
    default_assessment = {
        "methodology_described": 0.5,
        "claims_supported": 0.5,
        "writing_quality": 0.5,
        "references_present": 0.5,
        "academic_rigor": 0.5,
        "overall_quality": 0.5,
        "is_likely_genuine": True,
        "concerns": ["Quality assessment unavailable — defaulting to quarantine"],
        "recommendation": "quarantine",
    }

    if not ANTHROPIC_API_KEY:
        default_assessment["concerns"] = ["ANTHROPIC_API_KEY not set — skipping Claude assessment"]
        return default_assessment

    # Truncate text to avoid excessive token usage
    text_truncated = text[:8000] if text else ""
    if len(text_truncated) < 100:
        return {
            "methodology_described": 0.1,
            "claims_supported": 0.1,
            "writing_quality": 0.1,
            "references_present": 0.1,
            "academic_rigor": 0.1,
            "overall_quality": 0.1,
            "is_likely_genuine": False,
            "concerns": ["Extracted text is too short to assess (< 100 chars)"],
            "recommendation": "reject",
        }

    prompt = QUALITY_ASSESSMENT_PROMPT.format(
        title=title or "Unknown",
        doi_verified=str(doi_verified),
        journal_flagged=str(journal_flagged),
        text=text_truncated,
    )

    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "content-type": "application/json",
        "anthropic-version": "2023-06-01",
    }
    body = {
        "model": "claude-sonnet-4-20250514",
        "max_tokens": 1000,
        "temperature": 0.1,
        "messages": [{"role": "user", "content": prompt}],
    }

    try:
        resp = httpx.post(ANTHROPIC_API, json=body, headers=headers, timeout=60)

        # Handle rate limits
        if resp.status_code == 429:
            retry_after = int(resp.headers.get("retry-after", 30))
            print(f"  Rate limited — waiting {retry_after}s...")
            time.sleep(retry_after)
            resp = httpx.post(ANTHROPIC_API, json=body, headers=headers, timeout=60)

        # Handle credit exhaustion
        if resp.status_code in (402, 529):
            print(f"  Credits exhausted (HTTP {resp.status_code}) — using default assessment")
            default_assessment["concerns"] = [
                f"Claude API unavailable (HTTP {resp.status_code}) — defaulting to quarantine"
            ]
            return default_assessment

        resp.raise_for_status()
        response_text = resp.json()["content"][0]["text"]

        # Parse JSON from response
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0]
        elif "```" in response_text:
            response_text = response_text.split("```")[1].split("```")[0]

        assessment = json.loads(response_text.strip())

        # Validate expected keys exist
        required_keys = [
            "methodology_described", "claims_supported", "writing_quality",
            "references_present", "academic_rigor", "overall_quality",
            "is_likely_genuine", "concerns", "recommendation",
        ]
        for key in required_keys:
            if key not in assessment:
                assessment[key] = default_assessment.get(key)

        # Ensure recommendation is valid
        if assessment["recommendation"] not in ("approve", "quarantine", "reject"):
            assessment["recommendation"] = "quarantine"

        return assessment

    except Exception as e:
        print(f"  Claude quality assessment error: {e}")
        default_assessment["concerns"] = [f"Claude API error: {str(e)} — defaulting to quarantine"]
        return default_assessment


# ============================================================
# 4. Duplicate Detection
# ============================================================

def check_duplicate(title: str, doi: str | None) -> dict:
    """Check if a paper with the same DOI or similar title already exists.

    Args:
        title: Paper title.
        doi: Paper DOI (optional).

    Returns:
        Dict with duplicate status and match info.
    """
    result = {"is_duplicate": False, "existing_paper_id": None, "match_type": None}

    # Check by DOI first (exact match)
    if doi:
        doi_clean = doi.strip()
        if doi_clean.startswith("http"):
            doi_clean = re.sub(r"^https?://doi\.org/", "", doi_clean)

        existing = _supabase_get("papers", {
            "doi": f"eq.{doi_clean}",
            "select": "id",
        })
        # Also try with URL prefix
        if not existing:
            existing = _supabase_get("papers", {
                "doi": f"eq.https://doi.org/{doi_clean}",
                "select": "id",
            })
        if existing:
            return {
                "is_duplicate": True,
                "existing_paper_id": existing[0]["id"],
                "match_type": "doi",
            }

    # Check by title (case-insensitive via ilike)
    if title and title.strip():
        # Use PostgREST ilike for case-insensitive match
        existing = _supabase_get("papers", {
            "title": f"ilike.{title.strip()}",
            "select": "id",
        })
        if existing:
            return {
                "is_duplicate": True,
                "existing_paper_id": existing[0]["id"],
                "match_type": "title",
            }

    return result


# ============================================================
# 5. Main Orchestrator
# ============================================================

def process_upload(upload_id: str) -> dict:
    """Process an uploaded paper through the full quality gate pipeline.

    Steps:
        1. Fetch upload record
        2. Verify DOI (if present)
        3. Check journal reputation
        4. Check for duplicates
        5. Run Claude quality assessment
        6. Calculate final score and status
        7. Update upload record
        8. If approved, create paper entry

    Args:
        upload_id: UUID of the paper_uploads record.

    Returns:
        Summary dict with processing results.
    """
    print(f"\n{'='*50}")
    print(f"Processing upload: {upload_id}")
    print(f"{'='*50}")

    # 1. Fetch the upload record
    records = _supabase_get("paper_uploads", {
        "id": f"eq.{upload_id}",
        "select": "*",
    })
    if not records:
        return {"error": f"Upload {upload_id} not found", "status": "error"}

    upload = records[0]
    text = upload.get("extracted_text") or ""
    title = upload.get("extracted_title") or ""
    doi = upload.get("extracted_doi")
    authors = upload.get("extracted_authors")

    print(f"  Title: {title[:80]}...")
    print(f"  DOI: {doi or 'none'}")
    print(f"  Text length: {len(text)} chars")

    # 2. Verify DOI
    doi_result = {"verified": False}
    journal_name = upload.get("journal_name") or ""
    if doi:
        print("  Verifying DOI...")
        doi_result = verify_doi(doi)
        if doi_result["verified"]:
            print(f"    Verified: {doi_result['title'][:60]}")
            # Use CrossRef journal name if we don't have one
            if not journal_name and doi_result.get("journal"):
                journal_name = doi_result["journal"]
        else:
            print("    DOI not verified")

    # 3. Check journal reputation
    print(f"  Checking journal: {journal_name or '(unknown)'}...")
    journal_result = check_journal_reputation(journal_name)
    if journal_result["flagged"]:
        print(f"    FLAGGED: {journal_result['reason']}")
    else:
        print("    Journal OK")

    # 4. Check for duplicates
    print("  Checking duplicates...")
    dup_result = check_duplicate(title, doi)
    if dup_result["is_duplicate"]:
        print(f"    DUPLICATE found (match: {dup_result['match_type']}, paper: {dup_result['existing_paper_id']})")
        # Update upload as rejected (duplicate)
        _supabase_patch(
            "paper_uploads",
            {"id": f"eq.{upload_id}"},
            {
                "quality_status": "rejected",
                "rejection_reason": f"Duplicate paper (matched by {dup_result['match_type']})",
                "paper_id": dup_result["existing_paper_id"],
                "doi_verified": doi_result["verified"],
                "journal_name": journal_name,
                "journal_flagged": journal_result["flagged"],
                "processed_at": datetime.now(tz=timezone.utc).isoformat(),
            },
        )
        return {
            "upload_id": upload_id,
            "status": "rejected",
            "reason": "duplicate",
            "existing_paper_id": dup_result["existing_paper_id"],
            "match_type": dup_result["match_type"],
        }

    # 5. Claude quality assessment
    print("  Running Claude quality assessment...")
    assessment = assess_quality_with_claude(
        text=text,
        title=title,
        doi_verified=doi_result["verified"],
        journal_flagged=journal_result["flagged"],
    )
    print(f"    Overall quality: {assessment.get('overall_quality', '?')}")
    print(f"    Recommendation: {assessment.get('recommendation', '?')}")
    if assessment.get("concerns"):
        for c in assessment["concerns"]:
            print(f"    Concern: {c}")

    # 6. Calculate final quality score
    #    Weighted average of Claude scores + penalties
    weights = {
        "methodology_described": 0.2,
        "claims_supported": 0.2,
        "writing_quality": 0.15,
        "references_present": 0.15,
        "academic_rigor": 0.15,
        "overall_quality": 0.15,
    }
    weighted_score = sum(
        float(assessment.get(k, 0.5)) * w
        for k, w in weights.items()
    )

    # Apply penalties
    if not doi_result["verified"]:
        weighted_score *= 0.9  # 10% penalty for unverified DOI
    if journal_result["flagged"]:
        weighted_score *= 0.85  # 15% penalty for flagged journal
    if not assessment.get("is_likely_genuine", True):
        weighted_score *= 0.5  # 50% penalty if Claude thinks it's not genuine

    quality_score = round(max(0.0, min(1.0, weighted_score)), 3)
    print(f"  Final quality score: {quality_score}")

    # 7. Determine status
    if quality_score >= 0.6 and not journal_result["flagged"]:
        quality_status = "approved"
    elif quality_score < 0.3:
        quality_status = "rejected"
    else:
        quality_status = "quarantined"

    # Override with Claude's recommendation if it's more conservative
    claude_rec = assessment.get("recommendation", "quarantine")
    if claude_rec == "reject" and quality_status != "rejected":
        quality_status = "rejected"
    elif claude_rec == "quarantine" and quality_status == "approved":
        quality_status = "quarantined"

    print(f"  Final status: {quality_status}")

    rejection_reason = None
    if quality_status == "rejected":
        concerns = assessment.get("concerns", [])
        rejection_reason = "; ".join(concerns) if concerns else "Quality score below threshold"

    # 8. Update the paper_uploads record
    crossref_data = doi_result.get("crossref_data")
    update_data = {
        "doi_verified": doi_result["verified"],
        "crossref_data": json.dumps(crossref_data) if crossref_data else None,
        "journal_name": journal_name or None,
        "journal_flagged": journal_result["flagged"],
        "quality_score": quality_score,
        "quality_assessment": json.dumps(assessment),
        "quality_status": quality_status,
        "rejection_reason": rejection_reason,
        "processed_at": datetime.now(tz=timezone.utc).isoformat(),
    }

    paper_id = None

    # 9. If approved, create a paper entry
    if quality_status == "approved":
        print("  Creating paper entry...")
        paper_row = {
            "title": title,
            "authors": json.dumps(authors) if authors else None,
            "abstract": text[:2000] if text else None,
            "full_text": text if text else None,
            "doi": doi,
            "source_journal": journal_name or None,
        }
        result = _supabase_post("papers", paper_row)
        if result:
            paper_id = result[0]["id"]
            update_data["paper_id"] = paper_id
            update_data["approved_at"] = datetime.now(tz=timezone.utc).isoformat()
            print(f"    Paper created: {paper_id}")
        else:
            print("    Failed to create paper entry")
            quality_status = "quarantined"
            update_data["quality_status"] = "quarantined"
            update_data["rejection_reason"] = "Paper creation failed — quarantined for manual review"

    _supabase_patch("paper_uploads", {"id": f"eq.{upload_id}"}, update_data)

    # 10. Return summary
    summary = {
        "upload_id": upload_id,
        "status": quality_status,
        "quality_score": quality_score,
        "doi_verified": doi_result["verified"],
        "journal_flagged": journal_result["flagged"],
        "is_duplicate": False,
        "assessment_recommendation": claude_rec,
        "concerns": assessment.get("concerns", []),
        "paper_id": paper_id,
    }
    print(f"\n  Done: {json.dumps(summary, indent=2)}")
    return summary
