"""Retrieval Attribution — measure which retrievers actually earn their cost.

Instrumentation only. No architecture changes, no retriever-internal edits.

Per query we record:
- per-retriever chunk counts, latency, token estimates
- which chunks the Synthesis Agent self-reports as used (used_chunk_ids)
- a post-hoc Haiku judge scoring each chunk 0/1/2 against the final answer

A chunk counts as USED if self-reported OR judge score == 2.
Both raw signals are kept in the log for later comparison.

Output: JSONL, one line per query. Analyze with:
  python -m backend.experiments.analyze_attribution
"""

import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel

from backend.search.models import RetrievalResult

logger = logging.getLogger(__name__)

# Internal source name -> experiment retriever name (spec naming)
SOURCE_TO_RETRIEVER = {
    "semantic": "semantic",
    "graph": "kg",
    "citation": "openalex",
    "user": "usergraph",
    # extras logged too — cheap, and lets us sanity-check later
    "perplexity": "perplexity",
    "controversy": "controversy",
}

# The four retrievers the experiment is about (always present in logs, zeroed if absent)
CORE_RETRIEVERS = ["semantic", "kg", "openalex", "usergraph"]

DEFAULT_LOG_PATH = os.path.join("data", "attribution", "attribution_log.jsonl")


class RetrievedChunk(BaseModel):
    chunk_id: str          # short content hash, stable per content
    item_id: str           # the [id] shown to the Synthesis Agent in context
    retriever: Literal["semantic", "kg", "openalex", "usergraph", "perplexity", "controversy"]
    content: str
    score: float | None = None


def enabled(explicit_path: str | None = None) -> str | None:
    """Attribution is on if a path is passed or ATTRIBUTION_LOG env is set."""
    return explicit_path or os.getenv("ATTRIBUTION_LOG") or None


def _hash(content: str) -> str:
    return hashlib.sha1(content.encode("utf-8", errors="replace")).hexdigest()[:10]


def chunks_from_results(results: list[RetrievalResult]) -> list[RetrievedChunk]:
    """Tag every retrieved item with provenance. Wraps — does not modify — retriever output."""
    chunks = []
    for result in results:
        retriever = SOURCE_TO_RETRIEVER.get(result.source)
        if not retriever:
            continue
        for item in result.items:
            chunks.append(RetrievedChunk(
                chunk_id=_hash(item.content),
                item_id=item.id,
                retriever=retriever,
                content=item.content,
                score=item.score,
            ))
    return chunks


def retriever_stats(
    results: list[RetrievalResult],
    timings_ms: dict[str, float],
) -> dict:
    """Per-retriever {n_chunks, latency_ms, tokens}. Core four always present."""
    stats = {name: {"n_chunks": 0, "latency_ms": 0, "tokens": 0} for name in CORE_RETRIEVERS}
    for result in results:
        name = SOURCE_TO_RETRIEVER.get(result.source)
        if not name:
            continue
        tokens = result.token_estimate or sum(len(i.content) // 4 for i in result.items)
        stats[name] = {
            "n_chunks": len(result.items),
            "latency_ms": round(timings_ms.get(result.source, 0)),
            "tokens": tokens,
        }
    return stats


async def judge_chunks(query: str, answer: str, chunks: list[RetrievedChunk]) -> dict[str, int]:
    """Signal B — one Haiku call scoring each chunk 0/1/2 against the final answer.

    0 = irrelevant, 1 = supportive/overlapping, 2 = the answer depends on it.
    Defensive parsing: any failure returns {} (chunks then rely on self-report only).
    """
    if not chunks or not answer:
        return {}

    chunk_lines = []
    for c in chunks[:40]:  # bound the judge context
        snippet = c.content[:300].replace("\n", " ")
        chunk_lines.append(f'- chunk_id "{c.chunk_id}": {snippet}')

    prompt = (
        "You are scoring retrieval chunks against a final answer.\n\n"
        f"QUESTION: {query}\n\n"
        f"FINAL ANSWER:\n{answer[:3000]}\n\n"
        "CHUNKS:\n" + "\n".join(chunk_lines) + "\n\n"
        "Score each chunk:\n"
        "0 = irrelevant to the answer\n"
        "1 = supportive/overlapping with the answer\n"
        "2 = the answer depends on it (removing it would break a claim)\n\n"
        'Return ONLY JSON mapping chunk_id to score, e.g. {"ab12cd34ef": 2, ...}'
    )

    try:
        from backend.config import settings
        from backend.integrations.claude_client import _call_claude

        resp = await _call_claude(prompt, model=settings.haiku_model, max_tokens=800, temperature=0.0)
        text = resp.text.strip()
        if "```" in text:
            text = text.split("```")[1].removeprefix("json").strip()
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end == -1:
            return {}
        raw = json.loads(text[start:end + 1])
        scores = {}
        for k, v in raw.items():
            try:
                scores[str(k)] = max(0, min(2, int(v)))
            except (TypeError, ValueError):
                continue
        return scores
    except Exception as e:
        logger.warning(f"Attribution judge failed (self-report only for this query): {e}")
        return {}


def build_record(
    query: str,
    query_type: str,
    chunks: list[RetrievedChunk],
    stats: dict,
    used_chunk_ids: list[str],
    judge_scores: dict[str, int],
    answer: str,
) -> dict:
    """One JSONL line per query."""
    used_set = set(used_chunk_ids or [])
    chunk_rows = []
    for c in chunks:
        chunk_rows.append({
            "chunk_id": c.chunk_id,
            "item_id": c.item_id,
            "retriever": c.retriever,
            # synthesis sees [item_id] in context; accept either identifier
            "self_report_used": (c.item_id in used_set) or (c.chunk_id in used_set),
            "judge_score": judge_scores.get(c.chunk_id),
        })

    return {
        "query_id": _hash(query + datetime.now(timezone.utc).isoformat()),
        "query": query,
        "query_type": query_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "retrievers": stats,
        "chunks": chunk_rows,
        "answer_len_tokens": len(answer) // 4,
    }


def write_record(record: dict, path: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
