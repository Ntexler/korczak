"""Chat API endpoints — full Navigator + Tutor pipeline."""

import re
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.integrations import supabase_client as db
from backend.integrations.claude_client import navigate, tutor
from backend.core.context_builder import build_context
from backend.core.mode_detector import detect_mode
from backend.core.level_detector import detect_level, response_level, LEVEL_DESCRIPTIONS
from backend.user.profile_builder import update_from_conversation
from backend.user.context_extractor import extract_context, update_user_profile
from backend.user.behavior_tracker import track_session
from backend.search.pipeline import run_search_pipeline

logger = logging.getLogger(__name__)
router = APIRouter()


class ChatMessage(BaseModel):
    message: str
    conversation_id: str | None = None
    mode: str = "auto"  # auto | navigator | tutor | briefing
    user_id: str | None = None  # Optional for knowledge tracking
    locale: str = "en"  # en | he — for language-aware responses


class ChatResponse(BaseModel):
    response: str
    conversation_id: str
    mode: str
    detected_mode: str | None = None
    concepts_referenced: list[dict] = []
    insight: dict | None = None


@router.post("/", response_model=ChatResponse)
async def chat(msg: ChatMessage):
    """Send a message to Korczak — full pipeline with mode/level detection."""
    try:
        # 1. Create or reuse conversation
        if msg.conversation_id:
            conversation_id = msg.conversation_id
        else:
            conv = await db.create_conversation(mode=msg.mode)
            conversation_id = str(conv["id"])

        # 2. Save user message
        await db.save_message(conversation_id, role="user", content=msg.message)

        # 3. Get conversation history
        history = []
        if msg.conversation_id:
            messages = await db.get_conversation_messages(conversation_id, limit=10)
            for m in messages[:-1]:
                history.append({"role": m["role"], "content": m["content"]})

        # 4. Detect mode (if auto)
        if msg.mode == "auto":
            active_mode = detect_mode(msg.message, "navigator", history or None)
        else:
            active_mode = msg.mode

        # 5. Detect user level
        user_level = detect_level(msg.message, history or None)
        resp_level = response_level(user_level)

        # 6-8. Run search pipeline (replaces old build_context + navigate/tutor)
        socratic_level = min(resp_level, 2)
        try:
            pipeline_result = await run_search_pipeline(
                user_message=msg.message,
                conversation_history=history if history else None,
                user_id=msg.user_id,
                mode=active_mode,
                level_description=LEVEL_DESCRIPTIONS[resp_level],
                socratic_level=socratic_level,
                locale=msg.locale,
            )
            response_text = pipeline_result.response_text
            concepts_referenced = pipeline_result.concepts_referenced
            insight = _extract_insight(response_text) if active_mode != "tutor" else None

            if pipeline_result.token_usage.total > 0:
                logger.info(
                    f"Pipeline tokens: {pipeline_result.token_usage.total} "
                    f"(stages: {pipeline_result.stages_completed})"
                )
        except Exception as e:
            # Fallback to old pipeline if search pipeline fails entirely
            logger.error(f"Search pipeline failed, falling back: {e}")
            graph_context, concepts_referenced = await build_context(msg.message)
            if active_mode == "tutor":
                response_text = await tutor(
                    user_message=msg.message,
                    graph_context=graph_context,
                    user_context="",
                    level_description=LEVEL_DESCRIPTIONS[resp_level],
                    socratic_level=socratic_level,
                    history=history if history else None,
                )
                insight = None
            else:
                response_text = await navigate(
                    user_message=msg.message,
                    graph_context=graph_context,
                    user_context="",
                    history=history if history else None,
                )
                insight = _extract_insight(response_text)

        # 9. Save assistant response
        await db.save_message(
            conversation_id,
            role="assistant",
            content=response_text,
            concepts_referenced=concepts_referenced,
        )

        # 10. Update user knowledge graph (async, non-blocking)
        if msg.user_id and concepts_referenced:
            try:
                await update_from_conversation(
                    user_id=msg.user_id,
                    concepts_referenced=concepts_referenced,
                    user_message=msg.message,
                    assistant_response=response_text,
                )
            except Exception as e:
                logger.warning(f"User graph update failed: {e}")

        # 11. Extract personal context (Layer 2) — implicit, never asks
        if msg.user_id:
            try:
                signals = extract_context(msg.message)
                if signals:
                    await update_user_profile(msg.user_id, signals)
            except Exception as e:
                logger.warning(f"Context extraction failed: {e}")

        # 12. Track behavioral patterns (Layer 3)
        if msg.user_id:
            try:
                await track_session(msg.user_id, msg.message, active_mode, concepts_referenced)
            except Exception as e:
                logger.warning(f"Behavior tracking failed: {e}")

        return ChatResponse(
            response=response_text,
            conversation_id=conversation_id,
            mode=active_mode,
            detected_mode=active_mode if msg.mode == "auto" else None,
            concepts_referenced=concepts_referenced,
            insight=insight,
        )

    except Exception as e:
        logger.error(f"Chat error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history/{conversation_id}")
async def get_history(conversation_id: str):
    """Fetch message history for a conversation."""
    try:
        messages = await db.get_conversation_messages(conversation_id)
        return {"conversation_id": conversation_id, "messages": messages}
    except Exception as e:
        logger.error(f"History fetch error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


def _extract_insight(text: str) -> dict | None:
    """Extract the unsolicited insight section from the response."""
    patterns = [
        r"(?:\*\*)?(?:Unsolicited )?Insight(?:\*\*)?[:\s]*(.+?)(?:\n\n|\Z)",
        r"(?:\*\*)?Something you might not have considered(?:\*\*)?[:\s]*(.+?)(?:\n\n|\Z)",
        r"(?:\*\*)?Blind spot(?:\*\*)?[:\s]*(.+?)(?:\n\n|\Z)",
        r"(?:\*\*)?What you might be missing(?:\*\*)?[:\s]*(.+?)(?:\n\n|\Z)",
        r"(?:\*\*)?A connection worth noting(?:\*\*)?[:\s]*(.+?)(?:\n\n|\Z)",
        r"(?:\*\*)?Did you know(?:\*\*)?[:\s]*(.+?)(?:\n\n|\Z)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        if match:
            content = match.group(1).strip()
            lower = pattern.lower()
            if "blind" in lower:
                insight_type = "blind_spot"
            elif "connection" in lower:
                insight_type = "connection"
            else:
                insight_type = "insight"
            return {"type": insight_type, "content": content[:500]}

    return None
