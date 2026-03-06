"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { useDebugChannel } from "@/hooks/use-debug-channel";
import { useMicrophone } from "@/hooks/use-microphone";
import { useVAD } from "@/hooks/use-vad";
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
    peerConnection,
    sendControl,
    onControlMessage,
    onDebugMessage,
    error,
  } = useVoiceSession();

  const {
    status: micStatus,
    stream,
    startMicrophone,
    stopMicrophone,
    attachToConnection,
  } = useMicrophone();

  const { isSpeaking } = useVAD({
    stream,
    sendControl,
    enabled: status === "connected",
  });

  const { state: debugState, handleDebugMessage } = useDebugChannel();
  const [debugEnabled, setDebugEnabled] = useState(false);

  const [transcriptions, setTranscriptions] = useState<TranscriptionEntry[]>(
    [],
  );
  const [isAgentSpeaking, setIsAgentSpeaking] = useState(false);
  const partialRef = useRef<string>("");

  // Handle incoming control messages (transcriptions)
  const handleControlMessage = useCallback((msg: TranscriptionMessage) => {
    if (msg.type === "transcription") {
      if (msg.is_final) {
        setTranscriptions((prev) => [
          ...prev,
          {
            id: `${Date.now()}-agent`,
            speaker: "agent",
            text: msg.text,
            timestamp: Date.now(),
          },
        ]);
        partialRef.current = "";
      } else {
        partialRef.current = msg.text;
      }
    }
  }, []);

  // Wire control and debug message handlers
  useEffect(() => {
    onControlMessage(handleControlMessage);
  }, [onControlMessage, handleControlMessage]);

  useEffect(() => {
    onDebugMessage(handleDebugMessage);
  }, [onDebugMessage, handleDebugMessage]);

  const handleStart = useCallback(async () => {
    const audioStream = await startMicrophone();
    if (!audioStream) return;

    await startSession();
  }, [startMicrophone, startSession]);

  // Attach microphone to peer connection once connected
  useEffect(() => {
    if (status === "connected" && peerConnection && stream) {
      attachToConnection(peerConnection);
    }
  }, [status, peerConnection, stream, attachToConnection]);

  const handleEnd = useCallback(async () => {
    stopMicrophone();
    await endSession();
    setTranscriptions([]);
    setIsAgentSpeaking(false);
  }, [stopMicrophone, endSession]);

  // Toggle debug mode — sends enable/disable on control DataChannel
  const toggleDebug = useCallback(() => {
    setDebugEnabled((prev) => {
      const next = !prev;
      sendControl({ type: next ? "debug_enable" : "debug_disable" });
      return next;
    });
  }, [sendControl]);

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
        {status === "failed" && (
          <span className="text-destructive">
            {error ?? "Connection failed"}
          </span>
        )}
      </div>

      {/* Mic permission denied fallback */}
      {micStatus === "denied" && (
        <div className="text-sm text-destructive text-center px-4">
          Microphone access denied. Please allow microphone permission in your
          browser settings and reload the page.
        </div>
      )}

      {/* Animation indicators */}
      <div className="flex items-center justify-center gap-16">
        <div className="flex flex-col items-center gap-2">
          <MicAnimation isActive={isActive && isSpeaking} />
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
            disabled={micStatus === "denied"}
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

      {/* Debug panel (lazy-loaded, only when toggled) */}
      {debugEnabled && (
        <DebugPanel
          turns={debugState.turns}
          fsmState={debugState.fsmState}
          routing={debugState.routing}
          events={debugState.events}
          latencies={debugState.latencies}
        />
      )}
    </div>
  );
}
