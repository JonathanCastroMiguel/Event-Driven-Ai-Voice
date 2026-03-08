import { act, renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { useDebugChannel } from "@/hooks/use-debug-channel";

function makeDebugEvent(
  turn_id: string,
  stage: string,
  overrides: Record<string, unknown> = {},
) {
  return {
    type: "debug_event",
    turn_id,
    stage,
    delta_ms: 0,
    total_ms: 0,
    ts: Date.now(),
    ...overrides,
  };
}

describe("useDebugChannel", () => {
  it("starts with empty state", () => {
    const { result } = renderHook(() => useDebugChannel());
    expect(result.current.state.turns).toHaveLength(0);
  });

  it("groups events by turn_id into timelines", () => {
    const { result } = renderHook(() => useDebugChannel());

    act(() => {
      result.current.handleDebugMessage(
        makeDebugEvent("turn-1", "speech_start", { delta_ms: 0, total_ms: 0 }),
      );
      result.current.handleDebugMessage(
        makeDebugEvent("turn-1", "speech_stop", {
          delta_ms: 500,
          total_ms: 500,
        }),
      );
      result.current.handleDebugMessage(
        makeDebugEvent("turn-1", "audio_committed", {
          delta_ms: 10,
          total_ms: 510,
        }),
      );
    });

    expect(result.current.state.turns).toHaveLength(1);
    expect(result.current.state.turns[0].turn_id).toBe("turn-1");
    expect(result.current.state.turns[0].stages).toHaveLength(3);
    expect(result.current.state.turns[0].stages[0].stage).toBe("speech_start");
    expect(result.current.state.turns[0].stages[2].total_ms).toBe(510);
  });

  it("splits delegate route events into main + specialist_stages", () => {
    const { result } = renderHook(() => useDebugChannel());

    act(() => {
      result.current.handleDebugMessage(
        makeDebugEvent("turn-d", "speech_start"),
      );
      result.current.handleDebugMessage(
        makeDebugEvent("turn-d", "route_result", {
          route_type: "delegate",
          label: "sales",
        }),
      );
      result.current.handleDebugMessage(
        makeDebugEvent("turn-d", "fill_silence", { delta_ms: 5 }),
      );
      result.current.handleDebugMessage(
        makeDebugEvent("turn-d", "specialist_sent", { delta_ms: 10 }),
      );
      result.current.handleDebugMessage(
        makeDebugEvent("turn-d", "specialist_processing", { delta_ms: 50 }),
      );
      result.current.handleDebugMessage(
        makeDebugEvent("turn-d", "specialist_ready", { delta_ms: 200 }),
      );
      result.current.handleDebugMessage(
        makeDebugEvent("turn-d", "generation_start", { delta_ms: 5 }),
      );
    });

    const turn = result.current.state.turns[0];
    expect(turn.is_delegate).toBe(true);
    expect(turn.specialist_stages).toHaveLength(3);
    expect(turn.specialist_stages[0].stage).toBe("specialist_sent");
    expect(turn.specialist_stages[2].stage).toBe("specialist_ready");
    // Main stages should not include specialist_* stages
    expect(turn.stages.find((s) => s.stage === "fill_silence")).toBeTruthy();
    expect(turn.stages.find((s) => s.stage === "generation_start")).toBeTruthy();
  });

  it("evicts oldest turn when FIFO exceeds 5", () => {
    const { result } = renderHook(() => useDebugChannel());

    act(() => {
      for (let i = 1; i <= 6; i++) {
        result.current.handleDebugMessage(
          makeDebugEvent(`turn-${i}`, "speech_start"),
        );
      }
    });

    expect(result.current.state.turns).toHaveLength(5);
    // Newest first
    expect(result.current.state.turns[0].turn_id).toBe("turn-6");
    // Oldest (turn-1) should be evicted
    expect(
      result.current.state.turns.find((t) => t.turn_id === "turn-1"),
    ).toBeUndefined();
  });

  it("marks turn as interrupted on barge_in", () => {
    const { result } = renderHook(() => useDebugChannel());

    act(() => {
      result.current.handleDebugMessage(
        makeDebugEvent("turn-b", "speech_start"),
      );
      result.current.handleDebugMessage(
        makeDebugEvent("turn-b", "generation_start"),
      );
      result.current.handleDebugMessage(
        makeDebugEvent("turn-b", "barge_in"),
      );
    });

    const turn = result.current.state.turns[0];
    expect(turn.barge_in).toBe(true);
    expect(turn.stages).toHaveLength(3);
    expect(turn.stages[2].stage).toBe("barge_in");
  });

  it("ignores non-debug_event messages", () => {
    const { result } = renderHook(() => useDebugChannel());

    act(() => {
      result.current.handleDebugMessage(null);
      result.current.handleDebugMessage("not an object");
      result.current.handleDebugMessage({ type: "other_event" });
      result.current.handleDebugMessage({ type: "debug_event" }); // no turn_id
    });

    expect(result.current.state.turns).toHaveLength(0);
  });

  it("clearState resets all turns", () => {
    const { result } = renderHook(() => useDebugChannel());

    act(() => {
      result.current.handleDebugMessage(
        makeDebugEvent("turn-1", "speech_start"),
      );
    });
    expect(result.current.state.turns).toHaveLength(1);

    act(() => {
      result.current.clearState();
    });
    expect(result.current.state.turns).toHaveLength(0);
  });
});
