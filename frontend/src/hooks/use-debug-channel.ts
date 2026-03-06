"use client";

import { useCallback, useState } from "react";

import type { DebugEvent } from "@/lib/types";

interface DebugState {
  /** Turn history from turn_update events. */
  turns: DebugTurn[];
  /** Current FSM state. */
  fsmState: string | null;
  /** Latest routing decision. */
  routing: DebugRouting | null;
  /** All debug events (most recent first, max 100). */
  events: DebugEvent[];
  /** Latency measurements. */
  latencies: DebugLatency[];
}

export interface DebugTurn {
  turnId: string;
  text: string;
  routeA: string;
  routeB: string | null;
  policyKey: string | null;
  specialist: string | null;
  ts: number;
}

export interface DebugRouting {
  routeALabel: string;
  routeAConfidence: number;
  routeBLabel: string | null;
  routeBConfidence: number | null;
  shortCircuit: string | null;
  fallbackUsed: boolean;
}

export interface DebugLatency {
  type: string;
  ms: number;
  ts: number;
}

interface UseDebugChannelReturn {
  /** Current debug state. */
  state: DebugState;
  /** Whether debug mode is enabled. */
  isEnabled: boolean;
  /** Handle an incoming debug message (register as handler). */
  handleDebugMessage: (msg: unknown) => void;
}

const MAX_EVENTS = 100;

function createEmptyState(): DebugState {
  return {
    turns: [],
    fsmState: null,
    routing: null,
    events: [],
    latencies: [],
  };
}

export function useDebugChannel(): UseDebugChannelReturn {
  const [state, setState] = useState<DebugState>(createEmptyState);
  const [isEnabled, setIsEnabled] = useState(false);

  const handleDebugMessage = useCallback((raw: unknown) => {
    const msg = raw as DebugEvent;
    if (!msg || typeof msg !== "object" || !("type" in msg)) return;

    setIsEnabled(true);

    setState((prev) => {
      const events = [msg, ...prev.events].slice(0, MAX_EVENTS);
      const next = { ...prev, events };

      switch (msg.type) {
        case "turn_update":
          next.turns = [
            ...prev.turns,
            {
              turnId: String(msg.turn_id ?? ""),
              text: String(msg.text ?? ""),
              routeA: String(msg.route_a ?? ""),
              routeB: msg.route_b ? String(msg.route_b) : null,
              policyKey: msg.policy_key ? String(msg.policy_key) : null,
              specialist: msg.specialist ? String(msg.specialist) : null,
              ts: Number(msg.ts ?? Date.now()),
            },
          ];
          break;

        case "fsm_state":
          next.fsmState = String(msg.state ?? "unknown");
          break;

        case "routing":
          next.routing = {
            routeALabel: String(msg.route_a_label ?? ""),
            routeAConfidence: Number(msg.route_a_confidence ?? 0),
            routeBLabel: msg.route_b_label
              ? String(msg.route_b_label)
              : null,
            routeBConfidence: msg.route_b_confidence
              ? Number(msg.route_b_confidence)
              : null,
            shortCircuit: msg.short_circuit
              ? String(msg.short_circuit)
              : null,
            fallbackUsed: Boolean(msg.fallback_used),
          };
          break;

        case "latency":
          next.latencies = [
            ...prev.latencies,
            {
              type: String(msg.latency_type ?? "turn_processing"),
              ms: Number(msg.turn_processing_ms ?? msg.ms ?? 0),
              ts: Number(msg.ts ?? Date.now()),
            },
          ];
          break;
      }

      return next;
    });
  }, []);

  return { state, isEnabled, handleDebugMessage };
}
