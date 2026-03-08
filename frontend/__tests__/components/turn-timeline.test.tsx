import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { TurnTimeline } from "@/components/debug/turn-timeline";
import type { DebugTurnTimeline } from "@/hooks/use-debug-channel";

function makeTurn(overrides: Partial<DebugTurnTimeline> = {}): DebugTurnTimeline {
  return {
    turn_id: "test-turn",
    stages: [],
    is_delegate: false,
    specialist_stages: [],
    barge_in: false,
    ...overrides,
  };
}

describe("TurnTimeline", () => {
  it("renders single-row for direct route", () => {
    const turn = makeTurn({
      stages: [
        { stage: "speech_start", delta_ms: 0, total_ms: 0, ts: 1000 },
        { stage: "speech_stop", delta_ms: 500, total_ms: 500, ts: 1500 },
        {
          stage: "route_result",
          delta_ms: 100,
          total_ms: 600,
          ts: 1600,
          label: "greeting",
          route_type: "direct",
        },
        { stage: "generation_start", delta_ms: 10, total_ms: 610, ts: 1610 },
        { stage: "generation_finish", delta_ms: 200, total_ms: 810, ts: 1810 },
      ],
    });

    const { container } = render(<TurnTimeline turn={turn} />);
    expect(screen.getByText("Speech Start")).toBeInTheDocument();
    expect(screen.getByText("greeting (direct)")).toBeInTheDocument();
    expect(screen.getByText("Gen Finish")).toBeInTheDocument();
    // Should NOT have specialist sub-flow label
    expect(container.textContent).not.toContain("specialist:");
  });

  it("renders branching layout for delegate route", () => {
    const turn = makeTurn({
      is_delegate: true,
      stages: [
        { stage: "speech_start", delta_ms: 0, total_ms: 0, ts: 1000 },
        {
          stage: "route_result",
          delta_ms: 100,
          total_ms: 100,
          ts: 1100,
          label: "sales",
          route_type: "delegate",
        },
        { stage: "fill_silence", delta_ms: 5, total_ms: 105, ts: 1105 },
        { stage: "generation_start", delta_ms: 300, total_ms: 405, ts: 1405 },
      ],
      specialist_stages: [
        { stage: "specialist_sent", delta_ms: 10, total_ms: 110, ts: 1110 },
        { stage: "specialist_processing", delta_ms: 50, total_ms: 160, ts: 1160 },
        { stage: "specialist_ready", delta_ms: 200, total_ms: 360, ts: 1360 },
      ],
    });

    const { container } = render(<TurnTimeline turn={turn} />);
    expect(screen.getByText("sales (delegate)")).toBeInTheDocument();
    expect(screen.getByText("Fill Silence")).toBeInTheDocument();
    expect(screen.getByText("Specialist Sent")).toBeInTheDocument();
    expect(screen.getByText("Specialist Ready")).toBeInTheDocument();
    // Should have specialist sub-flow label
    expect(container.textContent).toContain("specialist:");
  });

  it("renders barge-in as truncated timeline", () => {
    const turn = makeTurn({
      barge_in: true,
      stages: [
        { stage: "speech_start", delta_ms: 0, total_ms: 0, ts: 1000 },
        { stage: "generation_start", delta_ms: 300, total_ms: 300, ts: 1300 },
        { stage: "barge_in", delta_ms: 100, total_ms: 400, ts: 1400 },
      ],
    });

    render(<TurnTimeline turn={turn} />);
    expect(screen.getByText("Barge In")).toBeInTheDocument();
    // No generation_finish
    expect(screen.queryByText("Gen Finish")).not.toBeInTheDocument();
  });

  it("applies green color for fast stages (<100ms)", () => {
    const turn = makeTurn({
      stages: [
        { stage: "speech_start", delta_ms: 50, total_ms: 50, ts: 1000 },
      ],
    });

    const { container } = render(<TurnTimeline turn={turn} />);
    const box = container.querySelector(".border-green-500");
    expect(box).toBeInTheDocument();
  });

  it("applies yellow color for moderate stages (100-300ms)", () => {
    const turn = makeTurn({
      stages: [
        { stage: "speech_stop", delta_ms: 150, total_ms: 150, ts: 1000 },
      ],
    });

    const { container } = render(<TurnTimeline turn={turn} />);
    const box = container.querySelector(".border-yellow-500");
    expect(box).toBeInTheDocument();
  });

  it("applies red color for slow stages (>=300ms)", () => {
    const turn = makeTurn({
      stages: [
        { stage: "model_processing", delta_ms: 450, total_ms: 450, ts: 1000 },
      ],
    });

    const { container } = render(<TurnTimeline turn={turn} />);
    const box = container.querySelector(".border-red-500");
    expect(box).toBeInTheDocument();
  });

  it("renders nothing for empty stages", () => {
    const turn = makeTurn({ stages: [] });
    const { container } = render(<TurnTimeline turn={turn} />);
    expect(container.innerHTML).toBe("");
  });
});
