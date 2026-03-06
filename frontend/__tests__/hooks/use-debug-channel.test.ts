import { act, renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { useDebugChannel } from "@/hooks/use-debug-channel";

describe("useDebugChannel", () => {
  it("starts with empty state", () => {
    const { result } = renderHook(() => useDebugChannel());
    expect(result.current.state.turns).toHaveLength(0);
    expect(result.current.state.fsmState).toBeNull();
    expect(result.current.state.routing).toBeNull();
    expect(result.current.state.events).toHaveLength(0);
    expect(result.current.state.latencies).toHaveLength(0);
    expect(result.current.isEnabled).toBe(false);
  });

  it("handles turn_update event", () => {
    const { result } = renderHook(() => useDebugChannel());

    act(() => {
      result.current.handleDebugMessage({
        type: "turn_update",
        turn_id: "abc-123",
        text: "hola",
        route_a: "simple",
        route_b: null,
        policy_key: "greeting",
        ts: 1000,
      });
    });

    expect(result.current.state.turns).toHaveLength(1);
    expect(result.current.state.turns[0].text).toBe("hola");
    expect(result.current.state.turns[0].routeA).toBe("simple");
    expect(result.current.isEnabled).toBe(true);
  });

  it("handles fsm_state event", () => {
    const { result } = renderHook(() => useDebugChannel());

    act(() => {
      result.current.handleDebugMessage({
        type: "fsm_state",
        state: "thinking",
      });
    });

    expect(result.current.state.fsmState).toBe("thinking");
  });

  it("handles routing event", () => {
    const { result } = renderHook(() => useDebugChannel());

    act(() => {
      result.current.handleDebugMessage({
        type: "routing",
        route_a_label: "domain",
        route_a_confidence: 0.85,
        route_b_label: "billing",
        route_b_confidence: 0.9,
        short_circuit: null,
        fallback_used: false,
      });
    });

    expect(result.current.state.routing).not.toBeNull();
    expect(result.current.state.routing!.routeALabel).toBe("domain");
    expect(result.current.state.routing!.routeAConfidence).toBe(0.85);
    expect(result.current.state.routing!.routeBLabel).toBe("billing");
  });

  it("handles latency event", () => {
    const { result } = renderHook(() => useDebugChannel());

    act(() => {
      result.current.handleDebugMessage({
        type: "latency",
        turn_processing_ms: 42,
        ts: 1000,
      });
    });

    expect(result.current.state.latencies).toHaveLength(1);
    expect(result.current.state.latencies[0].ms).toBe(42);
  });

  it("limits events to 100", () => {
    const { result } = renderHook(() => useDebugChannel());

    act(() => {
      for (let i = 0; i < 110; i++) {
        result.current.handleDebugMessage({
          type: "test",
          index: i,
        });
      }
    });

    expect(result.current.state.events).toHaveLength(100);
  });

  it("ignores invalid messages", () => {
    const { result } = renderHook(() => useDebugChannel());

    act(() => {
      result.current.handleDebugMessage(null);
      result.current.handleDebugMessage("not an object");
      result.current.handleDebugMessage(42);
    });

    expect(result.current.state.events).toHaveLength(0);
  });
});
