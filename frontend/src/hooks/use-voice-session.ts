"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { api } from "@/lib/api";
import type { ConnectionStatus, ControlInMessage } from "@/lib/types";

const WS_BASE =
  (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(
    /^http/,
    "ws",
  );

interface UseVoiceSessionReturn {
  status: ConnectionStatus;
  callId: string | null;
  startSession: () => Promise<void>;
  endSession: () => Promise<void>;
  onControlMessage: (handler: (msg: ControlInMessage) => void) => void;
  onDebugMessage: (handler: (msg: unknown) => void) => void;
  sendDebugControl: (enabled: boolean) => void;
  error: string | null;
}

export function useVoiceSession(): UseVoiceSessionReturn {
  const [status, setStatus] = useState<ConnectionStatus>("idle");
  const [callId, setCallId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const pcRef = useRef<RTCPeerConnection | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const eventWsRef = useRef<WebSocket | null>(null);
  const dcRef = useRef<RTCDataChannel | null>(null);
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
      audioRef.current.remove();
      audioRef.current = null;
    }
    if (eventWsRef.current) {
      eventWsRef.current.close();
      eventWsRef.current = null;
    }
    dcRef.current = null;

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

      // 2. Open event-forwarding WebSocket to backend
      const eventWs = new WebSocket(
        `${WS_BASE}/api/v1/calls/${call_id}/events`,
      );
      eventWsRef.current = eventWs;

      // Buffer backend messages until data channel is open, then flush
      const pendingMessages: string[] = [];
      let dcReady = false;

      const sendOrBuffer = (data: string) => {
        const dc = dcRef.current;
        if (dcReady && dc && dc.readyState === "open") {
          dc.send(data);
        } else {
          pendingMessages.push(data);
        }
      };

      const flushPending = () => {
        dcReady = true;
        const dc = dcRef.current;
        if (dc && dc.readyState === "open") {
          for (const msg of pendingMessages) {
            dc.send(msg);
          }
        }
        pendingMessages.length = 0;
      };

      // Handle messages from backend — route to OpenAI or handle locally
      const backendOnlyTypes = new Set([
        "debug_event",
        "turn_update",
        "fsm_state",
        "transcript_final",
      ]);

      eventWs.addEventListener("message", (e: MessageEvent) => {
        const raw = e.data as string;
        try {
          const parsed = JSON.parse(raw) as Record<string, unknown>;
          const msgType = parsed.type as string | undefined;
          if (msgType && backendOnlyTypes.has(msgType)) {
            // Backend-only event — route to debug handler, don't forward to OpenAI
            debugHandlerRef.current?.(parsed);
            return;
          }
        } catch {
          // Not JSON — forward to OpenAI as-is
        }
        sendOrBuffer(raw);
      });

      // 3. Create RTCPeerConnection
      const pc = new RTCPeerConnection();
      pcRef.current = pc;

      // 4. Audio playback from OpenAI — appended to DOM for AEC to work
      const audio = document.createElement("audio");
      audio.autoplay = true;
      audio.style.display = "none";
      audio.crossOrigin = "anonymous";
      document.body.appendChild(audio);
      audioRef.current = audio;
      pc.ontrack = (e) => {
        audio.srcObject = e.streams[0];
      };

      // 5. Microphone
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });
      pc.addTrack(stream.getTracks()[0]);

      // 6. Data channel — wire listeners inline (not in useEffect)
      const dc = pc.createDataChannel("oai-events");
      dcRef.current = dc;

      dc.addEventListener("open", () => {
        setStatus("connected");
        flushPending();
      });

      dc.addEventListener("message", (e: MessageEvent) => {
        try {
          const raw = e.data as string;

          // Forward ALL events to backend via WebSocket
          if (eventWsRef.current?.readyState === WebSocket.OPEN) {
            eventWsRef.current.send(raw);
          }

          const event = JSON.parse(raw) as Record<string, unknown>;

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

      // 7. Connection state
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

      // 8. SDP exchange
      const offer = await pc.createOffer();
      await pc.setLocalDescription(offer);

      const answer = await api.calls.offer(call_id, offer.sdp!);
      await pc.setRemoteDescription(
        new RTCSessionDescription({ sdp: answer.sdp, type: "answer" }),
      );
    } catch (err) {
      const isMicDenied =
        err instanceof DOMException && err.name === "NotAllowedError";
      const message = isMicDenied
        ? "Microphone access is required for voice calls. Please allow microphone access in your browser settings."
        : err instanceof Error
          ? err.message
          : "Failed to start session";
      setError(message);
      setStatus(isMicDenied ? "mic_denied" : "failed");
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

  const sendDebugControl = useCallback((enabled: boolean) => {
    const ws = eventWsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: enabled ? "debug_enable" : "debug_disable" }));
    }
  }, []);

  return {
    status,
    callId,
    startSession,
    endSession,
    onControlMessage,
    onDebugMessage,
    sendDebugControl,
    error,
  };
}
