import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MessageBubble } from "@/features/conversation/MessageBubble";
import type { TurnResult } from "@/utils/types";

function makeTurn(overrides: Partial<TurnResult> = {}): TurnResult {
  return {
    turn_id: "t-1",
    session_id: "s-1",
    turn_number: 1,
    user_message: "Something moody",
    assistant_message: "",
    step_type: "show",
    converged: false,
    created_at: new Date("2026-05-16T12:00:00Z").toISOString(),
    ambiguity_meta: null,
    recommendation: null,
    ...overrides,
  };
}

describe("MessageBubble waiting state", () => {
  it("renders the wait mask when the latest turn has no assistant_message", () => {
    render(
      <MessageBubble
        turn={makeTurn({ assistant_message: "" })}
        isLast={true}
        onChoose={vi.fn()}
      />,
    );

    expect(screen.getByTestId("waiting-bubble-content")).toBeInTheDocument();
    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it("does NOT render the wait mask when the assistant_message is present", () => {
    render(
      <MessageBubble
        turn={makeTurn({ assistant_message: "Here are some films." })}
        isLast={true}
        onChoose={vi.fn()}
      />,
    );

    expect(screen.queryByTestId("waiting-bubble-content")).not.toBeInTheDocument();
    expect(screen.getByText(/here are some films/i)).toBeInTheDocument();
  });

  it("does NOT render the wait mask for a non-last empty turn (defensive)", () => {
    render(
      <MessageBubble
        turn={makeTurn({ assistant_message: "" })}
        isLast={false}
        onChoose={vi.fn()}
      />,
    );

    expect(screen.queryByTestId("waiting-bubble-content")).not.toBeInTheDocument();
  });
});
