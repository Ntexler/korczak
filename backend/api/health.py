"""Health check endpoints."""

import logging

from fastapi import APIRouter

from backend.graph.consistency_checker import run_consistency_check
from backend.graph.pipeline_health import run_pipeline_health
from backend.graph.quality_monitor import run_quality_check
from backend.graph.cost_monitor import run_cost_check

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/health")
async def health_check():
    return {"status": "ok", "service": "korczak-api"}


@router.get("/health/detailed")
async def detailed_health():
    """Run all monitors and return aggregated health report."""
    try:
        consistency = await run_consistency_check()
        pipeline = await run_pipeline_health()
        quality = await run_quality_check(limit=50)
        cost = await run_cost_check(days=30)

        overall_healthy = (
            consistency.healthy
            and pipeline.all_apis_healthy
            and quality.healthy
        )

        return {
            "status": "healthy" if overall_healthy else "degraded",
            "graph": consistency.summary(),
            "pipeline": pipeline.summary(),
            "quality": quality.summary(),
            "cost": cost.summary(),
        }
    except Exception as e:
        logger.error(f"Health check error: {e}", exc_info=True)
        return {
            "status": "error",
            "error": str(e),
        }
