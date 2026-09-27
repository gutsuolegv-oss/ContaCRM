import { useState, type FormEvent } from "react";

import { useAuth, useMe } from "../auth/useAuth";

const MIN_LENGTH = 12;

export function ChangePasswordPage() {
  const me = useMe();
  const { changePassword, logout } = useAuth();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [repeat, setRepeat] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (next !== repeat) return setError("Parolele noi nu coincid");
    setBusy(true);
    try {
      await changePassword(current, next);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Parola nu a putut fi schimbată");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="center-page">
      <form className="card card-b auth-card stack" onSubmit={(e) => void submit(e)}>
        <h2 style={{ margin: 0 }}>Schimbă parola</h2>
        <div className="notice">
          {me.full_name}, parola ta a fost setată de administrator. Alege una nouă, de cel puțin{" "}
          {MIN_LENGTH} caractere, ca să continui.
        </div>
        {error && <div className="error">{error}</div>}
        <input type="email" value={me.email} autoComplete="username" hidden readOnly />
        <div className="field">
          <label htmlFor="current">Parola actuală</label>
          <input
            id="current"
            className="input"
            type="password"
            autoComplete="current-password"
            value={current}
            onChange={(e) => setCurrent(e.target.value)}
            required
          />
        </div>
        <div className="field">
          <label htmlFor="next">Parola nouă</label>
          <input
            id="next"
            className="input"
            type="password"
            autoComplete="new-password"
            minLength={MIN_LENGTH}
            value={next}
            onChange={(e) => setNext(e.target.value)}
            required
          />
        </div>
        <div className="field">
          <label htmlFor="repeat">Repetă parola nouă</label>
          <input
            id="repeat"
            className="input"
            type="password"
            autoComplete="new-password"
            minLength={MIN_LENGTH}
            value={repeat}
            onChange={(e) => setRepeat(e.target.value)}
            required
          />
        </div>
        <button className="btn primary" type="submit" disabled={busy}>
          Salvează parola
        </button>
        <button className="btn ghost" type="button" onClick={() => void logout()}>
          Ieșire
        </button>
      </form>
    </div>
  );
}
