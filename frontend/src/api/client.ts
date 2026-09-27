/**
 * Clientul HTTP pentru /api.
 *
 * - Access token-ul (15 min) stă doar în memorie; se trimite în antetul Authorization.
 * - Refresh token-ul e într-un cookie httpOnly pe care JavaScript nu-l vede; browserul îl
 *   trimite singur la /api/auth/refresh.
 * - La un 401, se face O reîmprospătare (una singură, chiar dacă mai multe cereri eșuează
 *   deodată) și cererea se repetă. Dacă nici asta nu merge, sesiunea s-a încheiat.
 */

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

type Query = Record<string, string | number | boolean | null | undefined>;

interface RequestOptions {
  query?: Query;
  body?: unknown;
  blob?: boolean; // răspunsul e un fișier, nu JSON
}

let accessToken: string | null = null;
let refreshing: Promise<boolean> | null = null;
let onSessionEnded: () => void = () => {};

export function setAccessToken(token: string | null): void {
  accessToken = token;
}

export function setSessionEndedHandler(handler: () => void): void {
  onSessionEnded = handler;
}

/** Access token nou din cookie-ul de sesiune. `false` dacă sesiunea nu mai e validă. */
export function refreshAccessToken(): Promise<boolean> {
  refreshing ??= (async () => {
    try {
      const resp = await fetch("/api/auth/refresh", {
        method: "POST",
        credentials: "same-origin",
      });
      if (!resp.ok) return false;
      accessToken = ((await resp.json()) as { access_token: string }).access_token;
      return true;
    } catch {
      return false;
    }
  })().finally(() => {
    refreshing = null;
  });
  return refreshing;
}

function url(path: string, query?: Query): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value !== undefined && value !== null && value !== "") params.set(key, String(value));
  }
  const qs = params.toString();
  return qs ? `${path}?${qs}` : path;
}

/** Mesajul de eroare din răspunsul FastAPI (`detail` text sau lista de erori de validare). */
async function errorMessage(resp: Response): Promise<string> {
  try {
    const body = (await resp.json()) as { detail?: unknown };
    if (typeof body.detail === "string") return body.detail;
    if (Array.isArray(body.detail)) {
      return body.detail
        .map((e: { loc?: unknown[]; msg?: string }) => {
          const field = e.loc?.filter((p) => p !== "body").join(".");
          return field ? `${field}: ${e.msg}` : e.msg;
        })
        .join("; ");
    }
  } catch {
    // fără corp JSON
  }
  return `Eroare ${resp.status}`;
}

async function request<T>(
  method: string,
  path: string,
  { query, body, blob }: RequestOptions = {},
  retry = true,
): Promise<T> {
  const headers: Record<string, string> = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (accessToken) headers.Authorization = `Bearer ${accessToken}`;

  const resp = await fetch(url(path, query), {
    method,
    headers,
    credentials: "same-origin",
    body: body === undefined ? undefined : JSON.stringify(body),
  });

  if (resp.status === 401 && retry && !path.startsWith("/api/auth/")) {
    if (await refreshAccessToken()) return request<T>(method, path, { query, body, blob }, false);
    accessToken = null;
    onSessionEnded();
  }
  if (!resp.ok) throw new ApiError(resp.status, await errorMessage(resp));
  if (resp.status === 204) return undefined as T;
  if (blob) return (await resp.blob()) as T;
  return (await resp.json()) as T;
}

export const api = {
  get: <T>(path: string, query?: Query) => request<T>("GET", path, { query }),
  post: <T>(path: string, body?: unknown, query?: Query) =>
    request<T>("POST", path, { body, query }),
  patch: <T>(path: string, body: unknown) => request<T>("PATCH", path, { body }),
  put: <T>(path: string, body: unknown) => request<T>("PUT", path, { body }),
  del: <T>(path: string) => request<T>("DELETE", path),
  /** Descarcă un fișier protejat (cu autentificarea curentă) și îl salvează în browser. */
  download: async (path: string, filename: string) => {
    const file = await request<Blob>("GET", path, { blob: true });
    const url = URL.createObjectURL(file);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    link.click();
    URL.revokeObjectURL(url);
  },
};
