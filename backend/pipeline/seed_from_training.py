"""
Claude Knowledge Reconstruction Pipeline.

For canonical works that are stubs (books/classics with no accessible abstract),
ask Claude directly to reconstruct a comprehensive analysis from its training
knowledge. This is 100% legal — it's generated content, not reproduction.

Works best for well-known canonical texts:
  Kant, Hegel, Nietzsche, Foucault, Dante, Confucius, Dogen, etc.

Usage:
  python -m backend.pipeline.seed_from_training --budget 5
  python -m backend.pipeline.seed_from_training --budget 10 --model sonnet
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

from backend.pipeline.claim_builder import build_claim_row

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
ANTHROPIC_API = "https://api.anthropic.com/v1/messages"

HAIKU_INPUT = 0.80 / 1_000_000
HAIKU_OUTPUT = 4.0 / 1_000_000
SONNET_INPUT = 3.0 / 1_000_000
SONNET_OUTPUT = 15.0 / 1_000_000

CONCURRENCY = 5
budget_spent = 0.0
budget_limit = 5.0
_lock = None

HEADERS_SUPABASE = {
    "apikey": SUPABASE_SERVICE_KEY,
    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}


RECONSTRUCTION_PROMPT = """You are an expert scholar with deep knowledge of the canonical works of world thought. Analyze the following classic work based on your training knowledge. You are NOT reproducing copyrighted text — you are generating your own scholarly analysis.

WORK: {title}
AUTHOR: {author}
YEAR: {year}
LANGUAGE: {lang}
WHY CANONICAL: {why}

Produce a comprehensive JSON analysis with these fields:

1. paper_type: {{"type": "book|theoretical|original_research|philosophical_treatise|religious_text|literary_work|scientific_treatise", "subfield": str, "summary": str}}
   - summary: 2-3 sentences capturing the work's core contribution

2. concepts: Array of 10-15 central concepts the work introduces or is central to. For each:
   {{"name": str, "type": "theory|method|framework|phenomenon|tool|metric|critique|paradigm", "definition": str, "novelty_at_time": "high|medium|low", "well_established": bool}}
   - Include the KEY TERMS the work is known for (e.g. for Heidegger: Dasein, being-in-the-world, authenticity, Mitsein)
   - For foreign works, include original language terms AND English translations
   - definition: 1-2 sentences explaining each

3. claims: Array of 5-10 MAJOR CLAIMS/ARGUMENTS the work makes. For each:
   {{"claim": str, "evidence_type": "empirical|theoretical|comparative|methodological", "strength": "strong|moderate|weak", "testable": bool}}
   - Focus on the central theses, not minor points

4. relationships: Array of 5-10 relationships to OTHER specific works/authors:
   {{"from": str, "to": str, "type": "BUILDS_ON|CONTRADICTS|EXTENDS|APPLIES|RESPONDS_TO|ANALOGOUS_TO", "confidence": float, "explanation": str}}
   - Name specific works (e.g. "Hegel's Phenomenology of Spirit" not "German idealism")
   - confidence 0.8+ for well-established scholarly consensus

5. historical_significance:
   {{"paradigm_shift": bool, "influenced_fields": [str], "controversy_generated": str, "lasting_impact": str}}
   - paradigm_shift: only TRUE for truly field-defining works
   - lasting_impact: 2-3 sentences on what this work changed in its field

Return ONLY valid JSON with keys: paper_type, concepts, claims, relationships, historical_significance

Be thorough — this is a canonical work, deserving of detailed analysis."""


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
        "definition": c.get("definition"), "confidence": 0.85,
    })
    return result[0]["id"] if result else None


async def reconstruct_analysis(client, paper, model="haiku"):
    """Ask Claude to generate a comprehensive analysis from training knowledge."""
    global budget_spent
    async with _lock:
        if budget_spent >= budget_limit:
            return "STOP"

    # Extract metadata
    title = paper["title"]
    authors_raw = paper.get("authors", "[]")
    try:
        authors_list = json.loads(authors_raw) if isinstance(authors_raw, str) else authors_raw
        author = authors_list[0].get("name", "") if authors_list else ""
    except Exception:
        author = ""
    year = paper.get("publication_year", 0)
    why = paper.get("canonical_reason", "")
    lang = paper.get("language", "en") or "en"

    lang_names = {
        "en": "English", "de": "German", "fr": "French", "ru": "Russian",
        "ja": "Japanese", "zh": "Chinese", "es": "Spanish", "it": "Italian",
        "ar": "Arabic", "am": "Amharic", "he": "Hebrew",
    }
    lang_label = lang_names.get(lang, lang)

    prompt = RECONSTRUCTION_PROMPT.format(
        title=title, author=author, year=year, why=why, lang=lang_label
    )

    if model == "sonnet":
        model_id = "claude-sonnet-4-20250514"
        in_cost, out_cost = SONNET_INPUT, SONNET_OUTPUT
    else:
        model_id = "claude-haiku-4-5-20251001"
        in_cost, out_cost = HAIKU_INPUT, HAIKU_OUTPUT

    body = {
        "model": model_id,
        "max_tokens": 5000,
        "temperature": 0.3,
        "messages": [{"role": "user", "content": prompt}],
    }
    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "content-type": "application/json",
        "anthropic-version": "2023-06-01",
    }
    for _ in range(2):
        try:
            r = await client.post(ANTHROPIC_API, json=body, headers=headers, timeout=180)
            if r.status_code == 429:
                await asyncio.sleep(10)
                continue
            if r.status_code in (402, 529):
                return "STOP"
            r.raise_for_status()
            data = r.json()
            text = data["content"][0]["text"]
            usage = data.get("usage", {})
            cost = usage.get("input_tokens", 0) * in_cost + usage.get("output_tokens", 0) * out_cost
            async with _lock:
                budget_spent += cost
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0]
            elif "```" in text:
                text = text.split("```")[1].split("```")[0]
            return json.loads(text.strip())
        except httpx.ReadTimeout:
            continue
        except json.JSONDecodeError:
            return None
        except Exception as e:
            print(f"    Error: {e}")
            return None
    return None


async def update_paper_from_reconstruction(client, paper_id, analysis):
    """Persist reconstruction as paper analysis + concepts/claims/relationships."""
    pt = analysis.get("paper_type", {}) or {}
    await supabase_patch(client, "papers", {"id": f"eq.{paper_id}"}, {
        "paper_type": pt.get("type"),
        "subfield": pt.get("subfield"),
        "abstract": pt.get("summary"),  # Use summary as abstract
        "analysis": json.dumps(analysis),
        "analysis_model": "claude-haiku-4-5-20251001-reconstructed",
        "analyzed_at": datetime.now(tz=timezone.utc).isoformat(),
        "is_stub": False,
    })

    concept_ids = {}
    for c in analysis.get("concepts", []):
        cid = await get_or_create_concept(client, c)
        if cid:
            concept_ids[c["name"]] = cid
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
                build_claim_row(paper_id, cl, default_strength="strong", claim_text_override=ct),
            )
    for rel in analysis.get("relationships", []):
        from_name = rel.get("from", "")
        to_name = rel.get("to", "")
        if not from_name or not to_name:
            continue
        from_id = concept_ids.get(from_name) or await get_or_create_concept(client, {"name": from_name, "type": "phenomenon"})
        to_id = concept_ids.get(to_name) or await get_or_create_concept(client, {"name": to_name, "type": "phenomenon"})
        if from_id and to_id:
            await supabase_post(client, "relationships", {
                "source_type": "concept", "source_id": from_id,
                "target_type": "concept", "target_id": to_id,
                "relationship_type": rel.get("type", "BUILDS_ON"),
                "confidence": rel.get("confidence", 0.8),
                "explanation": rel.get("explanation"),
                "paper_id": paper_id,
            })


async def process_stub(client, paper, sem, stats, model):
    if budget_spent >= budget_limit:
        return
    async with sem:
        if budget_spent >= budget_limit:
            return
        analysis = await reconstruct_analysis(client, paper, model)
        if analysis == "STOP":
            return
        if not analysis or isinstance(analysis, str):
            stats["failed"] += 1
            return
        await update_paper_from_reconstruction(client, paper["id"], analysis)
        stats["success"] += 1
        n_c = len(analysis.get("concepts", []))
        n_r = len(analysis.get("relationships", []))
        n_cl = len(analysis.get("claims", []))
        print(f"  ✓ [{stats['success']}] {paper['title'][:55]} ({n_c}c/{n_cl}cl/{n_r}r) ${budget_spent:.3f}")


async def async_main():
    global budget_limit, _lock

    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--budget", type=float, default=5.0)
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--model", choices=["haiku", "sonnet"], default="haiku")
    parser.add_argument("--fields", help="Comma-separated canonical fields to process")
    args = parser.parse_args()

    budget_limit = args.budget
    _lock = asyncio.Lock()

    async with httpx.AsyncClient() as client:
        params = {
            "canonical": "eq.true",
            "is_stub": "eq.true",
            "select": "id,title,authors,publication_year,canonical_field,canonical_reason,language",
            "limit": str(args.limit),
        }
        if args.fields:
            fields = [f.strip() for f in args.fields.split(",")]
            # PostgREST syntax: canonical_field=in.(a,b,c)
            params["canonical_field"] = f"in.({','.join(fields)})"
        papers = await supabase_get(client, "papers", params)

        print(f"\n{'='*60}")
        print(f"CLAUDE KNOWLEDGE RECONSTRUCTION")
        print(f"Model: {args.model} | Budget: ${budget_limit} | Stubs to process: {len(papers)}")
        print(f"{'='*60}\n")

        sem = asyncio.Semaphore(CONCURRENCY)
        stats = {"success": 0, "failed": 0}
        batch_size = CONCURRENCY * 2
        for i in range(0, len(papers), batch_size):
            if budget_spent >= budget_limit:
                print("\n*** BUDGET LIMIT ***")
                break
            batch = papers[i:i+batch_size]
            await asyncio.gather(*[process_stub(client, p, sem, stats, args.model) for p in batch])

        print(f"\n{'='*60}")
        print(f"RESULTS:")
        print(f"  Successfully reconstructed: {stats['success']}")
        print(f"  Failed:                     {stats['failed']}")
        print(f"  Cost:                       ${budget_spent:.3f} / ${budget_limit}")
        print(f"{'='*60}")


def main():
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
