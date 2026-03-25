"""Session repository for managing active call sessions in a process."""

from __future__ import annotations

import asyncio
import os
import signal
from typing import TYPE_CHECKING, Any, Callable, Coroutine
from uuid import UUID

import structlog

from src.infrastructure.session_models import (
    ConcurrencyLimitExceeded,
    DuplicateSessionError,
    LifecycleHookRegistry,
    SessionMetadata,
)

if TYPE_CHECKING:
    from src.api.routes.calls import CallSessionEntry

logger = structlog.get_logger()


class SessionRepository:
    """Manages the lifecycle of all active call sessions in a process.
    
    Provides:
    - CRUD operations for sessions (create, get, remove, list, count)
    - Concurrency limit enforcement (configurable max_sessions_per_process)
    - Lifecycle hooks (session_created, session_ended, session_error)
    - Redis secondary index integration
    - Graceful shutdown orchestration
    - call_id isolation guarantees
    
    Single instance per process (acts as singleton or injected dependency).
    """

    def __init__(
        self,
        max_sessions_per_process: int = 50,
        redis_registry: Any = None,  # Optional RedisSessionRegistry
        shutdown_timeout: int = 10,
    ) -> None:
        """Initialize SessionRepository.
        
        Args:
            max_sessions_per_process: Maximum concurrent sessions allowed (default 50)
            redis_registry: Optional RedisSessionRegistry for secondary indexing
            shutdown_timeout: Graceful shutdown timeout in seconds (default 10)
        """
        self._max_sessions = max_sessions_per_process
        self._redis_registry = redis_registry
        self._shutdown_timeout = shutdown_timeout
        
        # In-memory session registry: call_id -> CallSessionEntry
        self._sessions: dict[UUID, "CallSessionEntry"] = {}
        
        # Track graceful drain state
        self._sessions_draining: set[UUID] = set()
        self._shutdown_event: asyncio.Event | None = None
        
        # Lifecycle hooks
        self._hooks = LifecycleHookRegistry()
        
        # Process ID for Redis registration
        self._process_id = str(os.getpid())
        
        # Call_id mismatch observability counter
        self._call_id_mismatch_count = 0

    # ====================================================================
    # CRUD Operations
    # ====================================================================
    async def create_session(
        self, call_id: UUID, voice_client_type: str, session_entry: "CallSessionEntry"
    ) -> "CallSessionEntry":
        """Create and register a new session.
        
        Args:
            call_id: Unique identifier for this call
            voice_client_type: Type of voice client (e.g., 'webrtc', 'websocket')
            session_entry: Pre-built CallSessionEntry with all runtime actors
            
        Returns:
            The registered CallSessionEntry
            
        Raises:
            DuplicateSessionError: If call_id already exists
            ConcurrencyLimitExceeded: If max_sessions_per_process limit reached
        """
        # Check for duplicates
        if call_id in self._sessions:
            logger.warning("duplicate_session_create_attempt", call_id=str(call_id))
            raise DuplicateSessionError(call_id)
        
        # Check concurrency limit
        if len(self._sessions) >= self._max_sessions:
            logger.warning(
                "concurrency_limit_exceeded",
                current_count=len(self._sessions),
                max_allowed=self._max_sessions,
            )
            raise ConcurrencyLimitExceeded(len(self._sessions), self._max_sessions)
        
        # Register in-memory
        self._sessions[call_id] = session_entry
        logger.info("session_created_in_memory", call_id=str(call_id))
        
        # Register in Redis (if available)
        if self._redis_registry:
            try:
                import time
                metadata = {
                    "call_id": str(call_id),
                    "voice_client_type": voice_client_type,
                    "process_id": self._process_id,
                    "created_at": int(time.time() * 1000),
                }
                await self._redis_registry.register(call_id, metadata)
                logger.info("session_registered_in_redis", call_id=str(call_id))
            except Exception as e:
                logger.warning(
                    "redis_registration_failed",
                    call_id=str(call_id),
                    error=str(e),
                )
                # Continue: Redis unavailability doesn't block session creation
        
        # Fire lifecycle hook
        metadata_dict = {
            "call_id": str(call_id),
            "voice_client_type": voice_client_type,
            "process_id": self._process_id,
        }
        await self._hooks.fire("session_created", call_id, metadata_dict)
        
        return session_entry

    def get_session(self, call_id: UUID) -> "CallSessionEntry" | None:
        """Retrieve an active session by call_id.
        
        Args:
            call_id: The call identifier
            
        Returns:
            CallSessionEntry if found, None otherwise
        """
        return self._sessions.get(call_id)

    async def remove_session(self, call_id: UUID) -> None:
        """Remove a session and deregister it.
        
        Args:
            call_id: The call identifier
        """
        if call_id not in self._sessions:
            logger.debug("remove_nonexistent_session", call_id=str(call_id))
            return
        
        # Remove from memory
        session = self._sessions.pop(call_id, None)
        
        # Deregister from Redis
        if self._redis_registry and session:
            try:
                await self._redis_registry.remove(call_id)
                logger.info("session_deregistered_from_redis", call_id=str(call_id))
            except Exception as e:
                logger.warning(
                    "redis_deregistration_failed",
                    call_id=str(call_id),
                    error=str(e),
                )
        
        logger.info("session_removed", call_id=str(call_id))
        
        # Fire lifecycle hook
        metadata_dict = {"call_id": str(call_id)}
        await self._hooks.fire("session_ended", call_id, metadata_dict)

    def list_sessions(self) -> list["CallSessionEntry"]:
        """List all active sessions.
        
        Returns:
            List of CallSessionEntry objects for all active sessions
        """
        return list(self._sessions.values())

    def session_count(self) -> int:
        """Get the number of active sessions.
        
        Returns:
            Current session count
        """
        return len(self._sessions)

    # ====================================================================
    # Lifecycle Hooks
    # ====================================================================

    def register_hook(
        self, event: str, callback: Callable[[UUID, dict[str, Any]], Coroutine[Any, Any, None]]
    ) -> None:
        """Register a callback for a lifecycle event.
        
        Args:
            event: One of 'session_created', 'session_ended', 'session_error'
            callback: async callable(call_id: UUID, metadata: dict[str, Any]) -> None
        """
        self._hooks.register(event, callback)

    def unregister_hook(
        self, event: str, callback: Callable[[UUID, dict[str, Any]], Coroutine[Any, Any, None]]
    ) -> None:
        """Unregister a lifecycle callback."""
        self._hooks.unregister(event, callback)

    # ====================================================================
    # call_id Isolation & Observability
    # ====================================================================

    def get_call_id_mismatch_count(self) -> int:
        """Get observability counter for call_id mismatch events."""
        return self._call_id_mismatch_count

    def increment_call_id_mismatch(self) -> None:
        """Increment call_id mismatch counter (called by Coordinator)."""
        self._call_id_mismatch_count += 1

    # ====================================================================
    # Graceful Shutdown
    # ====================================================================

    async def shutdown(self) -> None:
        """Gracefully shut down all sessions.
        
        Steps:
        1. Send termination signal to all coordinators
        2. Wait up to shutdown_timeout for graceful drain
        3. Force-close any remaining sessions
        4. Log final state
        """
        logger.info("session_repository_shutdown_started")
        
        if not self._sessions:
            logger.info("session_repository_shutdown_complete_no_sessions")
            return
        
        # Mark all sessions as draining
        self._sessions_draining = set(self._sessions.keys())
        self._shutdown_event = asyncio.Event()
        
        # Send termination event to all coordinators
        drain_timeout = self._shutdown_timeout
        start_time = asyncio.get_event_loop().time()
        
        for call_id, session in list(self._sessions.items()):
            try:
                # Emit termination signal to coordinator
                coordinator = session.coordinator
                logger.info("sending_termination_signal", call_id=str(call_id))
                
                # Create and emit a termination event
                # (Coordinator will finalize and allow graceful cleanup)
                # This is a simple signal; actual implementation depends on
                # how Coordinator processes termination events
                if hasattr(coordinator, "on_shutdown"):
                    await coordinator.on_shutdown()
                
            except Exception as e:
                logger.error(
                    "termination_signal_error",
                    call_id=str(call_id),
                    error=str(e),
                )
        
        # Wait for graceful drain with timeout
        try:
            while self._sessions_draining and (
                asyncio.get_event_loop().time() - start_time < drain_timeout
            ):
                await asyncio.sleep(0.1)
        except asyncio.TimeoutError:
            logger.warning("graceful_shutdown_timeout")
        
        # Force-close remaining sessions
        remaining = list(self._sessions.keys())
        for call_id in remaining:
            logger.info("force_closing_session", call_id=str(call_id))
            await self.remove_session(call_id)
        
        self._sessions_draining.clear()
        logger.info("session_repository_shutdown_complete", sessions_closed=len(remaining))

    # ====================================================================
    # Utility
    # ====================================================================

    def get_process_id(self) -> str:
        """Return the process ID."""
        return self._process_id
