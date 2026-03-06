## ADDED Requirements

### Requirement: WebSocket connection lifecycle
The `OpenAIRealtimeProvider` SHALL open a persistent WebSocket connection to `wss://api.openai.com/v1/realtime` on initialization and close it on `close()`.

#### Scenario: Connection established on init
- **WHEN** `OpenAIRealtimeProvider` is created with a valid `OPENAI_API_KEY` and `OPENAI_REALTIME_MODEL`
- **THEN** it SHALL open a WebSocket connection with headers `Authorization: Bearer <key>` and `OpenAI-Beta: realtime=v1`
- **AND** a background reader task SHALL be started to process incoming messages

#### Scenario: Connection closed on close
- **WHEN** `close()` is called
- **THEN** the WebSocket connection SHALL be closed
- **AND** the background reader task SHALL be cancelled

#### Scenario: Connection error during init
- **WHEN** the WebSocket connection fails (invalid key, network error)
- **THEN** the provider SHALL raise an exception with a descriptive error message

### Requirement: Streaming audio send
The provider SHALL accept PCM16 24kHz audio frames via `send_audio()` and forward them to the OpenAI Realtime API with minimal latency.

#### Scenario: Audio frame sent
- **WHEN** `send_audio(frame)` is called with a PCM16 24kHz audio frame
- **THEN** the provider SHALL send an `input_audio_buffer.append` message with the frame base64-encoded
- **AND** the send SHALL NOT await a response (fire-and-forget)

#### Scenario: Audio frame sent while disconnected
- **WHEN** `send_audio(frame)` is called but the WebSocket is disconnected
- **THEN** the provider SHALL log a warning and silently discard the frame

### Requirement: Audio buffer commit on speech end
The provider SHALL commit the audio buffer when signaled that speech has ended, triggering transcription.

#### Scenario: Buffer committed
- **WHEN** `commit_audio_buffer()` is called
- **THEN** the provider SHALL send an `input_audio_buffer.commit` message to the WebSocket

### Requirement: Streaming transcription receive
The provider SHALL yield `TranscriptionEvent` objects via `receive_transcription()` as they arrive from the OpenAI Realtime API.

#### Scenario: Final transcription received
- **WHEN** the WebSocket receives a `conversation.item.input_audio_transcription.completed` message with transcript "necesito ayuda"
- **THEN** `receive_transcription()` SHALL yield `TranscriptionEvent(text="necesito ayuda", is_final=True)`

#### Scenario: Multiple transcriptions in sequence
- **WHEN** the user speaks multiple utterances during a call
- **THEN** `receive_transcription()` SHALL yield each transcription in order as they arrive

#### Scenario: Transcription after close
- **WHEN** `close()` has been called
- **THEN** `receive_transcription()` SHALL stop iteration

### Requirement: Streaming TTS generation
The provider SHALL accept text via `send_text_for_tts()` and yield PCM16 24kHz audio frames as they arrive from the OpenAI Realtime API.

#### Scenario: TTS audio streamed
- **WHEN** `send_text_for_tts(text)` is called with response text
- **THEN** the provider SHALL send a `response.create` message with modalities `["audio", "text"]`
- **AND** yield PCM16 24kHz audio frames as `response.audio.delta` messages arrive (base64-decoded)

#### Scenario: TTS stream completes
- **WHEN** the WebSocket receives a `response.audio.done` message
- **THEN** the async iterator from `send_text_for_tts()` SHALL complete

#### Scenario: TTS error
- **WHEN** the OpenAI API returns an error during TTS generation
- **THEN** the async iterator SHALL raise an exception with the error details

### Requirement: Background message reader
The provider SHALL run a background asyncio task that reads all incoming WebSocket messages and dispatches them to the appropriate internal queues.

#### Scenario: Transcription event routed to STT queue
- **WHEN** the reader receives a `conversation.item.input_audio_transcription.completed` message
- **THEN** it SHALL create a `TranscriptionEvent` and put it in the STT queue

#### Scenario: Audio delta routed to TTS queue
- **WHEN** the reader receives a `response.audio.delta` message
- **THEN** it SHALL base64-decode the audio data and put the bytes in the TTS queue

#### Scenario: Audio done signals TTS completion
- **WHEN** the reader receives a `response.audio.done` message
- **THEN** it SHALL put a `None` sentinel in the TTS queue to signal stream end

#### Scenario: Unknown message type ignored
- **WHEN** the reader receives a message with an unhandled type
- **THEN** it SHALL log the type at debug level and continue

### Requirement: Sample rate conversion
The provider SHALL handle conversion between aiortc's output sample rate (48kHz) and OpenAI's required 24kHz.

#### Scenario: 48kHz to 24kHz downsampling
- **WHEN** `send_audio()` receives a 48kHz PCM16 frame
- **THEN** the provider SHALL downsample to 24kHz by taking every 2nd sample before sending

#### Scenario: 24kHz TTS audio returned as-is
- **WHEN** TTS audio frames arrive from OpenAI at 24kHz
- **THEN** `send_text_for_tts()` SHALL yield the frames without resampling (the bridge handles upsampling if needed)
