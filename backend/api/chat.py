"""Chat API endpoints — full Navigator pipeline."""

import re
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.integrations import supabase_client as db
from backend.integrations.claude_client import navigate
from backend.core.context_builder import build_context

logger = logging.getLogger(__name__)
router = APIRouter()


class ChatMessage(BaseModel):
    message: str
    conversation_id: str | None = None
    mode: str = "navigator"  # navigator | tutor | briefing


class ChatResponse(BaseModel):
    response: str
    conversation_id: str
    mode: str
    concepts_referenced: list[dict] = []
    insight: dict | None = None


@router.post("/", response_model=ChatResponse)
async def chat(msg: ChatMessage):
    """Send a message to Korczak — full pipeline."""
    try:
        # 1. Create or reuse conversation
        if msg.conversation_id:
            conversation_id = msg.conversation_id
        else:
            conv = await db.create_conversation(mode=msg.mode)
            conversation_id = str(conv["id"])

        # 2. Save user message
        await db.save_message(conversation_id, role="user", content=msg.message)

        # 3. Build graph context
        graph_context, concepts_referenced = await build_context(msg.message)

        # 4. Get conversation history for multi-turn
        history = []
        if msg.conversation_id:
            messages = await db.get_conversation_messages(conversation_id, limit=10)
            # Exclude the message we just saved (last one)
            for m in messages[:-1]:
                history.append({"role": m["role"], "content": m["content"]})

        # 5. Call Navigator
        response_text = await navigate(
            user_message=msg.message,
            graph_context=graph_context,
            user_context="Anonymous user exploring the knowledge graph.",
            history=history if history else None,
        )

        # 6. Extract insight from response (look for marked section)
        insight = _extract_insight(response_text)

        # 7. Save assistant response
        await db.save_message(
            conversation_id,
            role="assistant",
            content=response_text,
            concepts_referenced=concepts_referenced,
        )

        return ChatResponse(
            response=response_text,
            conversation_id=conversation_id,
            mode=msg.mode,
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
    # Look for common patterns Korczak uses to mark insights
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
            # Determine insight type
            lower = pattern.lower()
            if "blind" in lower:
                insight_type = "blind_spot"
            elif "connection" in lower:
                insight_type = "connection"
            else:
                insight_type = "insight"
            return {"type": insight_type, "content": content[:500]}

    return None
