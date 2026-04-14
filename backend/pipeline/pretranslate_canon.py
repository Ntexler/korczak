"""Pre-translate canonical papers to accessibility languages.

For every canonical paper that has an abstract, translate title +
abstract to Hebrew and Arabic (Phase 3 accessibility defaults). Later
passes can add Amharic + Russian + more. Translations are cached in
the paper_translations table by the existing translator.

This is the "knowledge should be free" pass — canon available in the
languages of people most likely to be underserved by paywalled
English-language corpora.

Usage:
  python -m backend.pipeline.pretranslate_canon --budget 8
  python -m backend.pipeline.pretranslate_canon --budget 4 --languages he
  python -m backend.pipeline.pretranslate_canon --languages he,ar,am,ru --limit 50
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone

import httpx
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
ANTHROPIC_API = "https://api.anthropic.com/v1/messages"

HAIKU_INPUT = 0.80 / 1_000_000
HAIKU_OUTPUT = 4.0 / 1_000_000

CONCURRENCY = 5
budget_spent = 0.0
budget_limit = 8.0
_lock = None

HEADERS_SUPABASE = {
    "apikey": SUPABASE_SERVICE_KEY,
    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}

LANG_NAMES = {
    "he": "Hebrew", "ar": "Arabic", "am": "Amharic", "ru": "Russian",
    "es": "Spanish", "hi": "Hindi", "pt": "Portuguese", "fr": "French",
    "de": "German", "ja": "Japanese", "zh": "Chinese",
}


TRANSLATION_PROMPT = """Translate the following canonical work's title and abstract from {source_name} to {target_name}.

Rules:
1. Preserve technical terms accurately; keep the canonical English/original term in parentheses after first use if there's no standard {target_name} term.
2. Keep proper nouns (author names, place names, institutions) unchanged.
3. Maintain academic register — this is a foundational/canonical text; translate with gravity, not casually.
4. Return JSON ONLY, no prose.

Title: {title}
Abstract: {abstract}

Return:
{{"translated_title": "...", "translated_abstract": "...", "quality_notes": "..."}}"""


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


def detect_source(text: str) -> str:
    if not text:
        return "en"
    for char in text[:200]:
        c = ord(char)
        if 0x4E00 <= c <= 0x9FFF: return "zh"
        if 0x3040 <= c <= 0x309F or 0x30A0 <= c <= 0x30FF: return "ja"
        if 0xAC00 <= c <= 0xD7AF: return "ko"
        if 0x0590 <= c <= 0x05FF: return "he"
        if 0x0600 <= c <= 0x06FF: return "ar"
        if 0x0E00 <= c <= 0x0E7F: return "th"
        if 0x0900 <= c <= 0x097F: return "hi"
        if 0x0400 <= c <= 0x04FF: return "ru"
        if 0x0370 <= c <= 0x03FF: return "el"
        if 0x1200 <= c <= 0x137F: return "am"
    return "en"


async def translate_one(client, paper, target_lang):
    global budget_spent
    async with _lock:
        if budget_spent >= budget_limit:
            return "STOP"

    paper_id = paper["id"]
    source_lang = paper.get("language") or detect_source(
        (paper.get("abstract") or "") + " " + (paper.get("title") or "")
    )
    if source_lang == target_lang:
        return "skip"

    title = (paper.get("title") or "").strip()
    abstract = (paper.get("abstract") or "").strip()
    if not abstract or len(abstract) < 40:
        return "no_abstract"

    # Skip if cached
    cached = await supabase_get(client, "paper_translations", {
        "paper_id": f"eq.{paper_id}",
        "target_language": f"eq.{target_lang}",
        "select": "id",
    })
    if cached:
        return "cached"

    source_name = LANG_NAMES.get(source_lang, source_lang)
    target_name = LANG_NAMES.get(target_lang, target_lang)
    prompt = TRANSLATION_PROMPT.format(
        source_name=source_name, target_name=target_name,
        title=title, abstract=abstract[:3000],
    )

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
    try:
        r = await client.post(ANTHROPIC_API, json=body, headers=headers, timeout=90)
        if r.status_code != 200:
            return None
        data = r.json()
        text = data["content"][0]["text"]
        usage = data.get("usage", {})
        cost = usage.get("input_tokens", 0) * HAIKU_INPUT + usage.get("output_tokens", 0) * HAIKU_OUTPUT
        async with _lock:
            budget_spent += cost
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]
        parsed = json.loads(text.strip())
    except Exception as e:
        return None

    await supabase_post(client, "paper_translations", {
        "paper_id": paper_id,
        "source_language": source_lang,
        "target_language": target_lang,
        "translated_title": parsed.get("translated_title", ""),
        "translated_abstract": parsed.get("translated_abstract", ""),
        "quality_notes": parsed.get("quality_notes"),
        "model": "claude-haiku-4-5-20251001",
        "translated_at": datetime.now(tz=timezone.utc).isoformat(),
    })
    return "ok"


async def async_main():
    global budget_limit, _lock
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--budget", type=float, default=8.0)
    parser.add_argument("--languages", default="he,ar")
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--min-canonical-rank", type=int, default=999,
                        help="Only pre-translate canonical_rank <= this")
    args = parser.parse_args()

    budget_limit = args.budget
    _lock = asyncio.Lock()
    targets = [l.strip() for l in args.languages.split(",")]

    print(f"\n{'='*60}")
    print(f"PRE-TRANSLATING CANONICAL WORKS")
    print(f"Target languages: {', '.join(LANG_NAMES.get(l, l) for l in targets)}")
    print(f"Budget: ${budget_limit} | Limit: {args.limit} papers per language")
    print(f"{'='*60}")

    async with httpx.AsyncClient() as client:
        papers = await supabase_get(client, "papers", {
            "canonical": "eq.true",
            "abstract": "not.is.null",
            "select": "id,title,abstract,language,canonical_rank,canonical_field",
            "order": "canonical_rank.asc.nullslast",
            "limit": str(args.limit),
        })
        papers = [p for p in papers if p.get("abstract") and len(p["abstract"]) >= 40]
        print(f"  Candidates with abstracts: {len(papers)}")

        for target_lang in targets:
            print(f"\n--- Translating to {LANG_NAMES.get(target_lang, target_lang)} ---")
            stats = {"ok": 0, "cached": 0, "skip": 0, "no_abstract": 0, "failed": 0}
            sem = asyncio.Semaphore(CONCURRENCY)

            async def process(p):
                if budget_spent >= budget_limit:
                    return
                async with sem:
                    if budget_spent >= budget_limit:
                        return
                    result = await translate_one(client, p, target_lang)
                    if result == "STOP": return
                    if result in stats:
                        stats[result] += 1
                    elif result is None:
                        stats["failed"] += 1
                    if stats["ok"] % 10 == 0 and stats["ok"] > 0:
                        print(f"    [{stats['ok']}] translated — ${budget_spent:.3f}")

            await asyncio.gather(*[process(p) for p in papers])
            print(f"  Done {target_lang}: ok={stats['ok']} cached={stats['cached']} "
                  f"skip={stats['skip']} no_abs={stats['no_abstract']} failed={stats['failed']}")
            if budget_spent >= budget_limit:
                print(f"\n*** BUDGET LIMIT — stopping ***")
                break

    print(f"\n{'='*60}")
    print(f"TOTAL COST: ${budget_spent:.3f} / ${budget_limit}")
    print(f"{'='*60}")


def main():
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
