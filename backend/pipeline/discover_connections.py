"""
Korczak Discovery Engine — find hidden connections in the knowledge graph.

Scans for 6 types of discoveries:
  1. analogical_bridge     — same concept in different fields
  2. citation_gap          — papers sharing concepts but not citing each other
  3. contradiction         — opposing claims about the same thing
  4. unrealized_potential  — concepts with many inputs but few outputs
  5. temporal_gap          — old testable claims never followed up
  6. cross_lingual_bridge  — foreign concepts missing English analog

Each candidate is surfaced by SQL, then evaluated by Claude Haiku.
Findings are persisted to the `discoveries` table for human review.

Usage:
  python -m backend.pipeline.discover_connections --budget 5
  python -m backend.pipeline.discover_connections --budget 5 --kinds analogical_bridge,unrealized_potential
"""

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone

import httpx
import psycopg2
import psycopg2.extras
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
budget_limit = 5.0
_lock = None

HEADERS_SUPABASE = {
    "apikey": SUPABASE_SERVICE_KEY,
    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}

DB_PARAMS = {
    "host": "db.bgrdmydbrtnucunbpobl.supabase.co",
    "port": 5432,
    "user": "postgres",
    "password": "KOR@9876CZAK",
    "database": "postgres",
}


# ---------------------------------------------------------------------------
# SQL pattern queries — return candidate tuples
# ---------------------------------------------------------------------------

QUERY_ANALOGICAL_BRIDGE = """
WITH concept_fields AS (
    SELECT c.id, c.name, c.normalized_name,
           array_agg(DISTINCT p.paper_type) FILTER (WHERE p.paper_type IS NOT NULL) AS fields,
           COUNT(DISTINCT pc.paper_id) as usage_count
    FROM concepts c
    JOIN paper_concepts pc ON pc.concept_id = c.id
    JOIN papers p ON p.id = pc.paper_id
    WHERE p.paper_type IS NOT NULL
    GROUP BY c.id, c.name, c.normalized_name
)
SELECT id, name, fields, usage_count
FROM concept_fields
WHERE array_length(fields, 1) >= 3
  AND usage_count >= 3
ORDER BY usage_count DESC
LIMIT %s
"""

QUERY_CITATION_GAP = """
SELECT
    p1.id AS paper_a_id,
    p2.id AS paper_b_id,
    p1.title AS title_a,
    p2.title AS title_b,
    p1.publication_year AS year_a,
    p2.publication_year AS year_b,
    COUNT(DISTINCT pc1.concept_id) AS shared_concepts,
    array_agg(DISTINCT c.name) FILTER (WHERE c.name IS NOT NULL) AS concept_names
FROM paper_concepts pc1
JOIN paper_concepts pc2 ON pc1.concept_id = pc2.concept_id AND pc1.paper_id < pc2.paper_id
JOIN papers p1 ON p1.id = pc1.paper_id
JOIN papers p2 ON p2.id = pc2.paper_id
JOIN concepts c ON c.id = pc1.concept_id
WHERE p1.canonical = TRUE OR p2.canonical = TRUE
GROUP BY p1.id, p2.id, p1.title, p2.title, p1.publication_year, p2.publication_year
HAVING COUNT(DISTINCT pc1.concept_id) >= 4
   AND NOT EXISTS (
        SELECT 1 FROM relationships r
        WHERE ((r.source_id = p1.id AND r.target_id = p2.id)
           OR (r.source_id = p2.id AND r.target_id = p1.id))
          AND r.source_type = 'paper' AND r.target_type = 'paper'
   )
ORDER BY shared_concepts DESC
LIMIT %s
"""

QUERY_UNREALIZED_POTENTIAL = """
WITH degree AS (
    SELECT c.id, c.name, c.definition,
        (SELECT COUNT(*) FROM relationships r WHERE r.target_id = c.id AND r.target_type = 'concept') AS incoming,
        (SELECT COUNT(*) FROM relationships r WHERE r.source_id = c.id AND r.source_type = 'concept') AS outgoing,
        (SELECT COUNT(*) FROM paper_concepts pc WHERE pc.concept_id = c.id) AS paper_count
    FROM concepts c
    WHERE c.definition IS NOT NULL
)
SELECT id, name, definition, incoming, outgoing, paper_count
FROM degree
WHERE incoming >= 3 AND outgoing <= 1 AND paper_count >= 2
ORDER BY incoming DESC, paper_count DESC
LIMIT %s
"""

QUERY_TEMPORAL_GAP = """
SELECT cl.id, cl.claim_text, cl.evidence_type, p.title, p.publication_year,
       p.id as paper_id,
       array_agg(DISTINCT c.name) FILTER (WHERE c.name IS NOT NULL) as concepts
FROM claims cl
JOIN papers p ON p.id = cl.paper_id
LEFT JOIN paper_concepts pc ON pc.paper_id = p.id
LEFT JOIN concepts c ON c.id = pc.concept_id
WHERE cl.testable = TRUE
  AND p.publication_year IS NOT NULL
  AND p.publication_year < 2000
  AND cl.strength = 'strong'
GROUP BY cl.id, cl.claim_text, cl.evidence_type, p.title, p.publication_year, p.id
LIMIT %s
"""

QUERY_CROSS_LINGUAL = """
SELECT p.id, p.title, p.language, p.canonical_field,
       array_agg(DISTINCT c.name) FILTER (WHERE c.name IS NOT NULL) as concepts,
       p.abstract
FROM papers p
JOIN paper_concepts pc ON pc.paper_id = p.id
JOIN concepts c ON c.id = pc.concept_id
WHERE p.canonical = TRUE
  AND p.language IS NOT NULL
  AND p.language != 'en'
  AND p.canonical_field LIKE 'canonical-%%'
GROUP BY p.id, p.title, p.language, p.canonical_field, p.abstract
LIMIT %s
"""

QUERY_CONTRADICTION = """
SELECT
    cl1.id as claim_a, cl2.id as claim_b,
    cl1.claim_text as text_a, cl2.claim_text as text_b,
    p1.title as paper_a, p2.title as paper_b,
    p1.id as paper_a_id, p2.id as paper_b_id,
    array_agg(DISTINCT c.name) FILTER (WHERE c.name IS NOT NULL) as shared_concepts
FROM claims cl1
JOIN claims cl2 ON cl1.id < cl2.id
JOIN papers p1 ON p1.id = cl1.paper_id
JOIN papers p2 ON p2.id = cl2.paper_id
JOIN paper_concepts pc1 ON pc1.paper_id = cl1.paper_id
JOIN paper_concepts pc2 ON pc2.paper_id = cl2.paper_id AND pc2.concept_id = pc1.concept_id
JOIN concepts c ON c.id = pc1.concept_id
WHERE cl1.paper_id != cl2.paper_id
  AND (p1.canonical = TRUE OR p2.canonical = TRUE)
  AND cl1.strength = 'strong' AND cl2.strength = 'strong'
GROUP BY cl1.id, cl2.id, cl1.claim_text, cl2.claim_text, p1.title, p2.title, p1.id, p2.id
HAVING COUNT(DISTINCT pc1.concept_id) >= 2
ORDER BY RANDOM()
LIMIT %s
"""


# ---------------------------------------------------------------------------
# Claude evaluator prompts
# ---------------------------------------------------------------------------

def prompt_analogical_bridge(concept_name, fields, sample_papers):
    return f"""You are a scholar analyzing a knowledge graph. You found that the concept "{concept_name}" appears in multiple academic fields: {', '.join(fields)}.

Sample papers using this concept:
{chr(10).join(f"  - [{p.get('paper_type','?')}] {p['title'][:80]}" for p in sample_papers[:5])}

Is this a meaningful ANALOGICAL BRIDGE between fields, or is the concept being used in genuinely different, unrelated senses? Evaluate:

1. Is this the SAME concept applied across fields, or different concepts sharing a name?
2. If same: what insight comes from the cross-field appearance?
3. If different: what are the distinct meanings?
4. Confidence that this is a genuine bridge (0-1)
5. Novelty — is this well-known already, or an under-appreciated connection? (0-1)

Return JSON:
{{
  "is_genuine_bridge": bool,
  "insight": "1-3 sentence explanation",
  "distinct_meanings": ["field1: meaning", "field2: meaning"] if different,
  "confidence": 0.0-1.0,
  "novelty": 0.0-1.0,
  "importance": 0.0-1.0
}}
"""


def prompt_citation_gap(title_a, year_a, title_b, year_b, concepts):
    older, newer = (title_a, year_a), (title_b, year_b)
    if year_a and year_b and year_b < year_a:
        older, newer = (title_b, year_b), (title_a, year_a)
    return f"""Two papers share {len(concepts)} concepts but neither cites the other:

Paper A: "{title_a}" ({year_a})
Paper B: "{title_b}" ({year_b})

Shared concepts: {', '.join(concepts[:15])}

Analyze:
1. Should the newer paper be aware of the older one? (Was the older one known/available?)
2. What does their non-citation tell us — oversight, independent discovery, or parallel traditions?
3. What insight would emerge from linking them?
4. Confidence this is a meaningful gap (0-1)

Return JSON:
{{
  "is_meaningful_gap": bool,
  "reason": "why they weren't connected",
  "insight_from_linking": "what we learn by connecting them",
  "confidence": 0.0-1.0,
  "novelty": 0.0-1.0,
  "importance": 0.0-1.0
}}
"""


def prompt_unrealized_potential(concept_name, definition, incoming, outgoing, paper_count):
    return f"""A concept in our graph has UNREALIZED POTENTIAL — many papers reference it but few build on it.

Concept: "{concept_name}"
Definition: {definition or '(none)'}
Papers discussing it: {paper_count}
Other concepts pointing to it (incoming): {incoming}
Other concepts it builds to (outgoing): {outgoing}

This asymmetry suggests the concept is foundational but under-exploited. Propose research directions:

1. What specific untried applications could extend this concept?
2. What adjacent fields haven't applied it yet?
3. A concrete hypothesis that could be tested
4. How novel is this direction (0-1)?
5. How tractable is it — could a grad student work on it? (0-1)

Return JSON:
{{
  "research_directions": ["direction 1", "direction 2", "direction 3"],
  "hypothesis": "one specific testable hypothesis",
  "adjacent_fields": ["field1", "field2"],
  "confidence": 0.0-1.0,
  "novelty": 0.0-1.0,
  "importance": 0.0-1.0
}}
"""


def prompt_contradiction(text_a, paper_a, text_b, paper_b, concepts):
    return f"""Two claims about the same concepts — they may contradict.

Claim A (from "{paper_a}"): {text_a}

Claim B (from "{paper_b}"): {text_b}

Shared concepts: {', '.join(concepts[:8])}

Evaluate:
1. Do these genuinely CONTRADICT, or are they about different aspects?
2. If contradiction: which side has more evidence in scholarship?
3. If not contradiction: what's the actual relationship (complementary, scope, etc.)?
4. Confidence of contradiction (0-1)

Return JSON:
{{
  "is_contradiction": bool,
  "actual_relationship": "contradicts|complements|different_scope|same_but_rephrased",
  "analysis": "2-3 sentence explanation",
  "confidence": 0.0-1.0,
  "novelty": 0.0-1.0,
  "importance": 0.0-1.0
}}
"""


def prompt_temporal_gap(claim, year, paper_title, concepts):
    return f"""A testable claim from {year} that may not have been followed up:

Original paper: "{paper_title}"
Claim: {claim}
Related concepts: {', '.join(concepts[:8])}

Evaluate:
1. Has this claim been tested in subsequent research, to your knowledge?
2. If yes: what's the verdict? supported/refuted/mixed?
3. If no: why not — too hard? forgotten? superseded?
4. Is there a modern method that could test it now?
5. Is this worth someone's attention? (importance 0-1)

Return JSON:
{{
  "has_been_tested": bool,
  "verdict": "supported|refuted|mixed|untested",
  "modern_test_suggestion": "one specific approach" or null,
  "why_untested": "reason" or null,
  "confidence": 0.0-1.0,
  "novelty": 0.0-1.0,
  "importance": 0.0-1.0
}}
"""


def prompt_cross_lingual(title, language, concepts, abstract):
    lang_names = {"de": "German", "fr": "French", "ru": "Russian", "ja": "Japanese",
                  "zh": "Chinese", "es": "Spanish", "it": "Italian", "ar": "Arabic",
                  "am": "Amharic", "he": "Hebrew"}
    lang_label = lang_names.get(language, language)
    return f"""A canonical work in {lang_label} that may have under-recognized connections to English-language thought.

Title: {title}
Abstract/summary: {(abstract or '')[:500]}
Key concepts: {', '.join(concepts[:10])}

For each major concept in this work, identify:
1. Does it have a direct English analog in major philosophy/theory traditions?
2. Is the concept translated/preserved well in English scholarship, or does something essential get lost?
3. What English-language works SHOULD engage with this but don't?

Return JSON:
{{
  "concept_bridges": [
    {{"foreign_concept": "x", "english_analog": "y", "what_is_lost": "..."}}
  ],
  "missing_english_engagement": "1-2 sentence explanation",
  "confidence": 0.0-1.0,
  "novelty": 0.0-1.0,
  "importance": 0.0-1.0
}}
"""


# ---------------------------------------------------------------------------
# Core evaluator
# ---------------------------------------------------------------------------

async def call_claude(client, prompt, max_tokens=1500):
    global budget_spent
    async with _lock:
        if budget_spent >= budget_limit:
            return None
    body = {
        "model": "claude-haiku-4-5-20251001",
        "max_tokens": max_tokens,
        "temperature": 0.4,
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
        return json.loads(text.strip())
    except Exception as e:
        return None


# ---------------------------------------------------------------------------
# Supabase helpers
# ---------------------------------------------------------------------------

async def insert_discovery(client, row):
    r = await client.post(
        f"{SUPABASE_URL}/rest/v1/discoveries",
        json=row, headers=HEADERS_SUPABASE, timeout=15,
    )
    return r.status_code in (200, 201)


async def fetch_papers_for_concept(conn, concept_id, limit=5):
    """Get sample papers using a concept."""
    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute("""
            SELECT p.id, p.title, p.paper_type
            FROM papers p
            JOIN paper_concepts pc ON pc.paper_id = p.id
            WHERE pc.concept_id = %s
            LIMIT %s
        """, (concept_id, limit))
        return [dict(r) for r in cur.fetchall()]


# ---------------------------------------------------------------------------
# Discovery handlers
# ---------------------------------------------------------------------------

async def run_analogical_bridge(conn, client, limit, stats):
    print("\n--- Analogical Bridges ---")
    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute(QUERY_ANALOGICAL_BRIDGE, (limit,))
        candidates = [dict(r) for r in cur.fetchall()]
    print(f"  Found {len(candidates)} candidates")

    sem = asyncio.Semaphore(CONCURRENCY)

    async def process(c):
        if budget_spent >= budget_limit: return
        async with sem:
            if budget_spent >= budget_limit: return
            papers = await fetch_papers_for_concept(conn, c["id"])
            fields = c["fields"] or []
            result = await call_claude(client, prompt_analogical_bridge(c["name"], fields, papers))
            if not result: return
            if not result.get("is_genuine_bridge"): return
            await insert_discovery(client, {
                "kind": "analogical_bridge",
                "title": f"'{c['name']}' bridges {len(fields)} fields",
                "description": result.get("insight", ""),
                "claude_reasoning": json.dumps(result, ensure_ascii=False)[:2000],
                "concept_ids": [c["id"]],
                "confidence": float(result.get("confidence", 0.5)),
                "novelty": float(result.get("novelty", 0.5)),
                "importance": float(result.get("importance", 0.5)),
            })
            stats["analogical_bridge"] += 1
            print(f"  ✓ '{c['name']}' — conf {result.get('confidence'):.2f} nov {result.get('novelty'):.2f}")

    await asyncio.gather(*[process(c) for c in candidates])


async def run_citation_gap(conn, client, limit, stats):
    print("\n--- Citation Gaps ---")
    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute(QUERY_CITATION_GAP, (limit,))
        candidates = [dict(r) for r in cur.fetchall()]
    print(f"  Found {len(candidates)} candidates")

    sem = asyncio.Semaphore(CONCURRENCY)

    async def process(c):
        if budget_spent >= budget_limit: return
        async with sem:
            if budget_spent >= budget_limit: return
            concepts = c["concept_names"] or []
            result = await call_claude(client, prompt_citation_gap(
                c["title_a"], c["year_a"], c["title_b"], c["year_b"], concepts
            ))
            if not result: return
            if not result.get("is_meaningful_gap"): return
            await insert_discovery(client, {
                "kind": "citation_gap",
                "title": f"Gap: {c['title_a'][:40]} ↔ {c['title_b'][:40]}",
                "description": result.get("insight_from_linking", ""),
                "claude_reasoning": json.dumps(result, ensure_ascii=False)[:2000],
                "paper_ids": [str(c["paper_a_id"]), str(c["paper_b_id"])],
                "confidence": float(result.get("confidence", 0.5)),
                "novelty": float(result.get("novelty", 0.5)),
                "importance": float(result.get("importance", 0.5)),
            })
            stats["citation_gap"] += 1
            print(f"  ✓ Gap between {c['title_a'][:35]}... ↔ {c['title_b'][:35]}...")

    await asyncio.gather(*[process(c) for c in candidates])


async def run_unrealized_potential(conn, client, limit, stats):
    print("\n--- Unrealized Potential ---")
    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute(QUERY_UNREALIZED_POTENTIAL, (limit,))
        candidates = [dict(r) for r in cur.fetchall()]
    print(f"  Found {len(candidates)} candidates")

    sem = asyncio.Semaphore(CONCURRENCY)

    async def process(c):
        if budget_spent >= budget_limit: return
        async with sem:
            if budget_spent >= budget_limit: return
            result = await call_claude(client, prompt_unrealized_potential(
                c["name"], c["definition"], c["incoming"], c["outgoing"], c["paper_count"]
            ))
            if not result: return
            await insert_discovery(client, {
                "kind": "unrealized_potential",
                "title": f"Untapped: '{c['name']}'",
                "description": result.get("hypothesis", ""),
                "claude_reasoning": json.dumps(result, ensure_ascii=False)[:2000],
                "concept_ids": [c["id"]],
                "confidence": float(result.get("confidence", 0.5)),
                "novelty": float(result.get("novelty", 0.5)),
                "importance": float(result.get("importance", 0.5)),
            })
            stats["unrealized_potential"] += 1
            print(f"  ✓ '{c['name']}' — {c['incoming']} in / {c['outgoing']} out — novelty {result.get('novelty'):.2f}")

    await asyncio.gather(*[process(c) for c in candidates])


async def run_contradiction(conn, client, limit, stats):
    print("\n--- Contradictions ---")
    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute(QUERY_CONTRADICTION, (limit,))
        candidates = [dict(r) for r in cur.fetchall()]
    print(f"  Found {len(candidates)} candidates")

    sem = asyncio.Semaphore(CONCURRENCY)

    async def process(c):
        if budget_spent >= budget_limit: return
        async with sem:
            if budget_spent >= budget_limit: return
            concepts = c["shared_concepts"] or []
            result = await call_claude(client, prompt_contradiction(
                c["text_a"], c["paper_a"], c["text_b"], c["paper_b"], concepts
            ))
            if not result: return
            if not result.get("is_contradiction"): return
            await insert_discovery(client, {
                "kind": "contradiction",
                "title": f"Debate: {c['paper_a'][:40]} vs {c['paper_b'][:40]}",
                "description": result.get("analysis", ""),
                "claude_reasoning": json.dumps(result, ensure_ascii=False)[:2000],
                "paper_ids": [str(c["paper_a_id"]), str(c["paper_b_id"])],
                "claim_ids": [str(c["claim_a"]), str(c["claim_b"])],
                "confidence": float(result.get("confidence", 0.5)),
                "novelty": float(result.get("novelty", 0.5)),
                "importance": float(result.get("importance", 0.5)),
            })
            stats["contradiction"] += 1
            print(f"  ✓ Contradiction: {c['paper_a'][:30]}... ⚔ {c['paper_b'][:30]}...")

    await asyncio.gather(*[process(c) for c in candidates])


async def run_temporal_gap(conn, client, limit, stats):
    print("\n--- Temporal Gaps ---")
    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute(QUERY_TEMPORAL_GAP, (limit,))
        candidates = [dict(r) for r in cur.fetchall()]
    print(f"  Found {len(candidates)} candidates")

    sem = asyncio.Semaphore(CONCURRENCY)

    async def process(c):
        if budget_spent >= budget_limit: return
        async with sem:
            if budget_spent >= budget_limit: return
            concepts = c["concepts"] or []
            result = await call_claude(client, prompt_temporal_gap(
                c["claim_text"], c["publication_year"], c["title"], concepts
            ))
            if not result: return
            if result.get("has_been_tested") is True:
                return
            await insert_discovery(client, {
                "kind": "temporal_gap",
                "title": f"Untested: '{c['title'][:45]}' ({c['publication_year']})",
                "description": result.get("modern_test_suggestion") or result.get("why_untested") or "",
                "claude_reasoning": json.dumps(result, ensure_ascii=False)[:2000],
                "paper_ids": [str(c["paper_id"])],
                "claim_ids": [str(c["id"])],
                "confidence": float(result.get("confidence", 0.5)),
                "novelty": float(result.get("novelty", 0.5)),
                "importance": float(result.get("importance", 0.5)),
            })
            stats["temporal_gap"] += 1
            print(f"  ✓ Gap from {c['publication_year']}: {c['title'][:40]}...")

    await asyncio.gather(*[process(c) for c in candidates])


async def run_cross_lingual(conn, client, limit, stats):
    print("\n--- Cross-Lingual Bridges ---")
    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute(QUERY_CROSS_LINGUAL, (limit,))
        candidates = [dict(r) for r in cur.fetchall()]
    print(f"  Found {len(candidates)} candidates")

    sem = asyncio.Semaphore(CONCURRENCY)

    async def process(c):
        if budget_spent >= budget_limit: return
        async with sem:
            if budget_spent >= budget_limit: return
            concepts = c["concepts"] or []
            if not concepts:
                return
            result = await call_claude(client, prompt_cross_lingual(
                c["title"], c["language"], concepts, c["abstract"]
            ))
            if not result: return
            await insert_discovery(client, {
                "kind": "cross_lingual_bridge",
                "title": f"{c['language']}: '{c['title'][:50]}'",
                "description": result.get("missing_english_engagement", ""),
                "claude_reasoning": json.dumps(result, ensure_ascii=False)[:2000],
                "paper_ids": [str(c["id"])],
                "confidence": float(result.get("confidence", 0.5)),
                "novelty": float(result.get("novelty", 0.5)),
                "importance": float(result.get("importance", 0.5)),
            })
            stats["cross_lingual_bridge"] += 1
            print(f"  ✓ {c['language']}: {c['title'][:50]}...")

    await asyncio.gather(*[process(c) for c in candidates])


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def async_main():
    global budget_limit, _lock
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--budget", type=float, default=5.0)
    parser.add_argument("--limit", type=int, default=30, help="Candidates per kind")
    parser.add_argument("--kinds", default="all")
    args = parser.parse_args()

    budget_limit = args.budget
    _lock = asyncio.Lock()

    all_kinds = ["analogical_bridge", "citation_gap", "unrealized_potential",
                 "contradiction", "temporal_gap", "cross_lingual_bridge"]
    selected = all_kinds if args.kinds == "all" else [k.strip() for k in args.kinds.split(",")]

    print(f"\n{'='*60}")
    print(f"KORCZAK DISCOVERY ENGINE")
    print(f"Budget: ${budget_limit}  |  Limit per kind: {args.limit}")
    print(f"Kinds: {', '.join(selected)}")
    print(f"{'='*60}")

    conn = psycopg2.connect(**DB_PARAMS)
    stats = {k: 0 for k in all_kinds}

    try:
        async with httpx.AsyncClient() as client:
            # Start run log
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO discovery_runs (run_type) VALUES (%s) RETURNING id",
                    (','.join(selected),)
                )
                run_id = cur.fetchone()[0]
                conn.commit()

            runners = {
                "analogical_bridge": run_analogical_bridge,
                "citation_gap": run_citation_gap,
                "unrealized_potential": run_unrealized_potential,
                "contradiction": run_contradiction,
                "temporal_gap": run_temporal_gap,
                "cross_lingual_bridge": run_cross_lingual,
            }
            for k in selected:
                if budget_spent >= budget_limit: break
                if k in runners:
                    await runners[k](conn, client, args.limit, stats)

            # Complete run log
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE discovery_runs SET completed_at=NOW(), discoveries_found=%s, cost_usd=%s WHERE id=%s",
                    (sum(stats.values()), budget_spent, run_id)
                )
                conn.commit()
    finally:
        conn.close()

    print(f"\n{'='*60}")
    print(f"DISCOVERY RESULTS:")
    for k, n in stats.items():
        print(f"  {k:25} {n}")
    print(f"  {'Total':25} {sum(stats.values())}")
    print(f"  Cost:                    ${budget_spent:.3f} / ${budget_limit}")
    print(f"{'='*60}")


def main():
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
