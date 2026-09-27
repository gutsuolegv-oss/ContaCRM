import { useContext } from "react";

import type { Me } from "../api/types";
import { AuthContext, type AuthState } from "./AuthContext";

export function useAuth(): AuthState {
  const auth = useContext(AuthContext);
  if (!auth) throw new Error("useAuth în afara AuthProvider");
  return auth;
}

/** Utilizatorul logat (doar în paginile protejate, unde sigur există). */
export function useMe(): Me {
  const { user } = useAuth();
  if (!user) throw new Error("useMe fără utilizator logat");
  return user;
}

export const ROLE_LABEL: Record<Me["role"], string> = {
  admin: "Admin",
  director: "Director",
  contabil: "Contabil",
};

export function isEditor(user: Me): boolean {
  return user.role === "admin" || user.role === "director";
}
