"use client";

import { cn } from "@/lib/utils";
import type { DebugStage, DebugTurnTimeline } from "@/hooks/use-debug-channel";

/** Human-readable stage labels. */
const STAGE_LABELS: Record<string, string> = {
  speech_start: "Speech Start",
  speech_stop: "Speech Stop",
  audio_committed: "Audio Committed",
  prompt_sent: "Prompt Sent",
  model_processing: "Model Inference",
  route_result: "Route Result",
  fill_silence: "Fill Silence",
  generation_start: "Gen Start",
  generation_finish: "Gen Finish",
  audio_playback_start: "Audio Start",
  audio_playback_end: "Audio End",
  barge_in: "Barge In",
  specialist_sent: "Specialist Sent",
  specialist_processing: "Specialist Processing",
  specialist_ready: "Specialist Ready",
};

function stageLabel(stage: DebugStage): string {
  if (stage.stage === "route_result") {
    if (stage.route_type === "delegate" && stage.label) {
      return `Delegate \u2192 ${stage.label}`;
    }
    return "Direct Response";
  }
  return STAGE_LABELS[stage.stage] ?? stage.stage;
}

function deltaColor(_delta_ms: number): string {
  return "border-green-500 bg-green-500/10";
}

function bridgeTimingLabel(stage: DebugStage): string | null {
  if (stage.send_to_created_ms !== undefined) return `bridge: ${stage.send_to_created_ms}ms`;
  if (stage.created_to_done_ms !== undefined) return `bridge: ${stage.created_to_done_ms}ms`;
  return null;
}

function StageBox({ stage, isBarge }: { stage: DebugStage; isBarge?: boolean }) {
  const bridgeTiming = bridgeTimingLabel(stage);
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
      {bridgeTiming && (
        <span className="text-blue-500/70">{bridgeTiming}</span>
      )}
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

/** Compute silence duration: Speech Stop → Audio Start (ms). */
function computeSilenceMs(stages: DebugStage[]): number | null {
  const speechStop = stages.find((s) => s.stage === "speech_stop");
  const audioStart = stages.find((s) => s.stage === "audio_playback_start");
  if (!speechStop || !audioStart) return null;
  return audioStart.ts - speechStop.ts;
}

function silenceColor(_ms: number): string {
  return "text-green-600";
}

function SilenceBanner({ stages }: { stages: DebugStage[] }) {
  const silenceMs = computeSilenceMs(stages);
  if (silenceMs === null) return null;
  return (
    <div className="flex items-center gap-2 mb-1 text-[11px] font-mono">
      <span className="text-muted-foreground">Response time:</span>
      <span className={cn("font-bold", silenceColor(silenceMs))}>
        {silenceMs}ms
      </span>
      <span className="text-muted-foreground/60">
        (Speech Stop → Audio Start + routing)
      </span>
    </div>
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

    // Specialist row starts after route_result column.
    // Each stage + arrow pair occupies one grid column.
    // beforeRoute has N stages → occupies columns 1..N (with arrows between).
    // The specialist row should start at column N+1, forking from route_result.
    const specialistColStart = beforeRoute.length + 1;

    return (
      <div className="space-y-1">
        <SilenceBanner stages={turn.stages} />
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

        {/* Sub-flow row: specialist stages — offset dynamically to fork from route_result */}
        <div className="flex items-center overflow-x-auto gap-1">
          {/* Spacer: invisible replicas of beforeRoute stages to align the specialist row */}
          <div className="flex items-center gap-1 shrink-0" style={{ visibility: "hidden" }}>
            {beforeRoute.map((s, i) => (
              <span key={i} className="flex items-center gap-1">
                {i > 0 && <Arrow />}
                <StageBox stage={s} />
              </span>
            ))}
          </div>
          <div className="flex items-center gap-1 border-l-2 border-dashed border-muted-foreground/30 pl-2">
            <span className="text-[10px] text-muted-foreground mr-1 shrink-0">specialist:</span>
            {turn.specialist_stages.map((s, i) => (
              <span key={i} className="flex items-center gap-1">
                {i > 0 && <Arrow />}
                <StageBox stage={s} />
              </span>
            ))}
          </div>
        </div>
      </div>
    );
  }

  // Single row for direct routes
  return (
    <div>
      <SilenceBanner stages={turn.stages} />
      <div className="flex items-center overflow-x-auto gap-1">
      {turn.stages.map((s, i) => (
        <span key={i} className="flex items-center gap-1">
          {i > 0 && <Arrow />}
          <StageBox stage={s} isBarge={s.stage === "barge_in"} />
        </span>
      ))}
      </div>
    </div>
  );
}
