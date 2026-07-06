"""Proposition Engine — cluster claims into canonical propositions.

The atomic unit of real understanding: ONE proposition that many papers
assert, negate, or qualify — instead of 50 disconnected claim rows for
the same idea phrased 50 ways.

The two-stage pipeline (embeddings are negation-blind — "A causes B" and
"A does not cause B" score ~0.9 cosine — so a verification pass is mandatory):

  claim ──► pgvector: nearest propositions (cosine > 0.85)   [cheap, blind]
        ──► Haiku verify: asserts / negates / qualifies /     [50 tokens,
            unrelated, per candidate                            sees negation]
        ──► link with stance, or create a new proposition

Consensus per proposition = the real evidence balance:
  12 assert / 2 qualify / 1 negate — on the SAME claim, finally.

Usage:
  python -m backend.graph.propositions --field Anthropology --limit 200
"""

import argparse
import asyncio
import json
import logging
import sys

logger = logging.getLogger(__name__)

SIMILARITY_THRESHOLD = 0.85


async def _verify_stance(new_claim: str, candidates: list[dict]) -> list[dict]:
    """One Haiku call: stance of new claim vs each candidate proposition.

    Returns [{index, stance}] where stance in asserts/negates/qualifies/unrelated.
    Fail-open to [] (claim becomes its own proposition — safe default).
    """
    lines = [f"{i}. {c['canonical_text'][:200]}" for i, c in enumerate(candidates[:5])]
    prompt = (
        "A NEW claim vs EXISTING canonical propositions. For each, classify:\n"
        "- asserts: same proposition (possibly reworded)\n"
        "- negates: asserts the OPPOSITE\n"
        "- qualifies: agrees but adds conditions/limits\n"
        "- unrelated: different proposition\n\n"
        f"NEW CLAIM: {new_claim[:400]}\n\nEXISTING:\n" + "\n".join(lines) +
        '\n\nReturn ONLY JSON: [{"index": 0, "stance": "asserts"}, ...]'
    )
    try:
        from backend.config import settings
        from backend.integrations.claude_client import _call_claude
        resp = await _call_claude(prompt, model=settings.haiku_model, max_tokens=150, temperature=0.0)
        text = resp.text
        if "```" in text:
            text = text.split("```")[1].removeprefix("json").strip()
        start, end = text.find("["), text.rfind("]")
        parsed = json.loads(text[start:end + 1])
        return [
            {"index": int(v["index"]), "stance": v["stance"]}
            for v in parsed
            if isinstance(v, dict) and v.get("stance") in ("asserts", "negates", "qualifies", "unrelated")
        ]
    except Exception as e:
        logger.debug(f"Stance verification failed (claim becomes new proposition): {e}")
        return []


async def assimilate_claim(claim: dict, concept_id: str | None = None, field: str | None = None) -> dict:
    """Assimilate one claim into the proposition layer.

    claim: {id, claim_text, embedding?, confidence?}
    Returns {action: linked|created|skipped, proposition_id, stance}.
    """
    from backend.integrations.supabase_client import get_client
    client = get_client()

    text = (claim.get("claim_text") or "").strip()
    if len(text) < 20:
        return {"action": "skipped", "reason": "too short"}

    # Already assimilated?
    existing = client.table("claim_propositions").select("proposition_id").eq(
        "claim_id", claim["id"]
    ).limit(1).execute()
    if existing.data:
        return {"action": "skipped", "reason": "already linked",
                "proposition_id": existing.data[0]["proposition_id"]}

    # Embedding (from the claim row, or generate)
    embedding = claim.get("embedding")
    if not embedding:
        try:
            from backend.integrations.openai_client import get_embedding
            embedding = await get_embedding(text)
        except Exception as e:
            return {"action": "skipped", "reason": f"no embedding: {e}"}

    # Stage 1: nearest propositions (negation-blind)
    candidates = []
    try:
        result = client.rpc("match_propositions", {
            "query_embedding": embedding,
            "match_threshold": SIMILARITY_THRESHOLD,
            "match_count": 5,
        }).execute()
        candidates = result.data or []
    except Exception as e:
        logger.debug(f"match_propositions RPC failed: {e}")

    # Stage 2: stance verification (sees negation)
    if candidates:
        verdicts = await _verify_stance(text, candidates)
        for v in verdicts:
            if v["stance"] in ("asserts", "negates", "qualifies") and v["index"] < len(candidates):
                prop_id = candidates[v["index"]]["id"]
                client.table("claim_propositions").insert({
                    "claim_id": claim["id"],
                    "proposition_id": prop_id,
                    "stance": v["stance"],
                    "match_confidence": candidates[v["index"]].get("similarity", 0.85),
                }).execute()
                await _update_evidence_balance(client, prop_id)
                if concept_id:
                    _link_concept(client, concept_id, prop_id)
                return {"action": "linked", "proposition_id": prop_id, "stance": v["stance"]}

    # No match — this claim founds a new proposition
    created = client.table("propositions").insert({
        "canonical_text": text[:500],
        "embedding": embedding,
        "field": field,
        "assert_count": 1,
        "evidence_mass": claim.get("confidence", 0.5),
    }).execute()
    if not created.data:
        return {"action": "skipped", "reason": "insert failed"}
    prop_id = created.data[0]["id"]

    client.table("claim_propositions").insert({
        "claim_id": claim["id"],
        "proposition_id": prop_id,
        "stance": "asserts",
        "match_confidence": 1.0,
    }).execute()
    if concept_id:
        _link_concept(client, concept_id, prop_id)
    return {"action": "created", "proposition_id": prop_id, "stance": "asserts"}


def _link_concept(client, concept_id: str, prop_id: str) -> None:
    try:
        client.table("concept_propositions").insert({
            "concept_id": concept_id, "proposition_id": prop_id,
        }).execute()
    except Exception:
        pass  # duplicate link — fine


async def _update_evidence_balance(client, prop_id: str) -> None:
    """Recount the assert/negate/qualify balance and derive consensus."""
    links = client.table("claim_propositions").select("stance").eq(
        "proposition_id", prop_id
    ).execute()
    stances = [l["stance"] for l in (links.data or [])]
    a, n, q = stances.count("asserts"), stances.count("negates"), stances.count("qualifies")

    if n > 0 and a > 0:
        status = "contested"
    elif a >= 3 and n == 0:
        status = "consensus"
    else:
        status = "emerging"

    client.table("propositions").update({
        "assert_count": a, "negate_count": n, "qualify_count": q,
        "evidence_mass": round(a + 0.5 * q - n, 2),
        "consensus_status": status,
    }).eq("id", prop_id).execute()


async def build_propositions(field: str | None = None, limit: int = 200) -> dict:
    """Batch job: assimilate un-linked claims into the proposition layer."""
    from backend.integrations.supabase_client import get_client
    client = get_client()

    # Claims not yet linked to any proposition (paginated diff)
    linked = client.table("claim_propositions").select("claim_id").limit(20000).execute()
    linked_ids = {l["claim_id"] for l in (linked.data or [])}

    claims = client.table("claims").select(
        "id, claim_text, embedding, confidence, paper_id"
    ).order("confidence", desc=True).limit(limit + len(linked_ids)).execute()

    todo = [c for c in (claims.data or []) if c["id"] not in linked_ids][:limit]
    stats = {"linked": 0, "created": 0, "skipped": 0}

    for i, claim in enumerate(todo):
        # Resolve the claim's concept via its paper (best-effort)
        concept_id = None
        try:
            pc = client.table("paper_concepts").select("concept_id").eq(
                "paper_id", claim["paper_id"]
            ).order("relevance", desc=True).limit(1).execute()
            if pc.data:
                concept_id = pc.data[0]["concept_id"]
        except Exception:
            pass

        result = await assimilate_claim(claim, concept_id=concept_id, field=field)
        stats[result["action"]] = stats.get(result["action"], 0) + 1
        if (i + 1) % 20 == 0:
            logger.info(f"  [{i + 1}/{len(todo)}] {stats}")
        await asyncio.sleep(0.1)

    return {"processed": len(todo), **stats}


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    sys.stdout.reconfigure(encoding="utf-8")
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    parser = argparse.ArgumentParser(description="Build the proposition layer from claims")
    parser.add_argument("--field", default=None)
    parser.add_argument("--limit", type=int, default=200)
    args = parser.parse_args()

    result = asyncio.run(build_propositions(field=args.field, limit=args.limit))
    print(json.dumps(result, indent=2))
