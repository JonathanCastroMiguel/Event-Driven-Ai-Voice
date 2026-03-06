import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { MicAnimation } from "@/components/voice/mic-animation";

describe("MicAnimation", () => {
  it("renders with inactive state", () => {
    const { container } = render(<MicAnimation isActive={false} />);
    const circle = container.querySelector(".bg-muted");
    expect(circle).toBeInTheDocument();
  });

  it("renders with active state", () => {
    const { container } = render(<MicAnimation isActive={true} />);
    const circle = container.querySelector(".bg-green-500");
    expect(circle).toBeInTheDocument();
  });

  it("shows ping animation when active", () => {
    const { container } = render(<MicAnimation isActive={true} />);
    const ping = container.querySelector(".animate-ping");
    expect(ping).toBeInTheDocument();
  });

  it("hides ping animation when inactive", () => {
    const { container } = render(<MicAnimation isActive={false} />);
    const ping = container.querySelector(".animate-ping");
    expect(ping).not.toBeInTheDocument();
  });
});
