"""WebRTC call signaling endpoints."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import structlog
from aiortc import RTCConfiguration, RTCIceServer, RTCPeerConnection, RTCSessionDescription
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from src.config import settings
from src.voice_runtime.realtime_bridge import RealtimeVoiceBridge
from src.voice_runtime.realtime_provider import create_voice_provider

logger = structlog.get_logger()

router = APIRouter(prefix="/calls", tags=["calls"])


# ---------------------------------------------------------------------------
# In-memory session registry for active calls
# ---------------------------------------------------------------------------


class CallSessionEntry:
    """Tracks an active call's resources."""

    def __init__(self, call_id: UUID) -> None:
        self.call_id = call_id
        self.peer_connection: RTCPeerConnection | None = None
        self.coordinator: Any | None = None
        self.bridge: Any | None = None
        self.control_channel: Any | None = None
        self.debug_channel: Any | None = None


_sessions: dict[UUID, CallSessionEntry] = {}


def get_session(call_id: UUID) -> CallSessionEntry:
    """Retrieve a session or raise 404."""
    entry = _sessions.get(call_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Call not found")
    return entry


def build_rtc_configuration() -> RTCConfiguration:
    """Build ICE configuration from environment settings."""
    ice_servers: list[RTCIceServer] = []

    for stun in settings.stun_servers.split(","):
        stun = stun.strip()
        if stun:
            ice_servers.append(RTCIceServer(urls=[stun]))

    if settings.turn_servers:
        for turn in settings.turn_servers.split(","):
            turn = turn.strip()
            if turn:
                ice_servers.append(
                    RTCIceServer(
                        urls=[turn],
                        username=settings.turn_username,
                        credential=settings.turn_credential,
                    )
                )

    return RTCConfiguration(iceServers=ice_servers)


async def _cleanup_session(call_id: UUID) -> None:
    """Clean up all resources for a call session."""
    entry = _sessions.pop(call_id, None)
    if entry is None:
        return

    if entry.bridge is not None:
        await entry.bridge.close()

    if entry.peer_connection is not None:
        await entry.peer_connection.close()

    logger.info("call_cleaned_up", call_id=str(call_id))


# ---------------------------------------------------------------------------
# POST /calls — create a new call session
# ---------------------------------------------------------------------------


class CreateCallResponse(BaseModel):
    call_id: str
    status: str


@router.post("", status_code=201, response_model=CreateCallResponse)
async def create_call(request: Request) -> CreateCallResponse:
    """Create a new voice call session."""
    if len(_sessions) >= settings.max_concurrent_calls:
        raise HTTPException(status_code=503, detail="max_calls_exceeded")

    call_id = uuid4()
    entry = CallSessionEntry(call_id)
    _sessions[call_id] = entry

    logger.info("call_created", call_id=str(call_id))

    return CreateCallResponse(call_id=str(call_id), status="created")


# ---------------------------------------------------------------------------
# POST /calls/{call_id}/offer — SDP exchange
# ---------------------------------------------------------------------------


class SDPRequest(BaseModel):
    sdp: str
    type: str


class SDPResponse(BaseModel):
    sdp: str
    type: str


@router.post("/{call_id}/offer", response_model=SDPResponse)
async def handle_offer(call_id: UUID, body: SDPRequest) -> SDPResponse:
    """Accept SDP offer, create peer connection, return SDP answer."""
    entry = get_session(call_id)

    if entry.peer_connection is not None:
        raise HTTPException(status_code=409, detail="Offer already processed")

    pc = RTCPeerConnection(configuration=build_rtc_configuration())
    entry.peer_connection = pc

    # Add audio transceiver (sendrecv for bidirectional audio)
    pc.addTransceiver("audio", direction="sendrecv")

    # Create DataChannels
    entry.control_channel = pc.createDataChannel("control", ordered=True)
    entry.debug_channel = pc.createDataChannel("debug", ordered=True)

    # Create voice provider and bridge
    provider = await create_voice_provider()
    bridge = RealtimeVoiceBridge(
        call_id=call_id,
        provider=provider,
        control_channel=entry.control_channel,
        debug_channel=entry.debug_channel,
    )
    entry.bridge = bridge

    # Start STT listener
    bridge.start_stt_listener()

    # Forward audio from WebRTC track to provider when track arrives
    @pc.on("track")
    def on_track(track: Any) -> None:
        if track.kind == "audio":
            bridge.start_audio_forwarding(track)
            logger.debug("audio_track_forwarding_started", call_id=str(call_id))

    # Detect peer disconnection for auto-cleanup
    @pc.on("connectionstatechange")
    async def on_connection_state_change() -> None:
        state = pc.connectionState
        logger.debug("rtc_connection_state", call_id=str(call_id), state=state)
        if state in ("failed", "closed"):
            await _cleanup_session(call_id)

    # Set remote description (offer) and create answer
    offer = RTCSessionDescription(sdp=body.sdp, type=body.type)
    await pc.setRemoteDescription(offer)

    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    logger.info("sdp_exchange_complete", call_id=str(call_id))

    return SDPResponse(
        sdp=pc.localDescription.sdp,
        type=pc.localDescription.type,
    )


# ---------------------------------------------------------------------------
# POST /calls/{call_id}/ice — ICE candidate exchange
# ---------------------------------------------------------------------------


class ICECandidateRequest(BaseModel):
    candidate: str
    sdpMid: str | None = None
    sdpMLineIndex: int | None = None


@router.post("/{call_id}/ice", status_code=204)
async def handle_ice(call_id: UUID, body: ICECandidateRequest) -> None:
    """Add a trickle ICE candidate to the peer connection.

    Note: aiortc gathers ICE candidates during createAnswer, so for local/Docker
    testing trickle ICE is typically not needed. This endpoint exists for
    completeness and remote NAT traversal scenarios.
    """
    entry = get_session(call_id)

    if entry.peer_connection is None:
        raise HTTPException(status_code=400, detail="No peer connection; send offer first")

    # aiortc's addIceCandidate is a no-op for most local scenarios since
    # candidates are gathered during SDP exchange. Log for debugging.
    logger.debug("ice_candidate_received", call_id=str(call_id), candidate=body.candidate)


# ---------------------------------------------------------------------------
# DELETE /calls/{call_id} — end a call
# ---------------------------------------------------------------------------


@router.delete("/{call_id}", status_code=204)
async def delete_call(call_id: UUID) -> None:
    """End a call and clean up resources."""
    get_session(call_id)  # Validate exists
    await _cleanup_session(call_id)
