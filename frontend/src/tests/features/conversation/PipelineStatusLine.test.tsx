import { describe, it, expect, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import {
  PipelineStatusLine,
  STAGES,
} from "@/features/conversation/PipelineStatusLine";
import { useUiStore } from "@/store/uiStore";

describe("STAGES", () => {
  it("has copy for every backend ProgressStep", () => {
    const required = ["understand", "choose", "finalize", "wrap_up"] as const;
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

  it("renders the role=status wrapper but no stage label before any progress event", () => {
    render(<PipelineStatusLine />);

    const status = screen.getByRole("status");
    expect(status).toBeInTheDocument();
    expect(status).toHaveAttribute("aria-live", "polite");
    expect((status.textContent ?? "").trim()).toBe("");
  });

  it("renders the understand-stage label as soon as the first event arrives", () => {
    useUiStore.getState().setCurrentStep("understand");
    render(<PipelineStatusLine />);
    expect(screen.getByRole("status").textContent ?? "").toMatch(/reading your taste/i);
  });

  it("reflects the current step from the store", () => {
    useUiStore.getState().setCurrentStep("choose");
    render(<PipelineStatusLine />);
    expect(screen.getByRole("status").textContent ?? "").toMatch(/weighing the best picks/i);
  });

  it("honours the step prop override (used in tests)", () => {
    useUiStore.getState().setCurrentStep("understand");
    render(<PipelineStatusLine step="finalize" />);
    expect(screen.getByRole("status").textContent ?? "").toMatch(/writing your reply/i);
  });
});
