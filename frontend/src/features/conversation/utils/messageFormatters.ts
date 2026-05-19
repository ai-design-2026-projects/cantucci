import type { AmbiguityMeta } from "@/utils/types";

/**
 * Format a UTC ISO timestamp into a short time label for message bubbles.
 *
 * @param iso - ISO 8601 date string.
 * @returns Short time string, e.g. ``"2:32 PM"``.
 */
export function formatTimestamp(iso: string): string {
  return new Date(iso).toLocaleTimeString(undefined, {
    hour: "numeric",
    minute: "2-digit",
  });
}

/**
 * Extract button labels from ambiguity_meta for the AmbiguityChoice renderer.
 *
 * For "binary" format: returns ["Yes", "No"].
 * For "forced_choice": returns placeholder labels until the backend enriches
 * the payload with option text.
 *
 * @param meta - AmbiguityMeta from a TurnDto.
 * @returns Array of string labels to render as choice buttons.
 */
export function normaliseAmbiguityChoices(meta: AmbiguityMeta): string[] {
  if (meta.ui_format === "binary") {
    return ["Yes", "No"];
  }
  // forced_choice — two clusters; placeholder labels until option text is added to API
  return ["Option A", "Option B"];
}
