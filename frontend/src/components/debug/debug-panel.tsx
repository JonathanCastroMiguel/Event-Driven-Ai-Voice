"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type {
  DebugTurn,
  DebugRouting,
  DebugLatency,
} from "@/hooks/use-debug-channel";
import type { DebugEvent } from "@/lib/types";

interface DebugPanelProps {
  turns: DebugTurn[];
  fsmState: string | null;
  routing: DebugRouting | null;
  events: DebugEvent[];
  latencies: DebugLatency[];
}

export function DebugPanel({
  turns,
  fsmState,
  routing,
  events,
  latencies,
}: DebugPanelProps) {
  return (
    <div className="w-full max-w-4xl mx-auto space-y-4">
      {/* Top row: FSM + Routing + Latency */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* FSM State */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-xs font-medium text-muted-foreground">
              FSM State
            </CardTitle>
          </CardHeader>
          <CardContent>
            <Badge variant={fsmState === "done" ? "default" : "secondary"}>
              {fsmState ?? "—"}
            </Badge>
          </CardContent>
        </Card>

        {/* Routing */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-xs font-medium text-muted-foreground">
              Last Routing
            </CardTitle>
          </CardHeader>
          <CardContent className="text-xs space-y-1">
            {routing ? (
              <>
                <div className="flex justify-between">
                  <span>Route A:</span>
                  <span className="font-mono">
                    {routing.routeALabel} ({(routing.routeAConfidence * 100).toFixed(0)}%)
                  </span>
                </div>
                {routing.routeBLabel && (
                  <div className="flex justify-between">
                    <span>Route B:</span>
                    <span className="font-mono">
                      {routing.routeBLabel} ({((routing.routeBConfidence ?? 0) * 100).toFixed(0)}%)
                    </span>
                  </div>
                )}
                {routing.shortCircuit && (
                  <div className="flex justify-between">
                    <span>Short circuit:</span>
                    <Badge variant="outline" className="text-[10px]">
                      {routing.shortCircuit}
                    </Badge>
                  </div>
                )}
                {routing.fallbackUsed && (
                  <Badge variant="destructive" className="text-[10px]">
                    LLM fallback
                  </Badge>
                )}
              </>
            ) : (
              <span className="text-muted-foreground">—</span>
            )}
          </CardContent>
        </Card>

        {/* Latency */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-xs font-medium text-muted-foreground">
              Latency
            </CardTitle>
          </CardHeader>
          <CardContent className="text-xs">
            {latencies.length > 0 ? (
              <div className="space-y-1">
                {latencies.slice(-3).map((l, i) => (
                  <div key={i} className="flex justify-between font-mono">
                    <span>{l.type}</span>
                    <span
                      className={cn(
                        l.ms > 200 ? "text-destructive" : "text-green-600",
                      )}
                    >
                      {l.ms}ms
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              <span className="text-muted-foreground">—</span>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Turn history */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-xs font-medium text-muted-foreground">
            Turn History
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="max-h-40 overflow-y-auto text-xs space-y-2">
            {turns.length === 0 ? (
              <span className="text-muted-foreground">No turns yet.</span>
            ) : (
              turns.map((turn, i) => (
                <div
                  key={i}
                  className="flex gap-2 items-start border-b pb-1 last:border-0"
                >
                  <Badge variant="outline" className="text-[10px] shrink-0">
                    {turn.routeA}
                    {turn.routeB && ` → ${turn.routeB}`}
                  </Badge>
                  <span className="text-muted-foreground truncate">
                    {turn.text}
                  </span>
                </div>
              ))
            )}
          </div>
        </CardContent>
      </Card>

      {/* Event log */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-xs font-medium text-muted-foreground">
            Event Log (last 20)
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="max-h-48 overflow-y-auto text-[11px] font-mono space-y-0.5">
            {events.length === 0 ? (
              <span className="text-muted-foreground">No events yet.</span>
            ) : (
              events.slice(0, 20).map((event, i) => (
                <div key={i} className="text-muted-foreground">
                  <span className="text-foreground">{event.type}</span>{" "}
                  {JSON.stringify(
                    Object.fromEntries(
                      Object.entries(event).filter(([k]) => k !== "type"),
                    ),
                  )}
                </div>
              ))
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
