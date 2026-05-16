import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import {
  PipelineStatusLine,
  selectStage,
  STAGES,
  type PipelineStage,
} from "@/features/conversation/PipelineStatusLine";

describe("selectStage", () => {
  it("returns the first stage at elapsed 0", () => {
    expect(selectStage(0).id).toBe("retrieval");
  });

  it("returns the stage whose startSeconds was last crossed", () => {
    expect(selectStage(8).id).toBe("clustering");
    expect(selectStage(20).id).toBe("decision");
    expect(selectStage(35).id).toBe("ambiguity");
  });

  it("works on a custom stages table", () => {
    const stages: PipelineStage[] = [
      { id: "a", startSeconds: 0, variants: ["A"] },
      { id: "b", startSeconds: 5, variants: ["B"] },
    ];
    expect(selectStage(0, stages).id).toBe("a");
    expect(selectStage(4.9, stages).id).toBe("a");
    expect(selectStage(5, stages).id).toBe("b");
  });
});

describe("STAGES", () => {
  it("starts at 0 and is ordered by startSeconds", () => {
    expect(STAGES[0].startSeconds).toBe(0);
    for (let i = 1; i < STAGES.length; i++) {
      expect(STAGES[i].startSeconds).toBeGreaterThan(STAGES[i - 1].startSeconds);
    }
  });

  it("gives every stage at least one variant", () => {
    for (const s of STAGES) {
      expect(s.variants.length).toBeGreaterThan(0);
    }
  });
});

describe("PipelineStatusLine", () => {
  it("renders with role=status and an initial retrieval-stage variant", () => {
    render(<PipelineStatusLine tickMs={1000} />);

    const status = screen.getByRole("status");
    expect(status).toBeInTheDocument();
    expect(status).toHaveAttribute("aria-live", "polite");
    // First retrieval-stage variant should be the one mounted at t=0.
    expect(status.textContent ?? "").toMatch(/finding films you might love/i);
  });

  it("renders the first variant from a custom stages table on mount", () => {
    const stages: PipelineStage[] = [
      { id: "only", startSeconds: 0, variants: ["First", "Second"] },
    ];
    render(<PipelineStatusLine tickMs={1000} stages={stages} />);
    expect(screen.getByRole("status").textContent ?? "").toMatch(/first/i);
  });
});

