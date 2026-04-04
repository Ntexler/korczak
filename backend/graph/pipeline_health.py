"""Pipeline Health Monitor — checks external API availability and data freshness.

Checks:
  1. External API health (OpenAlex, Semantic Scholar, CrossRef, Retraction Watch)
  2. Data freshness (newest paper ingested, newest concept updated)
  3. Ingestion stats (papers per day/week, enrichment coverage)
  4. Source evidence coverage (how many papers have multi-source validation)

Usage:
    python -m backend.graph.pipeline_health
"""

import asyncio
import logging
from datetime import datetime, timezone
from dataclasses import dataclass, field

import httpx

from backend.integrations.supabase_client import get_client

logger = logging.getLogger(__name__)

# External APIs to check
API_ENDPOINTS = {
    "openalex": {
        "url": "https://api.openalex.org/works?per_page=1",
        "timeout": 10,
    },
    "semantic_scholar": {
        "url": "https://api.semanticscholar.org/graph/v1/paper/search?query=test&limit=1",
        "timeout": 10,
    },
    "crossref": {
        "url": "https://api.crossref.org/works?rows=1",
        "timeout": 10,
    },
}


@dataclass
class APIStatus:
    name: str
    available: bool
    response_time_ms: int = 0
    error: str | None = None


@dataclass
class PipelineReport:
    timestamp: str
    apis: list[APIStatus] = field(default_factory=list)
    newest_paper_date: str | None = None
    newest_concept_update: str | None = None
    total_papers: int = 0
    papers_with_s2: int = 0
    papers_with_crossref: int = 0
    papers_with_claims: int = 0
    enrichment_coverage_pct: float = 0.0

    @property
    def all_apis_healthy(self) -> bool:
        return all(a.available for a in self.apis)

    def summary(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "all_apis_healthy": self.all_apis_healthy,
            "apis": [
                {"name": a.name, "available": a.available,
                 "response_time_ms": a.response_time_ms, "error": a.error}
                for a in self.apis
            ],
            "data_freshness": {
                "newest_paper_date": self.newest_paper_date,
                "newest_concept_update": self.newest_concept_update,
            },
            "coverage": {
                "total_papers": self.total_papers,
                "papers_with_s2_data": self.papers_with_s2,
                "papers_with_crossref_data": self.papers_with_crossref,
                "papers_with_claims": self.papers_with_claims,
                "enrichment_coverage_pct": round(self.enrichment_coverage_pct, 1),
            },
        }


async def check_api_health() -> list[APIStatus]:
    """Ping external APIs and measure response time."""
    results = []
    async with httpx.AsyncClient() as client:
        for name, cfg in API_ENDPOINTS.items():
            start = datetime.now(timezone.utc)
            try:
                resp = await client.get(cfg["url"], timeout=cfg["timeout"])
                elapsed = (datetime.now(timezone.utc) - start).total_seconds() * 1000
                results.append(APIStatus(
                    name=name,
                    available=resp.status_code == 200,
                    response_time_ms=int(elapsed),
                    error=None if resp.status_code == 200 else f"HTTP {resp.status_code}",
                ))
            except Exception as e:
                elapsed = (datetime.now(timezone.utc) - start).total_seconds() * 1000
                results.append(APIStatus(
                    name=name,
                    available=False,
                    response_time_ms=int(elapsed),
                    error=str(e)[:200],
                ))
    return results


async def check_data_freshness(client) -> tuple[str | None, str | None]:
    """Get the most recent paper and concept update dates."""
    newest_paper = (
        client.table("papers")
        .select("created_at")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    newest_concept = (
        client.table("concepts")
        .select("updated_at")
        .order("updated_at", desc=True)
        .limit(1)
        .execute()
    )
    paper_date = newest_paper.data[0]["created_at"] if newest_paper.data else None
    concept_date = newest_concept.data[0]["updated_at"] if newest_concept.data else None
    return paper_date, concept_date


async def check_enrichment_coverage(client) -> dict:
    """Check how many papers have multi-source validation data."""
    total = client.table("papers").select("id", count="exact").execute()
    total_count = total.count or 0

    # Papers with S2 data (have s2_id or influential_citation_count)
    s2_count = 0
    crossref_count = 0
    try:
        s2 = client.table("source_evidence").select("paper_id", count="exact").eq("source", "semantic_scholar").execute()
        s2_count = s2.count or 0
    except Exception:
        pass

    try:
        cr = client.table("source_evidence").select("paper_id", count="exact").eq("source", "crossref").execute()
        crossref_count = cr.count or 0
    except Exception:
        pass

    # Papers with claims
    claims = client.table("claims").select("paper_id").execute()
    papers_with_claims = len(set(c["paper_id"] for c in claims.data))

    return {
        "total": total_count,
        "s2": s2_count,
        "crossref": crossref_count,
        "claims": papers_with_claims,
    }


async def run_pipeline_health() -> PipelineReport:
    """Run all pipeline health checks."""
    client = get_client()
    report = PipelineReport(timestamp=datetime.now(timezone.utc).isoformat())

    # Check APIs
    report.apis = await check_api_health()

    # Check data freshness
    report.newest_paper_date, report.newest_concept_update = await check_data_freshness(client)

    # Check enrichment coverage
    cov = await check_enrichment_coverage(client)
    report.total_papers = cov["total"]
    report.papers_with_s2 = cov["s2"]
    report.papers_with_crossref = cov["crossref"]
    report.papers_with_claims = cov["claims"]
    report.enrichment_coverage_pct = (
        (cov["s2"] + cov["crossref"]) / (2 * cov["total"]) * 100
        if cov["total"] > 0 else 0
    )

    return report


def print_report(report: PipelineReport):
    """Pretty-print the pipeline health report."""
    print("=" * 60)
    print("KORCZAK PIPELINE HEALTH CHECK")
    print("=" * 60)
    print(f"Timestamp: {report.timestamp}")
    print()

    print("External APIs:")
    for api in report.apis:
        icon = "OK" if api.available else "FAIL"
        print(f"  [{icon}] {api.name:20s} {api.response_time_ms:>5d}ms  {api.error or ''}")
    print()

    print("Data Freshness:")
    print(f"  Newest paper:  {report.newest_paper_date or 'N/A'}")
    print(f"  Newest update: {report.newest_concept_update or 'N/A'}")
    print()

    print("Enrichment Coverage:")
    print(f"  Total papers:       {report.total_papers}")
    print(f"  With S2 data:       {report.papers_with_s2}")
    print(f"  With CrossRef data: {report.papers_with_crossref}")
    print(f"  With claims:        {report.papers_with_claims}")
    print(f"  Overall coverage:   {report.enrichment_coverage_pct:.1f}%")
    print()


if __name__ == "__main__":
    async def main():
        report = await run_pipeline_health()
        print_report(report)

    asyncio.run(main())
