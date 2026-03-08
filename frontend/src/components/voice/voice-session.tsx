"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { useDebugChannel } from "@/hooks/use-debug-channel";
import { useVoiceSession } from "@/hooks/use-voice-session";
import type { TranscriptionEntry, TranscriptionMessage } from "@/lib/types";

import { MicAnimation } from "./mic-animation";
import { SpeakerAnimation } from "./speaker-animation";
import { TranscriptionPanel } from "./transcription-panel";

// Lazy-load debug panel (only rendered when toggled)
const DebugPanel = dynamic(
  () =>
    import("@/components/debug/debug-panel").then((mod) => ({
      default: mod.DebugPanel,
    })),
  { ssr: false },
);

export function VoiceSession() {
  const {
    status,
    callId,
    startSession,
    endSession,
    onControlMessage,
    onDebugMessage,
    sendDebugControl,
    error,
  } = useVoiceSession();

  const { state: debugState, handleDebugMessage, clearState } =
    useDebugChannel();
  const [debugEnabled, setDebugEnabled] = useState(false);

  const [transcriptions, setTranscriptions] = useState<TranscriptionEntry[]>(
    [],
  );
  const [isAgentSpeaking, setIsAgentSpeaking] = useState(false);
  const [isUserSpeaking, setIsUserSpeaking] = useState(false);

  // Handle incoming transcription messages (translated from OpenAI events)
  const handleControlMessage = useCallback((msg: TranscriptionMessage) => {
    if (msg.type === "transcription" && msg.is_final) {
      const speaker = msg.speaker ?? "agent";
      setTranscriptions((prev) => [
        ...prev,
        {
          id: `${Date.now()}-${speaker}`,
          speaker,
          text: msg.text,
          timestamp: Date.now(),
        },
      ]);
    }
  }, []);

  // Handle OpenAI events for speaking indicators
  const handleDebugForSpeaking = useCallback((event: unknown) => {
    const e = event as Record<string, unknown>;
    if (e.type === "input_audio_buffer.speech_started") {
      setIsUserSpeaking(true);
    } else if (e.type === "input_audio_buffer.speech_stopped") {
      setIsUserSpeaking(false);
    } else if (e.type === "response.audio.delta") {
      setIsAgentSpeaking(true);
    } else if (e.type === "response.audio.done") {
      setIsAgentSpeaking(false);
    }
  }, []);

  // Wire message handlers
  useEffect(() => {
    onControlMessage(handleControlMessage);
  }, [onControlMessage, handleControlMessage]);

  useEffect(() => {
    onDebugMessage((event: unknown) => {
      handleDebugMessage(event);
      handleDebugForSpeaking(event);
    });
  }, [onDebugMessage, handleDebugMessage, handleDebugForSpeaking]);

  const handleStart = useCallback(async () => {
    await startSession();
  }, [startSession]);

  const handleEnd = useCallback(async () => {
    await endSession();
    setTranscriptions([]);
    setIsAgentSpeaking(false);
    setIsUserSpeaking(false);
  }, [endSession]);

  // Toggle debug mode — sends control message to backend
  const toggleDebug = useCallback(() => {
    const next = !debugEnabled;
    setDebugEnabled(next);
    sendDebugControl(next);
    if (!next) {
      clearState();
    }
  }, [debugEnabled, sendDebugControl, clearState]);

  const isActive = status === "connected";
  const isConnecting = status === "connecting";

  return (
    <div className="flex flex-col items-center gap-8 w-full max-w-2xl mx-auto">
      {/* Status indicator */}
      <div className="text-sm text-muted-foreground">
        {status === "idle" && "Ready to start"}
        {isConnecting && "Connecting..."}
        {isActive && `Connected (${callId?.slice(0, 8)}...)`}
        {status === "disconnected" && "Disconnected"}
        {(status === "failed" || status === "mic_denied") && (
          <span className="text-destructive">
            {error ?? "Connection failed"}
          </span>
        )}
      </div>

      {/* Animation indicators */}
      <div className="flex items-center justify-center gap-16">
        <div className="flex flex-col items-center gap-2">
          <MicAnimation isActive={isActive && isUserSpeaking} />
          <span className="text-xs text-muted-foreground">You</span>
        </div>
        <div className="flex flex-col items-center gap-2">
          <SpeakerAnimation isActive={isAgentSpeaking} />
          <span className="text-xs text-muted-foreground">Agent</span>
        </div>
      </div>

      {/* Start / End / Debug buttons */}
      <div className="flex items-center gap-3">
        {!isActive && !isConnecting ? (
          <Button
            size="lg"
            onClick={handleStart}
            disabled={status === "mic_denied"}
          >
            Start Call
          </Button>
        ) : (
          <Button
            size="lg"
            variant="destructive"
            onClick={handleEnd}
            disabled={isConnecting}
          >
            {isConnecting ? "Connecting..." : "End Call"}
          </Button>
        )}

        {isActive && (
          <Button size="sm" variant="outline" onClick={toggleDebug}>
            {debugEnabled ? "Hide Debug" : "Show Debug"}
          </Button>
        )}
      </div>

      {/* Transcription panel */}
      <TranscriptionPanel entries={transcriptions} />

      {/* Debug panel (lazy-loaded, only when toggled) — breaks out of parent max-w */}
      {debugEnabled && (
        <div className="w-[calc(100vw-2rem)] max-w-7xl">
          <DebugPanel turns={debugState.turns} />
        </div>
      )}
    </div>
  );
}
