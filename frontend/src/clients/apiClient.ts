/**
 * Base fetch wrapper for all backend API calls.
 *
 * Sends cookies with every request (credentials: "include") so the HttpOnly
 * auth_token cookie is forwarded automatically. Normalises HTTP errors into
 * ApiError instances so TanStack Query sees them as failures.
 */

export type FieldErrors = Partial<Record<string, string>>;

/** Structured error thrown for any non-2xx response or network failure. */
export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly detail: string,
    public readonly fieldErrors: FieldErrors = {},
  ) {
    super(`${status} ${detail}`);
    this.name = "ApiError";
  }
}

/** Invoked on any 401 response that is not the bootstrap /auth/me call. */
let on401: (() => void) | null = null;

/**
 * Register a global handler for 401 responses.
 *
 * @param cb - Callback invoked whenever a non-bootstrap request returns 401.
 */
export function setOn401(cb: () => void): void {
  on401 = cb;
}

/**
 * Normalise a FastAPI error body into a flat detail string and optional field map.
 *
 * FastAPI emits two shapes:
 *   - `{"detail": "string message"}`
 *   - `{"detail": [{"loc": ["body", "field"], "msg": "...", "type": "..."}]}`
 */
function parseErrorBody(body: unknown): { detail: string; fieldErrors: FieldErrors } {
  if (typeof body !== "object" || body === null) {
    return { detail: "Something went wrong. Please try again.", fieldErrors: {} };
  }
  const raw = (body as Record<string, unknown>).detail;

  if (typeof raw === "string") {
    return { detail: raw, fieldErrors: {} };
  }

  if (Array.isArray(raw)) {
    const fieldErrors: FieldErrors = {};
    const parts: string[] = [];
    for (const item of raw as Array<{ loc?: string[]; msg?: string }>) {
      const field = item.loc?.filter((s) => s !== "body").at(-1) ?? "error";
      const msg = item.msg ?? "Invalid value";
      fieldErrors[field] = msg;
      parts.push(`${field}: ${msg}`);
    }
    return { detail: parts.join("; "), fieldErrors };
  }

  return { detail: "Something went wrong. Please try again.", fieldErrors: {} };
}

async function request<T>(url: string, init?: RequestInit, isBootstrap = false): Promise<T> {
  let res: Response;
  try {
    res = await fetch(url, {
      credentials: "include",
      headers: { "Content-Type": "application/json", ...init?.headers },
      ...init,
    });
  } catch {
    throw new ApiError(0, "Could not reach the server.");
  }

  if (!res.ok) {
    let detail = res.statusText || "Something went wrong. Please try again.";
    let fieldErrors: FieldErrors = {};

    try {
      const body: unknown = await res.json();
      ({ detail, fieldErrors } = parseErrorBody(body));
    } catch {
      // ignore JSON parse failure; use the defaults above
    }

    if (res.status === 401 && !isBootstrap) {
      on401?.();
    }

    throw new ApiError(res.status, detail, fieldErrors);
  }

  if (res.status === 204) {
    return undefined as T;
  }

  return res.json() as Promise<T>;
}

/**
 * GET helper — deserialises JSON response into T.
 *
 * @param url - Relative endpoint path.
 * @param isBootstrap - When true, 401 does not trigger the global on401 handler.
 * @returns Parsed response body.
 */
export function get<T>(url: string, isBootstrap = false): Promise<T> {
  return request<T>(url, undefined, isBootstrap);
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

/**
 * DELETE helper — issues a DELETE request and returns the parsed response (or void for 204).
 *
 * @param url - Relative endpoint path.
 * @returns Parsed response body, or undefined for 204 No Content.
 */
export function del<T>(url: string): Promise<T> {
  return request<T>(url, { method: "DELETE" });
}
