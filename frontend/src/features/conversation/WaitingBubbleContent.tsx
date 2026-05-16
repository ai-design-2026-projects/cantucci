import { TypingDots } from "./TypingDots";
import { PipelineStatusLine } from "./PipelineStatusLine";

/**
 * Wait-state content rendered inside the assistant bubble while the LLM
 * pipeline (~20–40s) is still in flight.
 *
 * Composes the visual layers of the mask:
 *   1. Three pulsing typing dots — a familiar chat affordance that signals
 *      "something is coming".
 *   2. A product-soft status line that rotates through phrasings and advances
 *      through pipeline stages over time.
 *
 * Mounted by ``MessageBubble`` only when the assistant message is empty and
 * this is the latest turn. As soon as the real message arrives, the parent
 * swaps this out for ``StreamingText`` — no minimum hold time.
 *
 * @returns The composed wait-state element.
 */
export function WaitingBubbleContent() {
  return (
    <div
      className="flex flex-col gap-2"
      data-testid="waiting-bubble-content"
    >
      <TypingDots />
      <PipelineStatusLine />
    </div>
  );
}
