"""
Foreign-language seeding pipeline.

Seeds top-cited papers in non-English languages from OpenAlex.
Makes the knowledge graph multilingual — captures canonical knowledge
not available in English.

Priority languages (Phase 3 accessibility):
  he (Hebrew) - especially Israeli research
  ar (Arabic)
  am (Amharic)
  ru (Russian)

Also seeds important knowledge corpora:
  de (German - philosophy, history of science)
  fr (French - post-structuralism, sociology)
  ja (Japanese - Zen, technology)
  zh (Chinese - classical philosophy, TCM)
  es (Spanish - decolonial theory)
  it (Italian - Renaissance, semiotics)

Usage:
  python -m backend.pipeline.seed_foreign --budget 30
  python -m backend.pipeline.seed_foreign --budget 30 --languages he,ar,am,ru
  python -m backend.pipeline.seed_foreign --language he --israeli-only --limit 500
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

CONCURRENCY = 10
budget_spent = 0.0
budget_limit = 30.0
papers_analyzed = 0
_budget_lock = None

HEADERS_SUPABASE = {}

# Priority languages for accessibility (translated TO these)
# Also languages with unique canonical knowledge (seed FROM these)
LANGUAGE_LABELS = {
    "he": "Hebrew (incl. Israeli research)",
    "ar": "Arabic",
    "am": "Amharic (Ethiopia)",
    "ru": "Russian",
    "de": "German",
    "fr": "French",
    "ja": "Japanese",
    "zh": "Chinese",
    "es": "Spanish",
    "it": "Italian",
    "pt": "Portuguese",
    "ko": "Korean",
    "hi": "Hindi",
}

# Default priority order
DEFAULT_LANGS = ["he", "ar", "am", "ru", "de", "fr", "ja", "zh", "es", "it"]


def init_supabase_headers():
    global HEADERS_SUPABASE
    HEADERS_SUPABASE = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


from backend.prompts.paper_analysis import ANALYSIS_PROMPT
from backend.pipeline.claim_builder import build_claim_row


# --- Supabase ---

async def supabase_get(client, table, params):
    r = await client.get(
        f"{SUPABASE_URL}/rest/v1/{table}",
        params=params, headers={**HEADERS_SUPABASE, "Prefer": ""}, timeout=15,
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


def normalize_name(name):
    return re.sub(r"[^a-z0-9\s]", "", name.lower()).strip()


def reconstruct_abstract(inv):
    if not inv:
        return ""
    positions = []
    for word, poss in inv.items():
        for p in poss:
            positions.append((p, word))
    positions.sort()
    return " ".join(w for _, w in positions)


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
        "definition": c.get("definition"), "confidence": 0.5,
    })
    return result[0]["id"] if result else None


# --- OpenAlex fetch ---

async def fetch_foreign_papers(client, lang_code, per_page=50, cursor="*", israeli_only=False, field_ids=None):
    """Fetch papers in a specific language, sorted by citations.
    field_ids: optional list of OpenAlex field IDs to restrict to (e.g. ['33','32','20'] for social sciences, psychology, economics)."""
    filter_parts = [
        f"language:{lang_code}",
        "has_abstract:true",
        "type:article",
        "from_publication_date:2000-01-01",
    ]
    if israeli_only and lang_code == "he":
        filter_parts.append("authorships.institutions.country_code:IL")
    if field_ids:
        filter_parts.append(f"primary_topic.field.id:{'|'.join(field_ids)}")

    params = {
        "filter": ",".join(filter_parts),
        "sort": "cited_by_count:desc",
        "per_page": str(per_page),
        "cursor": cursor,
        "select": "id,title,authorships,publication_year,abstract_inverted_index,cited_by_count,doi,primary_location,language",
    }
    email = os.getenv("OPENALEX_EMAIL")
    if email:
        params["mailto"] = email
    try:
        r = await client.get(f"{OPENALEX_BASE}/works", params=params, timeout=30)
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        print(f"  OpenAlex error: {e}")
    return {}


# --- Claude analysis ---

async def analyze_paper(client, title, authors, year, abstract, lang_code):
    """Analyze with Haiku. The prompt works for any language since Claude handles it."""
    global budget_spent, papers_analyzed

    if not abstract or len(abstract) < 50:
        return None
    async with _budget_lock:
        if budget_spent >= budget_limit:
            return "STOP"

    # Add language hint to prompt
    lang_hint = f"\n\nNote: This paper is in {LANGUAGE_LABELS.get(lang_code, lang_code)}. Extract concepts and claims in English for the knowledge graph, but preserve key terms in the original language where meaningful."
    prompt = ANALYSIS_PROMPT.format(title=title, authors=authors, year=year, abstract=abstract) + lang_hint

    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "content-type": "application/json",
        "anthropic-version": "2023-06-01",
    }
    body = {
        "model": "claude-haiku-4-5-20251001",
        "max_tokens": 2500,
        "temperature": 0.2,
        "messages": [{"role": "user", "content": prompt}],
    }

    for attempt in range(2):
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
            async with _budget_lock:
                budget_spent += cost
                papers_analyzed += 1
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0]
            elif "```" in text:
                text = text.split("```")[1].split("```")[0]
            return json.loads(text.strip())
        except httpx.ReadTimeout:
            continue
        except json.JSONDecodeError:
            return None
        except Exception:
            return None
    return None


async def insert_paper(client, raw, analysis, lang_code):
    try:
        oa_id = raw["id"].split("/")[-1]
        # Skip if exists
        existing = await supabase_get(client, "papers", {"openalex_id": f"eq.{oa_id}", "select": "id"})
        if existing:
            return existing[0]["id"]

        pt = analysis.get("paper_type") or {}
        authorships = raw.get("authorships", [])
        authors_json = json.dumps([
            {"name": a.get("author", {}).get("display_name", ""),
             "institution": (a.get("institutions", [{}])[0].get("display_name") if a.get("institutions") else None),
             "country": (a.get("institutions", [{}])[0].get("country_code") if a.get("institutions") else None)}
            for a in authorships[:10]
        ])
        paper_row = {
            "openalex_id": oa_id,
            "doi": raw.get("doi"),
            "title": raw.get("title", ""),
            "authors": authors_json,
            "publication_year": raw.get("publication_year"),
            "abstract": reconstruct_abstract(raw.get("abstract_inverted_index")),
            "paper_type": pt.get("type"),
            "subfield": pt.get("subfield"),
            "source_journal": ((raw.get("primary_location") or {}).get("source") or {}).get("display_name"),
            "cited_by_count": raw.get("cited_by_count", 0),
            "language": lang_code,
            "analysis": json.dumps(analysis),
            "analysis_model": "claude-haiku-4-5-20251001",
            "analyzed_at": datetime.now(tz=timezone.utc).isoformat(),
        }
        result = await supabase_post(client, "papers", paper_row)
        if not result:
            return None
        paper_id = result[0]["id"]

        concept_ids = {}
        for c in analysis.get("concepts", []):
            cid = await get_or_create_concept(client, c)
            if cid:
                concept_ids[c["name"]] = cid
                await supabase_post(client, "paper_concepts", {
                    "paper_id": paper_id, "concept_id": cid,
                    "novelty_in_paper": c.get("novelty_at_time", "low"),
                    "well_established": c.get("well_established", True),
                })
        for cl in analysis.get("claims", []):
            claim_text = cl.get("claim") or cl.get("claim_text")
            if claim_text:
                await supabase_post(
                    client,
                    "claims",
                    build_claim_row(paper_id, cl, claim_text_override=claim_text),
                )
        return paper_id
    except Exception as e:
        print(f"    Insert error: {e}")
        return None


# --- Seeding pipeline ---

async def seed_language(client, lang_code, limit, israeli_only=False, field_ids=None):
    label = LANGUAGE_LABELS.get(lang_code, lang_code)
    israeli_tag = " [ISRAELI-ONLY]" if israeli_only else ""
    fields_tag = f" [fields:{','.join(field_ids)}]" if field_ids else ""
    print(f"\n{'='*60}")
    print(f"SEEDING: {label}{israeli_tag}{fields_tag}")
    print(f"Target: {limit} papers | Budget: ${budget_limit:.2f}")
    print(f"{'='*60}")

    sem = asyncio.Semaphore(CONCURRENCY)
    cursor = "*"
    inserted = 0
    consecutive_skips = 0
    errors = 0

    async def process_one(raw):
        nonlocal inserted, consecutive_skips, errors
        if inserted >= limit or budget_spent >= budget_limit:
            return
        async with sem:
            if inserted >= limit or budget_spent >= budget_limit:
                return
            oa_id = raw["id"].split("/")[-1]
            existing = await supabase_get(client, "papers", {"openalex_id": f"eq.{oa_id}", "select": "id"})
            if existing:
                consecutive_skips += 1
                return
            consecutive_skips = 0

            abstract = reconstruct_abstract(raw.get("abstract_inverted_index"))
            if not abstract or len(abstract) < 50:
                return
            authors_list = raw.get("authorships", [])
            authors_str = ", ".join(a.get("author", {}).get("display_name", "") for a in authors_list[:5])
            year = raw.get("publication_year", 0)
            title = raw.get("title", "?")

            analysis = await analyze_paper(client, title, authors_str, year, abstract, lang_code)
            if analysis == "STOP":
                return
            if analysis and not isinstance(analysis, str):
                pid = await insert_paper(client, raw, analysis, lang_code)
                if pid:
                    inserted += 1
                    if inserted % 10 == 0 or inserted <= 3:
                        print(f"  [{inserted}/{limit}] {title[:55]}... ${budget_spent:.3f}")
                else:
                    errors += 1

    while inserted < limit and budget_spent < budget_limit:
        data = await fetch_foreign_papers(client, lang_code, min(50, limit - inserted + 10), cursor, israeli_only, field_ids)
        results = data.get("results", [])
        cursor = data.get("meta", {}).get("next_cursor")
        if not results or not cursor:
            print(f"  No more results ({inserted} inserted)")
            break
        # Stop if too many consecutive skips
        if consecutive_skips >= 100:
            print(f"  100 consecutive skips — moving on")
            break
        await asyncio.gather(*[process_one(r) for r in results])

    print(f"\n  Done: {inserted} inserted, {errors} errors, ${budget_spent:.3f}")
    return inserted


async def async_main():
    global budget_limit, _budget_lock

    sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Foreign-language paper seeding")
    parser.add_argument("--budget", type=float, default=30.0)
    parser.add_argument("--limit", type=int, default=300, help="Papers per language")
    parser.add_argument("--languages", default=",".join(DEFAULT_LANGS), help="Comma-separated language codes")
    parser.add_argument("--language", help="Single language code (overrides --languages)")
    parser.add_argument("--israeli-only", action="store_true", help="Only seed Israeli-affiliated papers (works with --language he)")
    parser.add_argument("--social-science-hebrew", action="store_true", help="Prioritize Hebrew social science fields (sociology, anthropology, political sci, economics)")
    args = parser.parse_args()

    budget_limit = args.budget
    _budget_lock = asyncio.Lock()

    if not SUPABASE_URL or not ANTHROPIC_API_KEY:
        print("ERROR: Missing env vars")
        sys.exit(1)
    init_supabase_headers()

    languages = [args.language] if args.language else [l.strip() for l in args.languages.split(",")]

    print(f"Seeding foreign-language papers in: {', '.join(languages)}")
    print(f"Budget: ${budget_limit:.2f} | Per-language: {args.limit}")

    total = 0
    async with httpx.AsyncClient() as client:
        for lang in languages:
            if budget_spent >= budget_limit:
                print(f"\n*** Budget exhausted ***")
                break

            # For Hebrew, prioritize: social sciences → Israeli → general
            if lang == "he":
                # Social sciences: 33=Social Sciences, 32=Psychology, 20=Economics
                soc_sci_fields = ["33", "32", "20"]
                # Pass 1: Israeli Hebrew social sciences (TOP PRIORITY)
                total += await seed_language(client, "he", args.limit // 3, israeli_only=True, field_ids=soc_sci_fields)
                if budget_spent >= budget_limit:
                    break
                # Pass 2: Any Hebrew social sciences
                total += await seed_language(client, "he", args.limit // 3, israeli_only=False, field_ids=soc_sci_fields)
                if budget_spent >= budget_limit:
                    break
                # Pass 3: General Israeli Hebrew (any field, by citations)
                total += await seed_language(client, "he", args.limit // 3, israeli_only=True)
            else:
                total += await seed_language(client, lang, args.limit)

    print(f"\n{'='*60}")
    print(f"TOTAL FOREIGN PAPERS: {total}")
    print(f"COST: ${budget_spent:.3f} / ${budget_limit:.2f}")
    print(f"{'='*60}")


def main():
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
