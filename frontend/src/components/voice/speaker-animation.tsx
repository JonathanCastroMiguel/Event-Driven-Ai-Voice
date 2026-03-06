"use client";

import { cn } from "@/lib/utils";

interface SpeakerAnimationProps {
  isActive: boolean;
}

export function SpeakerAnimation({ isActive }: SpeakerAnimationProps) {
  return (
    <div className="relative flex items-center justify-center w-16 h-16">
      {/* Pulsing ring when active */}
      {isActive && (
        <div className="absolute inset-0 rounded-full bg-blue-500/20 animate-ping" />
      )}

      {/* Main circle */}
      <div
        className={cn(
          "relative z-10 flex items-center justify-center w-14 h-14 rounded-full transition-colors duration-200",
          isActive ? "bg-blue-500" : "bg-muted",
        )}
      >
        {/* Speaker/volume icon */}
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
          <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5" />
          {isActive && (
            <>
              <path d="M15.54 8.46a5 5 0 0 1 0 7.07" />
              <path d="M19.07 4.93a10 10 0 0 1 0 14.14" />
            </>
          )}
        </svg>
      </div>
    </div>
  );
}
