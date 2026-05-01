"""
Chat API — /api/v1/chat

Endpoints:
  POST /stream   → Server-Sent Events (SSE) streaming response
  POST /message  → Single JSON response (for bots / schedulers)
"""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from app.agents.agent_loop import AgentLoop
from app.api.deps import get_current_user

router = APIRouter()


class ChatRequest(BaseModel):
    message:    str
    session_id: str | None = None


# ── Streaming endpoint (Android app / web) ───────────────────────────────────
@router.post("/stream")
async def chat_stream(
    req: ChatRequest,
    user: dict = Depends(get_current_user)
):
    """
    Stream the AI response token-by-token using Server-Sent Events.
    The Android app reads this as a chunked HTTP response.
    """
    user_id = user["id"]
    agent   = AgentLoop(user_id=user_id)

    async def event_generator():
        try:
            async for chunk in agent.run_stream(req.message):
                # SSE format: data: <chunk>\n\n
                yield f"data: {chunk}\n\n"
        except Exception as e:
            yield f"data: ❌ Error: {e}\n\n"
        finally:
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control":    "no-cache",
            "X-Accel-Buffering":"no",      # Needed for nginx
        }
    )


# ── Non-streaming endpoint (Telegram / WhatsApp bots) ───────────────────────
@router.post("/message")
async def chat_message(
    req: ChatRequest,
    user: dict = Depends(get_current_user)
):
    """Return a complete JSON response — for bot integrations."""
    agent  = AgentLoop(user_id=user["id"])
    reply  = await agent.run(req.message)
    return {"reply": reply, "user_id": user["id"]}
