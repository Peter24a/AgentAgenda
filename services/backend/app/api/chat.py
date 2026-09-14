import json
from datetime import datetime
from typing import AsyncGenerator
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from app.models.chat import ChatRequest
from app.db.database import get_events_for_date, save_proposal
from app.services.prompt_builder import build_llm_messages
from app.services.llm_service import stream_chat_completion
from app.services.proposal_parser import extract_proposal_from_text

router = APIRouter(prefix="/v1/chat", tags=["Chat"])

async def sse_event_generator(request: ChatRequest) -> AsyncGenerator[str, None]:
    target_date = request.date or datetime.now().strftime("%Y-%m-%d")
    events = await get_events_for_date(target_date)

    messages = build_llm_messages(
        current_date=target_date,
        events=events,
        user_message=request.message,
        history=request.history
    )

    full_response = ""
    async for chunk in stream_chat_completion(messages):
        full_response += chunk
        payload = json.dumps({"type": "token", "content": chunk})
        yield f"data: {payload}\n\n"

    # Analyze if completion generated a structured proposal
    proposal, clean_text = extract_proposal_from_text(full_response)
    if proposal:
        await save_proposal(proposal)
        prop_payload = json.dumps({
            "type": "proposal",
            "proposal": proposal.model_dump(mode="json")
        })
        yield f"data: {prop_payload}\n\n"

    done_payload = json.dumps({"type": "done"})
    yield f"data: {done_payload}\n\n"

@router.post("/stream")
async def chat_stream(request: ChatRequest):
    return StreamingResponse(
        sse_event_generator(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )
