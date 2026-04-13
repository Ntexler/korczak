"""Entity Resolution — embedding-based concept deduplication.

Finds and merges duplicate concepts that have different names but mean the same thing.
E.g., "participant observation" vs "Participant-Observation" vs "participatory observation"

Usage:
  python -m backend.pipeline.entity_resolution --dry-run
  python -m backend.pipeline.entity_resolution --merge
"""

import argparse
import asyncio
import logging
import sys
from collections import defaultdict

import httpx

from backend.config import settings
from backend.integrations.supabase_client import get_client
from backend.search.embeddings import get_embedding

logger = logging.getLogger(__name__)

# Similarity thresholds
AUTO_MERGE_THRESHOLD = 0.95   # Above this: auto-merge, clearly the same concept
REVIEW_THRESHOLD = 0.85       # Between 0.85-0.95: flag for review
BATCH_SIZE = 50


async def populate_embeddings():
    """Generate embeddings for all concepts that don't have one yet."""
    client = get_client()

    # Find concepts without embeddings
    result = client.table("concepts").select(
        "id, name, definition, type"
    ).is_("embedding", "null").order("paper_count", desc=True).limit(500).execute()

    if not result.data:
        logger.info("All concepts already have embeddings")
        return 0

    total = len(result.data)
    logger.info(f"Generating embeddings for {total} concepts...")
    populated = 0

    for i, concept in enumerate(result.data):
        try:
            # Build text for embedding: name + definition + type
            text = concept["name"]
            if concept.get("definition"):
                text += f": {concept['definition'][:200]}"
            if concept.get("type"):
                text += f" ({concept['type']})"

            embedding = await get_embedding(text)

            # Update in DB
            client.table("concepts").update(
                {"embedding": embedding}
            ).eq("id", concept["id"]).execute()
            populated += 1

            if (i + 1) % 20 == 0:
                logger.info(f"  {i+1}/{total} embeddings generated")

            await asyncio.sleep(0.1)  # Rate limit

        except Exception as e:
            logger.warning(f"  Failed for '{concept['name']}': {e}")
            await asyncio.sleep(1)  # Back off on error

    logger.info(f"Populated {populated}/{total} embeddings")
    return populated


async def find_duplicates(threshold: float = REVIEW_THRESHOLD) -> list[dict]:
    """Find potential duplicate concepts using embedding similarity."""
    client = get_client()

    # Get all concepts with embeddings
    result = client.table("concepts").select(
        "id, name, normalized_name, type, definition, paper_count, embedding"
    ).not_.is_("embedding", "null").order("paper_count", desc=True).execute()

    concepts = result.data
    if not concepts:
        logger.info("No concepts with embeddings found")
        return []

    logger.info(f"Checking {len(concepts)} concepts for duplicates...")
    duplicates = []
    checked = set()

    for i, concept_a in enumerate(concepts):
        if concept_a["id"] in checked:
            continue

        # Search for similar concepts using the RPC
        try:
            similar = client.rpc(
                "search_concepts_by_embedding",
                {
                    "query_embedding": concept_a["embedding"],
                    "match_threshold": threshold,
                    "match_count": 10,
                },
            ).execute()

            for match in similar.data:
                if match["id"] == concept_a["id"]:
                    continue
                if match["id"] in checked:
                    continue

                similarity = match.get("similarity", 0)
                if similarity >= threshold:
                    duplicates.append({
                        "concept_a": {
                            "id": concept_a["id"],
                            "name": concept_a["name"],
                            "type": concept_a["type"],
                            "paper_count": concept_a["paper_count"],
                        },
                        "concept_b": {
                            "id": match["id"],
                            "name": match["name"],
                            "type": match["type"],
                            "paper_count": match.get("paper_count", 0),
                        },
                        "similarity": similarity,
                        "auto_merge": similarity >= AUTO_MERGE_THRESHOLD,
                    })

        except Exception as e:
            logger.warning(f"  Search failed for '{concept_a['name']}': {e}")

        if (i + 1) % 50 == 0:
            logger.info(f"  Checked {i+1}/{len(concepts)}, found {len(duplicates)} pairs")

    logger.info(f"Found {len(duplicates)} duplicate pairs")
    return duplicates


async def merge_concepts(concept_keep_id: str, concept_remove_id: str):
    """Merge two concepts — keep one, reassign all references from the other.

    The concept with more paper links is kept. All relationships, paper_concepts,
    claims, and user_knowledge entries are reassigned.
    """
    client = get_client()

    # 1. Reassign paper_concepts
    client.table("paper_concepts").update(
        {"concept_id": concept_keep_id}
    ).eq("concept_id", concept_remove_id).execute()

    # 2. Reassign relationships (source)
    client.table("relationships").update(
        {"source_id": concept_keep_id}
    ).eq("source_id", concept_remove_id).eq("source_type", "concept").execute()

    # 3. Reassign relationships (target)
    client.table("relationships").update(
        {"target_id": concept_keep_id}
    ).eq("target_id", concept_remove_id).eq("target_type", "concept").execute()

    # 4. Reassign user_knowledge
    client.table("user_knowledge").update(
        {"concept_id": concept_keep_id}
    ).eq("concept_id", concept_remove_id).execute()

    # 5. Reassign knowledge_tree_nodes
    try:
        client.table("knowledge_tree_nodes").update(
            {"concept_id": concept_keep_id}
        ).eq("concept_id", concept_remove_id).execute()
    except Exception:
        pass  # Table might not exist

    # 6. Update paper_count on kept concept
    paper_count = client.table("paper_concepts").select(
        "id", count="exact"
    ).eq("concept_id", concept_keep_id).execute()
    client.table("concepts").update(
        {"paper_count": paper_count.count or 0}
    ).eq("id", concept_keep_id).execute()

    # 7. Delete the duplicate concept
    client.table("concepts").delete().eq("id", concept_remove_id).execute()


async def run_entity_resolution(dry_run: bool = True, auto_only: bool = True):
    """Full entity resolution pipeline."""
    # Step 1: Populate missing embeddings
    logger.info("=== Step 1: Populate Embeddings ===")
    populated = await populate_embeddings()

    # Step 2: Find duplicates
    logger.info("\n=== Step 2: Find Duplicates ===")
    duplicates = await find_duplicates()

    if not duplicates:
        logger.info("No duplicates found!")
        return

    # Step 3: Report
    auto_merges = [d for d in duplicates if d["auto_merge"]]
    review_needed = [d for d in duplicates if not d["auto_merge"]]

    print(f"\n{'='*60}")
    print(f"ENTITY RESOLUTION REPORT")
    print(f"{'='*60}")
    print(f"Total duplicate pairs: {len(duplicates)}")
    print(f"Auto-merge (>{AUTO_MERGE_THRESHOLD}): {len(auto_merges)}")
    print(f"Review needed ({REVIEW_THRESHOLD}-{AUTO_MERGE_THRESHOLD}): {len(review_needed)}")

    print(f"\n--- Auto-merge candidates ---")
    for d in auto_merges[:20]:
        a = d["concept_a"]
        b = d["concept_b"]
        print(f"  [{d['similarity']:.3f}] \"{a['name']}\" ({a['paper_count']} papers) "
              f"↔ \"{b['name']}\" ({b['paper_count']} papers)")

    if review_needed:
        print(f"\n--- Review needed ---")
        for d in review_needed[:20]:
            a = d["concept_a"]
            b = d["concept_b"]
            print(f"  [{d['similarity']:.3f}] \"{a['name']}\" ↔ \"{b['name']}\"")

    # Step 4: Merge (if not dry run)
    if not dry_run:
        to_merge = auto_merges if auto_only else duplicates
        logger.info(f"\n=== Step 3: Merging {len(to_merge)} pairs ===")
        merged = 0
        for d in to_merge:
            a = d["concept_a"]
            b = d["concept_b"]
            # Keep the one with more papers
            if a["paper_count"] >= b.get("paper_count", 0):
                keep, remove = a, b
            else:
                keep, remove = b, a

            try:
                await merge_concepts(keep["id"], remove["id"])
                merged += 1
                logger.info(f"  Merged: \"{remove['name']}\" → \"{keep['name']}\"")
            except Exception as e:
                logger.warning(f"  Merge failed: {e}")

        print(f"\nMerged {merged} pairs")
    else:
        print(f"\n(Dry run — use --merge to actually merge)")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Entity resolution for concepts")
    parser.add_argument("--dry-run", action="store_true", default=True,
                        help="Only report, don't merge (default)")
    parser.add_argument("--merge", action="store_true",
                        help="Actually merge auto-merge candidates")
    parser.add_argument("--merge-all", action="store_true",
                        help="Merge all candidates including review-needed")
    parser.add_argument("--embeddings-only", action="store_true",
                        help="Only populate embeddings, skip dedup")
    args = parser.parse_args()

    if args.embeddings_only:
        asyncio.run(populate_embeddings())
    elif args.merge or args.merge_all:
        asyncio.run(run_entity_resolution(dry_run=False, auto_only=not args.merge_all))
    else:
        asyncio.run(run_entity_resolution(dry_run=True))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
