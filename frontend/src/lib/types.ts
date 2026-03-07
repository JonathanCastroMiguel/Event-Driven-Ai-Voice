/** Shared TypeScript types for the voice client. */

/** Connection states for the voice session. */
export type ConnectionStatus =
  | "idle"
  | "connecting"
  | "connected"
  | "disconnected"
  | "failed";

/** A transcription message received via the data channel. */
export interface TranscriptionMessage {
  type: "transcription";
  text: string;
  is_final: boolean;
  speaker?: "human" | "agent";
}

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
