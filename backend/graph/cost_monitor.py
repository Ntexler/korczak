"""Cost Monitor — tracks Claude API usage and estimates costs.

Tracks:
  1. Conversations and messages count over time
  2. Estimated token usage per conversation (from message lengths)
  3. Estimated costs at current model pricing
  4. Budget alerts

Usage:
    python -m backend.graph.cost_monitor
    python -m backend.graph.cost_monitor --daily   # Show daily breakdown
"""

import asyncio
import argparse
import logging
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass, field
from collections import defaultdict

from backend.integrations.supabase_client import get_client
from backend.config import settings

logger = logging.getLogger(__name__)

# Approximate pricing per 1M tokens (as of 2026)
MODEL_PRICING = {
    "claude-sonnet-4-20250514": {"input": 3.0, "output": 15.0},
    "claude-sonnet-4-6": {"input": 3.0, "output": 15.0},
    "claude-haiku-4-5-20251001": {"input": 0.80, "output": 4.0},
    "claude-opus-4-6": {"input": 15.0, "output": 75.0},
}

# Rough chars-to-tokens ratio
CHARS_PER_TOKEN = 4

# Monthly budget alert threshold (USD)
DEFAULT_BUDGET_ALERT = 50.0


@dataclass
class DailyUsage:
    date: str
    conversations: int = 0
    messages: int = 0
    estimated_input_tokens: int = 0
    estimated_output_tokens: int = 0
    estimated_cost_usd: float = 0.0


@dataclass
class CostReport:
    timestamp: str
    model: str
    total_conversations: int = 0
    total_messages: int = 0
    total_assistant_messages: int = 0
    estimated_input_tokens: int = 0
    estimated_output_tokens: int = 0
    estimated_total_cost_usd: float = 0.0
    estimated_monthly_rate_usd: float = 0.0
    budget_alert: bool = False
    daily_breakdown: list[DailyUsage] = field(default_factory=list)

    def summary(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "model": self.model,
            "totals": {
                "conversations": self.total_conversations,
                "messages": self.total_messages,
                "assistant_messages": self.total_assistant_messages,
            },
            "tokens": {
                "estimated_input": self.estimated_input_tokens,
                "estimated_output": self.estimated_output_tokens,
            },
            "cost": {
                "estimated_total_usd": round(self.estimated_total_cost_usd, 4),
                "estimated_monthly_rate_usd": round(self.estimated_monthly_rate_usd, 2),
                "budget_alert": self.budget_alert,
            },
        }


def estimate_tokens(text: str) -> int:
    """Rough token estimate from character count."""
    return max(1, len(text) // CHARS_PER_TOKEN)


def estimate_cost(input_tokens: int, output_tokens: int, model: str) -> float:
    """Estimate USD cost for given token usage."""
    pricing = MODEL_PRICING.get(model, MODEL_PRICING.get("claude-sonnet-4-20250514", {"input": 3.0, "output": 15.0}))
    input_cost = (input_tokens / 1_000_000) * pricing["input"]
    output_cost = (output_tokens / 1_000_000) * pricing["output"]
    return input_cost + output_cost


async def run_cost_check(days: int = 30, show_daily: bool = False) -> CostReport:
    """Check API cost estimates for the last N days."""
    client = get_client()
    model = settings.navigator_model
    report = CostReport(
        timestamp=datetime.now(timezone.utc).isoformat(),
        model=model,
    )

    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    # Get conversations
    convs = client.table("conversations").select("id, created_at").gte("created_at", cutoff).execute()
    report.total_conversations = len(convs.data)

    # Get all messages in the period
    messages = (
        client.table("messages")
        .select("id, role, content, created_at")
        .gte("created_at", cutoff)
        .order("created_at", desc=False)
        .execute()
    )
    report.total_messages = len(messages.data)

    # Calculate token estimates
    daily: dict[str, DailyUsage] = defaultdict(lambda: DailyUsage(date=""))
    for msg in messages.data:
        tokens = estimate_tokens(msg.get("content", ""))
        date_str = msg["created_at"][:10]

        if date_str not in daily:
            daily[date_str] = DailyUsage(date=date_str)

        daily[date_str].messages += 1

        if msg["role"] == "user":
            # User messages are input tokens (plus system prompt ~1000 tokens overhead)
            report.estimated_input_tokens += tokens + 1000
            daily[date_str].estimated_input_tokens += tokens + 1000
        else:
            report.total_assistant_messages += 1
            report.estimated_output_tokens += tokens
            daily[date_str].estimated_output_tokens += tokens

    # Calculate costs
    report.estimated_total_cost_usd = estimate_cost(
        report.estimated_input_tokens, report.estimated_output_tokens, model
    )

    # Estimate monthly rate
    if days > 0 and report.total_messages > 0:
        daily_rate = report.estimated_total_cost_usd / max(1, len(daily))
        report.estimated_monthly_rate_usd = daily_rate * 30

    report.budget_alert = report.estimated_monthly_rate_usd > DEFAULT_BUDGET_ALERT

    # Daily breakdown
    for date_str in sorted(daily.keys()):
        d = daily[date_str]
        d.estimated_cost_usd = estimate_cost(
            d.estimated_input_tokens, d.estimated_output_tokens, model
        )
        report.daily_breakdown.append(d)

    # Count conversations per day
    for conv in convs.data:
        date_str = conv["created_at"][:10]
        if date_str in daily:
            daily[date_str].conversations += 1

    return report


def print_report(report: CostReport, show_daily: bool = False):
    """Pretty-print the cost report."""
    print("=" * 60)
    print("KORCZAK COST MONITOR")
    print("=" * 60)
    print(f"Timestamp: {report.timestamp}")
    print(f"Model: {report.model}")
    print()

    print("Usage:")
    print(f"  Conversations:      {report.total_conversations}")
    print(f"  Total messages:     {report.total_messages}")
    print(f"  Assistant messages: {report.total_assistant_messages}")
    print()

    print("Estimated Tokens:")
    print(f"  Input:  {report.estimated_input_tokens:>10,}")
    print(f"  Output: {report.estimated_output_tokens:>10,}")
    print()

    print("Estimated Cost:")
    print(f"  Total:        ${report.estimated_total_cost_usd:.4f}")
    print(f"  Monthly rate: ${report.estimated_monthly_rate_usd:.2f}/mo")
    if report.budget_alert:
        print(f"  *** BUDGET ALERT: Estimated monthly rate exceeds ${DEFAULT_BUDGET_ALERT:.0f} ***")
    print()

    if show_daily and report.daily_breakdown:
        print("Daily Breakdown:")
        print(f"  {'Date':12s} {'Msgs':>6s} {'Input':>10s} {'Output':>10s} {'Cost':>8s}")
        for d in report.daily_breakdown:
            print(f"  {d.date:12s} {d.messages:>6d} {d.estimated_input_tokens:>10,} {d.estimated_output_tokens:>10,} ${d.estimated_cost_usd:>7.4f}")
        print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Korczak Cost Monitor")
    parser.add_argument("--days", type=int, default=30, help="Look back N days")
    parser.add_argument("--daily", action="store_true", help="Show daily breakdown")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    async def main():
        report = await run_cost_check(days=args.days, show_daily=args.daily)
        if args.json:
            import json
            print(json.dumps(report.summary(), indent=2))
        else:
            print_report(report, show_daily=args.daily)

    asyncio.run(main())
