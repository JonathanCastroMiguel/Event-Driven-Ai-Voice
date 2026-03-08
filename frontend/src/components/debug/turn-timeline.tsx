"use client";

import { cn } from "@/lib/utils";
import type { DebugStage, DebugTurnTimeline } from "@/hooks/use-debug-channel";

/** Human-readable stage labels. */
const STAGE_LABELS: Record<string, string> = {
  speech_start: "Speech Start",
  speech_stop: "Speech Stop",
  audio_committed: "Audio Committed",
  prompt_sent: "Prompt Sent",
  model_processing: "Model Processing",
  route_result: "Route Result",
  fill_silence: "Fill Silence",
  generation_start: "Gen Start",
  generation_finish: "Gen Finish",
  barge_in: "Barge In",
  specialist_sent: "Specialist Sent",
  specialist_processing: "Specialist Processing",
  specialist_ready: "Specialist Ready",
};

function stageLabel(stage: DebugStage): string {
  if (stage.stage === "route_result" && stage.label) {
    return `${stage.label} (${stage.route_type ?? "direct"})`;
  }
  return STAGE_LABELS[stage.stage] ?? stage.stage;
}

function deltaColor(delta_ms: number): string {
  if (delta_ms < 100) return "border-green-500 bg-green-500/10";
  if (delta_ms < 300) return "border-yellow-500 bg-yellow-500/10";
  return "border-red-500 bg-red-500/10";
}

function StageBox({ stage, isBarge }: { stage: DebugStage; isBarge?: boolean }) {
  return (
    <div
      className={cn(
        "flex flex-col items-center px-3 py-1 rounded border text-[10px] font-mono min-w-[90px] shrink-0",
        isBarge
          ? "border-red-600 bg-red-600/20 text-red-700"
          : deltaColor(stage.delta_ms),
      )}
    >
      <span className="font-semibold text-foreground whitespace-nowrap">
        {stageLabel(stage)}
      </span>
      <span className="text-muted-foreground">
        +{stage.delta_ms}ms / {stage.total_ms}ms
      </span>
    </div>
  );
}

function Arrow() {
  return (
    <span className="text-muted-foreground text-xs shrink-0 mx-1">
      &rarr;
    </span>
  );
}

interface TurnTimelineProps {
  turn: DebugTurnTimeline;
}

export function TurnTimeline({ turn }: TurnTimelineProps) {
  if (turn.stages.length === 0) return null;

  // For delegate routes, split stages around route_result
  if (turn.is_delegate && turn.specialist_stages.length > 0) {
    // Find route_result index to split main flow
    const routeIdx = turn.stages.findIndex((s) => s.stage === "route_result");
    const beforeRoute = routeIdx >= 0 ? turn.stages.slice(0, routeIdx + 1) : turn.stages;
    const afterRoute = routeIdx >= 0 ? turn.stages.slice(routeIdx + 1) : [];

    return (
      <div className="space-y-1">
        {/* Main row: stages up to route_result, then fill_silence + generation */}
        <div className="flex items-center overflow-x-auto gap-1 pb-1">
          {beforeRoute.map((s, i) => (
            <span key={i} className="flex items-center gap-1">
              {i > 0 && <Arrow />}
              <StageBox stage={s} />
            </span>
          ))}
          {afterRoute.map((s, i) => (
            <span key={`after-${i}`} className="flex items-center gap-1">
              <Arrow />
              <StageBox stage={s} isBarge={s.stage === "barge_in"} />
            </span>
          ))}
        </div>

        {/* Sub-flow row: specialist stages */}
        <div className="flex items-center overflow-x-auto gap-1 pl-8 border-l-2 border-dashed border-muted-foreground/30 ml-4">
          <span className="text-[10px] text-muted-foreground mr-1 shrink-0">specialist:</span>
          {turn.specialist_stages.map((s, i) => (
            <span key={i} className="flex items-center gap-1">
              {i > 0 && <Arrow />}
              <StageBox stage={s} />
            </span>
          ))}
        </div>
      </div>
    );
  }

  // Single row for direct routes
  return (
    <div className="flex items-center overflow-x-auto gap-1">
      {turn.stages.map((s, i) => (
        <span key={i} className="flex items-center gap-1">
          {i > 0 && <Arrow />}
          <StageBox stage={s} isBarge={s.stage === "barge_in"} />
        </span>
      ))}
    </div>
  );
}
