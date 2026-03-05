from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Awaitable, Callable
from uuid import UUID, uuid5

import orjson
import structlog

from src.infrastructure.redis_client import TTLMap
from src.voice_runtime.events import ToolResult

logger = structlog.get_logger()

# Namespace UUID for deterministic tool_request_id generation
TOOL_NAMESPACE = UUID("b6e7f8d9-1234-5678-9abc-def012345678")

type ToolFunc = Callable[..., Awaitable[dict[str, object]]]


def compute_tool_request_id(agent_generation_id: UUID, tool_name: str, args: dict[str, object]) -> UUID:
    """Deterministic tool_request_id from generation_id + tool_name + args hash."""
    args_bytes = orjson.dumps(args, option=orjson.OPT_SORT_KEYS)
    args_hash = hashlib.sha256(args_bytes).hexdigest()
    key = f"{agent_generation_id}:{tool_name}:{args_hash}"
    return uuid5(TOOL_NAMESPACE, key)


class ToolExecutor:
    """Executes tools with timeout, cancellation, caching, and whitelist validation."""

    def __init__(
        self,
        tool_cache: TTLMap | None = None,
    ) -> None:
        self._tools: dict[str, ToolFunc] = {}
        self._cache = tool_cache
        self._running_tasks: dict[UUID, asyncio.Task[dict[str, object]]] = {}

    def register_tool(self, name: str, func: ToolFunc) -> None:
        self._tools[name] = func

    @property
    def registered_tools(self) -> set[str]:
        return set(self._tools.keys())

    async def execute(
        self,
        call_id: UUID,
        agent_generation_id: UUID,
        tool_request_id: UUID,
        tool_name: str,
        args: dict[str, object],
        timeout_ms: int,
    ) -> ToolResult:
        """Execute a tool with whitelist validation, caching, and timeout."""

        # Whitelist check
        if tool_name not in self._tools:
            logger.warning("unknown_tool_rejected", tool_name=tool_name)
            return ToolResult(
                call_id=call_id,
                agent_generation_id=agent_generation_id,
                tool_request_id=tool_request_id,
                ok=False,
                payload={"error": "unknown_tool"},
                ts=_now_ms(),
            )

        # Cache check
        if self._cache is not None:
            cached = await self._cache.get(str(tool_request_id))
            if cached is not None:
                logger.info("tool_cache_hit", tool_request_id=str(tool_request_id))
                return ToolResult(
                    call_id=call_id,
                    agent_generation_id=agent_generation_id,
                    tool_request_id=tool_request_id,
                    ok=True,
                    payload=orjson.loads(cached),
                    ts=_now_ms(),
                )

        # Execute with timeout
        tool_func = self._tools[tool_name]
        try:
            task = asyncio.create_task(tool_func(**args))
            self._running_tasks[tool_request_id] = task
            timeout_s = timeout_ms / 1000.0
            result_payload = await asyncio.wait_for(task, timeout=timeout_s)

            # Cache on success
            if self._cache is not None:
                await self._cache.set(
                    str(tool_request_id), orjson.dumps(result_payload).decode()
                )

            return ToolResult(
                call_id=call_id,
                agent_generation_id=agent_generation_id,
                tool_request_id=tool_request_id,
                ok=True,
                payload=result_payload,
                ts=_now_ms(),
            )
        except asyncio.TimeoutError:
            logger.warning("tool_timeout", tool_name=tool_name, timeout_ms=timeout_ms)
            return ToolResult(
                call_id=call_id,
                agent_generation_id=agent_generation_id,
                tool_request_id=tool_request_id,
                ok=False,
                payload={"error": "timeout"},
                ts=_now_ms(),
            )
        except asyncio.CancelledError:
            logger.info("tool_cancelled", tool_name=tool_name)
            return ToolResult(
                call_id=call_id,
                agent_generation_id=agent_generation_id,
                tool_request_id=tool_request_id,
                ok=False,
                payload={"error": "cancelled"},
                ts=_now_ms(),
            )
        except Exception as exc:
            logger.exception("tool_execution_error", tool_name=tool_name)
            return ToolResult(
                call_id=call_id,
                agent_generation_id=agent_generation_id,
                tool_request_id=tool_request_id,
                ok=False,
                payload={"error": str(exc)},
                ts=_now_ms(),
            )
        finally:
            self._running_tasks.pop(tool_request_id, None)

    def cancel(self, tool_request_id: UUID) -> bool:
        """Cancel a running tool. Returns True if cancellation was initiated."""
        task = self._running_tasks.get(tool_request_id)
        if task is not None and not task.done():
            task.cancel()
            return True
        return False


def _now_ms() -> int:
    import time
    return int(time.monotonic() * 1000)
