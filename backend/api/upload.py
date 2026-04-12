"""
Paper upload endpoints — upload PDFs, check processing status,
approve/reject quarantined uploads.

Register this router in main.py:
    from backend.api.upload import router as upload_router
    app.include_router(upload_router, prefix="/api", tags=["upload"])
"""

import json
import os
import re
from datetime import datetime, timezone

import httpx
from dotenv import load_dotenv
from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, UploadFile

from backend.pipeline.pdf_extractor import (
    extract_metadata_from_pdf,
    extract_text_from_pdf,
)
from backend.pipeline.paper_quality_gate import process_upload

load_dotenv()

router = APIRouter()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

HEADERS = {
    "apikey": SUPABASE_SERVICE_KEY,
    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}

# Regex for DOI patterns like 10.1234/something
DOI_REGEX = re.compile(r"\b(10\.\d{4,9}/[^\s,;\"')\]]+)")


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
    return None


def _extract_doi_from_text(text: str) -> str | None:
    """Try to find a DOI in the extracted text."""
    if not text:
        return None
    match = DOI_REGEX.search(text[:5000])  # DOI usually near the top
    if match:
        doi = match.group(1).rstrip(".")  # Strip trailing period
        return doi
    return None


def _extract_title_from_text(text: str) -> str:
    """Try to extract a title from the first lines of text."""
    if not text:
        return ""
    lines = text.strip().split("\n")
    # Take first non-empty line that looks like a title
    for line in lines[:10]:
        cleaned = line.strip()
        if len(cleaned) > 10 and len(cleaned) < 300:
            # Skip lines that look like headers/footers
            if any(skip in cleaned.lower() for skip in [
                "page ", "vol.", "volume ", "issn", "doi:", "http",
                "copyright", "all rights reserved",
            ]):
                continue
            return cleaned
    return ""


def _run_processing(upload_id: str):
    """Background task: run the quality gate pipeline."""
    try:
        process_upload(upload_id)
    except Exception as e:
        print(f"ERROR processing upload {upload_id}: {e}")
        # Mark as quarantined on unexpected error
        try:
            _supabase_patch(
                "paper_uploads",
                {"id": f"eq.{upload_id}"},
                {
                    "quality_status": "quarantined",
                    "rejection_reason": f"Processing error: {str(e)[:500]}",
                    "processed_at": datetime.now(tz=timezone.utc).isoformat(),
                },
            )
        except Exception:
            pass


# ============================================================
# Endpoints
# ============================================================

@router.post("/upload")
async def upload_paper(
    file: UploadFile,
    background_tasks: BackgroundTasks,
    user_id: str | None = Query(default=None),
):
    """Upload a PDF paper for processing.

    The file is immediately parsed for text and metadata, then a background
    task runs the full quality gate pipeline (DOI verification, journal check,
    duplicate detection, Claude quality assessment).

    Returns the upload_id for status polling.
    """
    # Validate file type
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")

    # Read file bytes
    pdf_bytes = await file.read()
    if not pdf_bytes:
        raise HTTPException(status_code=400, detail="Empty file")

    file_size = len(pdf_bytes)
    if file_size > 50 * 1024 * 1024:  # 50MB limit
        raise HTTPException(status_code=400, detail="File too large (max 50MB)")

    # Extract text and metadata from PDF
    extracted_text = extract_text_from_pdf(pdf_bytes)
    metadata = extract_metadata_from_pdf(pdf_bytes)

    # Try to get title from metadata, fall back to text extraction
    title = metadata.get("title") or _extract_title_from_text(extracted_text)
    authors = metadata.get("author") or None

    # Try to find DOI in text
    doi = _extract_doi_from_text(extracted_text)

    # Create paper_uploads record
    upload_data = {
        "uploaded_by": user_id,
        "original_filename": file.filename,
        "file_size_bytes": file_size,
        "extracted_text": extracted_text,
        "extracted_title": title,
        "extracted_authors": authors,
        "extracted_doi": doi,
        "quality_status": "pending",
        "created_at": datetime.now(tz=timezone.utc).isoformat(),
    }

    result = _supabase_post("paper_uploads", upload_data)
    if not result:
        raise HTTPException(status_code=500, detail="Failed to create upload record")

    upload_id = result[0]["id"]

    # Kick off background processing
    background_tasks.add_task(_run_processing, upload_id)

    return {
        "upload_id": upload_id,
        "status": "processing",
        "filename": file.filename,
        "file_size_bytes": file_size,
        "extracted_title": title,
        "extracted_doi": doi,
    }


@router.get("/upload/{upload_id}")
async def get_upload_status(upload_id: str):
    """Get the current status and details of a paper upload."""
    records = _supabase_get("paper_uploads", {
        "id": f"eq.{upload_id}",
        "select": "*",
    })
    if not records:
        raise HTTPException(status_code=404, detail="Upload not found")

    record = records[0]

    # Parse JSON fields for cleaner response
    for json_field in ("crossref_data", "quality_assessment"):
        val = record.get(json_field)
        if val and isinstance(val, str):
            try:
                record[json_field] = json.loads(val)
            except (json.JSONDecodeError, TypeError):
                pass

    return record


@router.get("/uploads")
async def list_uploads(
    user_id: str | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    """List paper uploads, optionally filtered by user and/or status."""
    params = {
        "select": (
            "id,uploaded_by,original_filename,file_size_bytes,"
            "extracted_title,extracted_doi,quality_status,quality_score,"
            "rejection_reason,paper_id,created_at,processed_at,approved_at"
        ),
        "order": "created_at.desc",
        "limit": str(limit),
        "offset": str(offset),
    }
    if user_id:
        params["uploaded_by"] = f"eq.{user_id}"
    if status:
        params["quality_status"] = f"eq.{status}"

    records = _supabase_get("paper_uploads", params)
    return {"uploads": records, "count": len(records)}


@router.post("/upload/{upload_id}/approve")
async def approve_upload(upload_id: str):
    """Manually approve a quarantined upload (admin action).

    Creates a paper entry in the papers table and updates the upload status.
    """
    records = _supabase_get("paper_uploads", {
        "id": f"eq.{upload_id}",
        "select": "*",
    })
    if not records:
        raise HTTPException(status_code=404, detail="Upload not found")

    upload = records[0]

    if upload.get("quality_status") == "approved":
        raise HTTPException(status_code=400, detail="Upload is already approved")
    if upload.get("quality_status") == "rejected":
        raise HTTPException(
            status_code=400,
            detail="Cannot approve a rejected upload — re-upload the paper instead",
        )
    if upload.get("quality_status") not in ("quarantined", "pending"):
        raise HTTPException(status_code=400, detail=f"Unexpected status: {upload.get('quality_status')}")

    # Create the paper entry
    text = upload.get("extracted_text") or ""
    paper_row = {
        "title": upload.get("extracted_title") or "",
        "authors": json.dumps(upload.get("extracted_authors")) if upload.get("extracted_authors") else None,
        "abstract": text[:2000] if text else None,
        "full_text": text if text else None,
        "doi": upload.get("extracted_doi"),
        "source_journal": upload.get("journal_name"),
    }

    result = _supabase_post("papers", paper_row)
    if not result:
        raise HTTPException(status_code=500, detail="Failed to create paper entry")

    paper_id = result[0]["id"]

    # Update the upload record
    now = datetime.now(tz=timezone.utc).isoformat()
    _supabase_patch(
        "paper_uploads",
        {"id": f"eq.{upload_id}"},
        {
            "quality_status": "approved",
            "paper_id": paper_id,
            "approved_at": now,
            "rejection_reason": None,
        },
    )

    return {
        "upload_id": upload_id,
        "status": "approved",
        "paper_id": paper_id,
        "approved_at": now,
    }


@router.post("/upload/{upload_id}/reject")
async def reject_upload(
    upload_id: str,
    reason: str = Query(default="Manually rejected by admin"),
):
    """Manually reject an upload (admin action)."""
    records = _supabase_get("paper_uploads", {
        "id": f"eq.{upload_id}",
        "select": "id,quality_status",
    })
    if not records:
        raise HTTPException(status_code=404, detail="Upload not found")

    upload = records[0]

    if upload.get("quality_status") == "rejected":
        raise HTTPException(status_code=400, detail="Upload is already rejected")
    if upload.get("quality_status") == "approved":
        raise HTTPException(
            status_code=400,
            detail="Cannot reject an already-approved upload",
        )

    _supabase_patch(
        "paper_uploads",
        {"id": f"eq.{upload_id}"},
        {
            "quality_status": "rejected",
            "rejection_reason": reason,
            "processed_at": datetime.now(tz=timezone.utc).isoformat(),
        },
    )

    return {
        "upload_id": upload_id,
        "status": "rejected",
        "reason": reason,
    }
