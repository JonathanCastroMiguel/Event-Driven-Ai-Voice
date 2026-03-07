## REMOVED Requirements

### Requirement: RealtimeVoiceBridge implements RealtimeClient Protocol
**Reason**: No backend audio relay needed. Browser connects directly to OpenAI via WebRTC.
**Migration**: Delete `realtime_bridge.py`. Coordinator integration with voice will be redesigned in a future change.

### Requirement: Audio forwarding to Realtime Voice API
**Reason**: Audio flows directly from browser to OpenAI. No backend audio relay.
**Migration**: No replacement needed.

### Requirement: STT transcription to EventEnvelope
**Reason**: Transcriptions go directly to browser via OpenAI data channel. Backend is not in the audio/event path.
**Migration**: Future change will add event forwarding from browser to backend for Coordinator integration.

### Requirement: VAD signal dispatch
**Reason**: Client-side VAD removed. OpenAI handles VAD server-side. Backend does not receive VAD signals.
**Migration**: Future change will add event forwarding from browser to backend.

### Requirement: TTS audio streaming back to browser
**Reason**: TTS audio flows directly from OpenAI to browser via WebRTC.
**Migration**: No replacement needed.

### Requirement: Voice cancellation
**Reason**: No backend voice control. Browser can send cancel events directly via the OpenAI data channel.
**Migration**: Future change may add backend-controlled cancellation.

### Requirement: RealtimeVoiceProvider Protocol
**Reason**: No backend voice provider needed.
**Migration**: Delete `realtime_provider.py`.

### Requirement: Transcription forwarding to frontend
**Reason**: OpenAI sends transcription events directly to browser via data channel.
**Migration**: Frontend translates OpenAI events to internal format.

### Requirement: Provider selection via factory
**Reason**: No voice provider factory needed.
**Migration**: Delete factory function and stub provider.

### Requirement: Audio buffer commit on speech end
**Reason**: OpenAI handles VAD and audio buffer management server-side.
**Migration**: No replacement needed.
