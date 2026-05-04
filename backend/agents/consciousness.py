"""Korczak Consciousness — learning log, reflection, curiosity, and voice.

This is Korczak's inner life. It tracks what he learns, reflects on it,
generates curiosity about what he doesn't know, and proactively reaches
out when he has something important to say.

Components:
1. Learning Log — diary of everything learned (discovered, confirmed, contradicted)
2. Reflection — periodic self-summaries ("this week I learned...")
3. Curiosity — queue of things Korczak wants to explore next
4. Voice (Mouth) — proactive messages to users and experts
5. Memory Sync — bidirectional Obsidian vault as long-term memory
"""

import logging
from datetime import datetime, timezone, timedelta

from backend.integrations.supabase_client import get_client

logger = logging.getLogger(__name__)


# ─── 1. Learning Log ────────────────────────────────────────────────────────

async def log_learning(
    entry_type: str,
    summary: str,
    concept_name: str | None = None,
    concept_id: str | None = None,
    field: str | None = None,
    detail: str | None = None,
    source: str | None = None,
    source_ref: str | None = None,
    confidence: float = 0.5,
) -> str:
    """Record something Korczak learned.

    entry_type: discovered, confirmed, contradicted, deepened,
                connected, corrected, from_expert, from_student
    """
    client = get_client()
    result = client.table("learning_log").insert({
        "entry_type": entry_type,
        "concept_id": concept_id,
        "concept_name": concept_name,
        "field": field,
        "summary": summary,
        "detail": detail,
        "source": source,
        "source_ref": source_ref,
        "confidence": confidence,
    }).execute()

    logger.info(f"Learning log: [{entry_type}] {summary[:80]}")
    return result.data[0]["id"] if result.data else ""


async def get_recent_learnings(
    field: str | None = None,
    limit: int = 20,
    hours: int | None = None,
) -> list[dict]:
    """Get recent learning log entries."""
    client = get_client()
    query = client.table("learning_log").select("*")
    if field:
        query = query.eq("field", field)
    if hours:
        since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        query = query.gte("created_at", since)
    result = query.order("created_at", desc=True).limit(limit).execute()
    return result.data or []


# ─── 2. Reflection ──────────────────────────────────────────────────────────

async def generate_reflection(
    reflection_type: str = "daily",
    field: str | None = None,
) -> dict:
    """Generate a self-reflection summarizing recent learning.

    Korczak looks back at his learning log and synthesizes:
    - What did I learn?
    - What surprised me?
    - What contradictions did I find?
    - What questions remain open?
    """
    hours = 24 if reflection_type == "daily" else 168  # 7 days for weekly
    entries = await get_recent_learnings(field=field, hours=hours)

    if not entries:
        return {"reflection_type": reflection_type, "summary": "No learning activity in this period."}

    # Categorize
    discoveries = [e for e in entries if e["entry_type"] in ("discovered", "deepened")]
    contradictions = [e for e in entries if e["entry_type"] == "contradicted"]
    connections = [e for e in entries if e["entry_type"] == "connected"]
    corrections = [e for e in entries if e["entry_type"] == "corrected"]
    from_experts = [e for e in entries if e["entry_type"] == "from_expert"]
    from_students = [e for e in entries if e["entry_type"] == "from_student"]

    # Build summary
    period = "today" if reflection_type == "daily" else "this week"
    parts = []

    if discoveries:
        names = [e.get("concept_name", "?") for e in discoveries[:5]]
        parts.append(f"Discovered or deepened understanding of: {', '.join(names)}")

    if contradictions:
        parts.append(f"Found {len(contradictions)} contradictions in the literature")
        for c in contradictions[:3]:
            parts.append(f"  - {c['summary']}")

    if connections:
        parts.append(f"Made {len(connections)} new connections between concepts")

    if from_experts:
        expert_names = set(e.get("source", "?") for e in from_experts)
        parts.append(f"Learned from experts: {', '.join(expert_names)}")

    if from_students:
        parts.append(f"Learned {len(from_students)} things from student interactions")

    if corrections:
        parts.append(f"Corrected {len(corrections)} misconceptions")

    summary = f"Reflection ({period}):\n" + "\n".join(parts)

    # Get open questions from curiosity queue
    client = get_client()
    open_q = client.table("curiosity_queue").select(
        "question"
    ).eq("status", "curious").order("priority", desc=True).limit(5).execute()
    open_questions = [q["question"] for q in (open_q.data or [])]

    # Store reflection
    now = datetime.now(timezone.utc)
    result = client.table("reflections").insert({
        "reflection_type": reflection_type,
        "field": field,
        "period_start": (now - timedelta(hours=hours)).isoformat(),
        "period_end": now.isoformat(),
        "summary": summary,
        "key_discoveries": [e.get("summary", "") for e in discoveries[:5]],
        "open_questions": open_questions,
        "contradictions_found": [e.get("summary", "") for e in contradictions[:5]],
        "connections_made": len(connections),
        "concepts_enriched": len(discoveries),
        "sources_consulted": len(set(e.get("source", "") for e in entries)),
    }).execute()

    return {
        "id": result.data[0]["id"] if result.data else None,
        "reflection_type": reflection_type,
        "field": field,
        "summary": summary,
        "stats": {
            "discoveries": len(discoveries),
            "contradictions": len(contradictions),
            "connections": len(connections),
            "corrections": len(corrections),
            "from_experts": len(from_experts),
            "from_students": len(from_students),
            "open_questions": len(open_questions),
        },
        "open_questions": open_questions,
    }


async def get_reflections(
    field: str | None = None,
    limit: int = 10,
) -> list[dict]:
    """Get past reflections."""
    client = get_client()
    query = client.table("reflections").select("*")
    if field:
        query = query.eq("field", field)
    result = query.order("created_at", desc=True).limit(limit).execute()
    return result.data or []


# ─── 3. Curiosity ───────────────────────────────────────────────────────────

async def add_curiosity(
    question: str,
    trigger: str,
    field: str | None = None,
    concept_name: str | None = None,
    concept_id: str | None = None,
    priority: int = 0,
) -> str:
    """Add something to Korczak's curiosity queue.

    trigger: what made him curious (e.g., "student asked about X",
    "found contradiction in Y", "paper Z mentioned unknown concept")
    """
    client = get_client()
    result = client.table("curiosity_queue").insert({
        "question": question,
        "field": field,
        "concept_id": concept_id,
        "concept_name": concept_name,
        "trigger": trigger,
        "priority": priority,
        "status": "curious",
    }).execute()

    logger.info(f"Curiosity: {question[:60]}... (trigger: {trigger[:40]})")
    return result.data[0]["id"] if result.data else ""


async def get_curiosities(
    field: str | None = None,
    status: str = "curious",
    limit: int = 10,
) -> list[dict]:
    """Get Korczak's current curiosities."""
    client = get_client()
    query = client.table("curiosity_queue").select("*").eq("status", status)
    if field:
        query = query.eq("field", field)
    result = query.order("priority", desc=True).order("created_at").limit(limit).execute()
    return result.data or []


async def auto_generate_curiosities(field: str, limit: int = 5) -> list[str]:
    """Korczak generates his own questions based on what he knows.

    Looks at the knowledge graph and asks:
    - "I know X and Y are connected, but WHY?"
    - "X has no contradictions — is it really that settled?"
    - "Nobody has written about the connection between A and B — is there one?"
    """
    client = get_client()

    from backend.agents.learning_agent import find_weak_spots
    weak = await find_weak_spots(field, limit=limit)

    generated = []
    for spot in weak:
        if "orphan" in spot["reasons"]:
            q = f"Is {spot['concept_name']} truly isolated, or am I missing connections to other concepts in {field}?"
            await add_curiosity(
                question=q, trigger="orphan_detection",
                field=field, concept_name=spot["concept_name"],
                concept_id=spot["concept_id"], priority=spot["score"],
            )
            generated.append(q)

        elif "important_but_uncertain" in spot["reasons"]:
            q = f"Why is {spot['concept_name']} referenced in {spot['paper_count']} papers but still has low confidence? What am I missing?"
            await add_curiosity(
                question=q, trigger="confidence_gap",
                field=field, concept_name=spot["concept_name"],
                concept_id=spot["concept_id"], priority=spot["score"],
            )
            generated.append(q)

    return generated


# ─── 4. Voice (Mouth) — Proactive Communication ────────────────────────────

async def generate_proactive_message(
    user_id: str,
    field: str | None = None,
) -> dict | None:
    """Generate a proactive message from Korczak to a user.

    Korczak speaks up when he has something worth sharing:
    - Found a contradiction relevant to what the user is studying
    - Discovered a connection between two things the user learned
    - Has a curiosity the user might help answer
    - Made a correction to something he taught the user before
    """
    # Check recent learnings
    entries = await get_recent_learnings(field=field, hours=24)

    if not entries:
        return None

    # Priority: contradictions > connections > discoveries
    contradictions = [e for e in entries if e["entry_type"] == "contradicted"]
    if contradictions:
        c = contradictions[0]
        return {
            "type": "contradiction_alert",
            "message": f"I found something interesting — {c['summary']}. This might change how we think about {c.get('concept_name', 'this topic')}.",
            "concept_name": c.get("concept_name"),
            "source": c.get("source"),
        }

    connections = [e for e in entries if e["entry_type"] == "connected"]
    if connections:
        c = connections[0]
        return {
            "type": "connection_discovered",
            "message": f"I made a connection you might find interesting: {c['summary']}",
            "concept_name": c.get("concept_name"),
        }

    corrections = [e for e in entries if e["entry_type"] == "corrected"]
    if corrections:
        c = corrections[0]
        return {
            "type": "correction",
            "message": f"I need to correct something I may have said before about {c.get('concept_name', 'a topic')}: {c['summary']}",
            "concept_name": c.get("concept_name"),
        }

    return None


# ─── 5. Memory Sync — Obsidian as Long-Term Memory ─────────────────────────

async def export_memory_to_obsidian(field: str | None = None) -> dict:
    """Export Korczak's learning log and reflections as Obsidian notes.

    Creates a 'Korczak Memory' vault structure:
      Korczak Memory/
        Learning Log/
          2026-05-04 — Discovered thick description connection.md
        Reflections/
          2026-05-04 — Daily Reflection.md
        Curiosities/
          Open Questions.md
    """
    import io
    import zipfile
    from datetime import datetime, timezone

    entries = await get_recent_learnings(field=field, limit=100)
    reflections = await get_reflections(field=field, limit=10)
    curiosities = await get_curiosities(field=field, limit=20)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # Learning log entries
        for entry in entries:
            date = entry.get("created_at", "")[:10]
            name = (entry.get("concept_name") or "general").replace("/", "-")
            filename = f"Korczak Memory/Learning Log/{date} — {entry['entry_type']} {name}.md"

            content = f"""---
type: {entry['entry_type']}
concept: "{entry.get('concept_name', '')}"
field: "{entry.get('field', '')}"
source: "{entry.get('source', '')}"
confidence: {entry.get('confidence', 0.5)}
date: "{date}"
tags:
  - korczak-memory
  - {entry['entry_type']}
---

# {entry.get('summary', '')}

{entry.get('detail', '')}

**Source**: {entry.get('source', 'unknown')} ({entry.get('source_ref', '')})
"""
            zf.writestr(filename, content)

        # Reflections
        for ref in reflections:
            date = ref.get("created_at", "")[:10]
            rtype = ref.get("reflection_type", "daily")
            filename = f"Korczak Memory/Reflections/{date} — {rtype.title()} Reflection.md"

            content = f"""---
type: reflection
reflection_type: {rtype}
field: "{ref.get('field', '')}"
date: "{date}"
concepts_enriched: {ref.get('concepts_enriched', 0)}
connections_made: {ref.get('connections_made', 0)}
tags:
  - korczak-memory
  - reflection
---

# {rtype.title()} Reflection — {date}

{ref.get('summary', '')}

## Open Questions
"""
            for q in (ref.get("open_questions") or []):
                content += f"- {q}\n"

            content += "\n## Key Discoveries\n"
            for d in (ref.get("key_discoveries") or []):
                content += f"- {d}\n"

            if ref.get("contradictions_found"):
                content += "\n## Contradictions Found\n"
                for c in ref["contradictions_found"]:
                    content += f"- {c}\n"

            zf.writestr(filename, content)

        # Curiosities
        if curiosities:
            content = """---
tags:
  - korczak-memory
  - curiosity
---

# What I'm Curious About

"""
            for c in curiosities:
                content += f"## {c.get('question', '')}\n"
                content += f"*Trigger*: {c.get('trigger', '')}\n"
                content += f"*Field*: {c.get('field', '')}\n"
                content += f"*Priority*: {c.get('priority', 0)}\n\n"

            zf.writestr("Korczak Memory/Curiosities/Open Questions.md", content)

    buf.seek(0)
    return {
        "zip_bytes": buf.read(),
        "entries": len(entries),
        "reflections": len(reflections),
        "curiosities": len(curiosities),
    }
