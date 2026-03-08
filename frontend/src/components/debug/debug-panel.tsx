"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { DebugTurnTimeline } from "@/hooks/use-debug-channel";

import { TurnTimeline } from "./turn-timeline";

interface DebugPanelProps {
  turns: DebugTurnTimeline[];
}

export function DebugPanel({ turns }: DebugPanelProps) {
  return (
    <div className="w-full mx-auto">
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-xs font-medium text-muted-foreground">
            Pipeline Timeline (last 5 turns)
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 min-h-[280px]">
          {turns.length === 0 ? (
            <span className="text-xs text-muted-foreground">
              Debug enabled. Waiting for events...
            </span>
          ) : (
            turns.map((turn) => (
              <div
                key={turn.turn_id}
                className="border-b last:border-0 pb-2 last:pb-0"
              >
                <TurnTimeline turn={turn} />
              </div>
            ))
          )}
        </CardContent>
      </Card>
    </div>
  );
}
