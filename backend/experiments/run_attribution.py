"""Run the retrieval attribution experiment — 20 labeled real queries.

Mix per protocol: 8 factual, 6 conceptual/connective, 4 follow-ups, 2 citation-chasing.
Each runs once through the existing pipeline with attribution logging on.

Usage:
  python -m backend.experiments.run_attribution
  python -m backend.experiments.run_attribution --log data/attribution/run2.jsonl --start 5
"""

import argparse
import asyncio
import sys

from dotenv import load_dotenv

load_dotenv()

LOG_PATH_DEFAULT = "data/attribution/attribution_log.jsonl"

# (query_type, query, conversation_history | None)
# Follow-ups carry a short real history so the pipeline resolves them like production.
QUERIES: list[tuple[str, str, list[dict] | None]] = [
    # ── Factual lookups (8) ──
    ("factual", "What is thick description in anthropology?", None),
    ("factual", "Who coined the term 'liminality' and in what context?", None),
    ("factual", "What is participant observation and when did it become standard practice?", None),
    ("factual", "What does 'emic vs etic' mean in ethnographic research?", None),
    ("factual", "What is the Sapir-Whorf hypothesis?", None),
    ("factual", "What is structuralism in anthropology?", None),
    ("factual", "What are rites of passage according to van Gennep?", None),
    ("factual", "What is cultural relativism?", None),

    # ── Conceptual / connective (6) ──
    ("conceptual", "How does thick description relate to symbolic interactionism?", None),
    ("conceptual", "How did Turner's concept of liminality build on van Gennep's rites of passage?", None),
    ("conceptual", "What are the main critiques of structuralism from post-structuralist anthropologists?", None),
    ("conceptual", "How does the anthropology of ignorance connect to the sociology of knowledge?", None),
    ("conceptual", "In what ways do interpretive and cognitive anthropology disagree about culture?", None),
    ("conceptual", "How does participant observation affect the objectivity claims of ethnographic research?", None),

    # ── Follow-ups on a prior topic (4) ──
    ("followup", "And how was that criticized later?", [
        {"role": "user", "content": "What is thick description in anthropology?"},
        {"role": "assistant", "content": "Thick description, introduced by Clifford Geertz in 'The Interpretation of Cultures' (1973), is a method of describing human behavior with its full context of meaning, not just the physical act."},
    ]),
    ("followup", "Can you give me a concrete example of that from fieldwork?", [
        {"role": "user", "content": "What does 'emic vs etic' mean in ethnographic research?"},
        {"role": "assistant", "content": "Emic refers to the insider's perspective — how members of a culture understand their own practices — while etic is the analytical outsider's framework imposed by the researcher."},
    ]),
    ("followup", "Which of those two positions has more empirical support today?", [
        {"role": "user", "content": "In what ways do interpretive and cognitive anthropology disagree about culture?"},
        {"role": "assistant", "content": "Interpretive anthropology (Geertz) treats culture as public webs of meaning to be read like a text, while cognitive anthropology locates culture in shared mental models and schemas inside individual minds."},
    ]),
    ("followup", "Does that framework still hold up in digital communities?", [
        {"role": "user", "content": "What are rites of passage according to van Gennep?"},
        {"role": "assistant", "content": "Van Gennep (1909) described rites of passage as three-stage rituals — separation, liminality, and incorporation — that move individuals between social statuses."},
    ]),

    # ── Citation-chasing (2) ──
    ("citation", "Which later papers built directly on Geertz's 'The Interpretation of Cultures'?", None),
    ("citation", "What are the most cited works on ritual and symbolic anthropology, and how do they cite each other?", None),
]


async def main():
    parser = argparse.ArgumentParser(description="Run the 20-query attribution protocol")
    parser.add_argument("--log", default=LOG_PATH_DEFAULT)
    parser.add_argument("--start", type=int, default=0, help="Resume from query index")
    parser.add_argument("--only-type", default=None, choices=["factual", "conceptual", "followup", "citation"])
    args = parser.parse_args()

    from backend.search.pipeline import run_search_pipeline

    queries = QUERIES[args.start:]
    if args.only_type:
        queries = [q for q in queries if q[0] == args.only_type]

    print(f"Running {len(queries)} queries → {args.log}\n")
    ok, failed = 0, 0

    for i, (qtype, query, history) in enumerate(queries):
        print(f"[{i + 1 + args.start}/{len(QUERIES)}] ({qtype}) {query[:70]}...")
        try:
            result = await run_search_pipeline(
                user_message=query,
                conversation_history=history,
                user_id="attribution-experiment",
                mode="navigator",
                locale="en",
                query_type=qtype,
                attribution_log_path=args.log,
            )
            logged = "attribution_logged" in result.stages_completed
            print(f"    → {len(result.response_text)} chars, "
                  f"{result.token_usage.total} tokens, logged={logged}")
            ok += 1
        except Exception as e:
            print(f"    → FAILED: {e}")
            failed += 1
        await asyncio.sleep(1)  # gentle pacing

    print(f"\nDone: {ok} ok, {failed} failed.")
    print(f"Analyze with: python -m backend.experiments.analyze_attribution --log {args.log}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(main())
