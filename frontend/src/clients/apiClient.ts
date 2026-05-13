/**
 * Base fetch wrapper for all backend API calls.
 *
 * Normalises HTTP errors into thrown Error objects so TanStack Query
 * sees them as failures and triggers the error state.
 */

/** @param url - Relative URL path (proxied to backend by Vite). */
async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    headers: { "Content-Type": "application/json", ...init?.headers },
    ...init,
  });

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = (await res.json()) as { detail?: string | object };
      detail =
        typeof body.detail === "string"
          ? body.detail
          : JSON.stringify(body.detail);
    } catch {
      // ignore parse failure, use statusText
    }
    throw new Error(`${res.status} ${detail}`);
  }

  return res.json() as Promise<T>;
}

/**
 * GET helper — deserialises JSON response into T.
 *
 * @param url - Relative endpoint path.
 * @returns Parsed response body.
 */
export function get<T>(url: string): Promise<T> {
  return request<T>(url);
}

/**
 * POST helper — serialises body to JSON and deserialises response.
 *
 * @param url - Relative endpoint path.
 * @param body - Request payload (will be JSON-stringified).
 * @returns Parsed response body.
 */
export function post<T>(url: string, body: unknown): Promise<T> {
  return request<T>(url, { method: "POST", body: JSON.stringify(body) });
}
