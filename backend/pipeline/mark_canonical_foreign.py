"""
Mark foreign-language canonical works in the knowledge graph.

Reads data/canonical_foreign.json and for each work:
1. Searches OpenAlex for the work (by title + author)
2. Creates a paper entry (with full analysis via Haiku) or links to existing
3. Marks as canonical with language tag

This ensures Heidegger, Foucault, Ibn Khaldun, Dogen, etc. are present in the graph
and prioritized over random top-cited modern papers.

Usage:
  python -m backend.pipeline.mark_canonical_foreign
  python -m backend.pipeline.mark_canonical_foreign --languages de,fr
  python -m backend.pipeline.mark_canonical_foreign --budget 10
"""

import argparse
import asyncio
import json
import os
import re
import sys
from datetime import datetime, timezone

import httpx
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
OPENALEX_BASE = "https://api.openalex.org"
ANTHROPIC_API = "https://api.anthropic.com/v1/messages"

HAIKU_INPUT_COST = 0.80 / 1_000_000
HAIKU_OUTPUT_COST = 4.0 / 1_000_000

budget_spent = 0.0
budget_limit = 10.0
_lock = None

HEADERS_SUPABASE = {
    "apikey": SUPABASE_SERVICE_KEY,
    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}

from backend.prompts.paper_analysis import ANALYSIS_PROMPT
from backend.pipeline.claim_builder import build_claim_row


async def supabase_get(client, table, params):
    r = await client.get(
        f"{SUPABASE_URL}/rest/v1/{table}", params=params,
        headers={**HEADERS_SUPABASE, "Prefer": ""}, timeout=15,
    )
    return r.json() if r.status_code == 200 else []


async def supabase_post(client, table, data):
    r = await client.post(
        f"{SUPABASE_URL}/rest/v1/{table}",
        json=data, headers=HEADERS_SUPABASE, timeout=15,
    )
    if r.status_code in (200, 201):
        return r.json()
    return None


async def supabase_patch(client, table, params, data):
    r = await client.patch(
        f"{SUPABASE_URL}/rest/v1/{table}", params=params,
        json=data, headers=HEADERS_SUPABASE, timeout=15,
    )
    return r.status_code in (200, 204)


def normalize_name(n):
    return re.sub(r"[^a-z0-9\s]", "", n.lower()).strip()


def reconstruct_abstract(inv):
    if not inv:
        return ""
    pos = []
    for word, poss in inv.items():
        for p in poss:
            pos.append((p, word))
    pos.sort()
    return " ".join(w for _, w in pos)


async def search_openalex(client, title, author, lang_code):
    """Search OpenAlex for a specific work."""
    search = f"{title} {author}".strip()
    try:
        r = await client.get(f"{OPENALEX_BASE}/works", params={
            "search": search,
            "per_page": 5,
            "select": "id,title,authorships,publication_year,abstract_inverted_index,cited_by_count,doi,primary_location,language",
        }, timeout=15)
        if r.status_code != 200:
            return None
        results = r.json().get("results", [])
        # Prefer matches in the target language if available
        for w in results:
            if w.get("language") == lang_code:
                return w
        return results[0] if results else None
    except Exception:
        return None


async def analyze_paper(client, title, authors, year, abstract, lang_code):
    global budget_spent
    if not abstract or len(abstract) < 50:
        return None
    async with _lock:
        if budget_spent >= budget_limit:
            return "STOP"

    prompt = ANALYSIS_PROMPT.format(title=title, authors=authors, year=year, abstract=abstract)
    body = {
        "model": "claude-haiku-4-5-20251001",
        "max_tokens": 2500,
        "temperature": 0.2,
        "messages": [{"role": "user", "content": prompt}],
    }
    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "content-type": "application/json",
        "anthropic-version": "2023-06-01",
    }
    for _ in range(2):
        try:
            r = await client.post(ANTHROPIC_API, json=body, headers=headers, timeout=60)
            if r.status_code == 429:
                await asyncio.sleep(5)
                continue
            if r.status_code in (402, 529):
                return "STOP"
            r.raise_for_status()
            data = r.json()
            text = data["content"][0]["text"]
            usage = data.get("usage", {})
            cost = usage.get("input_tokens", 0) * HAIKU_INPUT_COST + usage.get("output_tokens", 0) * HAIKU_OUTPUT_COST
            async with _lock:
                budget_spent += cost
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0]
            elif "```" in text:
                text = text.split("```")[1].split("```")[0]
            return json.loads(text.strip())
        except Exception:
            continue
    return None


async def get_or_create_concept(client, c):
    norm = normalize_name(c["name"])
    existing = await supabase_get(client, "concepts", {
        "normalized_name": f"eq.{norm}", "select": "id",
    })
    if existing:
        return existing[0]["id"]
    result = await supabase_post(client, "concepts", {
        "name": c["name"], "normalized_name": norm,
        "type": c.get("type", "phenomenon"),
        "definition": c.get("definition"), "confidence": 0.8,
    })
    return result[0]["id"] if result else None


async def process_canonical_work(client, work, lang_code, lang_label, rank):
    """Find/seed a foreign canonical work."""
    title = work["title"]
    author = work.get("author", "")
    year = work.get("year")
    why = work.get("why", "")
    field_tag = f"canonical-{lang_code}"

    # Check canonical_works table
    existing_cw = await supabase_get(client, "canonical_works", {
        "field": f"eq.{field_tag}", "title": f"eq.{title}",
        "select": "id,paper_id",
    })
    if existing_cw and existing_cw[0].get("paper_id"):
        return "already_linked"

    # Create canonical_works row
    if not existing_cw:
        cw_res = await supabase_post(client, "canonical_works", {
            "field": field_tag, "title": title, "author": author,
            "year": year, "why": why, "rank": rank,
        })
        cw_id = cw_res[0]["id"] if cw_res else None
    else:
        cw_id = existing_cw[0]["id"]

    # Search OpenAlex
    raw = await search_openalex(client, title, author, lang_code)
    paper_id = None

    if raw:
        oa_id = raw["id"].split("/")[-1]
        # Check if already in DB
        existing = await supabase_get(client, "papers", {
            "openalex_id": f"eq.{oa_id}", "select": "id",
        })
        if existing:
            paper_id = existing[0]["id"]
        else:
            # Build paper row and analyze if abstract is present
            abstract = reconstruct_abstract(raw.get("abstract_inverted_index"))
            authorships = raw.get("authorships", [])
            authors_json = json.dumps([
                {"name": a.get("author", {}).get("display_name", "")}
                for a in authorships[:10]
            ])

            analysis = None
            if abstract and len(abstract) > 50:
                authors_str = ", ".join(
                    a.get("author", {}).get("display_name", "") for a in authorships[:5]
                )
                analysis = await analyze_paper(
                    client, raw.get("title", title), authors_str,
                    raw.get("publication_year") or year, abstract, lang_code
                )

            paper_row = {
                "openalex_id": oa_id,
                "doi": raw.get("doi"),
                "title": raw.get("title", title),
                "authors": authors_json,
                "publication_year": raw.get("publication_year") or year,
                "abstract": abstract,
                "source_journal": ((raw.get("primary_location") or {}).get("source") or {}).get("display_name"),
                "cited_by_count": raw.get("cited_by_count", 0),
                "language": raw.get("language") or lang_code,
                "canonical": True,
                "canonical_field": field_tag,
                "canonical_rank": rank,
                "canonical_reason": why,
                "is_stub": (analysis is None or isinstance(analysis, str)),
            }
            if analysis and not isinstance(analysis, str):
                pt = analysis.get("paper_type") or {}
                paper_row["paper_type"] = pt.get("type")
                paper_row["subfield"] = pt.get("subfield")
                paper_row["analysis"] = json.dumps(analysis)
                paper_row["analysis_model"] = "claude-haiku-4-5-20251001"
                paper_row["analyzed_at"] = datetime.now(tz=timezone.utc).isoformat()

            result = await supabase_post(client, "papers", paper_row)
            if result:
                paper_id = result[0]["id"]
                # Insert concepts/claims if analyzed
                if analysis and not isinstance(analysis, str):
                    for c in analysis.get("concepts", []):
                        cid = await get_or_create_concept(client, c)
                        if cid:
                            await supabase_post(client, "paper_concepts", {
                                "paper_id": paper_id, "concept_id": cid,
                                "novelty_in_paper": c.get("novelty_at_time", "high"),
                                "well_established": c.get("well_established", True),
                            })
                    for cl in analysis.get("claims", []):
                        ct = cl.get("claim") or cl.get("claim_text")
                        if ct:
                            await supabase_post(
                                client,
                                "claims",
                                build_claim_row(paper_id, cl, claim_text_override=ct),
                            )

    # Pure stub if no OpenAlex match
    if not paper_id:
        row = {
            "title": title,
            "authors": json.dumps([{"name": author}] if author else []),
            "publication_year": year,
            "language": lang_code,
            "cited_by_count": 0,
            "canonical": True,
            "canonical_field": field_tag,
            "canonical_rank": rank,
            "canonical_reason": why,
            "is_stub": True,
        }
        pr = await supabase_post(client, "papers", row)
        if pr:
            paper_id = pr[0]["id"]

    # Link canonical_works → paper
    if paper_id and cw_id:
        await supabase_patch(client, "canonical_works", {"id": f"eq.{cw_id}"}, {
            "paper_id": paper_id,
        })

    return "marked" if paper_id else "failed"


async def async_main():
    global budget_limit, _lock

    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", default="data/canonical_foreign.json")
    parser.add_argument("--languages", default="all")
    parser.add_argument("--budget", type=float, default=10.0)
    args = parser.parse_args()

    budget_limit = args.budget
    _lock = asyncio.Lock()

    with open(args.file) as f:
        data = json.load(f)

    all_langs = list(data["languages"].keys())
    if args.languages == "all":
        selected = all_langs
    else:
        selected = [l.strip() for l in args.languages.split(",")]

    print(f"\n{'='*60}")
    print(f"FOREIGN CANONICAL MARKING")
    print(f"Languages: {', '.join(selected)}")
    print(f"Budget: ${budget_limit}")
    print(f"{'='*60}")

    stats = {"marked": 0, "already": 0, "failed": 0, "stubs": 0}

    async with httpx.AsyncClient() as client:
        for lang in selected:
            if lang not in data["languages"]:
                continue
            if budget_spent >= budget_limit:
                print(f"\n*** BUDGET EXHAUSTED ***")
                break

            lang_data = data["languages"][lang]
            label = lang_data["label"]
            works = lang_data["works"]
            print(f"\n--- {label} ({len(works)} works) ---")

            for rank, work in enumerate(works, 1):
                if budget_spent >= budget_limit:
                    break
                try:
                    result = await process_canonical_work(client, work, lang, label, rank)
                    if result == "marked":
                        stats["marked"] += 1
                        print(f"  [{rank}] ✓ {work['title'][:55]} — {work.get('author','')[:25]}")
                    elif result == "already_linked":
                        stats["already"] += 1
                    else:
                        stats["failed"] += 1
                        print(f"  [{rank}] ✗ {work['title'][:55]}")
                except Exception as e:
                    print(f"  [{rank}] ERROR: {e}")
                    stats["failed"] += 1

    print(f"\n{'='*60}")
    print(f"RESULTS:")
    print(f"  Marked:        {stats['marked']}")
    print(f"  Already:       {stats['already']}")
    print(f"  Failed:        {stats['failed']}")
    print(f"  Cost:          ${budget_spent:.3f} / ${budget_limit}")
    print(f"{'='*60}")


def main():
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
