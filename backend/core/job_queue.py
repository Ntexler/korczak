"""Background Job Queue — for heavy operations that shouldn't block API requests.

Jobs: paper seeding, vault analysis, briefing generation, embedding generation.

Simple DB-backed queue — no Redis/Celery needed for small scale.
For production: swap to ARQ (async Redis queue) when > 100 concurrent users.

Usage:
  # Enqueue a job
  job_id = await enqueue("analyze_paper", {"paper_id": "abc"}, user_id="user1")

  # Process pending jobs (call from a background loop or cron)
  await process_next_job()

  # Check job status
  job = await get_job_status(job_id)
"""

import logging
from datetime import datetime, timezone

from backend.integrations.supabase_client import get_client

logger = logging.getLogger(__name__)


async def enqueue(
    job_type: str,
    payload: dict,
    user_id: str | None = None,
    priority: int = 0,
) -> str:
    """Add a job to the queue. Returns job ID."""
    client = get_client()
    result = client.table("job_queue").insert({
        "job_type": job_type,
        "payload": payload,
        "user_id": user_id,
        "priority": priority,
        "status": "pending",
    }).execute()

    job_id = result.data[0]["id"]
    logger.info(f"Enqueued job {job_type}: {job_id} (priority={priority})")
    return job_id


async def get_job_status(job_id: str) -> dict | None:
    """Get current status of a job."""
    client = get_client()
    result = client.table("job_queue").select("*").eq("id", job_id).execute()
    return result.data[0] if result.data else None


async def get_user_jobs(user_id: str, limit: int = 10) -> list[dict]:
    """Get recent jobs for a user."""
    client = get_client()
    result = client.table("job_queue").select("*").eq(
        "user_id", user_id
    ).order("created_at", desc=True).limit(limit).execute()
    return result.data or []


async def process_next_job() -> dict | None:
    """Pick up and process the next pending job.

    Call this from a background loop:
      while True:
          await process_next_job()
          await asyncio.sleep(1)
    """
    client = get_client()

    # Grab next pending job (highest priority, oldest first)
    pending = client.table("job_queue").select("*").eq(
        "status", "pending"
    ).order("priority", desc=True).order(
        "created_at"
    ).limit(1).execute()

    if not pending.data:
        return None

    job = pending.data[0]
    job_id = job["id"]

    # Mark as processing
    client.table("job_queue").update({
        "status": "processing",
        "started_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", job_id).execute()

    try:
        result = await _execute_job(job)

        # Mark as completed
        client.table("job_queue").update({
            "status": "completed",
            "result": result,
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", job_id).execute()

        logger.info(f"Job {job['job_type']} ({job_id}) completed")
        return result

    except Exception as e:
        logger.error(f"Job {job['job_type']} ({job_id}) failed: {e}")
        client.table("job_queue").update({
            "status": "failed",
            "error": str(e),
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", job_id).execute()
        return None


async def _execute_job(job: dict) -> dict:
    """Route job to appropriate handler."""
    job_type = job["job_type"]
    payload = job.get("payload", {})
    user_id = job.get("user_id")

    if job_type == "vault_analysis":
        from backend.core.vault_parser import parse_vault_zip
        from backend.core.vault_analyzer import analyze_vault, save_analysis
        # payload should contain vault_bytes (base64) or analysis params
        return {"status": "vault_analysis requires direct upload — use /obsidian/import"}

    elif job_type == "generate_embeddings":
        from backend.core.embedding_cache import get_or_create_embedding
        texts = payload.get("texts", [])
        for text in texts[:100]:  # cap at 100 per job
            await get_or_create_embedding(text)
        return {"generated": min(len(texts), 100)}

    elif job_type == "briefing_generation":
        from backend.core.briefing_engine import generate_briefing
        briefing = await generate_briefing(
            user_id=user_id or "mock-user",
            briefing_type=payload.get("briefing_type", "daily"),
        )
        return {"briefing_id": briefing.get("id") if briefing else None}

    elif job_type == "analyze_paper":
        # Single paper analysis
        return {"status": "use seed_optimized.py for batch paper analysis"}

    elif job_type == "seed_papers":
        return {"status": "use seed_optimized.py CLI for paper seeding"}

    elif job_type == "syllabus_scrape":
        return {"status": "use scrape_mit_ocw.py or scrape_open_syllabus.py CLI"}

    else:
        return {"error": f"Unknown job type: {job_type}"}


async def cleanup_old_jobs(days: int = 30) -> int:
    """Delete completed/failed jobs older than N days."""
    client = get_client()
    from datetime import timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    result = client.table("job_queue").delete().in_(
        "status", ["completed", "failed"]
    ).lt("created_at", cutoff).execute()

    count = len(result.data) if result.data else 0
    logger.info(f"Cleaned up {count} old jobs")
    return count
