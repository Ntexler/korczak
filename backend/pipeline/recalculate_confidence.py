"""Recalculate concept confidence based on actual evidence in the graph.

Confidence formula:
  base = 0.3 (every concept starts here)
  + paper_count_bonus: 0.1 per paper (capped at 0.3)
  + relationship_bonus: 0.05 per relationship (capped at 0.2)
  + claim_bonus: 0.05 per supporting claim (capped at 0.1)
  + citation_bonus: if linked papers have high citations → +0.1

  Result capped at [0.3, 0.95]

This replaces the blanket 0.5 from seeding with evidence-based scores.
"""

import logging
from collections import Counter

from backend.integrations.supabase_client import get_client

logger = logging.getLogger(__name__)


def recalculate_all(dry_run: bool = False) -> dict:
    """Recalculate confidence for all concepts based on graph evidence."""
    client = get_client()

    # Load all data
    print("Loading graph data...")
    concepts = client.table("concepts").select("id, name, confidence").execute()
    paper_concepts = client.table("paper_concepts").select("paper_id, concept_id").execute()
    relationships = client.table("relationships").select("source_id, target_id").execute()

    # Load papers with citation counts for citation bonus
    papers = client.table("papers").select("id, cited_by_count").execute()
    paper_citations = {p["id"]: p.get("cited_by_count") or 0 for p in papers.data}

    # Build counts
    concept_paper_count = Counter(pc["concept_id"] for pc in paper_concepts.data)

    # Map concept → paper_ids for citation lookup
    concept_papers: dict[str, list[str]] = {}
    for pc in paper_concepts.data:
        concept_papers.setdefault(pc["concept_id"], []).append(pc["paper_id"])

    # Relationship count per concept (either side)
    concept_rel_count: Counter = Counter()
    for r in relationships.data:
        concept_rel_count[r["source_id"]] += 1
        concept_rel_count[r["target_id"]] += 1

    # Calculate new confidence for each concept
    updates = []
    distribution = Counter()

    for c in concepts.data:
        cid = c["id"]

        papers_count = concept_paper_count.get(cid, 0)
        rels_count = concept_rel_count.get(cid, 0)

        # Max citations among linked papers
        linked_papers = concept_papers.get(cid, [])
        max_citations = max((paper_citations.get(pid, 0) for pid in linked_papers), default=0)

        # Calculate confidence
        base = 0.3
        paper_bonus = min(papers_count * 0.1, 0.3)       # 0-0.3
        rel_bonus = min(rels_count * 0.05, 0.2)           # 0-0.2
        citation_bonus = 0.1 if max_citations >= 50 else (0.05 if max_citations >= 10 else 0)

        confidence = min(0.95, base + paper_bonus + rel_bonus + citation_bonus)
        confidence = round(confidence, 2)

        old = c.get("confidence", 0.5)
        if confidence != old:
            updates.append({
                "id": cid,
                "name": c["name"],
                "old": old,
                "new": confidence,
                "papers": papers_count,
                "rels": rels_count,
                "max_cit": max_citations,
            })

        # Track distribution
        if confidence >= 0.85:
            distribution["high (0.85+)"] += 1
        elif confidence >= 0.6:
            distribution["medium (0.6-0.85)"] += 1
        elif confidence >= 0.4:
            distribution["low (0.4-0.6)"] += 1
        else:
            distribution["emerging (<0.4)"] += 1

    print(f"\nNew distribution:")
    for k, v in sorted(distribution.items()):
        print(f"  {k}: {v}")

    print(f"\nChanges: {len(updates)} concepts to update")

    if not dry_run and updates:
        print("Applying updates...")
        batch_size = 50
        for i in range(0, len(updates), batch_size):
            batch = updates[i:i + batch_size]
            for u in batch:
                client.table("concepts").update(
                    {"confidence": u["new"]}
                ).eq("id", u["id"]).execute()
            print(f"  Updated {min(i + batch_size, len(updates))}/{len(updates)}")

        print("Done!")
    elif dry_run:
        print("\nDry run — no changes applied. Run with --apply to update.")
        # Show some examples
        print("\nSample changes:")
        for u in updates[:10]:
            print(f"  {u['name'][:40]:40s} {u['old']:.2f} -> {u['new']:.2f} "
                  f"(papers={u['papers']}, rels={u['rels']}, cit={u['max_cit']})")

    return {
        "total_concepts": len(concepts.data),
        "updated": len(updates),
        "distribution": dict(distribution),
    }


if __name__ == "__main__":
    import sys
    apply = "--apply" in sys.argv
    recalculate_all(dry_run=not apply)
