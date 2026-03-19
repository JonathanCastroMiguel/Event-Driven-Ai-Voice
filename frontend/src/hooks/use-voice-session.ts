"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { api } from "@/lib/api";
import type { ConnectionStatus, ControlInMessage } from "@/lib/types";

const WS_BASE =
  (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(
    /^http/,
    "ws",
  );

// Reduced assistant volume to minimize residual echo energy reaching the mic.
// Browser AEC handles most echo; lower volume reduces residual leakage.
const ASSISTANT_VOLUME = 0.20;

interface UseVoiceSessionReturn {
  status: ConnectionStatus;
  callId: string | null;
  isMuted: boolean;
  toggleMute: () => void;
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
  const [isMuted, setIsMuted] = useState(false);

  const pcRef = useRef<RTCPeerConnection | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const eventWsRef = useRef<WebSocket | null>(null);
  const dcRef = useRef<RTCDataChannel | null>(null);
  const controlHandlerRef = useRef<((msg: ControlInMessage) => void) | null>(
    null,
  );
  const debugHandlerRef = useRef<((msg: unknown) => void) | null>(null);
  const callIdRef = useRef<string | null>(null);
  const manuallyMutedRef = useRef<boolean>(false);
  const graceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Echo loop detection: rolling window of speech_started timestamps
  const speechStartedTimestamps = useRef<number[]>([]);
  const echoLoopWarnedRef = useRef<boolean>(false);

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

      // Track audio playback state for client debug events
      let firstAudioReceived = false;
      let currentDebugTurnId = "";

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
            // Track turn_id from debug events for client debug event emission
            if (msgType === "debug_event" && parsed.turn_id) {
              currentDebugTurnId = String(parsed.turn_id);
            }
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

      // 4. Audio playback — DOM <audio> element for speaker output
      const audio = document.createElement("audio");
      audio.autoplay = true;
      audio.style.display = "none";
      document.body.appendChild(audio);
      audioRef.current = audio;
      audio.volume = ASSISTANT_VOLUME;

      // 5. Microphone — browser AEC + grace period mic gating
      const micStream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
          // Prefer hardware/OS-level AEC when available; falls back to Chrome AEC3
          echoCancellationType: { ideal: "system" },
        } as MediaTrackConstraints,
      });

      const micTrack = micStream.getAudioTracks()[0];

      // AEC runtime diagnostics — verify echo cancellation is active
      const trackSettings = micTrack.getSettings();
      if (trackSettings.echoCancellation === true) {
        console.log("aec_verified", { echoCancellation: true, settings: trackSettings });
      } else {
        console.warn("aec_not_active", { settings: trackSettings });
      }
      if (typeof micTrack.getCapabilities === "function") {
        const caps = micTrack.getCapabilities();
        const echoCancellationType = (caps as Record<string, unknown>).echoCancellationType;
        if (Array.isArray(echoCancellationType) && echoCancellationType.includes("system")) {
          console.log("hardware_aec_available", { echoCancellationType });
        }
      }

      pc.addTrack(micTrack);

      // Mic gating with grace period: mute mic for the first 2s of assistant
      // playback (browser AEC needs time to converge), then unmute for barge-in.
      const GRACE_MS = 2000;

      const startGrace = () => {
        // Skip grace period entirely if user has manually muted
        if (manuallyMutedRef.current) return;

        // Mute mic immediately when assistant starts speaking
        const sender = pc.getSenders().find((s) => s.track?.kind === "audio");
        if (sender?.track) sender.track.enabled = false;

        // Unmute after grace period to allow barge-in
        if (graceTimerRef.current) clearTimeout(graceTimerRef.current);
        graceTimerRef.current = setTimeout(() => {
          if (manuallyMutedRef.current) { graceTimerRef.current = null; return; }
          const s = pc.getSenders().find((s) => s.track?.kind === "audio");
          if (s?.track) s.track.enabled = true;
          graceTimerRef.current = null;
        }, GRACE_MS);
      };

      const endGrace = () => {
        if (graceTimerRef.current) { clearTimeout(graceTimerRef.current); graceTimerRef.current = null; }
        // Only re-enable mic if user hasn't manually muted
        if (manuallyMutedRef.current) return;
        const sender = pc.getSenders().find((s) => s.track?.kind === "audio");
        if (sender?.track) sender.track.enabled = true;
      };

      pc.ontrack = (e) => {
        audio.srcObject = e.streams[0];
      };

      // 7. Data channel — wire listeners inline (not in useEffect)
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

          // Track audio playback for client debug events
          // In WebRTC mode, audio flows via RTP track (not response.audio.delta).
          // output_audio_buffer.started = speaker begins playing
          // output_audio_buffer.stopped = speaker finished playing all buffered audio
          if (event.type === "response.created") {
            firstAudioReceived = false;
          } else if (event.type === "output_audio_buffer.started") {
            startGrace();
            if (!firstAudioReceived) {
              firstAudioReceived = true;
              if (eventWsRef.current?.readyState === WebSocket.OPEN && currentDebugTurnId) {
                eventWsRef.current.send(JSON.stringify({
                  type: "client_debug_event",
                  stage: "audio_playback_start",
                  turn_id: currentDebugTurnId,
                  ts: Date.now(),
                }));
              }
            }
          } else if (event.type === "output_audio_buffer.stopped") {
            endGrace();
            if (eventWsRef.current?.readyState === WebSocket.OPEN && currentDebugTurnId) {
              eventWsRef.current.send(JSON.stringify({
                type: "client_debug_event",
                stage: "audio_playback_end",
                turn_id: currentDebugTurnId,
                ts: Date.now(),
              }));
            }
          }

          // Echo loop detection: track speech_started in rolling 10s window
          if (event.type === "input_audio_buffer.speech_started") {
            const ECHO_WINDOW_MS = 10_000;
            const ECHO_THRESHOLD = 5;
            const now = Date.now();
            const timestamps = speechStartedTimestamps.current;
            timestamps.push(now);
            // Prune events outside the window
            const cutoff = now - ECHO_WINDOW_MS;
            while (timestamps.length > 0 && timestamps[0] < cutoff) {
              timestamps.shift();
            }
            if (timestamps.length >= ECHO_THRESHOLD && !echoLoopWarnedRef.current) {
              console.warn("echo_loop_detected", {
                count: timestamps.length,
                window_ms: ECHO_WINDOW_MS,
              });
              echoLoopWarnedRef.current = true;
              // Reset rate-limit after window elapses
              setTimeout(() => { echoLoopWarnedRef.current = false; }, ECHO_WINDOW_MS);
            }
          }

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
            const text = ((event.transcript as string) ?? "").trim();
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

      // 8. Connection state
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

      // 9. SDP exchange
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
    setIsMuted(false);
    manuallyMutedRef.current = false;
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

  const toggleMute = useCallback(() => {
    const pc = pcRef.current;
    if (!pc) return;
    const sender = pc.getSenders().find((s) => s.track?.kind === "audio");
    if (sender?.track) {
      const next = !sender.track.enabled;
      sender.track.enabled = next;
      const muting = !next;
      manuallyMutedRef.current = muting;
      // Cancel any active grace timer when user manually mutes
      if (muting && graceTimerRef.current) {
        clearTimeout(graceTimerRef.current);
        graceTimerRef.current = null;
      }
      setIsMuted(muting);
    }
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
    isMuted,
    toggleMute,
    startSession,
    endSession,
    onControlMessage,
    onDebugMessage,
    sendDebugControl,
    error,
  };
}
