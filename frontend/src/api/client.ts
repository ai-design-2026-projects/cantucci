/**
 * Base API client. All requests use credentials: 'include' so the browser
 * sends the HttpOnly auth_token cookie automatically.
 *
 * @param path    - URL path (e.g. '/auth/login').
 * @param options - Fetch init options merged with defaults.
 * @returns Parsed JSON response body.
 * @throws {Error} On non-2xx responses, with `message` set to `detail` from the response body.
 */
export async function apiClient<T>(
    path: string,
    options: RequestInit = {},
): Promise<T> {
    const res = await fetch(path, {
        ...options,
        credentials: 'include',
        headers: {
            'Content-Type': 'application/json',
            ...options.headers,
        },
    })

    if (!res.ok) {
        let message = `HTTP ${res.status}`
        try {
            const body = await res.json()
            if (typeof body?.detail === 'string') message = body.detail
        } catch {
            // ignore parse errors on error responses
        }
        throw new Error(message)
    }

    if (res.status === 204) return undefined as T
    return res.json() as Promise<T>
}
