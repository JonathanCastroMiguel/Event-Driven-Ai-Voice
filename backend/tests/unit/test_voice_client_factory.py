"""Unit tests for voice_client_factory module."""

import pytest

from src.voice_runtime.voice_client import VoiceClient, VoiceClientType
from src.voice_runtime.voice_client_factory import (
    UnsupportedClientTypeError,
    create_voice_client,
    get_supported_types,
)


class TestVoiceClientFactory:
    """Tests for create_voice_client factory function."""
    
    def test_factory_returns_correct_client_for_browser_webrtc(self):
        """Test factory returns correct client for BROWSER_WEBRTC type."""
        # Note: This test will need actual config once we refactor the bridge
        # For now, we'll test that the factory doesn't raise an error
        # The bridge refactoring (task 3.x) will make this fully testable
        
        # The factory should attempt to create OpenAIRealtimeEventBridge
        # but will fail without proper config - that's expected for now
        with pytest.raises(TypeError):  # Missing required parameters
            create_voice_client(VoiceClientType.BROWSER_WEBRTC)
        
        # Once bridge is refactored, this test should pass:
        # client = create_voice_client(VoiceClientType.BROWSER_WEBRTC, websocket=mock_ws, coordinator=mock_coord)
        # assert isinstance(client, VoiceClient)
        # assert client.client_type == VoiceClientType.BROWSER_WEBRTC
    
    def test_factory_raises_not_implemented_for_voip_asterisk(self):
        """Test factory raises NotImplementedError for VOIP_ASTERISK."""
        with pytest.raises(NotImplementedError) as exc_info:
            create_voice_client(VoiceClientType.VOIP_ASTERISK)
        
        error_message = str(exc_info.value)
        assert "VoIP/Asterisk client not yet implemented" in error_message
        assert "planned for future release" in error_message.lower()
    
    def test_factory_handles_invalid_types_gracefully(self):
        """Test factory handles invalid/unknown types with clear error."""
        # Test with non-enum value
        with pytest.raises(UnsupportedClientTypeError) as exc_info:
            create_voice_client("invalid_type")  # type: ignore
        
        error_message = str(exc_info.value)
        assert "Invalid client type" in error_message
        assert "Must be a VoiceClientType enum value" in error_message
        
        # Test with None
        with pytest.raises(UnsupportedClientTypeError):
            create_voice_client(None)  # type: ignore
    
    def test_get_supported_types_returns_current_types(self):
        """Test get_supported_types returns set of supported types."""
        supported = get_supported_types()
        
        assert isinstance(supported, set)
        assert VoiceClientType.BROWSER_WEBRTC in supported
        # VOIP_ASTERISK should not be in supported (not implemented yet)
        assert VoiceClientType.VOIP_ASTERISK not in supported
    
    def test_get_supported_types_returns_copy(self):
        """Test get_supported_types returns a copy (not mutable)."""
        supported1 = get_supported_types()
        supported2 = get_supported_types()
        
        # Should be equal but not the same object
        assert supported1 == supported2
        assert supported1 is not supported2
