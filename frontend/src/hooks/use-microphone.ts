"use client";

import { useCallback, useRef, useState } from "react";

type MicStatus = "idle" | "requesting" | "active" | "denied" | "error";

interface UseMicrophoneReturn {
  /** Current microphone status. */
  status: MicStatus;
  /** The raw MediaStream from getUserMedia. */
  stream: MediaStream | null;
  /** Request microphone permission and start capture. */
  startMicrophone: () => Promise<MediaStream | null>;
  /** Stop microphone capture and release resources. */
  stopMicrophone: () => void;
  /** Add the microphone audio track to an RTCPeerConnection. */
  attachToConnection: (pc: RTCPeerConnection) => void;
}

export function useMicrophone(): UseMicrophoneReturn {
  const [status, setStatus] = useState<MicStatus>("idle");
  const streamRef = useRef<MediaStream | null>(null);

  const startMicrophone = useCallback(async (): Promise<MediaStream | null> => {
    setStatus("requesting");

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
        video: false,
      });
      streamRef.current = stream;
      setStatus("active");
      return stream;
    } catch (err) {
      if (err instanceof DOMException && err.name === "NotAllowedError") {
        setStatus("denied");
      } else {
        setStatus("error");
      }
      return null;
    }
  }, []);

  const stopMicrophone = useCallback(() => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    }
    setStatus("idle");
  }, []);

  const attachToConnection = useCallback((pc: RTCPeerConnection) => {
    const stream = streamRef.current;
    if (!stream) return;

    const audioTrack = stream.getAudioTracks()[0];
    if (audioTrack) {
      // Find the audio sender (from the transceiver we added) and replace its track
      const sender = pc.getSenders().find((s) => s.track === null || s.track?.kind === "audio");
      if (sender) {
        sender.replaceTrack(audioTrack);
      } else {
        pc.addTrack(audioTrack, stream);
      }
    }
  }, []);

  return {
    status,
    stream: streamRef.current,
    startMicrophone,
    stopMicrophone,
    attachToConnection,
  };
}
