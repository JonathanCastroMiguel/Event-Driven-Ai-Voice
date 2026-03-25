"""add_client_type_to_call_sessions

Revision ID: b4f3e2d1a5c8
Revises: 9ec54cec5c1d
Create Date: 2026-03-23 14:30:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b4f3e2d1a5c8"
down_revision: Union[str, None] = "9ec54cec5c1d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add client_type column to call_sessions table.
    
    The column is added with:
    - Type: VARCHAR (stores enum value as string, e.g., "browser_webrtc")
    - Nullable: False (required field)
    - Server default: "browser_webrtc" (for backward compatibility with existing rows)
    - Index: Not needed initially (can add later if analytics queries require it)
    """
    op.add_column(
        "call_sessions",
        sa.Column(
            "client_type",
            sa.VARCHAR(),
            nullable=False,
            server_default="browser_webrtc"
        )
    )


def downgrade() -> None:
    """Remove client_type column from call_sessions table."""
    op.drop_column("call_sessions", "client_type")
