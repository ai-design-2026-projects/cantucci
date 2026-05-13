import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { ConfidenceBar } from "@/components/ConfidenceBar";

describe("ConfidenceBar", () => {
  it("renders a progressbar role with aria-valuenow matching the score percentage", () => {
    render(<ConfidenceBar score={0.75} />);
    const bar = screen.getByRole("progressbar");
    expect(bar).toHaveAttribute("aria-valuenow", "75");
  });

  it("clamps score above 1 to 100%", () => {
    render(<ConfidenceBar score={1.5} />);
    const bar = screen.getByRole("progressbar");
    expect(bar).toHaveAttribute("aria-valuenow", "100");
  });

  it("clamps negative score to 0%", () => {
    render(<ConfidenceBar score={-0.3} />);
    const bar = screen.getByRole("progressbar");
    expect(bar).toHaveAttribute("aria-valuenow", "0");
  });

  it("uses provided label as aria-label", () => {
    render(<ConfidenceBar score={0.5} label="Drama score" />);
    const bar = screen.getByRole("progressbar");
    expect(bar).toHaveAttribute("aria-label", "Drama score");
  });

  it("falls back to a default aria-label based on pct when no label provided", () => {
    render(<ConfidenceBar score={0.4} />);
    const bar = screen.getByRole("progressbar");
    expect(bar).toHaveAttribute("aria-label", "40% confidence");
  });
});
