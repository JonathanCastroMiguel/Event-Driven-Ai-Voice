"""WebRTC call signaling endpoints.

Proxies SDP offer/answer to OpenAI Realtime WebRTC API.
The browser connects directly to OpenAI for audio — no server-side audio relay.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import httpx
import structlog
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.config import settings

logger = structlog.get_logger()

router = APIRouter(prefix="/calls", tags=["calls"])


# ---------------------------------------------------------------------------
# In-memory session registry
# ---------------------------------------------------------------------------


class CallSessionEntry:
    """Tracks an active call session."""

    def __init__(self, call_id: UUID) -> None:
        self.call_id = call_id


_sessions: dict[UUID, CallSessionEntry] = {}


def get_session(call_id: UUID) -> CallSessionEntry:
    entry = _sessions.get(call_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Call not found")
    return entry


# ---------------------------------------------------------------------------
# POST /calls — create a new call session
# ---------------------------------------------------------------------------


class CreateCallResponse(BaseModel):
    call_id: str
    status: str


@router.post("", status_code=201, response_model=CreateCallResponse)
async def create_call() -> CreateCallResponse:
    """Create a new voice call session."""
    if len(_sessions) >= settings.max_concurrent_calls:
        raise HTTPException(status_code=503, detail="max_calls_exceeded")

    call_id = uuid4()
    _sessions[call_id] = CallSessionEntry(call_id)
    logger.info("call_created", call_id=str(call_id))
    return CreateCallResponse(call_id=str(call_id), status="created")


# ---------------------------------------------------------------------------
# POST /calls/{call_id}/offer — proxy SDP to OpenAI Realtime WebRTC
# ---------------------------------------------------------------------------


class SDPRequest(BaseModel):
    sdp: str
    type: str


class SDPResponse(BaseModel):
    sdp: str
    type: str


@router.post("/{call_id}/offer", response_model=SDPResponse)
async def handle_offer(call_id: UUID, body: SDPRequest) -> SDPResponse:
    """Proxy SDP offer to OpenAI Realtime WebRTC API, return SDP answer.

    The browser connects directly to OpenAI via WebRTC for audio.
    Our backend just handles the signaling (SDP exchange).
    """
    get_session(call_id)

    model = settings.openai_realtime_model

    logger.info("proxying_sdp_to_openai", call_id=str(call_id), model=model)

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"https://api.openai.com/v1/realtime/calls?model={model}",
            headers={
                "Authorization": f"Bearer {settings.openai_api_key}",
                "Content-Type": "application/sdp",
            },
            content=body.sdp,
        )

    if resp.status_code not in (200, 201):
        logger.error(
            "openai_sdp_proxy_error",
            status=resp.status_code,
            body=resp.text[:500],
            call_id=str(call_id),
        )
        raise HTTPException(
            status_code=502,
            detail=f"OpenAI Realtime API error: {resp.status_code}",
        )

    answer_sdp = resp.text
    logger.info("sdp_exchange_complete", call_id=str(call_id))

    return SDPResponse(sdp=answer_sdp, type="answer")


# ---------------------------------------------------------------------------
# DELETE /calls/{call_id} — end a call
# ---------------------------------------------------------------------------


@router.delete("/{call_id}", status_code=204)
async def delete_call(call_id: UUID) -> None:
    """End a call and clean up resources."""
    get_session(call_id)
    _sessions.pop(call_id, None)
    logger.info("call_ended", call_id=str(call_id))
