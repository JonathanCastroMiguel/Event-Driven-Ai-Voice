"use client";

import { cn } from "@/lib/utils";

interface MicAnimationProps {
  isActive: boolean;
}

export function MicAnimation({ isActive }: MicAnimationProps) {
  return (
    <div className="relative flex items-center justify-center w-16 h-16">
      {/* Pulsing ring when active */}
      {isActive && (
        <div className="absolute inset-0 rounded-full bg-green-500/20 animate-ping" />
      )}

      {/* Main circle */}
      <div
        className={cn(
          "relative z-10 flex items-center justify-center w-14 h-14 rounded-full transition-colors duration-200",
          isActive ? "bg-green-500" : "bg-muted",
        )}
      >
        {/* Microphone icon (inline SVG to avoid extra dependencies) */}
        <svg
          xmlns="http://www.w3.org/2000/svg"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth={2}
          strokeLinecap="round"
          strokeLinejoin="round"
          className={cn(
            "w-6 h-6 transition-colors duration-200",
            isActive ? "text-white" : "text-muted-foreground",
          )}
        >
          <rect x="9" y="2" width="6" height="11" rx="3" />
          <path d="M5 10a7 7 0 0 0 14 0" />
          <line x1="12" y1="19" x2="12" y2="22" />
        </svg>
      </div>
    </div>
  );
}
