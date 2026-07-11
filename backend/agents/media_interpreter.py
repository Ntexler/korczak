"""Media interpreter — turns a clip into *evidence*, not just an embed.

Given a media record + the claim/concept it should reinforce, Korczak reads
the transcript and produces:
  - interpretation : what this clip means FOR the claim (Layer 1)
  - subtext        : "between the lines" — irony/aggression/what's NOT said
  - subtext_basis  : the concrete cue the subtext rests on (the humility rule)
  - grounding_quote: the exact spoken span the reading is anchored to (Layer 0)

Everything is then run through the SAME verification court as every other
enrichment: grounding checks that the quote was actually spoken (anti-
hallucination), and the result is stored as a *contestable interpretation*,
never as asserted fact. Reading intent into a real person is epistemically
dangerous — so subtext is always labelled, always basis-bearing.

Layers 2-3 (prosody from audio, visual/body-language from sampled frames —
the "Bibi's face" payload) are stubbed here behind analyze_moment_visual();
they run only on flagged moments and only once we build the vision pass.
"""

import json
import logging

from backend.config import settings
from backend.integrations.claude_client import _call_claude

logger = logging.getLogger(__name__)


_INTERPRET_PROMPT = """You are Korczak, reading a piece of media as EVIDENCE for a claim.

CLAIM / TOPIC: {claim}

MEDIA: "{title}"
SOURCE: {source}
DESCRIPTION: {description}

TRANSCRIPT (what was actually said — may be empty or partial):
\"\"\"
{transcript}
\"\"\"

Produce a STRICT JSON object, no prose around it:
{{
  "relevance": 0.0-1.0,          // how strongly this clip bears on the claim
  "interpretation": "...",        // what this clip MEANS for the claim — the reading a scholar would give, not a summary of the words
  "grounding_quote": "...",       // the EXACT span from the transcript your reading rests on; "" if transcript is empty
  "subtext": "...",               // what is communicated between the lines: irony, aggression, evasion, what is conspicuously NOT said. "" if none is warranted.
  "subtext_basis": "..."          // the concrete cue the subtext rests on (e.g. "says 'great job' right after describing a failure"). REQUIRED if subtext is non-empty.
}}

RULES — you are interpreting real people; be disciplined:
- interpretation and subtext are YOUR reading, offered as contestable, never as the person's proven intent. Do not write "he lied" / "she knew"; write what is SAID and what it is CONSISTENT WITH.
- Never invent a quote. grounding_quote must be a verbatim substring of the transcript, or "".
- If the transcript is empty, base a modest interpretation on title+description and set grounding_quote to "".
- No subtext without a concrete basis. Speculation is not subtext."""


async def interpret_media(record: dict, claim: str, transcript: str = "") -> dict:
    """Read one media record as evidence for `claim`. Returns the reading dict."""
    prompt = _INTERPRET_PROMPT.format(
        claim=claim[:600],
        title=(record.get("title") or "")[:300],
        source=record.get("source", ""),
        description=(record.get("description") or "")[:800],
        transcript=(transcript or "")[:5000] or "(no transcript available)",
    )
    try:
        resp = await _call_claude(prompt, model=settings.haiku_model, max_tokens=700, temperature=0.2)
        data = _parse_json(resp.text)
    except Exception as e:
        logger.warning(f"Media interpretation failed: {e}")
        data = {}

    return {
        "relevance": _clamp(data.get("relevance", 0.5)),
        "interpretation": (data.get("interpretation") or "").strip()[:1500],
        "grounding_quote": (data.get("grounding_quote") or "").strip()[:500],
        "subtext": (data.get("subtext") or "").strip()[:800],
        "subtext_basis": (data.get("subtext_basis") or "").strip()[:500],
    }


async def assess_and_store(client, record: dict, concept_id: str | None,
                           concept_name: str, claim: str, brought_by: str = "chappie",
                           contributed_by: str | None = None) -> dict | None:
    """Interpret → verify grounding through the court → store in media_evidence.

    Returns the stored row (or None). The interpretation is audited but stored
    as a contestable reading; grounding drives consensus_status, not truth.
    """
    from backend.agents.verification_court import try_verify

    transcript = ""
    try:
        from backend.integrations.media_sources import fetch_transcript
        transcript = await fetch_transcript(record)
    except Exception:
        pass

    reading = await interpret_media(record, claim, transcript)

    # Same court, grounding only: was the quote actually spoken?
    consensus = "unverified"
    verification = {}
    try:
        if reading["grounding_quote"] and transcript:
            v = await try_verify(
                claim_text=reading["interpretation"],
                concept_id=concept_id, concept_name=concept_name,
                enrichment_type="media_evidence", source=record.get("source", "media"),
                quote=reading["grounding_quote"], source_text=transcript,
                evidence_summary=record.get("title", ""),
            )
            verification = v.get("verification", {})
            consensus = {"auto_applied": "grounded", "auto_rejected": "refuted"}.get(
                v.get("route"), "unverified")
    except Exception as e:
        logger.debug(f"Media grounding check failed: {e}")

    row = {
        "concept_id": concept_id,
        "source": record.get("source"),
        "external_id": record.get("external_id"),
        "media_kind": record.get("media_kind", "video"),
        "title": (record.get("title") or "")[:400],
        "embed_url": record.get("embed_url"),
        "page_url": record.get("page_url"),
        "thumbnail_url": record.get("thumbnail_url"),
        "duration_seconds": record.get("duration_seconds"),
        "transcript_excerpt": (transcript or "")[:2000] or None,
        "grounding_quote": reading["grounding_quote"] or None,
        "interpretation": reading["interpretation"] or None,
        "subtext": reading["subtext"] or None,
        "subtext_basis": reading["subtext_basis"] or None,
        "relevance": reading["relevance"],
        "consensus_status": consensus,
        "verification": verification,
        "brought_by": brought_by,
        "contributed_by": contributed_by,
    }
    try:
        res = client.table("media_evidence").upsert(
            row, on_conflict="concept_id,source,external_id",
        ).execute()
        return (res.data or [None])[0]
    except Exception as e:
        logger.warning(f"media_evidence upsert failed: {e}")
        return None


async def analyze_moment_visual(record: dict, timestamp_s: float, window_s: float = 5.0) -> dict:
    """Layer 3 (STUB — the "Bibi's face" payload). Not wired into the default path.

    Planned: sample frames at [timestamp-window, timestamp+window], send them to
    a vision model to DESCRIBE observable affect (not read minds), and return a
    contestable visual reading with its frame-level basis. Requires the video
    bytes + frame extraction; built only after we align on the approach.
    """
    return {
        "available": False,
        "reason": "visual moment analysis not yet enabled",
        "planned_basis": f"frames around {timestamp_s:.1f}s (±{window_s:.0f}s)",
    }


# --- helpers ---------------------------------------------------------------

def _parse_json(text: str) -> dict:
    text = (text or "").strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1].lstrip("json").strip() if "```" in text else text
    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            return {}
    return {}


def _clamp(v, lo=0.0, hi=1.0):
    try:
        return max(lo, min(hi, float(v)))
    except (TypeError, ValueError):
        return 0.5
