import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api } from "../api/client";
import type { UserOut, UserRole } from "../api/types";
import { ROLE_LABEL, useMe } from "../auth/useAuth";
import { ErrorBox } from "../components/ErrorBox";
import { Icon } from "../components/Icon";
import { Avatar, Empty } from "../components/ui";
import { formatDate } from "../format";

const MIN_PASSWORD = 12;

const ROLE_BADGE: Record<UserRole, string> = {
  admin: "b-pri",
  director: "b-info",
  contabil: "b-grey",
};

export function UsersPage() {
  const me = useMe();
  const isAdmin = me.role === "admin";
  const queryClient = useQueryClient();
  const [showArchived, setShowArchived] = useState(false);
  const [creating, setCreating] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const users = useQuery({
    queryKey: ["users", showArchived],
    queryFn: () => api.get<UserOut[]>("/api/users", { include_archived: showArchived }),
  });
  const done = (text: string) => {
    setMessage(text);
    void queryClient.invalidateQueries({ queryKey: ["users"] });
  };

  const reset = useMutation({
    mutationFn: ({ id, password }: { id: number; password: string }) =>
      api.post<UserOut>(`/api/users/${id}/reset-password`, { password }),
    onSuccess: (u) =>
      done(`Parola lui ${u.full_name} a fost resetată; o va schimba la următoarea logare.`),
  });
  const archive = useMutation({
    mutationFn: (id: number) => api.del<UserOut>(`/api/users/${id}`),
    onSuccess: (u) => done(`${u.full_name} a fost arhivat; clienții lui au rămas nerepartizați.`),
  });
  const error = reset.error ?? archive.error;
  const active = users.data?.filter((u) => u.status !== "archived") ?? [];

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Utilizatori</h1>
          <p>
            {isAdmin ? "Conturile biroului." : "Conturile biroului (doar adminul le modifică)."}
            {users.data && ` ${active.length} active.`}
          </p>
        </div>
        <div className="page-actions">
          <label className="check">
            <input
              type="checkbox"
              checked={showArchived}
              onChange={(e) => setShowArchived(e.target.checked)}
            />
            arată și conturile arhivate
          </label>
          {isAdmin && !creating && (
            <button className="btn primary" onClick={() => setCreating(true)}>
              <Icon name="plus" size={16} /> Cont nou
            </button>
          )}
        </div>
      </div>
      {message && (
        <div className="callout ok" style={{ marginBottom: 16 }}>
          <Icon name="check" />
          <div style={{ flex: 1 }}>{message}</div>
          <button className="btn sm ghost" onClick={() => setMessage(null)} aria-label="Închide">
            <Icon name="x" size={14} />
          </button>
        </div>
      )}
      {error && (
        <div className="error" style={{ marginBottom: 16 }}>
          {error.message}
        </div>
      )}
      {isAdmin && creating && (
        <NewUserForm
          onClose={() => setCreating(false)}
          onCreated={(u) => {
            setCreating(false);
            done(`Contul pentru ${u.full_name} a fost creat.`);
          }}
        />
      )}
      <div className="card">
        {users.error ? (
          <ErrorBox error={users.error} />
        ) : !users.data ? (
          <div className="loading">Se încarcă…</div>
        ) : users.data.length === 0 ? (
          <Empty icon="team" title="Niciun cont" />
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Utilizator</th>
                  <th>Rol</th>
                  <th className="hide-sm">Ultima logare</th>
                  <th>Stare</th>
                  {isAdmin && <th />}
                </tr>
              </thead>
              <tbody>
                {users.data.map((u) => (
                  <tr key={u.id} style={u.status === "archived" ? { opacity: 0.6 } : undefined}>
                    <td>
                      <div className="person">
                        <Avatar name={u.full_name} size={34} />
                        <div className="grow">
                          <div className="strong">
                            {u.full_name}
                            {u.id === me.id && (
                              <span className="badge plain b-grey" style={{ marginLeft: 6 }}>
                                tu
                              </span>
                            )}
                          </div>
                          <div className="sub">{u.username}</div>
                        </div>
                      </div>
                    </td>
                    <td>
                      <span className={`badge plain ${ROLE_BADGE[u.role]}`}>
                        {u.role === "admin" && <Icon name="shield" size={12} />}
                        {ROLE_LABEL[u.role]}
                      </span>
                    </td>
                    <td className="muted hide-sm">{formatDate(u.last_login_at)}</td>
                    <td>
                      {u.status === "archived" ? (
                        <span className="badge b-grey">arhivat</span>
                      ) : u.must_change_password ? (
                        <span className="badge b-warn">parolă de schimbat</span>
                      ) : (
                        <span className="badge b-ok">activ</span>
                      )}
                    </td>
                    {isAdmin && (
                      <td className="num">
                        {u.status === "active" && u.id !== me.id && (
                          <span style={{ display: "inline-flex", gap: 4 }}>
                            <button
                              className="btn sm"
                              onClick={() => {
                                const password = window.prompt(
                                  `Parolă nouă pentru ${u.full_name} (minim ${MIN_PASSWORD} caractere):`,
                                );
                                if (password) reset.mutate({ id: u.id, password });
                              }}
                            >
                              <Icon name="key" size={14} /> Resetează parola
                            </button>
                            <button
                              className="btn sm ghost danger"
                              onClick={() => {
                                if (window.confirm(`Arhivezi contul lui ${u.full_name}?`))
                                  archive.mutate(u.id);
                              }}
                            >
                              <Icon name="archive" size={14} /> Arhivează
                            </button>
                          </span>
                        )}
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  );
}

function NewUserForm({
  onCreated,
  onClose,
}: {
  onCreated: (user: UserOut) => void;
  onClose: () => void;
}) {
  const [username, setUsername] = useState("");
  const [name, setName] = useState("");
  const [role, setRole] = useState<UserRole>("contabil");
  const [password, setPassword] = useState("");
  const create = useMutation({
    mutationFn: () =>
      api.post<UserOut>("/api/users", { username, full_name: name, role, password }),
    onSuccess: (user) => {
      setUsername("");
      setName("");
      setPassword("");
      onCreated(user);
    },
  });

  return (
    <form
      className="card"
      style={{ marginBottom: 16 }}
      onSubmit={(e) => {
        e.preventDefault();
        create.mutate();
      }}
    >
      <div className="card-h">
        <h3>
          <Icon name="user" size={16} /> Cont nou
        </h3>
        <button type="button" className="btn sm ghost" onClick={onClose} aria-label="Închide">
          <Icon name="x" size={14} />
        </button>
      </div>
      <div className="card-b stack">
        {create.error && <div className="error">{create.error.message}</div>}
        <div className="form">
          <div className="field">
            <label>Nume Prenume</label>
            <input
              className="input"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              autoFocus
            />
          </div>
          <div className="field">
            <label>Utilizator</label>
            <input
              className="input mono"
              placeholder="ex. ana.rusu"
              autoCapitalize="none"
              pattern="[A-Za-z0-9][A-Za-z0-9._\-]{1,49}"
              title="2-50 caractere: litere latine, cifre, punct, _ sau -"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
            />
          </div>
          <div className="field">
            <label>Rol</label>
            <select
              className="input"
              value={role}
              onChange={(e) => setRole(e.target.value as UserRole)}
            >
              <option value="contabil">Contabil</option>
              <option value="director">Director</option>
              <option value="admin">Admin</option>
            </select>
          </div>
          <div className="field">
            <label>Parolă inițială</label>
            <input
              className="input"
              type="password"
              autoComplete="new-password"
              placeholder={`minim ${MIN_PASSWORD} caractere`}
              minLength={MIN_PASSWORD}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </div>
        </div>
        <div
          className="form-actions"
          style={{ justifyContent: "space-between", alignItems: "center" }}
        >
          <span className="hint">
            Comunică parola personal; utilizatorul va fi obligat s-o schimbe la prima logare.
          </span>
          <button className="btn primary" type="submit" disabled={create.isPending}>
            Creează contul
          </button>
        </div>
      </div>
    </form>
  );
}
