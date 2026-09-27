import { useState, type FormEvent } from "react";

import { useAuth, useMe } from "../auth/useAuth";
import { Icon } from "../components/Icon";
import { PasswordInput } from "../components/ui";
import { AuthHero } from "./LoginPage";

const MIN_LENGTH = 12;

/** 0–4: lungime, litere mari/mici, cifre, simboluri. */
function strength(pw: string): number {
  if (!pw) return 0;
  let s = pw.length >= MIN_LENGTH ? 1 : 0;
  if (/[a-z]/.test(pw) && /[A-Z]/.test(pw)) s++;
  if (/\d/.test(pw)) s++;
  if (/[^A-Za-z0-9]/.test(pw)) s++;
  return s;
}
const STRENGTH_COLOR = ["var(--bad)", "var(--bad)", "var(--warn)", "var(--info)", "var(--ok)"];
const STRENGTH_LABEL = ["prea scurtă", "slabă", "acceptabilă", "bună", "puternică"];

export function ChangePasswordPage() {
  const me = useMe();
  const { changePassword, logout } = useAuth();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [repeat, setRepeat] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const score = strength(next);
  const mismatch = repeat.length > 0 && next !== repeat;

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
    <div className="auth-page">
      <AuthHero />
      <div className="auth-form-wrap">
        <form className="auth-card stack" onSubmit={(e) => void submit(e)}>
          <div>
            <span
              className="empty-ico"
              style={{ background: "var(--primary-soft)", color: "var(--primary)" }}
            >
              <Icon name="lock" />
            </span>
            <h1>Schimbă parola</h1>
            <p className="lead">
              {me.full_name}, parola ta a fost setată de administrator. Alege una nouă, de cel puțin{" "}
              {MIN_LENGTH} caractere, ca să continui.
            </p>
          </div>
          {error && <div className="error">{error}</div>}
          <input type="text" value={me.username} autoComplete="username" hidden readOnly />
          <div className="field">
            <label htmlFor="current">Parola actuală</label>
            <PasswordInput
              id="current"
              autoComplete="current-password"
              value={current}
              onChange={(e) => setCurrent(e.target.value)}
              required
            />
          </div>
          <div className="field">
            <label htmlFor="next">Parola nouă</label>
            <PasswordInput
              id="next"
              autoComplete="new-password"
              minLength={MIN_LENGTH}
              value={next}
              onChange={(e) => setNext(e.target.value)}
              required
            />
            {next && (
              <>
                <div className="pw-meter">
                  {[1, 2, 3, 4].map((i) => (
                    <span
                      key={i}
                      style={i <= score ? { background: STRENGTH_COLOR[score] } : undefined}
                    />
                  ))}
                </div>
                <div className="hint">
                  Parolă {STRENGTH_LABEL[score]}
                  {next.length < MIN_LENGTH && ` · încă ${MIN_LENGTH - next.length} caractere`}
                </div>
              </>
            )}
          </div>
          <div className="field">
            <label htmlFor="repeat">Repetă parola nouă</label>
            <PasswordInput
              id="repeat"
              autoComplete="new-password"
              minLength={MIN_LENGTH}
              value={repeat}
              onChange={(e) => setRepeat(e.target.value)}
              required
            />
            {mismatch && (
              <div className="hint" style={{ color: "var(--bad)" }}>
                Parolele nu coincid
              </div>
            )}
          </div>
          <button className="btn primary block" type="submit" disabled={busy}>
            Salvează parola
          </button>
          <button className="btn ghost block" type="button" onClick={() => void logout()}>
            <Icon name="logout" size={16} /> Ieșire
          </button>
        </form>
      </div>
    </div>
  );
}
