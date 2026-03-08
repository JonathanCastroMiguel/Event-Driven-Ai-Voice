"use client";

import { useCallback, useState } from "react";

/** A single stage in the pipeline timeline. */
export interface DebugStage {
  stage: string;
  delta_ms: number;
  total_ms: number;
  ts: number;
  label?: string;
  route_type?: "direct" | "delegate";
}

/** A complete turn timeline with main and optional specialist sub-flow. */
export interface DebugTurnTimeline {
  turn_id: string;
  stages: DebugStage[];
  is_delegate: boolean;
  specialist_stages: DebugStage[];
  barge_in: boolean;
}

interface DebugState {
  /** Last 5 turns (newest first). */
  turns: DebugTurnTimeline[];
}

interface UseDebugChannelReturn {
  state: DebugState;
  handleDebugMessage: (msg: unknown) => void;
  clearState: () => void;
}

const MAX_TURNS = 5;

const SPECIALIST_STAGES = new Set([
  "specialist_sent",
  "specialist_processing",
  "specialist_ready",
]);

function createEmptyState(): DebugState {
  return { turns: [] };
}

function createTurn(turn_id: string): DebugTurnTimeline {
  return {
    turn_id,
    stages: [],
    is_delegate: false,
    specialist_stages: [],
    barge_in: false,
  };
}

export function useDebugChannel(): UseDebugChannelReturn {
  const [state, setState] = useState<DebugState>(createEmptyState);

  const clearState = useCallback(() => {
    setState(createEmptyState());
  }, []);

  const handleDebugMessage = useCallback((raw: unknown) => {
    const msg = raw as Record<string, unknown>;
    if (!msg || typeof msg !== "object" || msg.type !== "debug_event") return;

    const turn_id = String(msg.turn_id ?? "");
    if (!turn_id) return;

    const stageEntry: DebugStage = {
      stage: String(msg.stage ?? ""),
      delta_ms: Number(msg.delta_ms ?? 0),
      total_ms: Number(msg.total_ms ?? 0),
      ts: Number(msg.ts ?? Date.now()),
    };

    if (msg.label !== undefined) stageEntry.label = String(msg.label);
    if (msg.route_type !== undefined)
      stageEntry.route_type = msg.route_type as "direct" | "delegate";

    setState((prev) => {
      const turns = [...prev.turns];
      let turnIndex = turns.findIndex((t) => t.turn_id === turn_id);

      if (turnIndex === -1) {
        // New turn — add at the front (newest first)
        const newTurn = createTurn(turn_id);
        turns.unshift(newTurn);
        turnIndex = 0;

        // Evict oldest if over limit
        if (turns.length > MAX_TURNS) {
          turns.pop();
        }
      }

      const turn = { ...turns[turnIndex] };

      if (stageEntry.stage === "barge_in") {
        turn.barge_in = true;
        turn.stages = [...turn.stages, stageEntry];
      } else if (SPECIALIST_STAGES.has(stageEntry.stage)) {
        turn.specialist_stages = [...turn.specialist_stages, stageEntry];
      } else {
        turn.stages = [...turn.stages, stageEntry];

        // Detect delegate route
        if (
          stageEntry.stage === "route_result" &&
          stageEntry.route_type === "delegate"
        ) {
          turn.is_delegate = true;
        }
      }

      turns[turnIndex] = turn;
      return { turns };
    });
  }, []);

  return { state, handleDebugMessage, clearState };
}
