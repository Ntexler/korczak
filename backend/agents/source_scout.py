"""Source Scout — finds verified, relevant source leads for Chappie.

The user's ask: a bot that hunts for websites and verified, relevant
information sources — leads that expand where Chappie can learn.

How it scouts (all free APIs):
1. From our own graph: which journals already back our papers per field
   (papers.source_journal) — proven-relevant leads.
2. OpenAlex /sources: top-cited journals for the field's topics —
   credibility from works_count / cited_by_count / h-index.
3. DOAJ (Directory of Open Access Journals): peer-reviewed OA journals
   by subject — verified open-access leads.

Every lead is:
- SSRF-validated (net_guard) before storage
- Scored for credibility (citations, OA status, review process)
- Stored in manual_sources with status='pending' — ADMIN-GATED like
  everything else. Chappie only learns from approved leads.

Usage:
  python -m backend.agents.source_scout --field Anthropology --limit 10
"""

import argparse
import asyncio
import json
import logging
import sys

import httpx

logger = logging.getLogger(__name__)

OPENALEX_BASE = "https://api.openalex.org"
DOAJ_BASE = "https://doaj.org/api/v3"


async def scout_from_own_graph(field: str, limit: int = 10) -> list[dict]:
    """Journals that already back our papers in this field — proven leads."""
    from backend.integrations.supabase_client import get_client
    from backend.core.fields import get_field_paper_ids

    client = get_client()
    ids = get_field_paper_ids(client, field)
    journal_counts: dict[str, int] = {}
    for i in range(0, min(len(ids), 400), 40):
        rows = client.table("papers").select("source_journal").in_(
            "id", ids[i:i + 40]
        ).execute()
        for p in (rows.data or []):
            j = p.get("source_journal")
            if j:
                journal_counts[j] = journal_counts.get(j, 0) + 1

    top = sorted(journal_counts.items(), key=lambda kv: -kv[1])[:limit]
    return [
        {"name": name, "why": f"already backs {count} of our {field} papers",
         "lead_type": "journal", "discovered_via": "own_graph", "score": min(1.0, count / 10)}
        for name, count in top
    ]


async def scout_openalex_sources(field: str, limit: int = 10) -> list[dict]:
    """Top-cited journals for this field via OpenAlex — free, credibility built in."""
    import os
    params = {
        "search": field,
        "per_page": limit,
        "sort": "cited_by_count:desc",
        "select": "id,display_name,homepage_url,works_count,cited_by_count,summary_stats,is_oa",
    }
    email = os.getenv("OPENALEX_EMAIL")
    if email:
        params["mailto"] = email
    leads = []
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{OPENALEX_BASE}/sources", params=params, timeout=15)
            if resp.status_code == 200:
                for s in resp.json().get("results", []):
                    h_index = (s.get("summary_stats") or {}).get("h_index", 0)
                    leads.append({
                        "name": s.get("display_name", ""),
                        "url": s.get("homepage_url") or "",
                        "why": f"{s.get('works_count', 0):,} works, "
                               f"{s.get('cited_by_count', 0):,} citations, h-index {h_index}"
                               + (", open access" if s.get("is_oa") else ""),
                        "lead_type": "journal",
                        "discovered_via": "openalex",
                        "score": min(1.0, h_index / 200 + (0.1 if s.get("is_oa") else 0)),
                    })
    except Exception as e:
        logger.warning(f"OpenAlex source scout failed: {e}")
    return leads


async def scout_doaj(field: str, limit: int = 10) -> list[dict]:
    """Peer-reviewed open-access journals from DOAJ — verified OA leads."""
    leads = []
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{DOAJ_BASE}/search/journals/{field}",
                params={"pageSize": limit}, timeout=15,
            )
            if resp.status_code == 200:
                for r in resp.json().get("results", []):
                    bib = r.get("bibjson", {})
                    url = ""
                    for ref in bib.get("ref", {}).items() if isinstance(bib.get("ref"), dict) else []:
                        pass
                    ref = bib.get("ref") or {}
                    url = ref.get("journal") if isinstance(ref, dict) else ""
                    leads.append({
                        "name": bib.get("title", ""),
                        "url": url or "",
                        "why": "DOAJ-listed: peer-reviewed open access"
                               + (f", publisher: {(bib.get('publisher') or {}).get('name', '')}"
                                  if bib.get("publisher") else ""),
                        "lead_type": "oa_journal",
                        "discovered_via": "doaj",
                        "score": 0.7,  # DOAJ listing itself is the verification
                    })
    except Exception as e:
        logger.warning(f"DOAJ scout failed: {e}")
    return leads


async def run_scout(field: str, limit_per_source: int = 8, store: bool = True) -> dict:
    """Full scouting run: gather leads, dedupe, validate, store for admin review."""
    own, oa_journals, doaj = await asyncio.gather(
        scout_from_own_graph(field, limit_per_source),
        scout_openalex_sources(field, limit_per_source),
        scout_doaj(field, limit_per_source),
        return_exceptions=True,
    )

    all_leads: list[dict] = []
    seen_names: set[str] = set()
    for batch in (own, oa_journals, doaj):
        if isinstance(batch, Exception):
            continue
        for lead in batch:
            key = (lead.get("name") or "").lower().strip()
            if key and key not in seen_names:
                seen_names.add(key)
                all_leads.append(lead)

    all_leads.sort(key=lambda l: -l.get("score", 0))

    stored = 0
    if store and all_leads:
        from backend.integrations.supabase_client import get_client
        from backend.core.net_guard import is_safe_url
        client = get_client()

        for lead in all_leads:
            url = lead.get("url") or ""
            if url:
                safe, _ = is_safe_url(url)
                if not safe:
                    continue
            try:
                client.table("manual_sources").insert({
                    "url": url or f"lead:{lead['name']}",
                    "field": field,
                    "source_type": "url",
                    "notes": json.dumps({
                        "name": lead["name"],
                        "why": lead["why"],
                        "lead_type": lead["lead_type"],
                        "discovered_via": lead["discovered_via"],
                        "score": lead["score"],
                    }, ensure_ascii=False),
                    "submitted_by": "source_scout",
                    "status": "pending",  # admin approves before Chappie uses it
                }).execute()
                stored += 1
            except Exception as e:
                logger.debug(f"Lead store failed: {e}")

    # Chappie notes what he found
    try:
        from backend.agents.consciousness import log_learning
        if all_leads:
            await log_learning(
                entry_type="discovered",
                summary=f"Scouted {len(all_leads)} source leads for {field} "
                        f"(top: {all_leads[0]['name']})",
                field=field, source="source_scout", confidence=0.6,
            )
    except Exception:
        pass

    return {
        "field": field,
        "leads_found": len(all_leads),
        "stored_for_review": stored,
        "top_leads": all_leads[:10],
    }


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    sys.stdout.reconfigure(encoding="utf-8")
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    parser = argparse.ArgumentParser(description="Scout verified source leads for Chappie")
    parser.add_argument("--field", default="Anthropology")
    parser.add_argument("--limit", type=int, default=8, help="Leads per scout source")
    parser.add_argument("--dry-run", action="store_true", help="Don't store, just print")
    args = parser.parse_args()

    result = asyncio.run(run_scout(args.field, args.limit, store=not args.dry_run))
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
