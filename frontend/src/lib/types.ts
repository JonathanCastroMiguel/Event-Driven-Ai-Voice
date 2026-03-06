/** Shared TypeScript types for the voice client. */

/** Connection states for the voice session. */
export type ConnectionStatus =
  | "idle"
  | "connecting"
  | "connected"
  | "disconnected"
  | "failed";

/** A transcription message received from the backend. */
export interface TranscriptionMessage {
  type: "transcription";
  text: string;
  is_final: boolean;
}

/** Control channel message sent from browser to backend. */
export type ControlOutMessage =
  | { type: "speech_started"; ts: number }
  | { type: "speech_ended"; ts: number }
  | { type: "debug_enable" }
  | { type: "debug_disable" };

/** Control channel message received from backend. */
export type ControlInMessage = TranscriptionMessage;

/** Debug event received from the backend debug DataChannel. */
export interface DebugEvent {
  type: string;
  ts?: number;
  [key: string]: unknown;
}

/** A single transcription entry for display. */
export interface TranscriptionEntry {
  id: string;
  speaker: "human" | "agent";
  text: string;
  timestamp: number;
}

/** API response for POST /calls. */
export interface CreateCallResponse {
  call_id: string;
  status: string;
}

/** API response for POST /calls/{call_id}/offer. */
export interface SDPResponse {
  sdp: string;
  type: string;
}
