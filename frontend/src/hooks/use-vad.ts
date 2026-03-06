"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import type { ControlOutMessage } from "@/lib/types";

interface UseVADOptions {
  /** The audio stream to monitor for speech. */
  stream: MediaStream | null;
  /** Callback to send control messages (speech_started/speech_ended). */
  sendControl: (message: ControlOutMessage) => void;
  /** Whether the VAD should be active. */
  enabled: boolean;
}

interface UseVADReturn {
  /** Whether speech is currently detected. */
  isSpeaking: boolean;
  /** Whether the VAD model is loaded and ready. */
  isReady: boolean;
  /** Error message if VAD initialization failed. */
  error: string | null;
}

export function useVAD({
  stream,
  sendControl,
  enabled,
}: UseVADOptions): UseVADReturn {
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [isReady, setIsReady] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Use refs for the VAD instance so we can clean up
  const vadRef = useRef<{ destroy: () => void } | null>(null);
  const initializingRef = useRef(false);

  const initVAD = useCallback(async () => {
    if (!stream || !enabled || initializingRef.current) return;
    initializingRef.current = true;

    try {
      // Dynamic import to avoid SSR issues (WASM)
      const { MicVAD } = await import("@ricky0123/vad-web");

      // Capture stream in closure for getStream callback
      const capturedStream = stream;
      const vad = await MicVAD.new({
        getStream: () => Promise.resolve(capturedStream),
        onSpeechStart: () => {
          setIsSpeaking(true);
          sendControl({ type: "speech_started", ts: Date.now() });
        },
        onSpeechEnd: () => {
          setIsSpeaking(false);
          sendControl({ type: "speech_ended", ts: Date.now() });
        },
        // Silero VAD parameters tuned for low latency
        positiveSpeechThreshold: 0.8,
        negativeSpeechThreshold: 0.4,
        minSpeechMs: 100,
        preSpeechPadMs: 30,
        redemptionMs: 250,
      });

      vad.start();
      vadRef.current = vad;
      setIsReady(true);
      setError(null);
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "VAD initialization failed";
      setError(message);
      setIsReady(false);
    } finally {
      initializingRef.current = false;
    }
  }, [stream, enabled, sendControl]);

  // Initialize VAD when stream becomes available
  useEffect(() => {
    if (stream && enabled) {
      initVAD();
    }

    return () => {
      if (vadRef.current) {
        vadRef.current.destroy();
        vadRef.current = null;
        setIsReady(false);
        setIsSpeaking(false);
      }
    };
  }, [stream, enabled, initVAD]);

  return { isSpeaking, isReady, error };
}
