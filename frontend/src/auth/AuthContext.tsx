import { createContext, useCallback, useEffect, useMemo, useState, type ReactNode } from "react";

import { api, refreshAccessToken, setAccessToken, setSessionEndedHandler } from "../api/client";
import type { AccessToken, Me } from "../api/types";

export interface AuthState {
  /** undefined: încă verificăm sesiunea; null: neautentificat. */
  user: Me | null | undefined;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  changePassword: (current: string, next: string) => Promise<void>;
}

export const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<Me | null | undefined>(undefined);

  const loadMe = useCallback(async () => setUser(await api.get<Me>("/api/auth/me")), []);

  useEffect(() => {
    setSessionEndedHandler(() => setUser(null));
    // La deschiderea paginii: sesiunea din cookie, dacă există.
    void (async () => {
      if (await refreshAccessToken()) {
        await loadMe().catch(() => setUser(null));
      } else {
        setUser(null);
      }
    })();
  }, [loadMe]);

  const login = useCallback(
    async (username: string, password: string) => {
      const token = await api.post<AccessToken>("/api/auth/login", { username, password });
      setAccessToken(token.access_token);
      await loadMe();
    },
    [loadMe],
  );

  const logout = useCallback(async () => {
    await api.post("/api/auth/logout").catch(() => undefined);
    setAccessToken(null);
    setUser(null);
  }, []);

  const changePassword = useCallback(
    async (current: string, next: string) => {
      const token = await api.post<AccessToken>("/api/auth/change-password", {
        current_password: current,
        new_password: next,
      });
      setAccessToken(token.access_token);
      await loadMe();
    },
    [loadMe],
  );

  const value = useMemo(
    () => ({ user, login, logout, changePassword }),
    [user, login, logout, changePassword],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
