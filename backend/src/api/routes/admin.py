"""Admin endpoints for call inspection."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import structlog
from fastapi import APIRouter, HTTPException, Request

logger = structlog.get_logger()

router = APIRouter(tags=["admin"])


@router.get("/calls")
async def list_calls(request: Request) -> list[dict[str, Any]]:
    """List recent call sessions."""
    pool = getattr(request.app.state, "db_pool", None)
    if pool is None:
        raise HTTPException(status_code=503, detail="Database not configured")

    rows = await pool.fetch(
        "SELECT call_id, started_at, ended_at, status, locale_hint "
        "FROM call_sessions ORDER BY started_at DESC LIMIT 50"
    )
    return [
        {
            "call_id": str(r["call_id"]),
            "started_at": r["started_at"],
            "ended_at": r["ended_at"],
            "status": r["status"],
            "locale_hint": r["locale_hint"],
        }
        for r in rows
    ]


@router.get("/calls/{call_id}")
async def get_call_detail(call_id: UUID, request: Request) -> dict[str, Any]:
    """Get call detail with turns and generations."""
    pool = getattr(request.app.state, "db_pool", None)
    if pool is None:
        raise HTTPException(status_code=503, detail="Database not configured")

    # Fetch call session
    call_row = await pool.fetchrow(
        "SELECT * FROM call_sessions WHERE call_id = $1", call_id
    )
    if call_row is None:
        raise HTTPException(status_code=404, detail="Call not found")

    # Fetch turns
    turn_rows = await pool.fetch(
        "SELECT * FROM turns WHERE call_id = $1 ORDER BY seq", call_id
    )

    # Fetch agent generations
    gen_rows = await pool.fetch(
        "SELECT * FROM agent_generations WHERE call_id = $1 ORDER BY created_at", call_id
    )

    return {
        "call": {
            "call_id": str(call_row["call_id"]),
            "started_at": call_row["started_at"],
            "ended_at": call_row["ended_at"],
            "status": call_row["status"],
            "locale_hint": call_row["locale_hint"],
        },
        "turns": [
            {
                "turn_id": str(r["turn_id"]),
                "seq": r["seq"],
                "started_at": r["started_at"],
                "finalized_at": r["finalized_at"],
                "text_final": r["text_final"],
                "language": r["language"],
                "state": r["state"],
            }
            for r in turn_rows
        ],
        "generations": [
            {
                "agent_generation_id": str(r["agent_generation_id"]),
                "turn_id": str(r["turn_id"]),
                "state": r["state"],
                "route_a_label": r["route_a_label"],
                "route_a_confidence": r["route_a_confidence"],
                "specialist": r["specialist"],
                "created_at": r["created_at"],
            }
            for r in gen_rows
        ],
    }
