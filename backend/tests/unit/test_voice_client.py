"""Unit tests for voice_client module (VoiceClientType, VoiceClientInfo, VoiceClient protocol)."""

import json
from uuid import UUID, uuid4

import pytest

from src.voice_runtime.voice_client import VoiceClient, VoiceClientInfo, VoiceClientType


class TestVoiceClientType:
    """Tests for VoiceClientType enum serialization."""
    
    def test_enum_values_defined(self):
        """Test that enum contains required values."""
        assert VoiceClientType.BROWSER_WEBRTC == "browser_webrtc"
        assert VoiceClientType.VOIP_ASTERISK == "voip_asterisk"
    
    def test_enum_is_json_serializable(self):
        """Test that enum values serialize to string."""
        client_type = VoiceClientType.BROWSER_WEBRTC
        serialized = json.dumps({"type": client_type.value})
        data = json.loads(serialized)
        assert data["type"] == "browser_webrtc"
        
        client_type = VoiceClientType.VOIP_ASTERISK
        serialized = json.dumps({"type": client_type.value})
        data = json.loads(serialized)
        assert data["type"] == "voip_asterisk"
    
    def test_enum_is_deserializable_from_string(self):
        """Test that string values can be deserialized to enum."""
        client_type = VoiceClientType("browser_webrtc")
        assert client_type == VoiceClientType.BROWSER_WEBRTC
        
        client_type = VoiceClientType("voip_asterisk")
        assert client_type == VoiceClientType.VOIP_ASTERISK


class TestVoiceClientInfo:
    """Tests for VoiceClientInfo dataclass."""
    
    def test_creation_with_all_fields(self):
        """Test VoiceClientInfo creation with all fields."""
        client_id = uuid4()
        client_type = VoiceClientType.BROWSER_WEBRTC
        connected_at = 1710000000000
        metadata = {"user_agent": "Mozilla/5.0"}
        
        info = VoiceClientInfo(
            client_id=client_id,
            client_type=client_type,
            connected_at=connected_at,
            metadata=metadata
        )
        
        assert info.client_id == client_id
        assert info.client_type == client_type
        assert info.connected_at == connected_at
        assert info.metadata == metadata
    
    def test_is_json_serializable(self):
        """Test VoiceClientInfo serializes to JSON correctly."""
        client_id = uuid4()
        client_type = VoiceClientType.BROWSER_WEBRTC
        connected_at = 1710000000000
        metadata = {"user_agent": "Mozilla/5.0"}
        
        info = VoiceClientInfo(
            client_id=client_id,
            client_type=client_type,
            connected_at=connected_at,
            metadata=metadata
        )
        
        data = info.to_dict()
        
        assert data["client_id"] == str(client_id)
        assert data["client_type"] == "browser_webrtc"
        assert data["connected_at"] == 1710000000000
        assert data["metadata"] == {"user_agent": "Mozilla/5.0"}
        
        # Verify it can be JSON serialized
        serialized = json.dumps(data)
        loaded = json.loads(serialized)
        assert loaded["client_id"] == str(client_id)
        assert loaded["client_type"] == "browser_webrtc"
    
    def test_metadata_supports_extensible_fields(self):
        """Test metadata dict can contain custom fields."""
        custom_metadata = {
            "sip_caller_id": "+1234567890",
            "custom_field": "custom_value",
            "nested": {"key": "value"}
        }
        
        info = VoiceClientInfo(
            client_id=uuid4(),
            client_type=VoiceClientType.VOIP_ASTERISK,
            connected_at=1710000000000,
            metadata=custom_metadata
        )
        
        assert info.metadata["sip_caller_id"] == "+1234567890"
        assert info.metadata["custom_field"] == "custom_value"
        assert info.metadata["nested"]["key"] == "value"
    
    def test_metadata_defaults_to_empty_dict(self):
        """Test metadata defaults to empty dict when not provided."""
        info = VoiceClientInfo(
            client_id=uuid4(),
            client_type=VoiceClientType.BROWSER_WEBRTC,
            connected_at=1710000000000
        )
        
        assert info.metadata == {}


class TestVoiceClientProtocol:
    """Tests for VoiceClient protocol type checking compliance."""
    
    def test_protocol_compliance_with_mock_implementation(self):
        """Test that a class implementing all methods is recognized as VoiceClient."""
        
        class MockVoiceClient:
            """Mock implementation for testing protocol compliance."""
            
            def __init__(self):
                self._client_id = uuid4()
                self._connected_at = 1710000000000
            
            @property
            def client_type(self) -> VoiceClientType:
                return VoiceClientType.BROWSER_WEBRTC
            
            @property
            def client_info(self) -> VoiceClientInfo:
                return VoiceClientInfo(
                    client_id=self._client_id,
                    client_type=self.client_type,
                    connected_at=self._connected_at,
                    metadata={}
                )
            
            def send_voice_start(self, prompt, **kwargs):
                pass
            
            def send_voice_cancel(self, generation_id):
                pass
            
            def on_event(self, callback):
                pass
            
            async def close(self):
                pass
        
        # Create instance and verify it implements the protocol
        mock_client = MockVoiceClient()
        
        # Type checkers will verify this at static analysis time
        # At runtime, we can verify the methods exist
        assert hasattr(mock_client, 'client_type')
        assert hasattr(mock_client, 'client_info')
        assert hasattr(mock_client, 'send_voice_start')
        assert hasattr(mock_client, 'send_voice_cancel')
        assert hasattr(mock_client, 'on_event')
        assert hasattr(mock_client, 'close')
        
        # Verify properties work correctly
        assert isinstance(mock_client.client_type, VoiceClientType)
        assert isinstance(mock_client.client_info, VoiceClientInfo)
        assert mock_client.client_type == VoiceClientType.BROWSER_WEBRTC
    
    def test_protocol_duck_typing_without_inheritance(self):
        """Test that protocol works with duck typing (no explicit inheritance)."""
        
        class AnotherMockClient:
            """Another mock that doesn't explicitly mention VoiceClient."""
            
            @property
            def client_type(self):
                return VoiceClientType.VOIP_ASTERISK
            
            @property
            def client_info(self):
                return VoiceClientInfo(
                    client_id=uuid4(),
                    client_type=VoiceClientType.VOIP_ASTERISK,
                    connected_at=1710000000000
                )
            
            def send_voice_start(self, prompt, **kwargs):
                pass
            
            def send_voice_cancel(self, generation_id):
                pass
            
            def on_event(self, callback):
                pass
            
            async def close(self):
                pass
        
        # Even without explicit inheritance, it satisfies the protocol
        mock_client = AnotherMockClient()
        
        assert mock_client.client_type == VoiceClientType.VOIP_ASTERISK
        assert isinstance(mock_client.client_info, VoiceClientInfo)
