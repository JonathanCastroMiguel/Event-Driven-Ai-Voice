/**
 * Integration tests for the debug event pipeline.
 *
 * Simulates realistic event sequences matching what the Coordinator emits
 * and verifies the full render pipeline: useDebugChannel → DebugPanel → TurnTimeline.
 */
import { act, render, renderHook, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { DebugPanel } from "@/components/debug/debug-panel";
import { useDebugChannel } from "@/hooks/use-debug-channel";
import type { DebugTurnTimeline } from "@/hooks/use-debug-channel";

// ---------------------------------------------------------------------------
// Helpers — realistic event sequences matching Coordinator._send_debug output
// ---------------------------------------------------------------------------

let seqTs = 1000;

function resetTs() {
  seqTs = 1000;
}

function debugEvent(
  turn_id: string,
  stage: string,
  deltaSinceLastMs: number,
  totalMs: number,
  extra: Record<string, unknown> = {},
) {
  seqTs += deltaSinceLastMs;
  return {
    type: "debug_event",
    turn_id,
    stage,
    delta_ms: deltaSinceLastMs,
    total_ms: totalMs,
    ts: seqTs,
    ...extra,
  };
}

/** 8-stage direct route (e.g. "greeting") as emitted by Coordinator. */
function directRouteEvents(turn_id: string) {
  resetTs();
  return [
    debugEvent(turn_id, "speech_start", 0, 0),
    debugEvent(turn_id, "speech_stop", 620, 620),
    debugEvent(turn_id, "audio_committed", 12, 632),
    debugEvent(turn_id, "prompt_sent", 8, 640),
    debugEvent(turn_id, "model_processing", 45, 685),
    debugEvent(turn_id, "route_result", 230, 915, {
      label: "greeting",
      route_type: "direct",
    }),
    debugEvent(turn_id, "generation_start", 5, 920),
    debugEvent(turn_id, "generation_finish", 1200, 2120),
  ];
}

/** 12-stage delegate route (e.g. "sales") as emitted by Coordinator. */
function delegateRouteEvents(turn_id: string) {
  resetTs();
  return [
    debugEvent(turn_id, "speech_start", 0, 0),
    debugEvent(turn_id, "speech_stop", 800, 800),
    debugEvent(turn_id, "audio_committed", 10, 810),
    debugEvent(turn_id, "prompt_sent", 6, 816),
    debugEvent(turn_id, "model_processing", 38, 854),
    debugEvent(turn_id, "route_result", 310, 1164, {
      label: "sales",
      route_type: "delegate",
    }),
    debugEvent(turn_id, "fill_silence", 3, 1167),
    debugEvent(turn_id, "specialist_sent", 15, 1182),
    debugEvent(turn_id, "specialist_processing", 42, 1224),
    debugEvent(turn_id, "specialist_ready", 480, 1704),
    debugEvent(turn_id, "generation_start", 8, 1712),
    debugEvent(turn_id, "generation_finish", 1500, 3212),
  ];
}

/** Barge-in during generation (interrupted turn). */
function bargeInEvents(turn_id: string) {
  resetTs();
  return [
    debugEvent(turn_id, "speech_start", 0, 0),
    debugEvent(turn_id, "speech_stop", 400, 400),
    debugEvent(turn_id, "audio_committed", 10, 410),
    debugEvent(turn_id, "prompt_sent", 5, 415),
    debugEvent(turn_id, "model_processing", 40, 455),
    debugEvent(turn_id, "route_result", 200, 655, {
      label: "billing",
      route_type: "direct",
    }),
    debugEvent(turn_id, "generation_start", 3, 658),
    debugEvent(turn_id, "barge_in", 350, 1008),
  ];
}

// ---------------------------------------------------------------------------
// Feed events into hook and return resulting turns for rendering
// ---------------------------------------------------------------------------

function feedEvents(events: Record<string, unknown>[][]): DebugTurnTimeline[] {
  const { result } = renderHook(() => useDebugChannel());

  for (const batch of events) {
    act(() => {
      for (const ev of batch) {
        result.current.handleDebugMessage(ev);
      }
    });
  }

  return result.current.state.turns;
}

// ---------------------------------------------------------------------------
// Integration: Hook + DebugPanel + TurnTimeline
// ---------------------------------------------------------------------------

describe("Debug pipeline integration", () => {
  describe("Direct route flow", () => {
    it("processes 8 stages and renders a complete single-row timeline", () => {
      const turns = feedEvents([directRouteEvents("direct-1")]);

      expect(turns).toHaveLength(1);
      expect(turns[0].stages).toHaveLength(8);
      expect(turns[0].is_delegate).toBe(false);
      expect(turns[0].specialist_stages).toHaveLength(0);
      expect(turns[0].barge_in).toBe(false);

      // Render the panel and verify visual output
      render(<DebugPanel turns={turns} />);

      expect(screen.getByText("Speech Start")).toBeInTheDocument();
      expect(screen.getByText("Speech Stop")).toBeInTheDocument();
      expect(screen.getByText("Audio Committed")).toBeInTheDocument();
      expect(screen.getByText("Prompt Sent")).toBeInTheDocument();
      expect(screen.getByText("Model Processing")).toBeInTheDocument();
      expect(screen.getByText("greeting (direct)")).toBeInTheDocument();
      expect(screen.getByText("Gen Start")).toBeInTheDocument();
      expect(screen.getByText("Gen Finish")).toBeInTheDocument();

      // Verify timing labels are displayed
      expect(screen.getByText("+620ms / 620ms")).toBeInTheDocument(); // speech_stop
      expect(screen.getByText("+1200ms / 2120ms")).toBeInTheDocument(); // generation_finish
    });

    it("color-codes stages: green for fast, yellow for moderate, red for slow", () => {
      const turns = feedEvents([directRouteEvents("color-1")]);
      const { container } = render(<DebugPanel turns={turns} />);

      // prompt_sent: delta=8ms → green
      const greenBoxes = container.querySelectorAll(".border-green-500");
      expect(greenBoxes.length).toBeGreaterThan(0);

      // route_result: delta=230ms → yellow
      const yellowBoxes = container.querySelectorAll(".border-yellow-500");
      expect(yellowBoxes.length).toBeGreaterThan(0);

      // generation_finish: delta=1200ms → red
      const redBoxes = container.querySelectorAll(".border-red-500");
      expect(redBoxes.length).toBeGreaterThan(0);
    });
  });

  describe("Delegate route flow", () => {
    it("processes 12 stages and renders a branching timeline", () => {
      const turns = feedEvents([delegateRouteEvents("delegate-1")]);

      expect(turns).toHaveLength(1);
      expect(turns[0].is_delegate).toBe(true);
      expect(turns[0].specialist_stages).toHaveLength(3);

      // Main stages: 9 (all except specialist_*)
      expect(turns[0].stages).toHaveLength(9);

      const { container } = render(<DebugPanel turns={turns} />);

      // Main flow stages present
      expect(screen.getByText("sales (delegate)")).toBeInTheDocument();
      expect(screen.getByText("Fill Silence")).toBeInTheDocument();
      expect(screen.getByText("Gen Start")).toBeInTheDocument();
      expect(screen.getByText("Gen Finish")).toBeInTheDocument();

      // Specialist sub-flow present
      expect(screen.getByText("Specialist Sent")).toBeInTheDocument();
      expect(screen.getByText("Specialist Processing")).toBeInTheDocument();
      expect(screen.getByText("Specialist Ready")).toBeInTheDocument();

      // Sub-flow label visible (branching indicator)
      expect(container.textContent).toContain("specialist:");
    });
  });

  describe("Barge-in flow", () => {
    it("renders interrupted timeline with barge-in indicator", () => {
      const turns = feedEvents([bargeInEvents("barge-1")]);

      expect(turns).toHaveLength(1);
      expect(turns[0].barge_in).toBe(true);
      expect(turns[0].stages).toHaveLength(8);

      render(<DebugPanel turns={turns} />);

      expect(screen.getByText("billing (direct)")).toBeInTheDocument();
      expect(screen.getByText("Barge In")).toBeInTheDocument();
      // No generation_finish since it was interrupted
      expect(screen.queryByText("Gen Finish")).not.toBeInTheDocument();
    });

    it("renders barge-in box with red styling", () => {
      const turns = feedEvents([bargeInEvents("barge-style")]);
      const { container } = render(<DebugPanel turns={turns} />);

      // Barge-in box should have red styling (border-red-600)
      const bargeBox = container.querySelector(".border-red-600");
      expect(bargeBox).toBeInTheDocument();
      expect(bargeBox?.textContent).toContain("Barge In");
    });
  });

  describe("FIFO multi-turn stack", () => {
    it("renders 5 turns newest-first, evicts oldest on 6th", () => {
      const allEvents = [];
      for (let i = 1; i <= 6; i++) {
        allEvents.push(directRouteEvents(`turn-${i}`));
      }
      const turns = feedEvents(allEvents);

      expect(turns).toHaveLength(5);
      expect(turns[0].turn_id).toBe("turn-6"); // newest first
      expect(turns[4].turn_id).toBe("turn-2"); // oldest surviving
      // turn-1 evicted
      expect(turns.find((t) => t.turn_id === "turn-1")).toBeUndefined();

      // Render and verify multiple timelines are shown
      render(<DebugPanel turns={turns} />);

      // Should have multiple "Speech Start" labels (one per turn)
      const speechStarts = screen.getAllByText("Speech Start");
      expect(speechStarts).toHaveLength(5);
    });
  });

  describe("Mixed flow sequence", () => {
    it("handles interleaved direct, delegate, and barge-in turns", () => {
      const turns = feedEvents([
        directRouteEvents("mixed-direct"),
        delegateRouteEvents("mixed-delegate"),
        bargeInEvents("mixed-barge"),
      ]);

      expect(turns).toHaveLength(3);

      // Newest first
      expect(turns[0].turn_id).toBe("mixed-barge");
      expect(turns[0].barge_in).toBe(true);

      expect(turns[1].turn_id).toBe("mixed-delegate");
      expect(turns[1].is_delegate).toBe(true);

      expect(turns[2].turn_id).toBe("mixed-direct");
      expect(turns[2].is_delegate).toBe(false);

      // Full render
      const { container } = render(<DebugPanel turns={turns} />);

      // All three route labels visible
      expect(screen.getByText("greeting (direct)")).toBeInTheDocument();
      expect(screen.getByText("sales (delegate)")).toBeInTheDocument();
      expect(screen.getByText("billing (direct)")).toBeInTheDocument();
      expect(screen.getByText("Barge In")).toBeInTheDocument();
      expect(container.textContent).toContain("specialist:");
    });
  });

  describe("Progressive rendering", () => {
    it("renders stages incrementally as events arrive", () => {
      const { result } = renderHook(() => useDebugChannel());

      // First event only
      act(() => {
        result.current.handleDebugMessage(
          debugEvent("prog-1", "speech_start", 0, 0),
        );
      });

      const { rerender } = render(
        <DebugPanel turns={result.current.state.turns} />,
      );
      expect(screen.getByText("Speech Start")).toBeInTheDocument();
      expect(screen.queryByText("Speech Stop")).not.toBeInTheDocument();

      // Second event arrives
      act(() => {
        result.current.handleDebugMessage(
          debugEvent("prog-1", "speech_stop", 500, 500),
        );
      });

      rerender(<DebugPanel turns={result.current.state.turns} />);
      expect(screen.getByText("Speech Start")).toBeInTheDocument();
      expect(screen.getByText("Speech Stop")).toBeInTheDocument();
    });
  });

  describe("Empty state", () => {
    it("shows waiting message when no turns exist", () => {
      render(<DebugPanel turns={[]} />);
      expect(
        screen.getByText("Debug enabled. Waiting for events..."),
      ).toBeInTheDocument();
    });
  });
});
