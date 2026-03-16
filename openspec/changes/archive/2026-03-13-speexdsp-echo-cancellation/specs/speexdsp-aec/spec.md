## REMOVED Capability

This capability (SpeexDSP WASM AEC) was abandoned because `MediaStreamDestination` tracks produce silence when added to `RTCPeerConnection` in Chrome, making any AudioWorklet-based AEC pipeline impossible with WebRTC.

All SpeexDSP-related files have been removed:
- `frontend/public/wasm/speexdsp.wasm`
- `frontend/public/wasm/speexdsp.js`
- `frontend/public/worklets/aec-processor.js`
- `scripts/build-speexdsp-wasm.sh`

Echo cancellation is now handled by the voice-client-ui capability using browser-native AEC + volume reduction + grace-period mic gating.
