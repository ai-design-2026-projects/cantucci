import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Composer } from "@/features/conversation/Composer";

describe("Composer", () => {
  it("calls onSubmit with the typed message when Enter is pressed", async () => {
    const onSubmit = vi.fn();
    render(<Composer isLoading={false} onSubmit={onSubmit} />);
    const textarea = screen.getByRole("textbox", { name: /oracle message/i });

    await userEvent.type(textarea, "thriller with a twist");
    fireEvent.keyDown(textarea, { key: "Enter", code: "Enter", shiftKey: false });

    expect(onSubmit).toHaveBeenCalledOnce();
    expect(onSubmit).toHaveBeenCalledWith("thriller with a twist");
  });

  it("does not submit on Shift+Enter", async () => {
    const onSubmit = vi.fn();
    render(<Composer isLoading={false} onSubmit={onSubmit} />);
    const textarea = screen.getByRole("textbox", { name: /oracle message/i });

    await userEvent.type(textarea, "some text");
    fireEvent.keyDown(textarea, { key: "Enter", code: "Enter", shiftKey: true });

    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("clears the input after submission", async () => {
    const onSubmit = vi.fn();
    render(<Composer isLoading={false} onSubmit={onSubmit} />);
    const textarea = screen.getByRole("textbox", { name: /oracle message/i }) as HTMLTextAreaElement;

    await userEvent.type(textarea, "sci-fi noir");
    fireEvent.keyDown(textarea, { key: "Enter", code: "Enter", shiftKey: false });

    expect(textarea.value).toBe("");
  });

  it("disables the textarea and send button while loading", () => {
    render(<Composer isLoading={true} onSubmit={vi.fn()} />);
    expect(screen.getByRole("textbox", { name: /oracle message/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /send message/i })).toBeDisabled();
  });

  it("does not submit an empty or whitespace-only message", async () => {
    const onSubmit = vi.fn();
    render(<Composer isLoading={false} onSubmit={onSubmit} />);
    const textarea = screen.getByRole("textbox", { name: /oracle message/i });

    await userEvent.type(textarea, "   ");
    fireEvent.keyDown(textarea, { key: "Enter", code: "Enter", shiftKey: false });

    expect(onSubmit).not.toHaveBeenCalled();
  });
});
