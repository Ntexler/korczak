"""Chat API endpoints."""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

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
    insight: dict | None = None  # Unsolicited insight


@router.post("/", response_model=ChatResponse)
async def chat(msg: ChatMessage):
    """Send a message to Korczak (HTTP fallback)."""
    # TODO: Wire to Navigator/Tutor core
    return ChatResponse(
        response="Korczak is setting up. Navigator coming in Phase 1c.",
        conversation_id=msg.conversation_id or "temp",
        mode=msg.mode,
    )


@router.websocket("/ws/{conversation_id}")
async def chat_websocket(websocket: WebSocket, conversation_id: str):
    """WebSocket endpoint for real-time chat."""
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_json()
            # TODO: Wire to Navigator/Tutor core with streaming
            await websocket.send_json({
                "type": "message",
                "content": "Korczak WebSocket connected. Navigator coming in Phase 1c.",
                "conversation_id": conversation_id,
            })
    except WebSocketDisconnect:
        pass
