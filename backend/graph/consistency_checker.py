"""Graph Consistency Checker — detects structural issues in the knowledge graph.

Checks:
  1. Orphan concepts (no relationships, no paper links)
  2. Duplicate concepts (same normalized_name)
  3. Circular contradictions (A CONTRADICTS B, B CONTRADICTS C, C BUILDS_ON A)
  4. Dangling relationships (source/target concept doesn't exist)
  5. Stale concepts (no updates in 90+ days)
  6. Missing definitions (concepts with no definition text)
  7. Confidence anomalies (relationships with 0 confidence or > 1.0)

Usage:
    python -m backend.graph.consistency_checker
    python -m backend.graph.consistency_checker --fix  # Auto-fix safe issues
"""

import asyncio
import argparse
import logging
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass, field

from backend.integrations.supabase_client import get_client

logger = logging.getLogger(__name__)


@dataclass
class Issue:
    severity: str  # critical, high, medium, low
    category: str
    description: str
    entity_ids: list[str] = field(default_factory=list)
    auto_fixable: bool = False


@dataclass
class ConsistencyReport:
    timestamp: str
    total_concepts: int = 0
    total_relationships: int = 0
    total_papers: int = 0
    issues: list[Issue] = field(default_factory=list)

    @property
    def critical_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "critical")

    @property
    def high_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "high")

    @property
    def healthy(self) -> bool:
        return self.critical_count == 0

    def summary(self) -> dict:
        by_cat = {}
        for i in self.issues:
            by_cat.setdefault(i.category, []).append(i)
        return {
            "timestamp": self.timestamp,
            "healthy": self.healthy,
            "total_concepts": self.total_concepts,
            "total_relationships": self.total_relationships,
            "total_papers": self.total_papers,
            "issues_by_severity": {
                "critical": self.critical_count,
                "high": self.high_count,
                "medium": sum(1 for i in self.issues if i.severity == "medium"),
                "low": sum(1 for i in self.issues if i.severity == "low"),
            },
            "issues_by_category": {k: len(v) for k, v in by_cat.items()},
            "total_issues": len(self.issues),
        }


async def run_consistency_check() -> ConsistencyReport:
    """Run all consistency checks and return a report."""
    client = get_client()
    report = ConsistencyReport(timestamp=datetime.now(timezone.utc).isoformat())

    # Get counts
    papers = client.table("papers").select("id", count="exact").execute()
    concepts = client.table("concepts").select("id", count="exact").execute()
    rels = client.table("relationships").select("id", count="exact").execute()
    report.total_papers = papers.count or 0
    report.total_concepts = concepts.count or 0
    report.total_relationships = rels.count or 0

    # Run checks in sequence (each uses client)
    await _check_orphan_concepts(client, report)
    await _check_duplicate_concepts(client, report)
    await _check_dangling_relationships(client, report)
    await _check_missing_definitions(client, report)
    await _check_confidence_anomalies(client, report)
    await _check_stale_concepts(client, report)
    await _check_circular_contradictions(client, report)

    return report


async def _check_orphan_concepts(client, report: ConsistencyReport):
    """Find concepts with no relationships AND no paper links."""
    # Get all concept IDs that appear in relationships
    rels = client.table("relationships").select("source_id, target_id").execute()
    linked_ids = set()
    for r in rels.data:
        linked_ids.add(r["source_id"])
        linked_ids.add(r["target_id"])

    # Get all concept IDs that appear in paper_concepts
    pc = client.table("paper_concepts").select("concept_id").execute()
    for p in pc.data:
        linked_ids.add(p["concept_id"])

    # Get all concepts
    all_concepts = client.table("concepts").select("id, name").execute()
    orphans = [c for c in all_concepts.data if c["id"] not in linked_ids]

    if orphans:
        report.issues.append(Issue(
            severity="medium",
            category="orphan_concepts",
            description=f"{len(orphans)} concepts have no relationships and no paper links",
            entity_ids=[c["id"] for c in orphans[:50]],
        ))


async def _check_duplicate_concepts(client, report: ConsistencyReport):
    """Find concepts with the same normalized_name."""
    concepts = client.table("concepts").select("id, name, normalized_name").execute()
    by_name: dict[str, list] = {}
    for c in concepts.data:
        norm = (c.get("normalized_name") or c["name"]).lower().strip()
        by_name.setdefault(norm, []).append(c)

    dupes = {name: items for name, items in by_name.items() if len(items) > 1}
    if dupes:
        ids = []
        for items in dupes.values():
            ids.extend(c["id"] for c in items)
        report.issues.append(Issue(
            severity="high",
            category="duplicate_concepts",
            description=f"{len(dupes)} concept names have duplicates ({sum(len(v) for v in dupes.values())} total entries)",
            entity_ids=ids[:50],
            auto_fixable=True,
        ))


async def _check_dangling_relationships(client, report: ConsistencyReport):
    """Find relationships pointing to non-existent concepts."""
    all_concepts = client.table("concepts").select("id").execute()
    concept_ids = {c["id"] for c in all_concepts.data}

    rels = client.table("relationships").select("id, source_id, target_id").execute()
    dangling = []
    for r in rels.data:
        if r["source_id"] not in concept_ids or r["target_id"] not in concept_ids:
            dangling.append(r["id"])

    if dangling:
        report.issues.append(Issue(
            severity="critical",
            category="dangling_relationships",
            description=f"{len(dangling)} relationships point to non-existent concepts",
            entity_ids=dangling[:50],
            auto_fixable=True,
        ))


async def _check_missing_definitions(client, report: ConsistencyReport):
    """Find concepts without definitions."""
    concepts = client.table("concepts").select("id, name, definition").execute()
    missing = [c for c in concepts.data if not c.get("definition")]

    if missing:
        pct = len(missing) / len(concepts.data) * 100 if concepts.data else 0
        report.issues.append(Issue(
            severity="low" if pct < 20 else "medium",
            category="missing_definitions",
            description=f"{len(missing)} concepts ({pct:.0f}%) have no definition",
            entity_ids=[c["id"] for c in missing[:50]],
        ))


async def _check_confidence_anomalies(client, report: ConsistencyReport):
    """Find relationships with invalid confidence scores."""
    rels = client.table("relationships").select("id, confidence").execute()
    anomalies = [r for r in rels.data if r.get("confidence", 0) <= 0 or r.get("confidence", 0) > 1.0]

    if anomalies:
        report.issues.append(Issue(
            severity="high",
            category="confidence_anomalies",
            description=f"{len(anomalies)} relationships have invalid confidence (<=0 or >1.0)",
            entity_ids=[r["id"] for r in anomalies[:50]],
            auto_fixable=True,
        ))


async def _check_stale_concepts(client, report: ConsistencyReport):
    """Find concepts not updated in 90+ days."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
    concepts = client.table("concepts").select("id, name, updated_at").lt("updated_at", cutoff).execute()

    if concepts.data:
        pct = len(concepts.data) / report.total_concepts * 100 if report.total_concepts else 0
        report.issues.append(Issue(
            severity="low",
            category="stale_concepts",
            description=f"{len(concepts.data)} concepts ({pct:.0f}%) not updated in 90+ days",
            entity_ids=[c["id"] for c in concepts.data[:50]],
        ))


async def _check_circular_contradictions(client, report: ConsistencyReport):
    """Detect cycles involving CONTRADICTS relationships.

    A circular contradiction is: A CONTRADICTS B, B relates to C, C BUILDS_ON A.
    This is logically inconsistent — if A contradicts B, things built on both
    A and B shouldn't form a supportive chain.
    """
    contradicts = (
        client.table("relationships")
        .select("source_id, target_id")
        .eq("relationship_type", "CONTRADICTS")
        .execute()
    )
    if not contradicts.data:
        return

    # Build a set of contradicting pairs
    contra_pairs = set()
    for r in contradicts.data:
        contra_pairs.add((r["source_id"], r["target_id"]))
        contra_pairs.add((r["target_id"], r["source_id"]))

    # Get BUILDS_ON relationships
    builds = (
        client.table("relationships")
        .select("source_id, target_id")
        .eq("relationship_type", "BUILDS_ON")
        .execute()
    )

    # Check: if A CONTRADICTS B, and C BUILDS_ON A, and C BUILDS_ON B → inconsistency
    builds_map: dict[str, set[str]] = {}  # concept -> set of concepts it builds on
    for r in builds.data:
        builds_map.setdefault(r["source_id"], set()).add(r["target_id"])

    circular = []
    for concept_id, foundations in builds_map.items():
        foundations_list = list(foundations)
        for i in range(len(foundations_list)):
            for j in range(i + 1, len(foundations_list)):
                a, b = foundations_list[i], foundations_list[j]
                if (a, b) in contra_pairs:
                    circular.append(concept_id)

    if circular:
        report.issues.append(Issue(
            severity="critical",
            category="circular_contradictions",
            description=f"{len(circular)} concepts build on mutually contradicting foundations",
            entity_ids=circular[:50],
        ))


async def fix_safe_issues(report: ConsistencyReport):
    """Auto-fix issues marked as auto_fixable."""
    client = get_client()
    fixed = 0

    for issue in report.issues:
        if not issue.auto_fixable:
            continue

        if issue.category == "dangling_relationships":
            for rid in issue.entity_ids:
                client.table("relationships").delete().eq("id", rid).execute()
                fixed += 1
            print(f"  Deleted {len(issue.entity_ids)} dangling relationships")

        if issue.category == "confidence_anomalies":
            for rid in issue.entity_ids:
                client.table("relationships").update({"confidence": 0.5}).eq("id", rid).execute()
                fixed += 1
            print(f"  Reset {len(issue.entity_ids)} confidence scores to 0.5")

    return fixed


def print_report(report: ConsistencyReport):
    """Pretty-print the consistency report."""
    summary = report.summary()
    print("=" * 60)
    print("KORCZAK GRAPH CONSISTENCY CHECK")
    print("=" * 60)
    print(f"Timestamp: {report.timestamp}")
    print(f"Graph: {report.total_papers} papers, {report.total_concepts} concepts, {report.total_relationships} relationships")
    print(f"Status: {'HEALTHY' if report.healthy else 'ISSUES FOUND'}")
    print()

    sev = summary["issues_by_severity"]
    print(f"Issues: {summary['total_issues']} total")
    print(f"  Critical: {sev['critical']}")
    print(f"  High:     {sev['high']}")
    print(f"  Medium:   {sev['medium']}")
    print(f"  Low:      {sev['low']}")
    print()

    for issue in report.issues:
        icon = {"critical": "!!!", "high": " !!", "medium": "  !", "low": "  ·"}[issue.severity]
        fix = " [auto-fixable]" if issue.auto_fixable else ""
        print(f"  {icon} [{issue.category}] {issue.description}{fix}")

    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Korczak Graph Consistency Checker")
    parser.add_argument("--fix", action="store_true", help="Auto-fix safe issues")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    async def main():
        report = await run_consistency_check()
        if args.json:
            import json
            print(json.dumps(report.summary(), indent=2))
        else:
            print_report(report)
        if args.fix:
            fixed = await fix_safe_issues(report)
            print(f"Fixed {fixed} issues.")

    asyncio.run(main())
