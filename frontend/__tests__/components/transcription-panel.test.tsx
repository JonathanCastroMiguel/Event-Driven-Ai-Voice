import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { TranscriptionPanel } from "@/components/voice/transcription-panel";
import type { TranscriptionEntry } from "@/lib/types";

describe("TranscriptionPanel", () => {
  it("shows placeholder when empty", () => {
    render(<TranscriptionPanel entries={[]} />);
    expect(
      screen.getByText("Transcriptions will appear here during the call."),
    ).toBeInTheDocument();
  });

  it("renders human transcription entry", () => {
    const entries: TranscriptionEntry[] = [
      { id: "1", speaker: "human", text: "Hello there", timestamp: Date.now() },
    ];
    render(<TranscriptionPanel entries={entries} />);
    expect(screen.getByText("Hello there")).toBeInTheDocument();
    expect(screen.getByText("You")).toBeInTheDocument();
  });

  it("renders agent transcription entry", () => {
    const entries: TranscriptionEntry[] = [
      {
        id: "2",
        speaker: "agent",
        text: "How can I help?",
        timestamp: Date.now(),
      },
    ];
    render(<TranscriptionPanel entries={entries} />);
    expect(screen.getByText("How can I help?")).toBeInTheDocument();
    expect(screen.getByText("Agent")).toBeInTheDocument();
  });

  it("renders multiple entries", () => {
    const entries: TranscriptionEntry[] = [
      { id: "1", speaker: "human", text: "Hi", timestamp: 1000 },
      { id: "2", speaker: "agent", text: "Hello!", timestamp: 2000 },
      {
        id: "3",
        speaker: "human",
        text: "I need help",
        timestamp: 3000,
      },
    ];
    render(<TranscriptionPanel entries={entries} />);
    expect(screen.getByText("Hi")).toBeInTheDocument();
    expect(screen.getByText("Hello!")).toBeInTheDocument();
    expect(screen.getByText("I need help")).toBeInTheDocument();
  });
});
