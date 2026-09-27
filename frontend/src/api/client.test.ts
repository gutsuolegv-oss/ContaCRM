import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { api, ApiError, setAccessToken, setSessionEndedHandler } from "./client";

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("api client", () => {
  const fetchMock = vi.fn<typeof fetch>();

  beforeEach(() => {
    vi.stubGlobal("fetch", fetchMock);
    setAccessToken("vechi");
  });
  afterEach(() => {
    fetchMock.mockReset();
    vi.unstubAllGlobals();
  });

  it("trimite access token-ul și parametrii", async () => {
    fetchMock.mockResolvedValueOnce(json(200, { ok: 1 }));
    await api.get("/api/clients", { q: "agro", limit: 10, empty: "", missing: undefined });
    const [path, init] = fetchMock.mock.calls[0]!;
    expect(path).toBe("/api/clients?q=agro&limit=10");
    expect((init?.headers as Record<string, string>).Authorization).toBe("Bearer vechi");
  });

  it("la 401 reîmprospătează o singură dată pentru cereri simultane, apoi repetă", async () => {
    fetchMock.mockImplementation(async (input, init) => {
      const path = String(input);
      if (path === "/api/auth/refresh") return json(200, { access_token: "nou" });
      const auth = (init?.headers as Record<string, string>).Authorization;
      return auth === "Bearer nou" ? json(200, { path }) : json(401, { detail: "expirat" });
    });
    const [a, b] = await Promise.all([api.get("/api/a"), api.get("/api/b")]);
    expect([a, b]).toEqual([{ path: "/api/a" }, { path: "/api/b" }]);
    const refreshes = fetchMock.mock.calls.filter(([p]) => p === "/api/auth/refresh");
    expect(refreshes).toHaveLength(1);
  });

  it("dacă nici reîmprospătarea nu merge, sesiunea se încheie", async () => {
    const ended = vi.fn();
    setSessionEndedHandler(ended);
    fetchMock.mockResolvedValue(json(401, { detail: "Sesiune expirată" }));
    await expect(api.get("/api/clients")).rejects.toMatchObject({ status: 401 });
    expect(ended).toHaveBeenCalledOnce();
  });

  it("mesajele de eroare FastAPI devin text", async () => {
    fetchMock.mockResolvedValueOnce(json(409, { detail: "Există deja un client activ" }));
    await expect(api.post("/api/clients", {})).rejects.toThrow("Există deja un client activ");
    fetchMock.mockResolvedValueOnce(
      json(422, { detail: [{ loc: ["body", "idno"], msg: "format invalid" }] }),
    );
    const error = await api.post("/api/clients", {}).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).message).toBe("idno: format invalid");
  });

  it("204 fără corp", async () => {
    fetchMock.mockResolvedValueOnce(new Response(null, { status: 204 }));
    await expect(api.del("/api/clients/1")).resolves.toBeUndefined();
  });
});
