"use client";

import { useCallback, useRef, useState } from "react";

import { api } from "@/lib/api";
import type {
  ConnectionStatus,
  ControlInMessage,
  ControlOutMessage,
} from "@/lib/types";

interface UseVoiceSessionReturn {
  /** Current connection status. */
  status: ConnectionStatus;
  /** Active call ID (set after POST /calls). */
  callId: string | null;
  /** Start a new voice session (POST /calls -> SDP exchange -> connected). */
  startSession: () => Promise<void>;
  /** End the current voice session. */
  endSession: () => Promise<void>;
  /** The RTCPeerConnection (for adding audio tracks). */
  peerConnection: RTCPeerConnection | null;
  /** Send a message on the control DataChannel. */
  sendControl: (message: ControlOutMessage) => void;
  /** Register a handler for control channel messages. */
  onControlMessage: (handler: (msg: ControlInMessage) => void) => void;
  /** Register a handler for debug channel messages. */
  onDebugMessage: (handler: (msg: unknown) => void) => void;
  /** Error message if connection failed. */
  error: string | null;
}

export function useVoiceSession(): UseVoiceSessionReturn {
  const [status, setStatus] = useState<ConnectionStatus>("idle");
  const [callId, setCallId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const pcRef = useRef<RTCPeerConnection | null>(null);
  const controlChannelRef = useRef<RTCDataChannel | null>(null);
  const debugChannelRef = useRef<RTCDataChannel | null>(null);
  const controlHandlerRef = useRef<((msg: ControlInMessage) => void) | null>(
    null,
  );
  const debugHandlerRef = useRef<((msg: unknown) => void) | null>(null);

  const cleanup = useCallback(async (currentCallId: string | null) => {
    if (pcRef.current) {
      pcRef.current.close();
      pcRef.current = null;
    }
    controlChannelRef.current = null;
    debugChannelRef.current = null;

    if (currentCallId) {
      try {
        await api.calls.end(currentCallId);
      } catch {
        // Best-effort cleanup
      }
    }
  }, []);

  const startSession = useCallback(async () => {
    setError(null);
    setStatus("connecting");

    try {
      // 1. Create call session
      const { call_id } = await api.calls.create();
      setCallId(call_id);

      // 2. Create RTCPeerConnection
      const pc = new RTCPeerConnection({
        iceServers: [{ urls: "stun:stun.l.google.com:19302" }],
      });
      pcRef.current = pc;

      // 3. Create DataChannels (must match server-side names)
      const controlChannel = pc.createDataChannel("control", { ordered: true });
      controlChannelRef.current = controlChannel;

      const debugChannel = pc.createDataChannel("debug", { ordered: true });
      debugChannelRef.current = debugChannel;

      // 4. Wire DataChannel message handlers
      controlChannel.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data) as ControlInMessage;
          controlHandlerRef.current?.(msg);
        } catch {
          // Ignore unparseable messages
        }
      };

      debugChannel.onmessage = (event) => {
        try {
          const msg: unknown = JSON.parse(event.data);
          debugHandlerRef.current?.(msg);
        } catch {
          // Ignore unparseable messages
        }
      };

      // 5. Handle connection state changes
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

      // 6. Add audio transceiver (sendrecv for bidirectional)
      pc.addTransceiver("audio", { direction: "sendrecv" });

      // 7. Create SDP offer
      const offer = await pc.createOffer();
      await pc.setLocalDescription(offer);

      // 8. Send offer to backend, get answer
      const answer = await api.calls.offer(call_id, offer.sdp!);
      await pc.setRemoteDescription(
        new RTCSessionDescription({ sdp: answer.sdp, type: "answer" }),
      );

      // 9. Handle ICE candidates
      pc.onicecandidate = (event) => {
        if (event.candidate) {
          api.calls
            .ice(call_id, event.candidate.candidate, event.candidate.sdpMid)
            .catch(() => {
              // Best-effort ICE trickle
            });
        }
      };
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Failed to start session";
      setError(message);
      setStatus("failed");
      await cleanup(callId);
    }
  }, [callId, cleanup]);

  const endSession = useCallback(async () => {
    const currentCallId = callId;
    setStatus("disconnected");
    setCallId(null);
    await cleanup(currentCallId);
  }, [callId, cleanup]);

  const sendControl = useCallback((message: ControlOutMessage) => {
    const channel = controlChannelRef.current;
    if (channel && channel.readyState === "open") {
      channel.send(JSON.stringify(message));
    }
  }, []);

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
    peerConnection: pcRef.current,
    sendControl,
    onControlMessage,
    onDebugMessage,
    error,
  };
}
