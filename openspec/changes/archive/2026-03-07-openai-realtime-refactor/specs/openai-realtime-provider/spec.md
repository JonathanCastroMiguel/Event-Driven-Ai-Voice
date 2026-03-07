## REMOVED Requirements

### Requirement: WebSocket connection lifecycle
**Reason**: Browser connects directly to OpenAI via WebRTC. Backend no longer maintains a WebSocket connection to the OpenAI Realtime API.
**Migration**: Delete `openai_realtime_provider.py`. Browser receives events via the `oai-events` data channel.

### Requirement: Streaming audio send
**Reason**: Audio flows directly from browser to OpenAI via WebRTC. No server-side audio forwarding needed.
**Migration**: No replacement needed. Browser streams microphone audio directly via WebRTC.

### Requirement: Audio buffer commit on speech end
**Reason**: OpenAI handles VAD server-side. No explicit buffer commit needed.
**Migration**: No replacement needed.

### Requirement: Streaming transcription receive
**Reason**: Transcriptions arrive at the browser via the OpenAI data channel, not via backend.
**Migration**: Frontend handles `conversation.item.input_audio_transcription.completed` events directly.

### Requirement: Streaming TTS generation
**Reason**: TTS audio flows directly from OpenAI to browser via WebRTC audio track.
**Migration**: No replacement needed.

### Requirement: Background message reader
**Reason**: No WebSocket connection to read from. All events go directly to browser.
**Migration**: Frontend data channel message handler replaces this.

### Requirement: Sample rate conversion
**Reason**: No server-side audio processing. WebRTC handles Opus codec natively.
**Migration**: No replacement needed.
