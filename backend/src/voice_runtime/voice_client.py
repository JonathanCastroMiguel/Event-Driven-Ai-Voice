"""Voice Client abstraction for multi-ingress support.

This module defines the VoiceClient protocol, VoiceClientType enum,
and VoiceClientInfo metadata structure to support multiple voice ingress
types (Browser WebRTC, VoIP/Asterisk, future SIP providers) through a
uniform interface.

Extension Point:
    To add a new ingress type:
    1. Add a new value to VoiceClientType enum
    2. Create a new client implementation that implements VoiceClient protocol
    3. Update VoiceClientFactory to instantiate the new client type
"""

from collections.abc import Coroutine
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Protocol
from uuid import UUID


class VoiceClientType(str, Enum):
    """Voice client ingress types.
    
    Attributes:
        BROWSER_WEBRTC: Browser-based WebRTC client (via WebSocket)
        VOIP_ASTERISK: VoIP/Asterisk client (via RabbitMQ)
    """
    BROWSER_WEBRTC = "browser_webrtc"
    VOIP_ASTERISK = "voip_asterisk"


@dataclass
class VoiceClientInfo:
    """Metadata for a voice client instance.
    
    Attributes:
        client_id: Unique identifier for this client instance
        client_type: The type of ingress (browser, VoIP, etc.)
        connected_at: Unix timestamp in milliseconds of connection establishment
        metadata: Extensible client-specific metadata (e.g., SIP caller ID, user-agent)
    """
    client_id: UUID
    client_type: VoiceClientType
    connected_at: int  # Unix timestamp in milliseconds
    metadata: dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "client_id": str(self.client_id),
            "client_type": self.client_type.value,
            "connected_at": self.connected_at,
            "metadata": self.metadata
        }


class VoiceClient(Protocol):
    """Protocol for voice client implementations.
    
    This protocol defines the interface that all voice client implementations
    must satisfy. It uses structural typing (duck typing) so implementations
    don't need explicit inheritance.
    
    The protocol extends the existing RealtimeClient contract with type awareness,
    enabling the system to support multiple ingress types through a uniform interface.
    
    Properties:
        client_type: Returns the type of this client (browser, VoIP, etc.)
        client_info: Returns full metadata for this client instance
    
    Methods:
        send_voice_start: Initiate voice generation with the given event
        send_voice_cancel: Cancel ongoing voice generation with the given event
        on_event: Register callback for events from this client
        close: Close the client connection and cleanup resources
    
    Note: Method signatures preserve compatibility with existing RealtimeClient protocol.
    Event types (RealtimeVoiceStart, RealtimeVoiceCancel) are imported from events module.
    """
    
    @property
    def client_type(self) -> VoiceClientType:
        """Return the type of this voice client."""
        ...
    
    @property
    def client_info(self) -> VoiceClientInfo:
        """Return full metadata for this client instance."""
        ...
    
    async def send_voice_start(self, event: Any) -> None:
        """Send a voice generation start command to the client.
        
        Args:
            event: RealtimeVoiceStart event containing prompt and generation metadata
        """
        ...
    
    async def send_voice_cancel(self, event: Any) -> None:
        """Cancel an ongoing voice generation.
        
        Args:
            event: RealtimeVoiceCancel event containing generation_id to cancel
        """
        ...
    
    def on_event(self, callback: Callable[[Any], Coroutine[Any, Any, None]]) -> None:
        """Register a callback to receive EventEnvelope instances from this client.
        
        Args:
            callback: Async function to call with EventEnvelope data
        """
        ...
    
    async def close(self) -> None:
        """Close the client connection and cleanup resources."""
        ...
