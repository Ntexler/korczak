"""Learner State & Discovery API — the metacognitive layer.

Endpoints:
  GET  /learner/me/map              — "You are here" concept map
  GET  /learner/me/next             — next concept to learn
  GET  /learner/me/reviews          — concepts due for spaced-repetition
  POST /learner/me/mastery          — update mastery after interaction
  POST /learner/me/paths            — create a learning path
  GET  /learner/me/paths            — list user's learning paths
  GET  /learner/me/paths/{id}       — path with steps + progress

  GET  /discoveries                 — list AI-found discoveries
  GET  /discoveries/{id}            — single discovery detail
  POST /discoveries/{id}/review     — mark human verdict on a discovery
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from backend.integrations import supabase_client as db
from backend.core import learning_paths as path_engine

logger = logging.getLogger(__name__)
router = APIRouter()


# =====================================================================
# Models
# =====================================================================

class MasteryOut(BaseModel):
    concept_id: str
    concept_name: str
    mastery_score: float
    mastery_level: str  # unseen | exposed | practicing | mastered
    times_seen: int
    times_correct: int
    last_seen: Optional[str] = None
    next_review_due: Optional[str] = None


class LearnerMap(BaseModel):
    user_id: str
    total_concepts: int
    mastered: int
    practicing: int
    exposed: int
    unseen_ready: int  # prerequisites met
    concepts: list[dict]  # enriched concept data


class NextStep(BaseModel):
    concept_id: str
    concept_name: str
    definition: Optional[str]
    reason: str  # why this is next
    prerequisites_met: list[dict] = []
    suggested_papers: list[dict] = []


class MasteryUpdate(BaseModel):
    concept_id: str
    interaction: str  # viewed | explained_correctly | explained_incorrectly | self_marked_mastered
    metadata: dict = {}


class PathGenerateRequest(BaseModel):
    user_id: str
    goal_concept_id: Optional[str] = None
    goal_concept_name: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    max_steps: int = 20
    save: bool = True


class DiscoveryOut(BaseModel):
    id: str
    kind: str
    title: str
    description: str
    claude_reasoning: Optional[str]
    paper_ids: list[str] = []
    concept_ids: list[str] = []
    confidence: float
    novelty: float
    importance: float
    reviewed: bool
    review_verdict: Optional[str] = None
    created_at: str


# =====================================================================
# Learner endpoints
# =====================================================================

def _mastery_from_score(score: float) -> str:
    if score >= 0.85:
        return "mastered"
    if score >= 0.5:
        return "practicing"
    if score > 0:
        return "exposed"
    return "unseen"


def _compute_next_review(score: float, ease: float = 2.5, interval: int = 1) -> datetime:
    """Simple SM-2 style spaced repetition."""
    if score < 0.3:
        new_interval = 1
    elif score < 0.6:
        new_interval = max(1, interval)
    elif score < 0.85:
        new_interval = max(3, int(interval * 1.5))
    else:
        new_interval = max(7, int(interval * ease))
    return datetime.now(tz=timezone.utc) + timedelta(days=new_interval)


@router.get("/me/map", response_model=LearnerMap)
async def get_learner_map(
    user_id: str = Query(..., description="User ID"),
    field: Optional[str] = None,
    limit: int = Query(default=200, le=500),
):
    """Return the learner's "You Are Here" map — concepts with mastery status."""
    try:
        client = db.get_client()

        # All concepts (optionally filtered)
        q = client.table("concepts").select("id,name,type,definition").limit(limit)
        concepts = q.execute().data

        # Mastery for this user
        mastery_rows = (
            client.table("user_concept_mastery")
            .select("concept_id,mastery_score,mastery_level,times_seen,times_correct,last_seen,next_review_due")
            .eq("user_id", user_id)
            .execute()
        ).data
        mastery_map = {r["concept_id"]: r for r in mastery_rows}

        # Prereqs: for each unseen concept, check if its BUILDS_ON / EXTENDS
        # prerequisites are all mastered (in mastery_map with score >= 0.7).
        mastered_ids = {cid for cid, m in mastery_map.items() if (m.get("mastery_score") or 0) >= 0.7}
        rels = (
            client.table("relationships")
            .select("source_id,target_id,relationship_type")
            .eq("source_type", "concept")
            .eq("target_type", "concept")
            .in_("relationship_type", ["BUILDS_ON", "EXTENDS", "APPLIES"])
            .execute()
        ).data
        prereqs_by_concept: dict = {}
        for r in rels:
            # source depends on target → target is a prereq of source
            prereqs_by_concept.setdefault(r["source_id"], set()).add(r["target_id"])

        enriched = []
        counts = {"mastered": 0, "practicing": 0, "exposed": 0, "unseen": 0, "unseen_ready": 0}
        for c in concepts:
            m = mastery_map.get(c["id"], {})
            level = m.get("mastery_level", "unseen")
            counts[level] = counts.get(level, 0) + 1
            prereqs_met = False
            if level == "unseen":
                reqs = prereqs_by_concept.get(c["id"], set())
                if reqs and reqs.issubset(mastered_ids):
                    counts["unseen_ready"] += 1
                    prereqs_met = True
                elif not reqs:
                    # No declared prereqs → counts as ready to enter
                    counts["unseen_ready"] += 1
                    prereqs_met = True
            enriched.append({
                **c,
                "mastery_level": level,
                "mastery_score": m.get("mastery_score", 0.0),
                "times_seen": m.get("times_seen", 0),
                "last_seen": m.get("last_seen"),
                "prereqs_met": prereqs_met,
            })

        return LearnerMap(
            user_id=user_id,
            total_concepts=len(concepts),
            mastered=counts["mastered"],
            practicing=counts["practicing"],
            exposed=counts["exposed"],
            unseen_ready=counts["unseen_ready"],
            concepts=enriched,
        )
    except Exception as e:
        logger.exception("Failed to build learner map")
        raise HTTPException(500, detail=str(e))


@router.get("/me/next", response_model=NextStep)
async def get_next_step(
    user_id: str = Query(...),
    goal_concept_id: Optional[str] = None,
):
    """Suggest the next concept for the learner, given current state."""
    try:
        client = db.get_client()

        # 1) Check if any concept is "practicing" — finish those first
        practicing = (
            client.table("user_concept_mastery")
            .select("concept_id,mastery_score")
            .eq("user_id", user_id)
            .eq("mastery_level", "practicing")
            .order("mastery_score", desc=True)
            .limit(1)
            .execute()
        ).data
        if practicing:
            cid = practicing[0]["concept_id"]
            c = client.table("concepts").select("*").eq("id", cid).single().execute().data
            return NextStep(
                concept_id=c["id"], concept_name=c["name"],
                definition=c.get("definition"),
                reason="You're practicing this — let's reinforce it.",
            )

        # 2) Spaced-rep: any review due?
        due = (
            client.table("user_concept_mastery")
            .select("concept_id,next_review_due")
            .eq("user_id", user_id)
            .lte("next_review_due", datetime.now(tz=timezone.utc).isoformat())
            .order("next_review_due")
            .limit(1)
            .execute()
        ).data
        if due:
            cid = due[0]["concept_id"]
            c = client.table("concepts").select("*").eq("id", cid).single().execute().data
            return NextStep(
                concept_id=c["id"], concept_name=c["name"],
                definition=c.get("definition"),
                reason="This is due for spaced-repetition review.",
            )

        # 3) Fresh concept with prerequisites met — high-paper-count concept
        concept = (
            client.table("concepts")
            .select("id,name,definition")
            .order("confidence", desc=True)
            .limit(1)
            .execute()
        ).data
        if concept:
            c = concept[0]
            return NextStep(
                concept_id=c["id"], concept_name=c["name"],
                definition=c.get("definition"),
                reason="High-confidence foundational concept — a good starting point.",
            )

        raise HTTPException(404, detail="No next concept available")
    except Exception as e:
        logger.exception("Failed to pick next concept")
        raise HTTPException(500, detail=str(e))


@router.get("/me/reviews", response_model=list[MasteryOut])
async def get_reviews_due(user_id: str = Query(...), limit: int = Query(default=20, le=100)):
    """Concepts due for spaced-repetition review."""
    try:
        client = db.get_client()
        rows = (
            client.table("user_concept_mastery")
            .select("*,concepts(name)")
            .eq("user_id", user_id)
            .lte("next_review_due", datetime.now(tz=timezone.utc).isoformat())
            .order("next_review_due")
            .limit(limit)
            .execute()
        ).data
        out = []
        for r in rows:
            out.append(MasteryOut(
                concept_id=r["concept_id"],
                concept_name=(r.get("concepts") or {}).get("name", ""),
                mastery_score=r.get("mastery_score", 0.0),
                mastery_level=r.get("mastery_level", "unseen"),
                times_seen=r.get("times_seen", 0),
                times_correct=r.get("times_correct", 0),
                last_seen=r.get("last_seen"),
                next_review_due=r.get("next_review_due"),
            ))
        return out
    except Exception as e:
        logger.exception("Failed to list reviews due")
        raise HTTPException(500, detail=str(e))


@router.post("/me/mastery")
async def update_mastery(user_id: str, payload: MasteryUpdate):
    """Update a concept's mastery after an interaction."""
    try:
        client = db.get_client()
        # Fetch existing
        rows = (
            client.table("user_concept_mastery")
            .select("*")
            .eq("user_id", user_id)
            .eq("concept_id", payload.concept_id)
            .execute()
        ).data
        now = datetime.now(tz=timezone.utc).isoformat()

        # Compute new state
        interaction = payload.interaction
        delta_correct = 1 if interaction == "explained_correctly" else 0
        delta_total = 1 if interaction in ("explained_correctly", "explained_incorrectly") else 0
        if interaction == "self_marked_mastered":
            new_score = 1.0
        else:
            prev = rows[0] if rows else {}
            old_score = prev.get("mastery_score", 0.0)
            if interaction == "viewed":
                new_score = max(old_score, 0.2)
            elif interaction == "explained_correctly":
                new_score = min(1.0, old_score + 0.2)
            elif interaction == "explained_incorrectly":
                new_score = max(0.0, old_score - 0.1)
            else:
                new_score = old_score

        level = _mastery_from_score(new_score)
        next_review = _compute_next_review(new_score).isoformat()

        if rows:
            r = rows[0]
            client.table("user_concept_mastery").update({
                "mastery_score": new_score,
                "mastery_level": level,
                "times_seen": r.get("times_seen", 0) + 1,
                "times_assessed": r.get("times_assessed", 0) + delta_total,
                "times_correct": r.get("times_correct", 0) + delta_correct,
                "last_seen": now,
                "next_review_due": next_review,
                "updated_at": now,
            }).eq("id", r["id"]).execute()
        else:
            client.table("user_concept_mastery").insert({
                "user_id": user_id,
                "concept_id": payload.concept_id,
                "mastery_score": new_score,
                "mastery_level": level,
                "times_seen": 1,
                "times_assessed": delta_total,
                "times_correct": delta_correct,
                "last_seen": now,
                "next_review_due": next_review,
            }).execute()

        # Log interaction
        client.table("user_interactions").insert({
            "user_id": user_id,
            "interaction_type": interaction,
            "concept_id": payload.concept_id,
            "metadata": payload.metadata,
        }).execute()

        return {"ok": True, "new_score": new_score, "level": level, "next_review": next_review}
    except Exception as e:
        logger.exception("Failed to update mastery")
        raise HTTPException(500, detail=str(e))


# =====================================================================
# Discovery endpoints
# =====================================================================

# =====================================================================
# Learning Path generator
# =====================================================================

@router.post("/paths/generate")
async def generate_path(req: PathGenerateRequest):
    """Generate a concrete learning path for the user toward a goal concept."""
    try:
        goal_id = req.goal_concept_id
        if not goal_id and req.goal_concept_name:
            goal_id = path_engine.find_concept_by_name(req.goal_concept_name)
            if not goal_id:
                raise HTTPException(404, detail=f"Concept '{req.goal_concept_name}' not found")
        if not goal_id:
            raise HTTPException(400, detail="Provide goal_concept_id or goal_concept_name")

        path = path_engine.generate_learning_path(
            user_id=req.user_id,
            goal_concept_id=goal_id,
            name=req.name,
            description=req.description,
            max_steps=req.max_steps,
            save=req.save,
        )
        return path
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to generate path")
        raise HTTPException(500, detail=str(e))


@router.get("/paths")
async def list_paths(user_id: str = Query(...)):
    """List a user's learning paths."""
    try:
        client = db.get_client()
        rows = (
            client.table("learning_paths")
            .select("*")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .execute()
        ).data
        return rows
    except Exception as e:
        logger.exception("Failed to list paths")
        raise HTTPException(500, detail=str(e))


@router.get("/paths/{path_id}")
async def get_path(path_id: str):
    """Return a path with its ordered steps."""
    try:
        client = db.get_client()
        path = (
            client.table("learning_paths").select("*").eq("id", path_id).single().execute()
        ).data
        steps = (
            client.table("learning_path_steps")
            .select("*,concepts(name,definition),papers(title)")
            .eq("path_id", path_id)
            .order("position")
            .execute()
        ).data
        return {"path": path, "steps": steps}
    except Exception as e:
        logger.exception("Failed to fetch path")
        raise HTTPException(500, detail=str(e))


# =====================================================================
# Discovery endpoints
# =====================================================================

@router.get("/discoveries", response_model=list[DiscoveryOut])
async def list_discoveries(
    kind: Optional[str] = None,
    reviewed: Optional[bool] = None,
    min_importance: float = Query(default=0.0, ge=0, le=1),
    limit: int = Query(default=30, le=100),
):
    """List AI-generated discoveries for human review."""
    try:
        client = db.get_client()
        q = client.table("discoveries").select("*").gte("importance", min_importance)
        if kind:
            q = q.eq("kind", kind)
        if reviewed is not None:
            q = q.eq("reviewed", reviewed)
        q = q.order("importance", desc=True).order("novelty", desc=True).limit(limit)
        rows = q.execute().data
        return [DiscoveryOut(
            id=r["id"], kind=r["kind"], title=r["title"], description=r["description"],
            claude_reasoning=r.get("claude_reasoning"),
            paper_ids=r.get("paper_ids") or [],
            concept_ids=r.get("concept_ids") or [],
            confidence=r.get("confidence", 0.5),
            novelty=r.get("novelty", 0.5),
            importance=r.get("importance", 0.5),
            reviewed=r.get("reviewed", False),
            review_verdict=r.get("review_verdict"),
            created_at=r.get("created_at", ""),
        ) for r in rows]
    except Exception as e:
        logger.exception("Failed to list discoveries")
        raise HTTPException(500, detail=str(e))


@router.post("/discoveries/{discovery_id}/review")
async def review_discovery(discovery_id: str, verdict: str, notes: Optional[str] = None, reviewer_id: Optional[str] = None):
    """Mark a discovery with a human review verdict."""
    if verdict not in ("confirmed", "rejected", "needs_evidence", "partially_correct"):
        raise HTTPException(400, detail="Invalid verdict")
    try:
        client = db.get_client()
        update = {
            "reviewed": True,
            "review_verdict": verdict,
            "review_notes": notes,
            "reviewed_at": datetime.now(tz=timezone.utc).isoformat(),
        }
        if reviewer_id:
            update["reviewed_by"] = reviewer_id
        client.table("discoveries").update(update).eq("id", discovery_id).execute()
        return {"ok": True, "verdict": verdict}
    except Exception as e:
        logger.exception("Failed to review discovery")
        raise HTTPException(500, detail=str(e))
