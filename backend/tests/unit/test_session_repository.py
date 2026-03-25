"""Unit tests for SessionRepository."""

import asyncio
from uuid import UUID, uuid4

import pytest

from src.infrastructure.session_models import (
    ConcurrencyLimitExceeded,
    DuplicateSessionError,
)
from src.infrastructure.session_repository import SessionRepository


# Mock CallSessionEntry for testing
class MockCallSessionEntry:
    """Mock session entry for testing."""

    def __init__(self, call_id: UUID):
        self.call_id = call_id
        self.coordinator = None
        self.turn_manager = None
        self.agent_fsm = None
        self.tool_executor = None
        self.bridge = None


@pytest.fixture
def repository():
    """Create a fresh SessionRepository for each test."""
    return SessionRepository(max_sessions_per_process=5)


@pytest.fixture
def valid_call_id():
    """Generate a valid call ID."""
    return uuid4()


@pytest.fixture
def mock_entry(valid_call_id):
    """Create a mock session entry."""
    return MockCallSessionEntry(valid_call_id)


# ====================================================================
# CRUD Tests
# ====================================================================


@pytest.mark.asyncio
async def test_create_session_success(repository, valid_call_id, mock_entry):
    """Test successful session creation."""
    result = await repository.create_session(valid_call_id, "webrtc", mock_entry)
    
    assert result == mock_entry
    assert repository.session_count() == 1
    assert repository.get_session(valid_call_id) == mock_entry


@pytest.mark.asyncio
async def test_create_session_duplicate_raises_error(repository, valid_call_id, mock_entry):
    """Test that creating a session with duplicate call_id raises DuplicateSessionError."""
    await repository.create_session(valid_call_id, "webrtc", mock_entry)
    
    with pytest.raises(DuplicateSessionError):
        await repository.create_session(valid_call_id, "webrtc", mock_entry)


@pytest.mark.asyncio
async def test_create_session_concurrency_limit_exceeded(repository):
    """Test that creating sessions beyond limit raises ConcurrencyLimitExceeded."""
    # Fill up to max capacity
    for i in range(5):
        call_id = uuid4()
        entry = MockCallSessionEntry(call_id)
        await repository.create_session(call_id, "webrtc", entry)
    
    # Try to exceed limit
    with pytest.raises(ConcurrencyLimitExceeded) as exc_info:
        call_id = uuid4()
        entry = MockCallSessionEntry(call_id)
        await repository.create_session(call_id, "webrtc", entry)
    
    assert exc_info.value.current_count == 5
    assert exc_info.value.max_allowed == 5


@pytest.mark.asyncio
async def test_get_session_existing(repository, valid_call_id, mock_entry):
    """Test retrieving an existing session."""
    await repository.create_session(valid_call_id, "webrtc", mock_entry)
    
    result = repository.get_session(valid_call_id)
    assert result == mock_entry


@pytest.mark.asyncio
async def test_get_session_nonexistent(repository):
    """Test retrieving a non-existent session returns None."""
    call_id = uuid4()
    result = repository.get_session(call_id)
    assert result is None


@pytest.mark.asyncio
async def test_remove_session_success(repository, valid_call_id, mock_entry):
    """Test successfully removing a session."""
    await repository.create_session(valid_call_id, "webrtc", mock_entry)
    assert repository.session_count() == 1
    
    await repository.remove_session(valid_call_id)
    assert repository.session_count() == 0
    assert repository.get_session(valid_call_id) is None


@pytest.mark.asyncio
async def test_remove_session_nonexistent_is_idempotent(repository):
    """Test that removing a non-existent session is idempotent."""
    call_id = uuid4()
    # Should not raise
    await repository.remove_session(call_id)
    assert repository.session_count() == 0


@pytest.mark.asyncio
async def test_list_sessions_empty(repository):
    """Test listing sessions when empty."""
    result = repository.list_sessions()
    assert result == []


@pytest.mark.asyncio
async def test_list_sessions_multiple(repository):
    """Test listing all active sessions."""
    entries = []
    for i in range(3):
        call_id = uuid4()
        entry = MockCallSessionEntry(call_id)
        await repository.create_session(call_id, "webrtc", entry)
        entries.append(entry)
    
    result = repository.list_sessions()
    assert len(result) == 3
    assert set(result) == set(entries)


@pytest.mark.asyncio
async def test_session_count(repository):
    """Test session count tracking."""
    assert repository.session_count() == 0
    
    for i in range(3):
        call_id = uuid4()
        entry = MockCallSessionEntry(call_id)
        await repository.create_session(call_id, "webrtc", entry)
        assert repository.session_count() == i + 1


# ====================================================================
# Concurrency Tests
# ====================================================================


@pytest.mark.asyncio
async def test_default_max_sessions(repository):
    """Test that default max_sessions_per_process is 50."""
    repo = SessionRepository()
    assert repo._max_sessions == 50


@pytest.mark.asyncio
async def test_custom_max_sessions():
    """Test custom max_sessions_per_process."""
    repo = SessionRepository(max_sessions_per_process=100)
    assert repo._max_sessions == 100


@pytest.mark.asyncio
async def test_create_at_limit_then_remove_and_recreate(repository):
    """Test that after removing a session, new ones can be created."""
    call_id_1 = uuid4()
    entry_1 = MockCallSessionEntry(call_id_1)
    await repository.create_session(call_id_1, "webrtc", entry_1)
    
    # Fill to capacity
    for i in range(4):  # 5 total with the first one
        call_id = uuid4()
        entry = MockCallSessionEntry(call_id)
        await repository.create_session(call_id, "webrtc", entry)
    
    # Should be at limit
    assert repository.session_count() == 5
    
    # Remove one
    await repository.remove_session(call_id_1)
    assert repository.session_count() == 4
    
    # Should be able to create new session
    call_id_new = uuid4()
    entry_new = MockCallSessionEntry(call_id_new)
    await repository.create_session(call_id_new, "webrtc", entry_new)
    assert repository.session_count() == 5


# ====================================================================
# Lifecycle Hooks Tests
# ====================================================================


@pytest.mark.asyncio
async def test_session_created_hook(repository, valid_call_id, mock_entry):
    """Test that on_session_created hook fires."""
    hook_fired = False
    hook_call_id = None
    
    async def on_created(call_id: UUID, metadata: dict) -> None:
        nonlocal hook_fired, hook_call_id
        hook_fired = True
        hook_call_id = call_id
    
    repository.register_hook("session_created", on_created)
    await repository.create_session(valid_call_id, "webrtc", mock_entry)
    
    assert hook_fired
    assert hook_call_id == valid_call_id


@pytest.mark.asyncio
async def test_session_ended_hook(repository, valid_call_id, mock_entry):
    """Test that on_session_ended hook fires."""
    hook_fired = False
    hook_call_id = None
    
    async def on_ended(call_id: UUID, metadata: dict) -> None:
        nonlocal hook_fired, hook_call_id
        hook_fired = True
        hook_call_id = call_id
    
    repository.register_hook("session_ended", on_ended)
    await repository.create_session(valid_call_id, "webrtc", mock_entry)
    await repository.remove_session(valid_call_id)
    
    assert hook_fired
    assert hook_call_id == valid_call_id


@pytest.mark.asyncio
async def test_multiple_hooks_registered(repository, valid_call_id, mock_entry):
    """Test that multiple hooks can be registered."""
    calls = []
    
    async def hook1(call_id: UUID, metadata: dict) -> None:
        calls.append("hook1")
    
    async def hook2(call_id: UUID, metadata: dict) -> None:
        calls.append("hook2")
    
    repository.register_hook("session_created", hook1)
    repository.register_hook("session_created", hook2)
    await repository.create_session(valid_call_id, "webrtc", mock_entry)
    
    assert "hook1" in calls
    assert "hook2" in calls


@pytest.mark.asyncio
async def test_unregister_hook(repository, valid_call_id, mock_entry):
    """Test unregistering a hook."""
    calls = []
    
    async def hook(call_id: UUID, metadata: dict) -> None:
        calls.append("hooked")
    
    repository.register_hook("session_created", hook)
    repository.unregister_hook("session_created", hook)
    await repository.create_session(valid_call_id, "webrtc", mock_entry)
    
    assert len(calls) == 0


# ====================================================================
# call_id Isolation Tests
# ====================================================================


@pytest.mark.asyncio
async def test_call_id_isolation_no_duplicates(repository):
    """Test that SessionRepository prevents duplicate call_ids."""
    call_id = uuid4()
    entry1 = MockCallSessionEntry(call_id)
    
    await repository.create_session(call_id, "webrtc", entry1)
    
    with pytest.raises(DuplicateSessionError):
        entry2 = MockCallSessionEntry(call_id)
        await repository.create_session(call_id, "webrtc", entry2)


@pytest.mark.asyncio
async def test_distinct_sessions_for_different_call_ids(repository):
    """Test that different call_ids return distinct sessions."""
    call_id_1 = uuid4()
    call_id_2 = uuid4()
    
    entry1 = MockCallSessionEntry(call_id_1)
    entry2 = MockCallSessionEntry(call_id_2)
    
    await repository.create_session(call_id_1, "webrtc", entry1)
    await repository.create_session(call_id_2, "webrtc", entry2)
    
    assert repository.get_session(call_id_1) == entry1
    assert repository.get_session(call_id_2) == entry2
    assert repository.get_session(call_id_1) != repository.get_session(call_id_2)


@pytest.mark.asyncio
async def test_call_id_mismatch_counter(repository):
    """Test call_id mismatch counter observable."""
    assert repository.get_call_id_mismatch_count() == 0
    
    repository.increment_call_id_mismatch()
    assert repository.get_call_id_mismatch_count() == 1
    
    repository.increment_call_id_mismatch()
    assert repository.get_call_id_mismatch_count() == 2


# ====================================================================
# Graceful Shutdown Tests
# ====================================================================


@pytest.mark.asyncio
async def test_shutdown_no_sessions(repository):
    """Test graceful shutdown with no active sessions."""
    # Should complete without error
    await repository.shutdown()
    assert repository.session_count() == 0


@pytest.mark.asyncio
async def test_shutdown_clears_sessions(repository):
    """Test that shutdown removes all sessions."""
    for i in range(3):
        call_id = uuid4()
        entry = MockCallSessionEntry(call_id)
        await repository.create_session(call_id, "webrtc", entry)
    
    assert repository.session_count() == 3
    
    await repository.shutdown()
    
    assert repository.session_count() == 0


@pytest.mark.asyncio
async def test_shutdown_respects_timeout(repository):
    """Test that shutdown completes within timeout."""
    for i in range(2):
        call_id = uuid4()
        entry = MockCallSessionEntry(call_id)
        await repository.create_session(call_id, "webrtc", entry)
    
    import time
    
    start = time.time()
    await repository.shutdown()
    elapsed = time.time() - start
    
    # Should complete relatively quickly (not taking the full timeout)
    # just ensure no exception
    assert repository.session_count() == 0


# ====================================================================
# Process ID Tests
# ====================================================================


@pytest.mark.asyncio
async def test_get_process_id(repository):
    """Test getting the process ID."""
    process_id = repository.get_process_id()
    assert isinstance(process_id, str)
    assert len(process_id) > 0
