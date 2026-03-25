"""Voice Client Factory for type-based client instantiation.

This module provides the factory function for creating VoiceClient implementations
based on client type. This is the single extension point for adding new ingress types.

Extension Guide:
    To add a new client type:
    1. Add the enum value to VoiceClientType in voice_client.py
    2. Import your new client implementation
    3. Add a case to create_voice_client() to return your implementation
    4. Update SUPPORTED_TYPES set
    5. Add factory tests for the new type
"""

from typing import Any

from src.voice_runtime.voice_client import VoiceClient, VoiceClientType


# Registry of supported client types (update when adding new implementations)
SUPPORTED_TYPES = {VoiceClientType.BROWSER_WEBRTC}


class UnsupportedClientTypeError(Exception):
    """Raised when an unsupported or invalid client type is requested."""
    pass


def create_voice_client(
    client_type: VoiceClientType,
    **config: Any
) -> VoiceClient:
    """Create a VoiceClient implementation based on client type.
    
    This is the single factory function for instantiating voice clients.
    It serves as the extension point for adding new ingress types.
    
    Args:
        client_type: The type of client to create (BROWSER_WEBRTC, VOIP_ASTERISK, etc.)
        **config: Client-specific configuration parameters passed to the implementation
    
    Returns:
        VoiceClient: A client implementation matching the requested type
    
    Raises:
        NotImplementedError: If the client type is defined but not yet implemented
        UnsupportedClientTypeError: If the client type is invalid or unknown
    
    Examples:
        >>> # Create browser WebRTC client
        >>> client = create_voice_client(
        ...     VoiceClientType.BROWSER_WEBRTC,
        ...     websocket=ws,
        ...     coordinator=coordinator
        ... )
        
        >>> # Attempt to create VoIP client (not yet implemented)
        >>> client = create_voice_client(VoiceClientType.VOIP_ASTERISK)
        NotImplementedError: VoIP/Asterisk client not yet implemented (planned for future release)
    """
    if not isinstance(client_type, VoiceClientType):
        raise UnsupportedClientTypeError(
            f"Invalid client type: {client_type}. Must be a VoiceClientType enum value. "
            f"Supported types: {', '.join(t.value for t in SUPPORTED_TYPES)}"
        )
    
    if client_type == VoiceClientType.BROWSER_WEBRTC:
        # Import here to avoid circular dependencies
        from src.voice_runtime.realtime_event_bridge import OpenAIRealtimeEventBridge
        
        return OpenAIRealtimeEventBridge(**config)
    
    elif client_type == VoiceClientType.VOIP_ASTERISK:
        # Placeholder for future VoIP bridge implementation
        raise NotImplementedError(
            "VoIP/Asterisk client not yet implemented (planned for future release). "
            "This client type will consume from RabbitMQ and translate Asterisk events "
            "into EventEnvelope. Implementation is tracked in a separate user story."
        )
    
    else:
        # Should not reach here if all enum values are handled above
        raise UnsupportedClientTypeError(
            f"Unsupported client type: {client_type.value}. "
            f"Supported types: {', '.join(t.value for t in SUPPORTED_TYPES)}"
        )


def get_supported_types() -> set[VoiceClientType]:
    """Get the set of currently supported client types.
    
    Returns:
        Set of VoiceClientType values that can be instantiated
    """
    return SUPPORTED_TYPES.copy()
