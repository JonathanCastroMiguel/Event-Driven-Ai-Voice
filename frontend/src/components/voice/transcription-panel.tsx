"use client";

import { useEffect, useRef } from "react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import type { TranscriptionEntry } from "@/lib/types";

interface TranscriptionPanelProps {
  entries: TranscriptionEntry[];
}

export function TranscriptionPanel({ entries }: TranscriptionPanelProps) {
  const scrollRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom on new entries
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [entries]);

  return (
    <Card className="w-full">
      <CardHeader className="pb-3">
        <CardTitle className="text-sm font-medium">Transcription</CardTitle>
      </CardHeader>
      <CardContent>
        <div
          ref={scrollRef}
          className="h-48 overflow-y-auto space-y-2 text-sm"
        >
          {entries.length === 0 ? (
            <p className="text-muted-foreground text-center py-8">
              Transcriptions will appear here during the call.
            </p>
          ) : (
            entries.map((entry) => (
              <div
                key={entry.id}
                className={cn(
                  "flex gap-2",
                  entry.speaker === "human" ? "justify-end" : "justify-start",
                )}
              >
                <div
                  className={cn(
                    "max-w-[80%] rounded-lg px-3 py-2",
                    entry.speaker === "human"
                      ? "bg-primary text-primary-foreground"
                      : "bg-muted",
                  )}
                >
                  <p className="text-xs font-medium mb-0.5 opacity-70">
                    {entry.speaker === "human" ? "You" : "Agent"}
                  </p>
                  <p>{entry.text}</p>
                </div>
              </div>
            ))
          )}
        </div>
      </CardContent>
    </Card>
  );
}
