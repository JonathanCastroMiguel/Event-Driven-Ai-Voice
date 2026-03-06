import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SpeakerAnimation } from "@/components/voice/speaker-animation";

describe("SpeakerAnimation", () => {
  it("renders with inactive state", () => {
    const { container } = render(<SpeakerAnimation isActive={false} />);
    const circle = container.querySelector(".bg-muted");
    expect(circle).toBeInTheDocument();
  });

  it("renders with active state", () => {
    const { container } = render(<SpeakerAnimation isActive={true} />);
    const circle = container.querySelector(".bg-blue-500");
    expect(circle).toBeInTheDocument();
  });

  it("shows ping animation when active", () => {
    const { container } = render(<SpeakerAnimation isActive={true} />);
    const ping = container.querySelector(".animate-ping");
    expect(ping).toBeInTheDocument();
  });
});
