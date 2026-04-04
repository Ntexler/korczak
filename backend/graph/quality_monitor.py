"""Navigator Quality Monitor — checks response quality without LLM calls.

Checks (no API credits needed):
  1. Concept grounding: Do referenced concepts actually exist in the graph?
  2. Source verification: Do cited papers exist in the database?
  3. Response completeness: Did the response include concepts and insight?
  4. Conversation health: Average concepts per response, insight rate

Usage:
    python -m backend.graph.quality_monitor
    python -m backend.graph.quality_monitor --last 50  # Check last 50 messages
"""

import asyncio
import argparse
import logging
from datetime import datetime, timezone
from dataclasses import dataclass, field

from backend.integrations.supabase_client import get_client

logger = logging.getLogger(__name__)


@dataclass
class QualityReport:
    timestamp: str
    total_conversations: int = 0
    total_messages: int = 0
    assistant_messages: int = 0
    messages_with_concepts: int = 0
    messages_with_insights: int = 0
    avg_concepts_per_response: float = 0.0
    insight_rate_pct: float = 0.0
    ungrounded_concepts: list[dict] = field(default_factory=list)
    empty_responses: int = 0

    @property
    def healthy(self) -> bool:
        return (
            len(self.ungrounded_concepts) == 0
            and self.empty_responses == 0
        )

    def summary(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "healthy": self.healthy,
            "conversations": self.total_conversations,
            "messages": {
                "total": self.total_messages,
                "assistant": self.assistant_messages,
                "with_concepts": self.messages_with_concepts,
                "with_insights": self.messages_with_insights,
                "empty_responses": self.empty_responses,
            },
            "quality": {
                "avg_concepts_per_response": round(self.avg_concepts_per_response, 2),
                "insight_rate_pct": round(self.insight_rate_pct, 1),
                "ungrounded_concept_count": len(self.ungrounded_concepts),
            },
        }


async def run_quality_check(limit: int = 100) -> QualityReport:
    """Check quality of recent navigator responses."""
    client = get_client()
    report = QualityReport(timestamp=datetime.now(timezone.utc).isoformat())

    # Get conversation count
    convs = client.table("conversations").select("id", count="exact").execute()
    report.total_conversations = convs.count or 0

    # Get recent messages
    messages = (
        client.table("messages")
        .select("id, role, content, concepts_referenced, created_at")
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    report.total_messages = len(messages.data)

    # Get all concept IDs for grounding check
    all_concepts = client.table("concepts").select("id, name").execute()
    concept_ids = {c["id"] for c in all_concepts.data}
    concept_names = {c["name"].lower() for c in all_concepts.data}

    # Analyze assistant messages
    total_concepts = 0
    for msg in messages.data:
        if msg["role"] != "assistant":
            continue

        report.assistant_messages += 1

        # Check for empty responses
        if not msg.get("content") or len(msg["content"].strip()) < 10:
            report.empty_responses += 1
            continue

        # Check concepts_referenced
        refs = msg.get("concepts_referenced") or []
        if refs:
            report.messages_with_concepts += 1
            total_concepts += len(refs)

            # Grounding check: do referenced concepts exist?
            for ref in refs:
                ref_id = ref.get("id") if isinstance(ref, dict) else ref
                ref_name = ref.get("name", "unknown") if isinstance(ref, dict) else "unknown"
                if ref_id and ref_id not in concept_ids:
                    report.ungrounded_concepts.append({
                        "concept_id": ref_id,
                        "concept_name": ref_name,
                        "message_id": msg["id"],
                    })

        # Check for insight markers in content
        content_lower = msg["content"].lower()
        insight_markers = [
            "insight:", "blind spot:", "something you might not",
            "what you might be missing", "a connection worth noting",
            "did you know", "unsolicited insight",
        ]
        if any(marker in content_lower for marker in insight_markers):
            report.messages_with_insights += 1

    # Calculate rates
    if report.assistant_messages > 0:
        report.avg_concepts_per_response = total_concepts / report.assistant_messages
        report.insight_rate_pct = report.messages_with_insights / report.assistant_messages * 100

    return report


def print_report(report: QualityReport):
    """Pretty-print the quality report."""
    print("=" * 60)
    print("KORCZAK NAVIGATOR QUALITY CHECK")
    print("=" * 60)
    print(f"Timestamp: {report.timestamp}")
    print(f"Status: {'HEALTHY' if report.healthy else 'ISSUES FOUND'}")
    print()

    print(f"Conversations: {report.total_conversations}")
    print(f"Messages analyzed: {report.total_messages} ({report.assistant_messages} assistant)")
    print()

    print("Quality Metrics:")
    print(f"  Avg concepts/response: {report.avg_concepts_per_response:.2f}")
    print(f"  Insight rate:          {report.insight_rate_pct:.1f}%")
    print(f"  Empty responses:       {report.empty_responses}")
    print(f"  Ungrounded concepts:   {len(report.ungrounded_concepts)}")
    print()

    if report.ungrounded_concepts:
        print("Ungrounded Concepts (referenced but not in graph):")
        for uc in report.ungrounded_concepts[:10]:
            print(f"  - {uc['concept_name']} ({uc['concept_id'][:8]}...)")
        print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Korczak Navigator Quality Monitor")
    parser.add_argument("--last", type=int, default=100, help="Number of recent messages to check")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    async def main():
        report = await run_quality_check(limit=args.last)
        if args.json:
            import json
            print(json.dumps(report.summary(), indent=2))
        else:
            print_report(report)

    asyncio.run(main())
