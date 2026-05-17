import { useState, useEffect } from "react";
import * as DialogPrimitive from "@radix-ui/react-dialog";
import { DialogOverlay, DialogPortal } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Mascot } from "@/components/mascot/Mascot";
import { RecommendationMessage } from "@/features/conversation/RecommendationMessage";
import { cn } from "@/lib/utils";
import type { SessionState, TurnResult } from "@/utils/types";

interface StopOverlayProps {
  /** Current session, used to detect terminal turns and recommendation. */
  session: SessionState | undefined;
  /** Called when the user clicks "New Session". */
  onRestart: () => void;
}

/**
 * Full-screen modal shown when the session reaches a terminal turn.
 *
 * Two visual tones:
 * - ``converged=true``: celebratory headline, gold accents, celebrate mascot.
 * - ``converged=false``: softer headline, muted accents, slumped mascot.
 *
 * Dismissable only via the internal buttons. Clicking the backdrop or pressing
 * Escape is suppressed so the user must make an explicit choice.
 *
 * @param session - Active session state (turns, status).
 * @param onRestart - Callback to tear down and boot a new session.
 */
export function StopOverlay({ session, onRestart }: StopOverlayProps) {
  const [dismissed, setDismissed] = useState(false);

  const sessionId = session?.session_id;
  useEffect(() => {
    setDismissed(false);
  }, [sessionId]);

  const stopTurn: TurnResult | undefined = session?.turns
    .filter((t) => t.step_type === "stop")
    .at(-1);

  const open = stopTurn !== undefined && !dismissed;
  const isConverged = stopTurn?.converged ?? false;

  return (
    <DialogPrimitive.Root open={open}>
      <DialogPortal>
        <DialogOverlay className="bg-background/90" />
        <DialogPrimitive.Content
          className={cn(
            "fixed left-[50%] top-[50%] z-50 translate-x-[-50%] translate-y-[-50%]",
            "w-full max-w-2xl max-h-[90vh] overflow-y-auto",
            "rounded-xl border border-border bg-card shadow-2xl",
            "data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:zoom-in-95",
            "data-[state=open]:slide-in-from-left-1/2 data-[state=open]:slide-in-from-top-[48%]",
            "focus:outline-none"
          )}
          onInteractOutside={(e) => e.preventDefault()}
          onEscapeKeyDown={(e) => e.preventDefault()}
          aria-describedby="stop-overlay-description"
        >
          <div className="flex flex-col gap-6 p-8">
            <div className="flex items-start gap-4">
              <Mascot
                pose={isConverged ? "celebrate" : "slumped"}
                size={64}
                className="shrink-0 mt-1"
              />
              <div className="flex flex-col gap-1.5">
                <h2
                  className={cn(
                    "font-display text-2xl tracking-tight leading-tight",
                    isConverged ? "text-primary" : "text-foreground"
                  )}
                >
                  {isConverged
                    ? "Here's your match"
                    : "Here's what we found in the time we had"}
                </h2>
                <p id="stop-overlay-description" className="text-sm text-muted-foreground">
                  {isConverged
                    ? "The oracle has spoken. This cluster has converged on your taste."
                    : "We've reached our limit, but didn't leave empty-handed."}
                </p>
              </div>
            </div>

            {stopTurn?.recommendation && (
              <RecommendationMessage recommendation={stopTurn.recommendation} />
            )}

            <div className="flex flex-col sm:flex-row items-center justify-end gap-3 pt-2">
              <Button
                variant="ghost"
                onClick={() => setDismissed(true)}
              >
                Review conversation
              </Button>
              <Button
                variant="default"
                onClick={onRestart}
                className={isConverged ? "" : "opacity-90"}
              >
                New Session
              </Button>
            </div>
          </div>
        </DialogPrimitive.Content>
      </DialogPortal>
    </DialogPrimitive.Root>
  );
}
