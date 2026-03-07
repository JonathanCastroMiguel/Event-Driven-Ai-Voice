"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { api } from "@/lib/api";
import type { ConnectionStatus, ControlInMessage } from "@/lib/types";

interface UseVoiceSessionReturn {
  status: ConnectionStatus;
  callId: string | null;
  startSession: () => Promise<void>;
  endSession: () => Promise<void>;
  onControlMessage: (handler: (msg: ControlInMessage) => void) => void;
  onDebugMessage: (handler: (msg: unknown) => void) => void;
  error: string | null;
}

export function useVoiceSession(): UseVoiceSessionReturn {
  const [status, setStatus] = useState<ConnectionStatus>("idle");
  const [callId, setCallId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const pcRef = useRef<RTCPeerConnection | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const controlHandlerRef = useRef<((msg: ControlInMessage) => void) | null>(
    null,
  );
  const debugHandlerRef = useRef<((msg: unknown) => void) | null>(null);
  const callIdRef = useRef<string | null>(null);

  const cleanup = useCallback(async (id: string | null) => {
    if (pcRef.current) {
      pcRef.current.getSenders().forEach((sender) => {
        if (sender.track) sender.track.stop();
      });
      pcRef.current.close();
      pcRef.current = null;
    }
    if (audioRef.current) {
      audioRef.current.srcObject = null;
      audioRef.current = null;
    }

    if (id) {
      try {
        await api.calls.end(id);
      } catch {
        // Best-effort
      }
    }
  }, []);

  // Clean up on page unload
  useEffect(() => {
    const onUnload = () => {
      if (callIdRef.current) {
        navigator.sendBeacon(
          `${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/api/v1/calls/${callIdRef.current}`,
        );
      }
    };
    window.addEventListener("beforeunload", onUnload);
    return () => window.removeEventListener("beforeunload", onUnload);
  }, []);

  const startSession = useCallback(async () => {
    setError(null);
    setStatus("connecting");

    let newCallId: string | null = null;

    try {
      // 1. Create call session
      const { call_id } = await api.calls.create();
      newCallId = call_id;
      setCallId(call_id);
      callIdRef.current = call_id;

      // 2. Create RTCPeerConnection
      const pc = new RTCPeerConnection();
      pcRef.current = pc;

      // 3. Audio playback from OpenAI
      const audio = document.createElement("audio");
      audio.autoplay = true;
      audioRef.current = audio;
      pc.ontrack = (e) => {
        audio.srcObject = e.streams[0];
      };

      // 4. Microphone
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      pc.addTrack(stream.getTracks()[0]);

      // 5. Data channel — wire listeners inline (not in useEffect)
      const dc = pc.createDataChannel("oai-events");

      dc.addEventListener("open", () => {
        setStatus("connected");
      });

      dc.addEventListener("message", (e: MessageEvent) => {
        try {
          const event = JSON.parse(e.data) as Record<string, unknown>;

          // Forward to debug handler (filter high-frequency audio deltas)
          if (event.type !== "response.audio.delta") {
            debugHandlerRef.current?.(event);
          }

          // Translate OpenAI events to transcription format
          if (
            event.type ===
            "conversation.item.input_audio_transcription.completed"
          ) {
            const text = (event.transcript as string) ?? "";
            if (text) {
              controlHandlerRef.current?.({
                type: "transcription",
                text,
                is_final: true,
                speaker: "human",
              });
            }
          } else if (event.type === "response.audio_transcript.done") {
            const text = (event.transcript as string) ?? "";
            if (text) {
              controlHandlerRef.current?.({
                type: "transcription",
                text,
                is_final: true,
                speaker: "agent",
              });
            }
          }
        } catch {
          // Ignore unparseable
        }
      });

      // 6. Connection state
      pc.onconnectionstatechange = () => {
        const state = pc.connectionState;
        if (state === "connected") {
          setStatus("connected");
        } else if (state === "failed") {
          setStatus("failed");
          setError("WebRTC connection failed");
        } else if (state === "disconnected" || state === "closed") {
          setStatus("disconnected");
        }
      };

      // 7. SDP exchange
      const offer = await pc.createOffer();
      await pc.setLocalDescription(offer);

      const answer = await api.calls.offer(call_id, offer.sdp!);
      await pc.setRemoteDescription(
        new RTCSessionDescription({ sdp: answer.sdp, type: "answer" }),
      );
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Failed to start session";
      setError(message);
      setStatus("failed");
      await cleanup(newCallId);
    }
  }, [cleanup]);

  const endSession = useCallback(async () => {
    const currentCallId = callIdRef.current;
    setStatus("disconnected");
    setCallId(null);
    callIdRef.current = null;
    await cleanup(currentCallId);
  }, [cleanup]);

  const onControlMessage = useCallback(
    (handler: (msg: ControlInMessage) => void) => {
      controlHandlerRef.current = handler;
    },
    [],
  );

  const onDebugMessage = useCallback((handler: (msg: unknown) => void) => {
    debugHandlerRef.current = handler;
  }, []);

  return {
    status,
    callId,
    startSession,
    endSession,
    onControlMessage,
    onDebugMessage,
    error,
  };
}
