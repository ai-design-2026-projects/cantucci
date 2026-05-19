import { Mascot } from "@/components/mascot/Mascot";
import { PipelineStatusLine } from "./PipelineStatusLine";

/**
 * Wait-state content rendered inside the assistant bubble while the LLM
 * pipeline (~20–40s) is still in flight.
 *
 * Composes the visual layers of the loading mask:
 *   1. A Lottie-animated mascot in "thinking" pose — three bouncing dots that
 *      signal activity without mimicking generic spinners.
 *   2. A product-soft status line that advances through pipeline stages as
 *      real progress events arrive on the NDJSON stream.
 *
 * Mounted by ``MessageBubble`` only when the assistant message is empty and
 * this is the latest turn.
 *
 * @returns The composed wait-state element.
 */
export function WaitingBubbleContent() {
  return (
    <div
      className="flex flex-row items-center gap-3"
      data-testid="waiting-bubble-content"
    >
      <Mascot pose="bob" size={40} />
      <PipelineStatusLine />
    </div>
  );
}
