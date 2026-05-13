/**
 * Format an ISO-8601 UTC timestamp into a short human-readable string.
 *
 * @param iso - ISO 8601 date string (e.g. ``"2024-01-15T14:32:00Z"``).
 * @returns Localised time string, e.g. ``"2:32 PM"``.
 */
export function formatTimestamp(iso: string): string {
  return new Date(iso).toLocaleTimeString(undefined, {
    hour: "numeric",
    minute: "2-digit",
  });
}
