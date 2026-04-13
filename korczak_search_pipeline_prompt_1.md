# Claude Code — Build Korczak Search Pipeline

## Context

You are building the search and retrieval engine for **Korczak 2.0** — an AI knowledge navigation platform built around a Knowledge Graph. The MVP domain is **anthropology**. The system is designed to feel like "an agent that knows you" — it combines academic knowledge retrieval with a deep User Graph that tracks how each user thinks and learns.

**Existing stack:**
- Supabase (PostgreSQL + pgvector + pg_trgm)
- FastAPI (Python)
- Next.js 14 (frontend — not in scope here)
- Claude API (Anthropic)
- Hume EVI (voice — not in scope here)

**What you are building today:** The complete search pipeline as a FastAPI module — from raw user query to final structured response. This is the core brain of Korczak.

---

## Architecture to Implement

The pipeline has 6 sequential stages. Build them in this exact order:

```
User Query
    ↓
[1] Query Analyst Agent        — decomposes and expands the query
    ↓
[2] Parallel Retrieval Layer   — 4 async retrievers run simultaneously
    ├── Semantic (pgvector + BM25 hybrid)
    ├── Graph Traversal (knowledge graph edges)
    ├── Citation Trace (OpenAlex API)
    └── User Context (User Graph)
    ↓
[3] Coverage Checker           — detects knowledge gaps, triggers retry (max 2x)
    ↓
[4] Synthesis Agent            — builds coherent response with source attribution
    ↓
[5] Skeptic Agent              — challenges synthesis, checks for missing perspectives
    ↓
[6] Final Response + User Graph Update
```

---

## File Structure to Create

```
korczak/
├── search/
│   ├── __init__.py
│   ├── pipeline.py          # main orchestrator — entry point
│   ├── query_analyst.py     # stage 1
│   ├── retrievers/
│   │   ├── __init__.py
│   │   ├── semantic.py      # pgvector + BM25 hybrid
│   │   ├── graph.py         # knowledge graph traversal
│   │   ├── citations.py     # OpenAlex API
│   │   └── user_context.py  # User Graph retrieval
│   ├── coverage.py          # stage 3 — coverage checker
│   ├── synthesis.py         # stage 4 — synthesis agent
│   ├── skeptic.py           # stage 5 — skeptic counter-agent
│   ├── models.py            # Pydantic models for all stages
│   └── cache.py             # Redis/in-memory query cache
├── api/
│   └── search_router.py     # FastAPI router exposing the pipeline
└── tests/
    └── test_pipeline.py     # integration test with 5 anthropology queries
```

---

## Detailed Implementation Instructions

### Step 1 — models.py (build this first)

Define all Pydantic models. Every stage communicates through typed models, never raw dicts.

```python
# Required models:

class QueryIntent(str, Enum):
    CONCEPTUAL = "conceptual"      # "what is X"
    NAVIGATIONAL = "navigational"  # "continue from where we were"
    COMPARATIVE = "comparative"    # "compare X and Y"
    DEEP_DIVE = "deep_dive"        # "tell me everything about X"

class SubQuery(BaseModel):
    query: str
    retriever: Literal["semantic", "graph", "citations", "user"]
    priority: int  # 1=high, 2=medium, 3=low

class AnalyzedQuery(BaseModel):
    original: str
    intent: QueryIntent
    core_concepts: list[str]
    expansion_terms: list[str]
    user_graph_signals: list[str]
    sub_queries: list[SubQuery]  # max 8
    scope: Literal["narrow", "standard", "broad"]

class Chunk(BaseModel):
    id: str
    text: str
    source_id: str
    source_title: str
    source_type: Literal["paper", "book", "node", "user_note"]
    relevance_score: float
    retriever_origin: str  # which retriever found this

class CoverageResult(BaseModel):
    coverage_score: float  # 0.0-1.0
    covered_aspects: list[str]
    missing_aspects: list[str]
    source_diversity: Literal["low", "medium", "high"]
    temporal_coverage: Literal["outdated", "current", "mixed"]
    needs_retry: bool
    retry_queries: list[str]

class Claim(BaseModel):
    text: str
    source_ids: list[str]
    confidence: float  # 0.0-1.0

class SynthesisResult(BaseModel):
    response: str
    claims: list[Claim]
    contradictions: list[str]
    knowledge_gaps: list[str]

class SkepticVerdict(str, Enum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"

class SkepticIssue(BaseModel):
    type: Literal["missing", "overconfident", "contradicts", "biased", "scope"]
    detail: str

class SkepticResult(BaseModel):
    verdict: SkepticVerdict
    issues: list[SkepticIssue]
    suggested_additions: list[str]
    confidence_adjustments: list[dict]

class KorczakResponse(BaseModel):
    content: str
    confidence: float
    sources: list[dict]
    knowledge_gaps: list[str]
    skeptic_warnings: list[str]
    suggested_next_nodes: list[str]
    mode: Literal["navigator", "socratic", "briefing"]
    retrieval_paths: list[str]
    tokens_used: int
    latency_ms: float
```

---

### Step 2 — query_analyst.py

Use `claude-haiku-4-5` (fast, cheap). This runs on every query so cost matters.

System prompt to use **verbatim**:

```
You are a Query Analyst for an anthropological knowledge navigation system.

Given a user query and their User Graph profile, return a JSON object with:
- intent: one of conceptual|navigational|comparative|deep_dive
- core_concepts: list of main anthropological concepts in the query
- expansion_terms: related concepts the user did NOT mention but are relevant
- user_graph_signals: elements from their profile that should bias retrieval
- sub_queries: list of targeted queries per retriever (max 8 total)
- scope: narrow|standard|broad (how wide should retrieval go)

Rules:
- expansion_terms come from YOUR knowledge, not from the user
- If intent is "navigational", set sub_queries to graph retriever only
- Prioritize sub_queries: 1=critical, 2=enrichment, 3=optional
- Return ONLY valid JSON, no preamble or explanation
```

The function signature:
```python
async def analyze_query(
    query: str,
    user_profile: dict,
    mode: str  # navigator|socratic|briefing
) -> AnalyzedQuery:
```

---

### Step 3 — retrievers/semantic.py

Hybrid retrieval: pgvector dense search + pg_trgm fulltext, merged with Reciprocal Rank Fusion.

```python
def reciprocal_rank_fusion(
    list_a: list[Chunk],
    list_b: list[Chunk],
    k: int = 60
) -> list[Chunk]:
    """
    RRF: score(d) = sum(1 / (k + rank(d)))
    Standard k=60 per the original paper.
    Returns deduplicated list sorted by RRF score, descending.
    """
```

Supabase RPC calls needed (create these SQL functions in Supabase):
- `match_documents(query_embedding, match_count, user_id)` — pgvector cosine similarity
- `fulltext_search(query_text, match_count)` — pg_trgm or websearch_to_tsquery

Return top 10 chunks after fusion.

---

### Step 4 — retrievers/graph.py

Weighted BFS on the knowledge graph. Do NOT do unweighted BFS — it retrieves too much noise.

```python
async def graph_traversal(
    concept_ids: list[str],
    depth: int = 2,
    min_edge_weight: float = 0.3,
    max_nodes: int = 30
) -> list[Chunk]:
    """
    Starting from concept_ids, traverse edges weighted >= min_edge_weight.
    Stop at depth=2 or max_nodes=30, whichever comes first.
    Convert each retrieved node to a Chunk.
    """
```

Supabase RPC needed: `weighted_graph_traversal(start_nodes, max_depth, min_edge_weight, max_nodes)`

---

### Step 5 — retrievers/citations.py

OpenAlex API — no auth needed for basic usage.

```python
BASE_URL = "https://api.openalex.org"

async def citation_retrieval(
    paper_ids: list[str],   # OpenAlex work IDs
    direction: Literal["forward", "backward", "both"] = "both",
    limit: int = 10
) -> list[Chunk]:
    """
    Forward citations: papers that CITE our papers (newer work)
    Backward citations: papers that our papers CITE (foundational work)
    Use httpx AsyncClient with 10s timeout.
    Rate limit: 100k requests/day free. Add 1s sleep between batches.
    """
```

OpenAlex endpoints to use:
- `GET /works/{id}/cited_by` — forward
- `GET /works/{id}` → `referenced_works` field — backward

---

### Step 6 — retrievers/user_context.py

```python
async def user_context_retrieval(
    user_id: str,
    concepts: list[str],
    top_k: int = 5
) -> list[Chunk]:
    """
    Retrieve from User Graph:
    1. Concepts the user has previously learned (bias toward those)
    2. Notes the user has taken
    3. User's current knowledge level per concept
    
    Returns chunks formatted with source_type="user_note"
    """
```

---

### Step 7 — coverage.py

Use `claude-haiku-4-5`. Cheap check — only triggers full retry if critical gaps found.

System prompt:
```
You are a Coverage Checker for an anthropological knowledge system.

Given a user query and retrieved text chunks, assess knowledge coverage.
Return JSON:
{
  "coverage_score": 0.0-1.0,
  "covered_aspects": ["..."],
  "missing_aspects": ["..."],
  "source_diversity": "low|medium|high",
  "temporal_coverage": "outdated|current|mixed",
  "needs_retry": true/false,
  "retry_queries": ["specific queries to fill gaps"]
}

Set needs_retry=true ONLY if missing_aspects are critical to answering the query.
Minor gaps do not warrant retry. Cost matters.
Return ONLY valid JSON.
```

**Retry logic (in pipeline.py):**
```python
MAX_COVERAGE_RETRIES = 2
retry_count = 0
while retry_count < MAX_COVERAGE_RETRIES:
    coverage = await check_coverage(query, chunks)
    if not coverage.needs_retry:
        break
    new_chunks = await targeted_retrieval(coverage.retry_queries)
    chunks = deduplicate(chunks + new_chunks)
    retry_count += 1
```

---

### Step 8 — synthesis.py

Use `claude-sonnet-4-5`. This is where quality matters most.

System prompt:
```
You are a Synthesis Agent for an anthropological knowledge system.

You receive retrieved text chunks from multiple sources. Your job:
1. Build a coherent, accurate response to the user's query
2. Attribute every major claim to a source using [source_id]
3. Explicitly flag contradictions between sources — do NOT silently pick one
4. Separate "established consensus" from "contested" from "your inference"
5. Assign confidence scores (0.0-1.0) to major claims
6. Note knowledge gaps you could not fill

Return JSON:
{
  "response": "full response text with [source_id] inline citations",
  "claims": [{"text": "...", "source_ids": ["..."], "confidence": 0.0}],
  "contradictions": ["..."],
  "knowledge_gaps": ["..."]
}

Response length is determined by mode:
- navigator: 2-3 paragraphs max
- socratic: answer the implicit question, then pose one question back
- briefing: comprehensive, structured with headers

Return ONLY valid JSON.
```

If skeptic returns FAIL, re-run synthesis with additional context:
```python
async def synthesize(
    query: str,
    chunks: list[Chunk],
    mode: str,
    user_profile: dict,
    skeptic_feedback: SkepticResult | None = None  # second pass
) -> SynthesisResult:
```

---

### Step 9 — skeptic.py

Use `claude-sonnet-4-5`. This is adversarial reasoning — needs quality.

System prompt **verbatim**:
```
You are a Skeptic Agent for an anthropological knowledge system.
You receive a synthesized response. You did NOT see the original query or sources.
Your job is to challenge the synthesis.

Check for:
1. MISSING_PERSPECTIVES — underrepresented schools of thought? Post-colonial? Feminist? Indigenous?
2. OVERCONFIDENCE — claims presented as certain that are actually contested?
3. CONTRADICTIONS — internal logical contradictions in the response itself?
4. SOURCE_BIAS — evidence of single-school or single-era dominance?
5. SCOPE_CREEP — did the response drift from what was actually asked?

Return JSON:
{
  "verdict": "pass|warn|fail",
  "issues": [{"type": "missing|overconfident|contradicts|biased|scope", "detail": "..."}],
  "suggested_additions": ["what should be added"],
  "confidence_adjustments": [{"claim_excerpt": "...", "suggested_confidence": 0.0}]
}

verdict=pass: response is solid
verdict=warn: response is usable but has notable caveats (return to user with warnings)
verdict=fail: synthesis needs to be redone (return issues to Synthesis Agent)

Be rigorous but proportional. Not every response needs additions.
Return ONLY valid JSON.
```

**Skeptic retry (max once):**
```python
MAX_SKEPTIC_RETRIES = 1  # never more than one retry

skeptic_result = await run_skeptic(synthesis)

if skeptic_result.verdict == SkepticVerdict.FAIL and skeptic_retries == 0:
    synthesis = await synthesize(
        query, chunks, mode, user_profile,
        skeptic_feedback=skeptic_result
    )
    skeptic_retries += 1
    skeptic_result = await run_skeptic(synthesis)
    # accept whatever verdict comes back — no infinite loops
```

---

### Step 10 — pipeline.py (orchestrator)

This is the main entry point. Wires all stages together.

```python
async def run_search_pipeline(
    query: str,
    user_id: str,
    mode: Literal["navigator", "socratic", "briefing"],
    current_node_id: str | None = None  # for navigator mode
) -> KorczakResponse:
    start_time = time.time()
    total_tokens = 0
    
    # Stage 1: analyze
    analyzed = await analyze_query(query, user_profile, mode)
    
    # Stage 2: parallel retrieval
    retrieval_tasks = build_retrieval_tasks(analyzed)
    results = await asyncio.gather(*retrieval_tasks, return_exceptions=True)
    chunks = merge_and_deduplicate(results)
    
    # Stage 3: coverage (with retry loop)
    # ...
    
    # Stage 4: synthesis
    # ...
    
    # Stage 5: skeptic (with one retry)
    # ...
    
    # Stage 6: build final response + async user graph update
    asyncio.create_task(update_user_graph(user_id, query, final_synthesis))
    
    return KorczakResponse(
        content=final_synthesis.response,
        latency_ms=(time.time() - start_time) * 1000,
        tokens_used=total_tokens,
        # ... rest of fields
    )
```

**Model routing (cost optimization):**
```python
MODEL_ROUTING = {
    "query_analyst":       "claude-haiku-4-5",
    "coverage_check":      "claude-haiku-4-5",
    "synthesis":           "claude-sonnet-4-5",
    "skeptic":             "claude-sonnet-4-5",
    "user_model_update":   "claude-haiku-4-5",
}
```

---

### Step 11 — cache.py

Simple in-memory cache for identical queries from the same user within 1 hour. Use `cachetools.TTLCache` (no Redis dependency for MVP).

```python
import hashlib
from cachetools import TTLCache

cache = TTLCache(maxsize=500, ttl=3600)

def cache_key(query: str, user_id: str, mode: str) -> str:
    return hashlib.md5(f"{query}:{user_id}:{mode}".encode()).hexdigest()
```

---

### Step 12 — api/search_router.py

```python
@router.post("/search", response_model=KorczakResponse)
async def search(
    request: SearchRequest,
    current_user: User = Depends(get_current_user)
) -> KorczakResponse:
```

Include error handling: if pipeline raises, return a graceful error with `content="אירעה שגיאה בחיפוש"` and `confidence=0.0`.

---

### Step 13 — tests/test_pipeline.py

Write integration tests using these 5 anthropology queries. Run them against the full pipeline (use `pytest-asyncio`):

```python
TEST_QUERIES = [
    "מה ההבדל בין טוטמיזם לפטישיזם?",
    "איך טורנר מגדיר liminality?",
    "מה הביקורת הפוסט-קולוניאלית על האנתרופולוגיה הקלאסית?",
    "תן לי overview של anthropology of kinship",
    "continue from what we learned about ritual"  # tests navigational intent
]
```

For each query, assert:
1. Pipeline completes without exception
2. `confidence > 0.0`
3. `len(sources) > 0`
4. `skeptic_warnings` is a list (even if empty)
5. Latency under 30 seconds

---

## Critical Rules

1. **All Claude API calls must be async** — use `anthropic.AsyncAnthropic()`
2. **All 4 retrievers run with `asyncio.gather()`** — never sequential
3. **`return_exceptions=True` in gather** — one failing retriever must not kill the pipeline
4. **Every Claude call parses JSON response** — wrap in try/except, log malformed responses, return safe defaults
5. **Token counting** — track `usage.input_tokens + usage.output_tokens` on every Claude call, accumulate in `KorczakResponse.tokens_used`
6. **Max iterations hard limits** — `MAX_COVERAGE_RETRIES = 2`, `MAX_SKEPTIC_RETRIES = 1`. These are non-negotiable.
7. **Confidence propagation** — if Skeptic downgrades claims, the final `confidence` field must reflect it
8. **User Graph update is async fire-and-forget** — use `asyncio.create_task()`, never await it in the response path

---

## Environment Variables Expected

```
ANTHROPIC_API_KEY=
SUPABASE_URL=
SUPABASE_SERVICE_KEY=
OPENALEX_EMAIL=your@email.com  # polite pool: faster rate limits
```

---

## Build Order

1. `models.py` — no dependencies, build and verify first
2. `cache.py` — simple, no Claude
3. `query_analyst.py` — first Claude call, test in isolation
4. `retrievers/semantic.py` — needs Supabase RPC (mock if not ready)
5. `retrievers/graph.py` — needs Supabase RPC (mock if not ready)
6. `retrievers/citations.py` — needs OpenAlex (can test independently)
7. `retrievers/user_context.py` — mock user profile for now
8. `coverage.py` — second Claude call
9. `synthesis.py` — third Claude call
10. `skeptic.py` — fourth Claude call
11. `pipeline.py` — wires everything together
12. `api/search_router.py` — exposes as endpoint
13. `tests/test_pipeline.py` — run all 5 test queries

If Supabase RPCs are not yet created, use mock retrievers that return 3-5 hardcoded chunks about anthropology. The pipeline logic must work end-to-end before the DB is wired.

---

## Definition of Done

- [ ] All 5 test queries return a `KorczakResponse` with no exceptions
- [ ] Parallel retrieval is confirmed async (check logs for concurrent execution)
- [ ] Coverage retry loop runs at most 2 times (assert in test)
- [ ] Skeptic retry runs at most 1 time (assert in test)
- [ ] Model routing confirmed: haiku for analyst+coverage, sonnet for synthesis+skeptic
- [ ] Token usage logged per request
- [ ] One query under 15 seconds end-to-end (with warm cache)
