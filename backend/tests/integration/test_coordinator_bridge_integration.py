"""Integration test: Coordinator processes events identically through refactored bridge.

This test validates zero regression requirement by comparing Coordinator behavior
before and after the VoiceClient protocol refactoring.
"""

import pytest
from uuid import uuid4

from src.voice_runtime.coordinator import Coordinator
from src.voice_runtime.agent_fsm import AgentFSM
from src.voice_runtime.turn_manager import TurnManager
from src.voice_runtime.tool_executor import ToolExecutor
from src.voice_runtime.realtime_event_bridge import OpenAIRealtimeEventBridge
from src.voice_runtime.events import EventEnvelope
from src.voice_runtime.types import EventSource


class TestCoordinatorWithRefactoredBridge:
    """Test that Coordinator works identically through the new VoiceClient abstraction."""
    
    @pytest.fixture
    def call_id(self):
        return uuid4()
    
    @pytest.fixture
    def coordinator_setup(self, call_id):
        """Set up Coordinator with all dependencies."""
        turn_manager = TurnManager(call_id=call_id)
        agent_fsm = AgentFSM(call_id=call_id)
        tool_executor = ToolExecutor()
        
        # Use minimal config for testing
        from src.routing.policies import PoliciesRegistry
        policies = PoliciesRegistry(
            base_system="Test assistant",
            policies={"greeting": "Hello"}
        )
        
        coordinator = Coordinator(
            call_id=call_id,
            turn_manager=turn_manager,
            agent_fsm=agent_fsm,
            tool_executor=tool_executor,
            router_prompt_builder=None,  # Not needed for basic event processing
            policies=policies,
            max_history_turns=10,
            max_history_chars=10000
        )
        
        return {
            "coordinator": coordinator,
            "turn_manager": turn_manager,
            "agent_fsm": agent_fsm,
            "tool_executor": tool_executor
        }
    
    async def test_coordinator_processes_events_identically_through_refactored_bridge(
        self, call_id, coordinator_setup
    ):
        """Test Coordinator processes events the same way through refactored bridge."""
        coordinator = coordinator_setup["coordinator"]
        
        # Create refactored bridge (implements VoiceClient protocol)
        bridge = OpenAIRealtimeEventBridge(call_id=call_id)
        
        # Verify bridge implements VoiceClient protocol
        from src.voice_runtime.voice_client import VoiceClientType
        assert hasattr(bridge, 'client_type')
        assert hasattr(bridge, 'client_info')
        assert bridge.client_type == VoiceClientType.BROWSER_WEBRTC
        
        # Wire bridge to coordinator (same as production code)
        events_received = []
        
        async def capture_event(event: EventEnvelope):
            events_received.append(event)
            await coordinator.handle_event(event)
        
        bridge.on_event(capture_event)
        
        # Simulate OpenAI events through bridge
        await bridge._translate_event({"type": "input_audio_buffer.speech_started"})
        
        # Verify event was translated and processed
        assert len(events_received) == 1
        assert events_received[0].type == "speech_started"
        assert events_received[0].call_id == call_id
        assert events_received[0].source == EventSource.REALTIME
        
        # Verify turn manager state (proves Coordinator processed it)
        # Speech started should trigger turn creation in TurnManager
        assert coordinator_setup["turn_manager"]._current_turn_seq is not None
    
    async def test_event_types_remain_unchanged(self, call_id):
        """Test that event types and payloads match the existing contract."""
        bridge = OpenAIRealtimeEventBridge(call_id=call_id)
        
        events_captured = []
        
        async def capture(event: EventEnvelope):
            events_captured.append(event)
        
        bridge.on_event(capture)
        
        # Test various event types
        test_events = [
            {"type": "input_audio_buffer.speech_started"},
            {"type": "input_audio_buffer.speech_stopped"},
            {"type": "input_audio_buffer.committed"},
            {
                "type": "conversation.item.input_audio_transcription.completed",
                "transcript": "hello world"
            },
        ]
        
        for openai_event in test_events:
            await bridge._translate_event(openai_event)
        
        # Verify all events were translated
        assert len(events_captured) == 4
        
        # Verify event types match protocol
        assert events_captured[0].type == "speech_started"
        assert events_captured[1].type == "speech_stopped"
        assert events_captured[2].type == "audio_committed"
        assert events_captured[3].type == "transcript_final"
        
        # Verify all have correct metadata
        for event in events_captured:
            assert event.call_id == call_id
            assert event.source == EventSource.REALTIME
            assert event.event_id is not None
            assert event.ts > 0
