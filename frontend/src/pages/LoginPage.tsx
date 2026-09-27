import { useState, type FormEvent } from "react";

import { useAuth } from "../auth/useAuth";
import { Icon } from "../components/Icon";
import { PasswordInput } from "../components/ui";

export function AuthHero() {
  return (
    <div className="auth-hero">
      <div className="brand">
        <div className="brand-mark">C</div>ContaCRM
      </div>
      <div>
        <h2>Toate rapoartele clienților, într-o singură grilă.</h2>
        <p>
          Termene calculate automat, obligații după regulile fiecărui client și o imagine clară a
          lunii pentru tot biroul.
        </p>
        <div className="auth-points">
          <div>
            <Icon name="grid" size={16} /> Grila lunară cu statusuri pe etape
          </div>
          <div>
            <Icon name="layers" size={16} /> Clasificator de rapoarte și reguli
          </div>
          <div>
            <Icon name="clock" size={16} /> Termene mutate automat pe zi lucrătoare
          </div>
        </div>
      </div>
      <div style={{ fontSize: 12, color: "#64748b" }}>© {new Date().getFullYear()} ContaCRM</div>
    </div>
  );
}

export function LoginPage() {
  const { login } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(username, password);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Autentificare eșuată");
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
            <h1>Bine ai revenit</h1>
            <p className="lead">Intră în contul tău de birou.</p>
          </div>
          {error && <div className="error">{error}</div>}
          <div className="field">
            <label htmlFor="username">Utilizator</label>
            <input
              id="username"
              className="input lg"
              autoComplete="username"
              autoCapitalize="none"
              spellCheck={false}
              placeholder="ex. ana.rusu"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
              autoFocus
            />
          </div>
          <div className="field">
            <label htmlFor="password">Parolă</label>
            <PasswordInput
              id="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </div>
          <button className="btn primary block" type="submit" disabled={busy}>
            {busy ? "Se verifică…" : "Intră"}
            {!busy && <Icon name="chevron" size={16} />}
          </button>
          <div className="hint" style={{ textAlign: "center" }}>
            Ai uitat parola? Cere-i administratorului să o reseteze.
          </div>
        </form>
      </div>
    </div>
  );
}
