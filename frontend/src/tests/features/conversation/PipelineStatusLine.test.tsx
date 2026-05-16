import { describe, it, expect, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import {
  PipelineStatusLine,
  STAGES,
} from "@/features/conversation/PipelineStatusLine";
import { useUiStore } from "@/store/uiStore";

describe("STAGES", () => {
  it("has copy for every backend ProgressStep", () => {
    const required = ["retrieval", "cluster", "decision", "ambiguity", "render", "persist"] as const;
    for (const step of required) {
      expect(STAGES[step].id).toBe(step);
      expect(STAGES[step].label.length).toBeGreaterThan(0);
    }
  });
});

describe("PipelineStatusLine", () => {
  beforeEach(() => {
    useUiStore.getState().reset();
  });

  it("renders with role=status and the retrieval-stage fallback before any progress event", () => {
    render(<PipelineStatusLine />);

    const status = screen.getByRole("status");
    expect(status).toBeInTheDocument();
    expect(status).toHaveAttribute("aria-live", "polite");
    expect(status.textContent ?? "").toMatch(/finding films you might love/i);
  });

  it("reflects the current step from the store", () => {
    useUiStore.getState().setCurrentStep("decision");
    render(<PipelineStatusLine />);
    expect(screen.getByRole("status").textContent ?? "").toMatch(/picking the best slate/i);
  });

  it("honours the step prop override (used in tests)", () => {
    useUiStore.getState().setCurrentStep("retrieval");
    render(<PipelineStatusLine step="ambiguity" />);
    expect(screen.getByRole("status").textContent ?? "").toMatch(/checking the close calls/i);
  });

  it("falls back to the initial label when step is explicitly null", () => {
    render(<PipelineStatusLine step={null} />);
    expect(screen.getByRole("status").textContent ?? "").toMatch(/finding films you might love/i);
  });
});
