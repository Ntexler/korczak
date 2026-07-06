"""Analyze the retrieval attribution log — the decision table.

Reads the JSONL produced by run_attribution.py and prints:
- Per-retriever: contribution rate, sole-source rate, unique-value rate,
  avg latency, avg tokens
- Per query-type breakdown
- Semantic-only cost/latency simulation
- Verdict against the pre-committed decision criteria

Usage:
  python -m backend.experiments.analyze_attribution
  python -m backend.experiments.analyze_attribution --log data/attribution/run2.jsonl
"""

import argparse
import json
import sys
from collections import defaultdict

CORE = ["semantic", "kg", "openalex", "usergraph"]
LOG_DEFAULT = "data/attribution/attribution_log.jsonl"


def used(chunk: dict) -> bool:
    """A chunk counts as used: self-reported OR judge score == 2."""
    return bool(chunk.get("self_report_used")) or chunk.get("judge_score") == 2


def load(path: str) -> list[dict]:
    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return records


def analyze(records: list[dict]) -> None:
    n = len(records)
    if n == 0:
        print("No records in log.")
        return

    # Per-retriever accumulators
    contributed = defaultdict(int)      # queries with >=1 used chunk from retriever
    sole_source = defaultdict(int)      # queries where ALL used chunks are from retriever
    unique_value = defaultdict(int)     # only retriever with any judge-score-2 chunk, and contributed
    latency_sum = defaultdict(float)
    tokens_sum = defaultdict(int)
    latency_n = defaultdict(int)

    # Per query-type
    by_type_total = defaultdict(int)
    by_type_contrib = defaultdict(lambda: defaultdict(int))
    by_type_sole = defaultdict(lambda: defaultdict(int))

    # Simulation accumulators
    total_latency_parallel = 0.0   # actual: max over retrievers (they run in parallel)
    total_tokens_all = 0
    semantic_latency = 0.0
    semantic_tokens = 0

    for rec in records:
        qtype = rec.get("query_type", "unknown")
        by_type_total[qtype] += 1

        stats = rec.get("retrievers", {})
        for name, s in stats.items():
            latency_sum[name] += s.get("latency_ms", 0)
            tokens_sum[name] += s.get("tokens", 0)
            latency_n[name] += 1

        total_latency_parallel += max((s.get("latency_ms", 0) for s in stats.values()), default=0)
        total_tokens_all += sum(s.get("tokens", 0) for s in stats.values())
        semantic_latency += stats.get("semantic", {}).get("latency_ms", 0)
        semantic_tokens += stats.get("semantic", {}).get("tokens", 0)

        chunks = rec.get("chunks", [])
        used_chunks = [c for c in chunks if used(c)]
        used_retrievers = {c["retriever"] for c in used_chunks}
        score2_retrievers = {c["retriever"] for c in chunks if c.get("judge_score") == 2}

        for r in used_retrievers:
            contributed[r] += 1
            by_type_contrib[qtype][r] += 1

        if len(used_retrievers) == 1:
            only = next(iter(used_retrievers))
            sole_source[only] += 1
            by_type_sole[qtype][only] += 1

        if len(score2_retrievers) == 1:
            only = next(iter(score2_retrievers))
            if only in used_retrievers:
                unique_value[only] += 1

    # ── Main table ──
    def pct(x: int) -> str:
        return f"{x / n * 100:5.1f}%"

    print(f"\n{'='*86}")
    print(f"RETRIEVAL ATTRIBUTION — {n} queries")
    print(f"{'='*86}")
    header = f"{'Retriever':<11} {'Contribution':>13} {'Sole-source':>12} {'Unique-value':>13} {'Avg latency':>12} {'Avg tokens':>11}"
    print(header)
    print("-" * len(header))
    for name in CORE + sorted(set(latency_sum) - set(CORE)):
        avg_lat = latency_sum[name] / max(latency_n[name], 1)
        avg_tok = tokens_sum[name] / max(latency_n[name], 1)
        print(f"{name:<11} {pct(contributed[name]):>13} {pct(sole_source[name]):>12} "
              f"{pct(unique_value[name]):>13} {avg_lat:>10.0f}ms {avg_tok:>11.0f}")

    # ── Per query type ──
    print(f"\n{'—'*86}\nPER QUERY TYPE (contribution / sole-source)")
    for qtype in sorted(by_type_total):
        tn = by_type_total[qtype]
        parts = []
        for name in CORE:
            c = by_type_contrib[qtype][name]
            s = by_type_sole[qtype][name]
            parts.append(f"{name} {c}/{tn} ({s} sole)")
        print(f"  {qtype:<12} n={tn:<3} " + " | ".join(parts))

    # ── Semantic-only simulation ──
    print(f"\n{'—'*86}\nSEMANTIC-ONLY SIMULATION")
    print(f"  Actual pipeline retrieval:  {total_latency_parallel:8.0f}ms total (parallel max/query), {total_tokens_all:>8} retrieval tokens")
    print(f"  Semantic-only would be:     {semantic_latency:8.0f}ms total, {semantic_tokens:>8} retrieval tokens")
    if total_tokens_all:
        print(f"  Token savings:  {(1 - semantic_tokens / total_tokens_all) * 100:.0f}%")
    if total_latency_parallel:
        print(f"  Latency change: {(semantic_latency / total_latency_parallel - 1) * 100:+.0f}%")

    # ── Decision criteria (pre-committed) ──
    print(f"\n{'='*86}\nDECISION CRITERIA")
    sem_sole = sole_source["semantic"] / n * 100
    factual_n = by_type_total.get("factual", 0)
    sem_sole_factual = (by_type_sole["factual"]["semantic"] / factual_n * 100) if factual_n else 0
    graph_unique = (unique_value["kg"] + unique_value["openalex"]) / n * 100
    usergraph_contrib = contributed["usergraph"] / n * 100

    print(f"  semantic sole-source overall: {sem_sole:.0f}%  (build tiering if >= 50%)")
    print(f"  semantic sole-source factual: {sem_sole_factual:.0f}%  (build tiering if >= 70%)")
    print(f"  kg+openalex unique-value:     {graph_unique:.0f}%  (keep parallel if >= 30%)")
    print(f"  usergraph contribution:       {usergraph_contrib:.0f}%  (investigate if < 15%)")

    verdicts = []
    if sem_sole >= 50 or sem_sole_factual >= 70:
        verdicts.append("→ BUILD TIERING (routing by query type first)")
    if graph_unique >= 30:
        verdicts.append("→ KEEP PARALLEL PIPELINE (graph earns its cost)")
    if usergraph_contrib < 15:
        verdicts.append("→ INVESTIGATE USERGRAPH (not feeding synthesis usefully)")
    if not verdicts:
        verdicts.append("→ AMBIGUOUS: run 20 more queries before deciding. Build nothing.")
    for v in verdicts:
        print(f"  {v}")

    # ── Per-query breakdown ──
    print(f"\n{'—'*86}\nPER-QUERY BREAKDOWN")
    for rec in records:
        chunks = rec.get("chunks", [])
        used_by = defaultdict(int)
        for c in chunks:
            if used(c):
                used_by[c["retriever"]] += 1
        used_str = ", ".join(f"{k}:{v}" for k, v in sorted(used_by.items())) or "none used"
        agree = sum(1 for c in chunks
                    if c.get("judge_score") is not None
                    and bool(c.get("self_report_used")) == (c["judge_score"] == 2))
        scored = sum(1 for c in chunks if c.get("judge_score") is not None)
        agreement = f"{agree}/{scored}" if scored else "n/a"
        print(f"  [{rec.get('query_type', '?'):<10}] {rec.get('query', '')[:52]:<54} used: {used_str:<38} signal-agree: {agreement}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--log", default=LOG_DEFAULT)
    args = parser.parse_args()
    analyze(load(args.log))
