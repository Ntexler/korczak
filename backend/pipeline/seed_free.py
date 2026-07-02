"""
Free Knowledge Graph Pipeline — build the graph at zero LLM cost.

Layer 0 of Korczak's knowledge: everything here comes from open academic
infrastructure, no Claude calls needed.

Sources (all free):
- OpenAlex topics/concepts  → concept nodes, pre-classified per paper
- OpenAlex referenced_works → CITES relationship edges between papers
- Semantic Scholar TLDR     → AI summaries for papers missing abstracts
- Wikipedia summaries       → VALIDATION ONLY, never the academic base
  (a Wikipedia-only definition is marked consensus_status='unverified')

Principle: only academic sources form Korczak's base knowledge.
Wikipedia can corroborate; it cannot establish.

Usage:
  python -m backend.pipeline.seed_free --domain anthropology --limit 500
  python -m backend.pipeline.seed_free --all-fields --limit 300
  python -m backend.pipeline.seed_free --enrich-tldr          # fill missing abstracts
  python -m backend.pipeline.seed_free --wiki-validate        # validate concepts vs Wikipedia
"""

import argparse
import json
import os
import sys
import time

import httpx
from dotenv import load_dotenv

load_dotenv()

import backend.pipeline.seed_optimized as seed_opt
from backend.pipeline.seed_optimized import (
    DOMAINS,
    init_supabase_headers,
    supabase_post,
    supabase_get,
    normalize_name,
    reconstruct_abstract,
    extract_authors,
)


def _headers() -> dict:
    """Live reference — init_supabase_headers() rebinds the module global."""
    return seed_opt.HEADERS_SUPABASE

SUPABASE_URL = os.getenv("SUPABASE_URL")
OPENALEX_BASE = "https://api.openalex.org"
S2_BASE = "https://api.semanticscholar.org/graph/v1"
WIKI_BASE = "https://en.wikipedia.org/api/rest_v1/page/summary"


# ─── OpenAlex fetch (with the fields the paid pipeline throws away) ─────────

def fetch_page(topic_id: str, per_page: int = 50, cursor: str = "*") -> dict:
    params = {
        "filter": (
            f"topics.id:{topic_id},"
            "has_abstract:true,language:en,type:article,"
            "from_publication_date:2010-01-01"
        ),
        "sort": "cited_by_count:desc",
        "per_page": per_page,
        "cursor": cursor,
        "select": (
            "id,title,authorships,publication_year,abstract_inverted_index,"
            "cited_by_count,doi,primary_location,topics,concepts,referenced_works"
        ),
    }
    email = os.getenv("OPENALEX_EMAIL")
    if email:
        params["mailto"] = email
    resp = httpx.get(f"{OPENALEX_BASE}/works", params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def paper_exists(openalex_id: str) -> str | None:
    rows = supabase_get("papers", {"openalex_id": f"eq.{openalex_id}", "select": "id"})
    return rows[0]["id"] if rows else None


# ─── Free concept extraction (OpenAlex classifications) ─────────────────────

# OpenAlex concept levels → rough Korczak type mapping
LEVEL_TO_TYPE = {0: "paradigm", 1: "framework", 2: "phenomenon", 3: "phenomenon", 4: "method", 5: "method"}

_concept_cache: dict[str, str] = {}  # normalized_name -> our concept id


def get_or_create_concept_free(name: str, level: int, subfield_hint: str = "") -> str | None:
    """Create a concept from OpenAlex classification. Academic base, no LLM."""
    norm = normalize_name(name)
    if not norm or len(norm) < 3:
        return None
    if norm in _concept_cache:
        return _concept_cache[norm]

    existing = supabase_get("concepts", {"normalized_name": f"eq.{norm}", "select": "id"})
    if existing:
        _concept_cache[norm] = existing[0]["id"]
        return existing[0]["id"]

    row = {
        "name": name,
        "normalized_name": norm,
        "type": LEVEL_TO_TYPE.get(level, "phenomenon"),
        "definition": None,  # filled later by papers/Claude/wiki-validation
        "confidence": 0.5,
        "definition_source": "openalex",
        "consensus_status": "emerging",
    }
    result = supabase_post("concepts", row)
    if result:
        _concept_cache[norm] = result[0]["id"]
        return result[0]["id"]
    return None


def insert_paper_free(raw: dict) -> tuple[str | None, list[str]]:
    """Insert a paper using only OpenAlex data. Returns (paper_id, referenced_openalex_ids)."""
    openalex_id = raw.get("id", "").split("/")[-1]
    refs = [r.split("/")[-1] for r in (raw.get("referenced_works") or [])]

    existing_id = paper_exists(openalex_id)
    if existing_id:
        return None, refs  # already in — still return refs for edge-building

    abstract = reconstruct_abstract(raw.get("abstract_inverted_index"))
    paper_row = {
        "openalex_id": openalex_id,
        "doi": raw.get("doi"),
        "title": raw.get("title", ""),
        "authors": json.dumps(extract_authors(raw.get("authorships", []))),
        "publication_year": raw.get("publication_year"),
        "abstract": abstract,
        "subfield": ((raw.get("topics") or [{}])[0].get("display_name")),
        "source_journal": ((raw.get("primary_location") or {}).get("source") or {}).get("display_name"),
        "cited_by_count": raw.get("cited_by_count", 0),
        "analysis_model": "openalex_free",
    }
    result = supabase_post("papers", paper_row)
    if not result:
        return None, refs
    paper_id = result[0]["id"]

    # Concepts from OpenAlex classification (score >= 0.4 keeps it meaningful)
    for c in (raw.get("concepts") or []):
        score = c.get("score", 0)
        if score < 0.4:
            continue
        cid = get_or_create_concept_free(c.get("display_name", ""), c.get("level", 2))
        if cid:
            supabase_post("paper_concepts", {
                "paper_id": paper_id,
                "concept_id": cid,
                "relevance": round(score, 3),
                "well_established": True,
            })

    return paper_id, refs


def build_citation_edges(ref_map: dict[str, list[str]]) -> int:
    """Create CITES relationships between papers we actually have.

    ref_map: our_paper_id -> [referenced openalex_ids]
    """
    # Build openalex_id -> our id lookup for all referenced ids, batched
    all_refs = sorted({r for refs in ref_map.values() for r in refs})
    oa_to_ours: dict[str, str] = {}
    for i in range(0, len(all_refs), 40):
        batch = all_refs[i:i + 40]
        rows = supabase_get("papers", {
            "openalex_id": f"in.({','.join(batch)})",
            "select": "id,openalex_id",
        })
        for row in rows:
            oa_to_ours[row["openalex_id"]] = row["id"]

    created = 0
    for src_id, refs in ref_map.items():
        for ref_oa in refs:
            tgt_id = oa_to_ours.get(ref_oa)
            if not tgt_id or tgt_id == src_id:
                continue
            result = supabase_post("relationships", {
                "source_type": "paper", "source_id": src_id,
                "target_type": "paper", "target_id": tgt_id,
                "relationship_type": "CITES",
                "confidence": 1.0,  # citations are factual, not inferred
                "explanation": "Direct citation (OpenAlex referenced_works)",
            })
            if result:
                created += 1
    return created


# ─── Semantic Scholar TLDR enrichment (free) ────────────────────────────────

def enrich_tldrs(limit: int = 200) -> int:
    """Fill missing/short abstracts with Semantic Scholar TLDRs. Free API."""
    papers = supabase_get("papers", {
        "select": "id,doi,abstract",
        "doi": "not.is.null",
        "limit": str(limit),
    })
    enriched = 0
    for p in papers:
        if p.get("abstract") and len(p["abstract"]) > 100:
            continue
        doi = (p.get("doi") or "").replace("https://doi.org/", "")
        if not doi:
            continue
        try:
            resp = httpx.get(f"{S2_BASE}/paper/DOI:{doi}", params={"fields": "tldr"}, timeout=10)
            if resp.status_code == 200:
                tldr = (resp.json().get("tldr") or {}).get("text", "")
                if tldr:
                    httpx.patch(
                        f"{SUPABASE_URL}/rest/v1/papers?id=eq.{p['id']}",
                        json={"abstract": tldr},
                        headers=_headers(), timeout=10,
                    )
                    enriched += 1
            time.sleep(1.1)  # S2 free tier: ~1 req/sec unauthenticated
        except Exception as e:
            print(f"    TLDR fetch failed for {doi}: {e}")
    return enriched


# ─── Wikipedia validation (VALIDATION ONLY — never the base) ────────────────

def wiki_validate_concepts(limit: int = 100) -> dict:
    """Cross-check concepts against Wikipedia.

    - Concept HAS an academic definition → wiki match recorded as validation boost.
    - Concept has NO definition → wiki summary used as placeholder BUT marked
      consensus_status='unverified' + definition_source='wikipedia'.
      It will not count as base knowledge until papers back it.
    """
    from datetime import datetime, timezone

    concepts = supabase_get("concepts", {
        "select": "id,name,definition,definition_source",
        "limit": str(limit),
        "order": "paper_count.desc",
    })
    validated = 0
    placeholders = 0

    for c in concepts:
        title = c["name"].replace(" ", "_")
        try:
            resp = httpx.get(f"{WIKI_BASE}/{title}", timeout=10,
                             headers={"User-Agent": "KorczakAI/1.0 (academic knowledge graph)"})
            if resp.status_code != 200:
                continue
            data = resp.json()
            extract = data.get("extract", "")
            if not extract or data.get("type") == "disambiguation":
                continue

            validation = {
                "wikipedia": {
                    "matches": True,
                    "url": data.get("content_urls", {}).get("desktop", {}).get("page", ""),
                    "checked_at": datetime.now(timezone.utc).isoformat(),
                }
            }
            patch: dict = {"external_validation": validation}

            if c.get("definition"):
                # Academic definition exists — Wikipedia only corroborates
                validated += 1
            else:
                # No academic definition — wiki fills the gap but stays UNVERIFIED
                patch["definition"] = extract[:500]
                patch["definition_source"] = "wikipedia"
                patch["consensus_status"] = "unverified"
                placeholders += 1

            httpx.patch(
                f"{SUPABASE_URL}/rest/v1/concepts?id=eq.{c['id']}",
                json=patch, headers=_headers(), timeout=10,
            )
            time.sleep(0.3)
        except Exception as e:
            print(f"    Wiki check failed for {c['name']}: {e}")

    return {"validated": validated, "unverified_placeholders": placeholders}


# ─── Main free-seeding loop ─────────────────────────────────────────────────

def seed_domain_free(domain_key: str, limit: int) -> dict:
    domain = DOMAINS[domain_key]
    print(f"\n{'='*60}\nFREE SEEDING: {domain['label']} (target {limit}, $0.00)\n{'='*60}")

    cursor = "*"
    inserted = 0
    skipped = 0
    ref_map: dict[str, list[str]] = {}

    while inserted < limit:
        try:
            data = fetch_page(domain["topic_id"], min(50, limit - inserted + 10), cursor)
        except Exception as e:
            print(f"  OpenAlex error: {e}")
            break

        results = data.get("results", [])
        cursor = data.get("meta", {}).get("next_cursor")
        if not results or not cursor:
            break

        for raw in results:
            if inserted >= limit:
                break
            paper_id, refs = insert_paper_free(raw)
            if paper_id:
                inserted += 1
                if refs:
                    ref_map[paper_id] = refs
                if inserted % 25 == 0:
                    print(f"  [{inserted}/{limit}] {raw.get('title', '')[:55]}...")
            else:
                skipped += 1
        time.sleep(0.2)

    print(f"  Building citation edges from {len(ref_map)} papers...")
    edges = build_citation_edges(ref_map)
    print(f"  Done: {inserted} papers, {edges} CITES edges, {skipped} skipped — cost: $0.00")
    return {"inserted": inserted, "edges": edges, "skipped": skipped}


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Free knowledge graph seeding (zero LLM cost)")
    parser.add_argument("--domain", choices=list(DOMAINS.keys()))
    parser.add_argument("--all-fields", action="store_true")
    parser.add_argument("--limit", type=int, default=300)
    parser.add_argument("--enrich-tldr", action="store_true", help="Fill missing abstracts from Semantic Scholar")
    parser.add_argument("--wiki-validate", action="store_true", help="Cross-check concepts vs Wikipedia (validation only)")
    args = parser.parse_args()

    if not SUPABASE_URL:
        print("ERROR: Set SUPABASE_URL and SUPABASE_SERVICE_KEY in .env")
        sys.exit(1)
    init_supabase_headers()

    if args.enrich_tldr:
        n = enrich_tldrs()
        print(f"TLDR-enriched {n} papers")
        return
    if args.wiki_validate:
        result = wiki_validate_concepts()
        print(f"Wikipedia validation: {result}")
        return

    domains = list(DOMAINS.keys()) if args.all_fields else ([args.domain] if args.domain else None)
    if not domains:
        parser.error("Specify --domain, --all-fields, --enrich-tldr, or --wiki-validate")

    totals = {"inserted": 0, "edges": 0}
    for d in domains:
        r = seed_domain_free(d, args.limit)
        totals["inserted"] += r["inserted"]
        totals["edges"] += r["edges"]

    print(f"\n{'='*60}\nTOTAL: {totals['inserted']} papers, {totals['edges']} citation edges — TOTAL COST: $0.00\n{'='*60}")


if __name__ == "__main__":
    main()
