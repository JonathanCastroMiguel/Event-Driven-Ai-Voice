"""Session management models and exceptions for the voice runtime."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from uuid import UUID

if TYPE_CHECKING:
    from src.api.routes.calls import CallSessionEntry


class SessionError(Exception):
    """Base exception for session management errors."""

    pass


class DuplicateSessionError(SessionError):
    """Raised when attempting to create a session with a duplicate call_id."""

    def __init__(self, call_id: UUID) -> None:
        self.call_id = call_id
        super().__init__(f"Session with call_id {call_id} already exists")


class ConcurrencyLimitExceeded(SessionError):
    """Raised when max_sessions_per_process limit is exceeded."""

    def __init__(self, current_count: int, max_allowed: int) -> None:
        self.current_count = current_count
        self.max_allowed = max_allowed
        super().__init__(
            f"Concurrency limit exceeded: {current_count}/{max_allowed} sessions active"
        )


@dataclass
class SessionMetadata:
    """Metadata about a session for Redis registration and observability."""

    call_id: UUID
    voice_client_type: str
    process_id: str
    created_at: int  # ms epoch
    last_activity: int | None = None


class LifecycleHookRegistry:
    """Manages lifecycle callbacks for session events."""

    def __init__(self) -> None:
        self._hooks: dict[str, list[Any]] = {
            "session_created": [],
            "session_ended": [],
            "session_error": [],
        }

    def register(self, event: str, callback: Any) -> None:
        """Register a callback for a lifecycle event.
        
        Args:
            event: One of 'session_created', 'session_ended', 'session_error'
            callback: async callable that receives (call_id: UUID, metadata: dict)
        """
        if event not in self._hooks:
            raise ValueError(f"Unknown lifecycle event: {event}")
        self._hooks[event].append(callback)

    def unregister(self, event: str, callback: Any) -> None:
        """Unregister a callback."""
        if event in self._hooks and callback in self._hooks[event]:
            self._hooks[event].remove(callback)

    def get_callbacks(self, event: str) -> list[Any]:
        """Get all callbacks for an event."""
        return self._hooks.get(event, [])

    async def fire(self, event: str, call_id: UUID, metadata: dict[str, Any]) -> None:
        """Fire all callbacks for an event (non-blocking)."""
        callbacks = self.get_callbacks(event)
        for callback in callbacks:
            try:
                if callable(callback):
                    import inspect

                    if inspect.iscoroutinefunction(callback):
                        await callback(call_id=call_id, metadata=metadata)
                    else:
                        callback(call_id=call_id, metadata=metadata)
            except Exception as e:
                # Log but don't raise; hook failures shouldn't block session ops
                import structlog

                logger = structlog.get_logger()
                logger.error(
                    "lifecycle_hook_error",
                    event=event,
                    call_id=str(call_id),
                    error=str(e),
                )
