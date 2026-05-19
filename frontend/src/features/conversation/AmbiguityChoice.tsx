import { motion } from "framer-motion";
import { Button } from "@/components/ui/button";
import type { AmbiguityMeta } from "@/utils/types";
import { normaliseAmbiguityChoices } from "./utils/messageFormatters";

interface AmbiguityChoiceProps {
  /** Metadata from the ask-type TurnDto. */
  meta: AmbiguityMeta;
  /** Called when the oracle selects a choice; receives the choice label text. */
  onChoose: (choice: string) => void;
}

/**
 * Renders a clarifying question's answer options as clickable buttons.
 *
 * Fades in with a stagger so the options feel deliberate rather than instant.
 * Clicking auto-submits the selected choice text as the next oracle turn.
 *
 * @param meta - AmbiguityMeta with ui_format and cluster_refs.
 * @param onChoose - Callback receiving the chosen label string.
 * @returns A row of animated choice buttons.
 */
export function AmbiguityChoice({ meta, onChoose }: AmbiguityChoiceProps) {
  const choices = normaliseAmbiguityChoices(meta);

  return (
    <div className="flex flex-col gap-2 self-end w-full max-w-[360px] mt-1">
      {choices.map((label, i) => (
        <motion.div
          key={label}
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: i * 0.08, duration: 0.2 }}
        >
          <Button variant="choice" className="w-full" onClick={() => onChoose(label)}>
            {label}
          </Button>
        </motion.div>
      ))}
    </div>
  );
}
