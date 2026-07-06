"""Verification Court — three witnesses before knowledge enters the graph.

The admin cannot be the judge of truth (no human can, across all fields).
So the admin becomes an auditor of PROCESS, and truth is established by
three independent checks:

1. GROUNDING (anti-hallucination, no LLM):
   The claim must include a quote from the source Chappie actually saw,
   and that quote must literally appear in the source text (fuzzy match).
   Not grounded → auto-reject. Kills fabrication at the root.

2. CORROBORATION (independent witnesses):
   The claim is checked against sources Chappie did NOT see — a fresh
   multi-source search. 2+ independent papers supporting → corroborated.
   A contradiction found → red flag.

3. REFUTATION (the adversary):
   A separate LLM call whose ONLY job is to refute: find any reason the
   claim is wrong, overstated, or unsupported by its cited evidence.
   Only claims that survive move forward.

Routing (deliberately conservative):
- not grounded OR decisively refuted        → auto_rejected (feeds the
                                              rejection learning loop)
- grounded + 2 witnesses + survived + it's a definition for a concept
  with no real definition yet               → auto_applied (full receipt)
- everything else                           → pending, WITH the receipt —
  human review becomes "read the receipt", not "be the domain expert"
"""

import json
import logging
import re
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

AUTO_APPROVE_ENABLED = True   # kill-switch; set False to route everything to pending


# ─── Witness 1: Grounding ───────────────────────────────────────────────────

def _normalize_ws(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def ground_check(quote: str | None, source_text: str | None) -> dict:
    """Does the supporting quote actually appear in the source text?

    Mechanical, no LLM. Fuzzy on whitespace/case; requires >= 60% of the
    quote's 6-word shingles to appear in the source (tolerates ellipses).
    """
    if not quote or not source_text:
        return {"passed": False, "reason": "no quote or no source text provided"}

    q = _normalize_ws(quote)
    s = _normalize_ws(source_text)

    if len(q) < 30:
        return {"passed": False, "reason": "quote too short to be meaningful"}

    if q in s:
        return {"passed": True, "match": "exact"}

    words = q.split()
    if len(words) < 6:
        return {"passed": q in s, "match": "short"}
    shingles = [" ".join(words[i:i + 6]) for i in range(0, len(words) - 5, 3)]
    hits = sum(1 for sh in shingles if sh in s)
    ratio = hits / max(len(shingles), 1)
    return {
        "passed": ratio >= 0.6,
        "match": f"shingle {ratio:.0%}",
        "reason": None if ratio >= 0.6 else "quote not found in source",
    }


# ─── Witness 2: Independent corroboration ───────────────────────────────────

async def corroborate(claim_text: str, concept_name: str | None) -> dict:
    """Check the claim against sources Chappie did NOT see.

    Fresh multi-source search + one Haiku assessment of the results.
    """
    try:
        from backend.integrations.multi_source_search import multi_source_search
        query = f"{concept_name}: {claim_text[:120]}" if concept_name else claim_text[:160]
        search = await multi_source_search(query=query, limit_per_source=4)
        papers = search.get("papers", [])[:8]
    except Exception as e:
        return {"independent_supports": 0, "contradicts": 0,
                "error": f"search failed: {e}", "sources": []}

    with_abstracts = [p for p in papers if p.get("abstract")]
    if not with_abstracts:
        return {"independent_supports": 0, "contradicts": 0,
                "sources": [], "note": "no independent abstracts found"}

    lines = [
        f"{i}. [{p.get('title', '')[:80]}] {p['abstract'][:250]}"
        for i, p in enumerate(with_abstracts)
    ]
    prompt = (
        "Does each independent abstract SUPPORT, CONTRADICT, or say NOTHING "
        "about the claim?\n\n"
        f"CLAIM: {claim_text[:400]}\n\nABSTRACTS:\n" + "\n".join(lines) +
        '\n\nReturn ONLY JSON: {"supports": [indices], "contradicts": [indices]}'
    )
    try:
        from backend.config import settings
        from backend.integrations.claude_client import _call_claude
        resp = await _call_claude(prompt, model=settings.haiku_model, max_tokens=120, temperature=0.0)
        text = resp.text
        if "```" in text:
            text = text.split("```")[1].removeprefix("json").strip()
        parsed = json.loads(text[text.find("{"):text.rfind("}") + 1])
        supports = [i for i in parsed.get("supports", []) if isinstance(i, int) and i < len(with_abstracts)]
        contradicts = [i for i in parsed.get("contradicts", []) if isinstance(i, int) and i < len(with_abstracts)]
        return {
            "independent_supports": len(supports),
            "contradicts": len(contradicts),
            "sources": [
                {"title": with_abstracts[i].get("title", "")[:100],
                 "doi": with_abstracts[i].get("doi"), "stance": "supports"}
                for i in supports
            ] + [
                {"title": with_abstracts[i].get("title", "")[:100],
                 "doi": with_abstracts[i].get("doi"), "stance": "contradicts"}
                for i in contradicts
            ],
        }
    except Exception as e:
        return {"independent_supports": 0, "contradicts": 0,
                "error": f"assessment failed: {e}", "sources": []}


# ─── Witness 3: The adversary ───────────────────────────────────────────────

async def refute(claim_text: str, evidence_summary: str) -> dict:
    """A dedicated refuter. Its only job: find why the claim is wrong,
    overstated, or unsupported by its own cited evidence."""
    prompt = (
        "You are an adversarial reviewer. Your ONLY job is to REFUTE this "
        "claim if possible. Look for: overstatement beyond the evidence, "
        "unsupported causal language, missing qualifiers, internal "
        "inconsistency with the cited evidence.\n\n"
        f"CLAIM: {claim_text[:500]}\n\n"
        f"ITS CITED EVIDENCE: {evidence_summary[:800]}\n\n"
        'Return ONLY JSON: {"refuted": true/false, '
        '"severity": "fatal"/"minor"/"none", "objections": ["..."]}'
    )
    try:
        from backend.config import settings
        from backend.integrations.claude_client import _call_claude
        resp = await _call_claude(prompt, model=settings.haiku_model, max_tokens=200, temperature=0.0)
        text = resp.text
        if "```" in text:
            text = text.split("```")[1].removeprefix("json").strip()
        parsed = json.loads(text[text.find("{"):text.rfind("}") + 1])
        return {
            "survived": not (parsed.get("refuted") and parsed.get("severity") == "fatal"),
            "severity": parsed.get("severity", "none"),
            "objections": [str(o)[:200] for o in (parsed.get("objections") or [])[:4]],
        }
    except Exception as e:
        # Fail-CLOSED for auto-approval: an unverifiable claim stays pending
        return {"survived": False, "severity": "unknown",
                "objections": [f"refuter unavailable: {e}"]}


# ─── The Court ──────────────────────────────────────────────────────────────

async def try_verify(
    claim_text: str,
    concept_id: str | None,
    concept_name: str | None,
    enrichment_type: str,
    source: str,
    quote: str | None = None,
    source_text: str | None = None,
    evidence_summary: str = "",
) -> dict:
    """Run the three witnesses and return a routing verdict.

    Returns {route: auto_applied|pending|auto_rejected, verification: {...}}.
    """
    verification: dict = {"checked_at": datetime.now(timezone.utc).isoformat()}

    # Witness 1: grounding.
    # An EXPLICIT quote that isn't in the source = fabrication → auto-reject.
    # A paraphrase (no quote given) can't be string-matched — grounding is
    # informational and the burden shifts to corroboration + refutation.
    if source_text and quote:
        grounding = ground_check(quote, source_text)
        verification["grounding"] = grounding
        if not grounding["passed"]:
            verification["verdict"] = "claimed quote not found in source — likely fabrication"
            return {"route": "auto_rejected", "verification": verification}
    elif source_text:
        informational = ground_check(claim_text[:300], source_text)
        verification["grounding"] = {**informational, "mode": "paraphrase — informational only"}
    else:
        verification["grounding"] = {"passed": None, "reason": "no source text available"}

    # Witness 2: independent corroboration
    corr = await corroborate(claim_text, concept_name)
    verification["corroboration"] = corr
    if corr.get("contradicts", 0) >= 2:
        verification["verdict"] = "independent sources contradict"
        return {"route": "pending", "verification": verification}  # contested — human sees the receipt

    # Witness 3: refutation
    ref = await refute(claim_text, evidence_summary or claim_text)
    verification["refutation"] = ref
    if not ref["survived"] and ref.get("severity") == "fatal":
        verification["verdict"] = "refuted decisively"
        return {"route": "auto_rejected", "verification": verification}

    # Conservative auto-approve: only well-witnessed DEFINITIONS for
    # concepts that don't have a real definition yet
    can_auto = (
        AUTO_APPROVE_ENABLED
        and enrichment_type == "definition"
        and verification["grounding"].get("passed") is not False
        and corr.get("independent_supports", 0) >= 2
        and corr.get("contradicts", 0) == 0
        and ref["survived"] and ref.get("severity") in ("none", "minor")
    )
    if can_auto and concept_id:
        try:
            from backend.integrations.supabase_client import get_client
            client = get_client()
            row = client.table("concepts").select("definition").eq("id", concept_id).execute()
            existing = (row.data[0].get("definition") or "") if row.data else ""
            if len(existing) < 60:
                verification["verdict"] = "grounded + 2 independent witnesses + survived refutation"
                return {"route": "auto_applied", "verification": verification}
        except Exception:
            pass

    verification["verdict"] = "verified receipt attached — human reviews process, not truth"
    return {"route": "pending", "verification": verification}


async def apply_auto_approved(concept_id: str, content: str) -> bool:
    """Apply an auto-approved definition (same effect as admin approve)."""
    try:
        from backend.integrations.supabase_client import get_client
        client = get_client()
        client.table("concepts").update({"definition": content[:500]}).eq("id", concept_id).execute()
        # keep the embedding fresh
        try:
            row = client.table("concepts").select("name").eq("id", concept_id).execute()
            name = row.data[0]["name"] if row.data else ""
            from backend.integrations.openai_client import get_embedding
            emb = await get_embedding(f"{name}: {content[:500]}")
            client.table("concepts").update({"embedding": emb}).eq("id", concept_id).execute()
        except Exception:
            pass
        return True
    except Exception as e:
        logger.warning(f"Auto-apply failed: {e}")
        return False


# ─── Single gateway: ALL enrichment paths submit through the court ──────────

async def submit_enrichment(
    concept_id: str | None,
    concept_name: str | None,
    field: str | None,
    enrichment_type: str,
    source: str,
    content: str,
    references: list | None = None,
    question_asked: str = "",
    priority: int = 0,
    quote: str | None = None,
    source_text: str | None = None,
) -> dict:
    """Verify, then route: auto-apply / pending-with-receipt / auto-reject.

    This is the ONLY door into pending_enrichments for agent-generated
    knowledge. Nothing gets in without its verification receipt.
    """
    from backend.integrations.supabase_client import get_client
    client = get_client()

    evidence_summary = "; ".join(
        str(r.get("title") or r.get("paper") or r)[:100] for r in (references or [])[:6]
    )
    result = await try_verify(
        claim_text=content,
        concept_id=concept_id,
        concept_name=concept_name,
        enrichment_type=enrichment_type,
        source=source,
        quote=quote,
        source_text=source_text,
        evidence_summary=evidence_summary,
    )
    route = result["route"]
    verification = result["verification"]

    applied = False
    if route == "auto_applied" and concept_id:
        applied = await apply_auto_approved(concept_id, content)
        if not applied:
            route = "pending"  # apply failed → fall back to human review

    status = {"auto_applied": "auto_applied", "auto_rejected": "auto_rejected"}.get(route, "pending")
    try:
        client.table("pending_enrichments").insert({
            "concept_id": concept_id,
            "concept_name": concept_name or "",
            "field": field,
            "enrichment_type": enrichment_type,
            "source": source,
            "content": content[:2000],
            "references": (references or [])[:10],
            "question_asked": question_asked[:400],
            "status": status,
            "priority": priority,
            "verification": verification,
        }).execute()
    except Exception as e:
        logger.warning(f"Enrichment record insert failed: {e}")

    # Auto-rejections feed the learning-from-rejection loop
    if route == "auto_rejected":
        try:
            from backend.agents.consciousness import log_learning
            await log_learning(
                entry_type="corrected",
                summary=f"Verification court rejected my {source} claim about "
                        f"{concept_name or '?'}: {verification.get('verdict', '')}",
                concept_name=concept_name, field=field, source=source, confidence=0.2,
            )
        except Exception:
            pass

    logger.info(f"Court verdict [{route}] for {concept_name or '?'} ({source}): "
                f"{verification.get('verdict', '')}")
    return {"route": route, "applied": applied, "verification": verification}
