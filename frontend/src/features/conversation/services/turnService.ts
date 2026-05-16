import type { TurnResult } from "@/utils/types";

/**
 * One wave-level checkpoint the backend can report progress on.
 *
 * Mirrors ``backend/orchestrator/progress.py::ProgressStep``. Orchestrator v2
 * runs in parallel waves, so checkpoints are wave-level rather than per-agent.
 */
export type ProgressStep =
  | "understand"
  | "choose"
  | "finalize"
  | "wrap_up";

/** Step boundary phase: ``start`` when entered, ``end`` when returned. */
export type ProgressPhase = "start" | "end";

/** A step-boundary event the backend pushes mid-turn. */
export interface ProgressEvent {
  type: "progress";
  step: ProgressStep;
  phase: ProgressPhase;
  ts: string;
}

/** Terminal success event carrying the full turn payload. */
export interface ResultEvent {
  type: "result";
  data: TurnResult;
}

/** Terminal failure event emitted when the worker raises mid-stream. */
export interface ErrorEvent {
  type: "error";
  code: string;
  message: string;
}

export type StreamEvent = ProgressEvent | ResultEvent | ErrorEvent;

/** Handlers invoked as NDJSON lines arrive from the backend. */
export interface StreamTurnHandlers {
  /** Called for each ``progress`` event. */
  onProgress?: (event: ProgressEvent) => void;
}

/**
 * Submit one oracle turn and consume the NDJSON event stream.
 *
 * Resolves with the ``TurnResult`` from the terminal ``result`` event and
 * rejects on either a terminal ``error`` event or a transport-level failure.
 * Progress events are dispatched to ``handlers.onProgress`` as they arrive.
 *
 * The response body is parsed line-by-line: chunks are concatenated into a
 * buffer that is split on ``\n``; any trailing partial line stays in the
 * buffer until the next chunk completes it.
 *
 * @param sessionId - UUID of the active session.
 * @param userMessage - Oracle's message text.
 * @param handlers - Optional callbacks for non-terminal events.
 * @returns The terminal ``TurnResult`` once the stream closes successfully.
 */
export async function streamTurn(
  sessionId: string,
  userMessage: string,
  handlers: StreamTurnHandlers = {},
): Promise<TurnResult> {
  const response = await fetch(`/sessions/${sessionId}/turns`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user_message: userMessage }),
  });

  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = (await response.json()) as { detail?: string | object };
      detail =
        typeof body.detail === "string"
          ? body.detail
          : JSON.stringify(body.detail);
    } catch {
      // Non-JSON error body; fall back to statusText.
    }
    throw new Error(`${response.status} ${detail}`);
  }

  if (!response.body) {
    throw new Error("Streaming response had no body");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let terminal: TurnResult | null = null;

  while (true) {
    const { value, done } = await reader.read();
    if (value) {
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() ?? "";
      for (const line of lines) {
        if (!line.trim()) continue;
        const event = JSON.parse(line) as StreamEvent;
        if (event.type === "progress") {
          handlers.onProgress?.(event);
        } else if (event.type === "result") {
          terminal = event.data;
        } else {
          throw new Error(`${event.code}: ${event.message}`);
        }
      }
    }
    if (done) break;
  }

  // Flush any tail bytes the decoder was holding.
  const tail = (buffer + decoder.decode()).trim();
  if (tail) {
    const event = JSON.parse(tail) as StreamEvent;
    if (event.type === "progress") {
      handlers.onProgress?.(event);
    } else if (event.type === "result") {
      terminal = event.data;
    } else {
      throw new Error(`${event.code}: ${event.message}`);
    }
  }

  if (terminal === null) {
    throw new Error("Stream closed without a terminal result event");
  }
  return terminal;
}
