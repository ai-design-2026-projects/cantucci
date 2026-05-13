import type { OracleType } from "@/store/sessionStore";

/**
 * Format a 1-based turn number as a human-readable label.
 *
 * @param n - 1-based turn number.
 * @returns Label string, e.g. ``"Turn 3"``.
 */
export function formatTurnLabel(n: number): string {
  return `Turn ${n}`;
}

/**
 * Return a display string for the oracle type badge.
 *
 * @param type - Oracle type from the session store.
 * @returns Human-readable label.
 */
export function formatOracleType(type: OracleType): string {
  return type === "human" ? "Human" : "LLM Oracle";
}
