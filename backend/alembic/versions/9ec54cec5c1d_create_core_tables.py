"""create_core_tables

Revision ID: 9ec54cec5c1d
Revises:
Create Date: 2026-03-05 21:33:34.043118

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "9ec54cec5c1d"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "call_sessions",
        sa.Column("call_id", sa.Uuid(), primary_key=True),
        sa.Column("provider_call_id", sa.Text(), nullable=True),
        sa.Column("started_at", sa.BigInteger(), nullable=False),
        sa.Column("ended_at", sa.BigInteger(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("locale_hint", sa.Text(), nullable=True),
        sa.Column("customer_context", sa.JSON(), nullable=True),
    )
    op.create_index("ix_call_sessions_status", "call_sessions", ["status"])

    op.create_table(
        "turns",
        sa.Column("turn_id", sa.Uuid(), primary_key=True),
        sa.Column(
            "call_id",
            sa.Uuid(),
            sa.ForeignKey("call_sessions.call_id"),
            nullable=False,
        ),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.BigInteger(), nullable=False),
        sa.Column("finalized_at", sa.BigInteger(), nullable=True),
        sa.Column("text_final", sa.Text(), nullable=True),
        sa.Column("language", sa.Text(), nullable=True),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("cancel_reason", sa.Text(), nullable=True),
        sa.Column("asr_confidence", sa.Float(), nullable=True),
    )
    op.create_index("ix_turns_call_id_seq", "turns", ["call_id", "seq"])

    op.create_table(
        "agent_generations",
        sa.Column("agent_generation_id", sa.Uuid(), primary_key=True),
        sa.Column(
            "call_id",
            sa.Uuid(),
            sa.ForeignKey("call_sessions.call_id"),
            nullable=False,
        ),
        sa.Column(
            "turn_id", sa.Uuid(), sa.ForeignKey("turns.turn_id"), nullable=False
        ),
        sa.Column("created_at", sa.BigInteger(), nullable=False),
        sa.Column("started_at", sa.BigInteger(), nullable=True),
        sa.Column("ended_at", sa.BigInteger(), nullable=True),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("route_a_label", sa.Text(), nullable=True),
        sa.Column("route_a_confidence", sa.Float(), nullable=True),
        sa.Column("policy_key", sa.Text(), nullable=True),
        sa.Column("specialist", sa.Text(), nullable=True),
        sa.Column("final_outcome", sa.Text(), nullable=True),
        sa.Column("cancel_reason", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_agent_generations_turn_id", "agent_generations", ["turn_id"]
    )

    op.create_table(
        "voice_generations",
        sa.Column("voice_generation_id", sa.Uuid(), primary_key=True),
        sa.Column("provider_voice_generation_id", sa.Text(), nullable=True),
        sa.Column(
            "call_id",
            sa.Uuid(),
            sa.ForeignKey("call_sessions.call_id"),
            nullable=False,
        ),
        sa.Column(
            "agent_generation_id",
            sa.Uuid(),
            sa.ForeignKey("agent_generations.agent_generation_id"),
            nullable=False,
        ),
        sa.Column(
            "turn_id", sa.Uuid(), sa.ForeignKey("turns.turn_id"), nullable=False
        ),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("started_at", sa.BigInteger(), nullable=True),
        sa.Column("ended_at", sa.BigInteger(), nullable=True),
        sa.Column("cancel_reason", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_voice_generations_agent_generation_id",
        "voice_generations",
        ["agent_generation_id"],
    )

    op.create_table(
        "tool_executions",
        sa.Column("tool_request_id", sa.Uuid(), primary_key=True),
        sa.Column(
            "call_id",
            sa.Uuid(),
            sa.ForeignKey("call_sessions.call_id"),
            nullable=False,
        ),
        sa.Column(
            "agent_generation_id",
            sa.Uuid(),
            sa.ForeignKey("agent_generations.agent_generation_id"),
            nullable=False,
        ),
        sa.Column(
            "turn_id", sa.Uuid(), sa.ForeignKey("turns.turn_id"), nullable=False
        ),
        sa.Column("tool_name", sa.Text(), nullable=False),
        sa.Column("args_hash", sa.Text(), nullable=False),
        sa.Column("args_json", sa.JSON(), nullable=True),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("started_at", sa.BigInteger(), nullable=True),
        sa.Column("ended_at", sa.BigInteger(), nullable=True),
        sa.Column("result_json", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_tool_executions_agent_generation_id",
        "tool_executions",
        ["agent_generation_id"],
    )


def downgrade() -> None:
    op.drop_table("tool_executions")
    op.drop_table("voice_generations")
    op.drop_table("agent_generations")
    op.drop_table("turns")
    op.drop_table("call_sessions")
