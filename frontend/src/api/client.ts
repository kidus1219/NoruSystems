const BASE = "/api";

/** Keeps DRF's per-field errors around so forms can render them inline. */
export class ApiError extends Error {
  status: number;
  fields: Record<string, string[]>;

  constructor(status: number, fields: Record<string, string[]>) {
    super(Object.values(fields).flat().join(" ") || `Request failed (${status})`);
    this.status = status;
    this.fields = fields;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });

  if (!response.ok) {
    let payload: unknown = {};
    try {
      payload = await response.json();
    } catch {
      /* not JSON, probably a 500 page. Fall through to the generic message. */
    }
    throw new ApiError(response.status, normaliseErrors(payload));
  }
  return response.status === 204 ? (undefined as T) : ((await response.json()) as T);
}

function normaliseErrors(payload: unknown): Record<string, string[]> {
  if (typeof payload !== "object" || payload === null) return { detail: ["Unexpected server response."] };
  return Object.fromEntries(
    Object.entries(payload as Record<string, unknown>).map(([key, value]) => [
      key,
      Array.isArray(value) ? value.map(String) : [String(value)],
    ]),
  );
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body: unknown) => request<T>(path, { method: "POST", body: JSON.stringify(body) }),
  patch: <T>(path: string, body: unknown) => request<T>(path, { method: "PATCH", body: JSON.stringify(body) }),
  delete: (path: string) => request<void>(path, { method: "DELETE" }),
};

/** Query string builder that drops empty values. */
export function qs(params: Record<string, string | number | boolean | undefined | null>) {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") search.set(key, String(value));
  }
  const encoded = search.toString();
  return encoded ? `?${encoded}` : "";
}
