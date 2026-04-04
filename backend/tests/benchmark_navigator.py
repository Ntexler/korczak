"""Korczak Navigator Benchmark — 20 questions across 6 categories.

Usage:
    python -m backend.tests.benchmark_navigator
    python -m backend.tests.benchmark_navigator --judge  # Auto-score with Claude
"""

import asyncio
import argparse
import json
import sys
import time

import httpx

API_BASE = "http://localhost:8001/api"

# 20 benchmark questions across 6 categories
BENCHMARK = [
    # Category 1: Positioning (where does concept X sit in the field?)
    {
        "id": 1,
        "category": "positioning",
        "question": "Where does participant observation fit in the history of anthropological methods?",
        "criteria": "Should mention Malinowski, distinguish from earlier armchair anthropology, note evolution to multi-sited ethnography",
    },
    {
        "id": 2,
        "category": "positioning",
        "question": "How central is kinship to modern anthropology?",
        "criteria": "Should note decline from central position, Schneider's critique, revival through new kinship studies",
    },
    {
        "id": 3,
        "category": "positioning",
        "question": "What role does reflexivity play in contemporary ethnography?",
        "criteria": "Should reference Writing Culture, Clifford/Marcus, postmodern turn, ongoing debates about navel-gazing",
    },
    # Category 2: Controversy (what are the active debates?)
    {
        "id": 4,
        "category": "controversy",
        "question": "What are the debates around decolonizing anthropology?",
        "criteria": "Should mention structural critiques, indigenous methodologies, institutional responses, specific scholars/movements",
    },
    {
        "id": 5,
        "category": "controversy",
        "question": "Is cultural relativism still defensible?",
        "criteria": "Should present both sides: Boas tradition vs. human rights universalism, FGM debates, moral limits",
    },
    {
        "id": 6,
        "category": "controversy",
        "question": "What is the ontological turn and why is it controversial?",
        "criteria": "Should reference Viveiros de Castro, Descola, Holbraad/Pedersen, critique that it romanticizes difference",
    },
    {
        "id": 7,
        "category": "controversy",
        "question": "How has anthropology's relationship with colonialism been critiqued?",
        "criteria": "Should mention Asad's Anthropology and the Colonial Encounter, complicity debates, fieldwork ethics",
    },
    # Category 3: Connection (how does X relate to Y?)
    {
        "id": 8,
        "category": "connection",
        "question": "How does medical anthropology connect to political economy?",
        "criteria": "Should reference structural violence (Farmer), critical medical anthropology, biosociality",
    },
    {
        "id": 9,
        "category": "connection",
        "question": "What's the relationship between linguistics and cognitive anthropology?",
        "criteria": "Should mention Sapir-Whorf, color terms debate, embodied cognition, recent neurolinguistics",
    },
    {
        "id": 10,
        "category": "connection",
        "question": "How do environmental anthropology and indigenous knowledge systems intersect?",
        "criteria": "Should reference TEK, ethnoecology, climate change studies, co-production of knowledge",
    },
    {
        "id": 11,
        "category": "connection",
        "question": "What connects ritual studies to political anthropology?",
        "criteria": "Should reference Turner's liminality/communitas, Geertz's Theatre State, state rituals, performativity",
    },
    # Category 4: Recency (what are the recent trends?)
    {
        "id": 12,
        "category": "recency",
        "question": "What are the emerging trends in digital anthropology?",
        "criteria": "Should mention platform studies, algorithmic ethnography, AI/ML anthropology, remote fieldwork post-COVID",
    },
    {
        "id": 13,
        "category": "recency",
        "question": "How has the anthropology of infrastructure evolved recently?",
        "criteria": "Should reference Star, Larkin, breakdown studies, supply chain anthropology, energy infrastructure",
    },
    {
        "id": 14,
        "category": "recency",
        "question": "What's new in the anthropology of sleep and consciousness?",
        "criteria": "Should reference sleep as cultural practice, polyphasic sleep studies, dreaming ethnographies",
    },
    # Category 5: Funding/Power (who drives the field?)
    {
        "id": 15,
        "category": "funding",
        "question": "How has funding shaped anthropological research priorities?",
        "criteria": "Should mention military funding (HTS), development agencies, applied vs pure research tension",
    },
    {
        "id": 16,
        "category": "funding",
        "question": "Which institutions have most influenced anthropological theory?",
        "criteria": "Should reference Chicago, Manchester, LSE, French tradition, shifting global centers",
    },
    {
        "id": 17,
        "category": "funding",
        "question": "How has open access changed knowledge production in anthropology?",
        "criteria": "Should mention HAU journal controversy, decolonizing publishing, accessibility vs prestige",
    },
    # Category 6: Blind Spots (what's missing?)
    {
        "id": 18,
        "category": "blind_spots",
        "question": "What topics are underrepresented in anthropological research?",
        "criteria": "Should identify actual gaps: anthropology of the wealthy, domestic fieldwork, non-Western theory",
    },
    {
        "id": 19,
        "category": "blind_spots",
        "question": "What methodological gaps exist in ethnographic research?",
        "criteria": "Should mention quantitative integration, replicability, longitudinal studies, team ethnography",
    },
    {
        "id": 20,
        "category": "blind_spots",
        "question": "Where is anthropology failing to engage with other disciplines?",
        "criteria": "Should mention neuroscience, data science, economics, genetics — missed interdisciplinary opportunities",
    },
]

JUDGE_SYSTEM = """You are evaluating a knowledge navigator's response to an academic question.

Score the response on a 1-5 scale:
1 = Wrong or irrelevant
2 = Partially correct but missing key points
3 = Adequate — hits main points but lacks depth
4 = Good — accurate, specific, cites relevant work
5 = Excellent — comprehensive, insightful, includes an unexpected connection or nuance

Criteria for this question: {criteria}

Respond with JSON only: {{"score": N, "reason": "one sentence explanation"}}"""


async def run_benchmark(use_judge: bool = False):
    """Run the 20-question benchmark."""
    results = []
    conversation_id = None
    total_time = 0

    print("=" * 60)
    print("KORCZAK NAVIGATOR BENCHMARK")
    print("=" * 60)

    async with httpx.AsyncClient(timeout=90) as client:
        for q in BENCHMARK:
            print(f"\n[{q['id']:2d}/20] ({q['category']}) {q['question'][:60]}...")
            start = time.time()

            try:
                resp = await client.post(
                    f"{API_BASE}/chat/",
                    json={
                        "message": q["question"],
                        "conversation_id": conversation_id,
                        "mode": "navigator",
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                elapsed = time.time() - start
                total_time += elapsed

                conversation_id = data.get("conversation_id")
                response_text = data.get("response", "")
                concepts = data.get("concepts_referenced", [])
                has_insight = data.get("insight") is not None

                result = {
                    "id": q["id"],
                    "category": q["category"],
                    "question": q["question"],
                    "response_length": len(response_text),
                    "concepts_count": len(concepts),
                    "has_insight": has_insight,
                    "time_s": round(elapsed, 1),
                }

                # Judge scoring
                if use_judge:
                    score_data = await judge_response(
                        client, q["question"], response_text, q["criteria"]
                    )
                    result["score"] = score_data.get("score", 0)
                    result["judge_reason"] = score_data.get("reason", "")
                    status = f"Score: {result['score']}/5"
                else:
                    result["score"] = None
                    status = f"{len(response_text)} chars"

                print(f"       {status} | {len(concepts)} concepts | insight: {has_insight} | {elapsed:.1f}s")
                results.append(result)

            except Exception as e:
                print(f"       ERROR: {e}")
                results.append({
                    "id": q["id"],
                    "category": q["category"],
                    "question": q["question"],
                    "error": str(e),
                    "score": 0,
                })

    # Summary
    print("\n" + "=" * 60)
    print("RESULTS SUMMARY")
    print("=" * 60)

    scored = [r for r in results if r.get("score") is not None and r["score"] is not None]
    errored = [r for r in results if "error" in r]

    if scored:
        avg_score = sum(r["score"] for r in scored) / len(scored)
        wins = sum(1 for r in scored if r["score"] >= 3)
        print(f"Average score: {avg_score:.1f}/5")
        print(f"Wins (>=3): {wins}/20")
        print(f"Pass criteria (15/20): {'PASS' if wins >= 15 else 'FAIL'}")

        # Per-category breakdown
        categories = {}
        for r in scored:
            cat = r["category"]
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(r["score"])

        print("\nPer category:")
        for cat, scores in sorted(categories.items()):
            avg = sum(scores) / len(scores)
            print(f"  {cat:15s}: {avg:.1f}/5 ({len(scores)} questions)")

    if errored:
        print(f"\nErrors: {len(errored)} questions failed")

    print(f"\nTotal time: {total_time:.0f}s ({total_time/20:.1f}s avg per question)")

    # Save results
    with open("benchmark_results.json", "w") as f:
        json.dump(results, f, indent=2)
    print("\nResults saved to benchmark_results.json")

    return results


async def judge_response(
    client: httpx.AsyncClient, question: str, response: str, criteria: str
) -> dict:
    """Use Claude as a judge to score the response."""
    try:
        resp = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": _get_api_key(),
                "content-type": "application/json",
                "anthropic-version": "2023-06-01",
            },
            json={
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 200,
                "temperature": 0,
                "system": JUDGE_SYSTEM.format(criteria=criteria),
                "messages": [
                    {
                        "role": "user",
                        "content": f"Question: {question}\n\nResponse:\n{response}",
                    }
                ],
            },
        )
        resp.raise_for_status()
        text = resp.json()["content"][0]["text"]
        # Parse JSON from response
        if "```" in text:
            text = text.split("```")[1].split("```")[0]
            if text.startswith("json"):
                text = text[4:]
        return json.loads(text.strip())
    except Exception:
        return {"score": 0, "reason": "Judge failed"}


def _get_api_key() -> str:
    """Get API key from .env."""
    import os
    from pathlib import Path

    env_path = Path(__file__).parent.parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.startswith("ANTHROPIC_API_KEY="):
                return line.split("=", 1)[1].strip()
    return os.environ.get("ANTHROPIC_API_KEY", "")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Korczak Navigator Benchmark")
    parser.add_argument("--judge", action="store_true", help="Use Claude as judge for auto-scoring")
    args = parser.parse_args()

    asyncio.run(run_benchmark(use_judge=args.judge))
