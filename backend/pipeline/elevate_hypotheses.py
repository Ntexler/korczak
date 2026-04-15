"""Research Hypothesis Elevator.

Takes high-importance `unrealized_potential` and `temporal_gap`
discoveries and converts them into structured entries in the
`research_hypotheses` table — testable propositions with a suggested
method, predicted outcome, and links back to the concepts and papers
that implicated them.

Usage:
  python -m backend.pipeline.elevate_hypotheses --budget 2
  python -m backend.pipeline.elevate_hypotheses --min-importance 0.7 --limit 20
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from typing import Optional

import httpx
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
ANTHROPIC_API = "https://api.anthropic.com/v1/messages"

HAIKU_INPUT = 0.80 / 1_000_000
HAIKU_OUTPUT = 4.0 / 1_000_000

budget_spent = 0.0
budget_limit = 2.0
_lock = None

HEADERS_SUPABASE = {
    "apikey": SUPABASE_SERVICE_KEY,
    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}


PROMPT = """You are turning a raw pattern finding into a structured research hypothesis.

DISCOVERY KIND: {kind}
DISCOVERY TITLE: {title}
DISCOVERY DESCRIPTION: {description}
ORIGINAL REASONING FROM THE GRAPH SCANNER:
{reasoning}

Elevate this into a hypothesis that a grad student or researcher could actually pursue. Produce:

- title: a short, precise title (under 15 words)
- hypothesis: one sentence, formally stated ("X will Y under condition Z"). Falsifiable.
- rationale: 2-4 sentences explaining why this is worth testing (what gap it fills, what it would show)
- predicted_outcome: what the researcher would expect to observe if the hypothesis is correct
- method_suggestion: a concrete first method (experiment, dataset, comparison) — not vague
- testable: true if the hypothesis can be empirically evaluated, false if purely theoretical

Return JSON only with those fields.
"""


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


async def elevate(client, discovery):
    global budget_spent
    async with _lock:
        if budget_spent >= budget_limit:
            return None

    prompt = PROMPT.format(
        kind=discovery["kind"],
        title=discovery["title"],
        description=discovery.get("description") or "",
        reasoning=(discovery.get("claude_reasoning") or "")[:1500],
    )
    body = {
        "model": "claude-haiku-4-5-20251001",
        "max_tokens": 1200,
        "temperature": 0.4,
        "messages": [{"role": "user", "content": prompt}],
    }
    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "content-type": "application/json",
        "anthropic-version": "2023-06-01",
    }
    try:
        r = await client.post(ANTHROPIC_API, json=body, headers=headers, timeout=60)
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
        return parsed
    except Exception:
        return None


async def async_main():
    global budget_limit, _lock
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--budget", type=float, default=2.0)
    parser.add_argument("--min-importance", type=float, default=0.6)
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument("--kinds", default="unrealized_potential,temporal_gap,research_direction")
    args = parser.parse_args()

    budget_limit = args.budget
    _lock = asyncio.Lock()
    kinds = [k.strip() for k in args.kinds.split(",")]

    async with httpx.AsyncClient() as client:
        # Grab the best unreviewed, un-elevated discoveries of the requested kinds
        # PostgREST `in.(a,b,c)` syntax:
        kinds_csv = ",".join(kinds)
        params = {
            "reviewed": "eq.false",
            "kind": f"in.({kinds_csv})",
            "importance": f"gte.{args.min_importance}",
            "select": "id,kind,title,description,claude_reasoning,paper_ids,concept_ids,importance,novelty",
            "order": "importance.desc,novelty.desc",
            "limit": str(args.limit),
        }
        discoveries = await supabase_get(client, "discoveries", params)
        print(f"\n{'='*60}")
        print(f"HYPOTHESIS ELEVATOR — {len(discoveries)} candidates")
        print(f"Budget: ${budget_limit} | Kinds: {kinds_csv}")
        print(f"{'='*60}\n")

        created = 0
        skipped = 0
        for d in discoveries:
            if budget_spent >= budget_limit:
                print("\n*** BUDGET LIMIT ***")
                break

            # Skip if a hypothesis already exists for this discovery
            existing = await supabase_get(client, "research_hypotheses", {
                "discovery_id": f"eq.{d['id']}", "select": "id",
            })
            if existing:
                skipped += 1
                continue

            result = await elevate(client, d)
            if not result:
                continue

            row = {
                "discovery_id": d["id"],
                "title": result.get("title") or d["title"][:100],
                "hypothesis": result.get("hypothesis") or "",
                "rationale": result.get("rationale") or "",
                "predicted_outcome": result.get("predicted_outcome"),
                "testable": bool(result.get("testable", True)),
                "method_suggestion": result.get("method_suggestion"),
                "related_paper_ids": d.get("paper_ids") or [],
                "related_concept_ids": d.get("concept_ids") or [],
                "status": "open",
            }
            created_row = await supabase_post(client, "research_hypotheses", row)
            if created_row:
                created += 1
                print(f"  ✓ {row['title'][:80]}")

        print(f"\n{'='*60}")
        print(f"  Elevated: {created}")
        print(f"  Already had hypothesis: {skipped}")
        print(f"  Cost: ${budget_spent:.3f} / ${budget_limit}")
        print(f"{'='*60}")


def main():
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
