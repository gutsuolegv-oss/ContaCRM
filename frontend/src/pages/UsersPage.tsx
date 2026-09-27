import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api } from "../api/client";
import type { UserOut, UserRole } from "../api/types";
import { ROLE_LABEL, useMe } from "../auth/useAuth";
import { ErrorBox } from "../components/ErrorBox";
import { formatDate } from "../format";

const MIN_PASSWORD = 12;

export function UsersPage() {
  const me = useMe();
  const isAdmin = me.role === "admin";
  const queryClient = useQueryClient();
  const [showArchived, setShowArchived] = useState(false);
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

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Utilizatori</h1>
          <p>
            {isAdmin ? "Conturile biroului." : "Conturile biroului (doar adminul le modifică)."}
          </p>
        </div>
        <label className="who" style={{ fontSize: 13 }}>
          <input
            type="checkbox"
            checked={showArchived}
            onChange={(e) => setShowArchived(e.target.checked)}
          />
          arată și conturile arhivate
        </label>
      </div>
      {message && (
        <div className="notice" style={{ marginBottom: 16 }}>
          {message}
        </div>
      )}
      {error && (
        <div className="error" style={{ marginBottom: 16 }}>
          {error.message}
        </div>
      )}
      {isAdmin && (
        <NewUserForm onCreated={(u) => done(`Contul pentru ${u.full_name} a fost creat.`)} />
      )}
      <div className="card">
        {users.error ? (
          <ErrorBox error={users.error} />
        ) : !users.data ? (
          <div className="loading">Se încarcă…</div>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Nume</th>
                  <th>Email</th>
                  <th>Rol</th>
                  <th>Ultima logare</th>
                  <th>Stare</th>
                  {isAdmin && <th />}
                </tr>
              </thead>
              <tbody>
                {users.data.map((u) => (
                  <tr key={u.id}>
                    <td className="strong">{u.full_name}</td>
                    <td>{u.email}</td>
                    <td>{ROLE_LABEL[u.role]}</td>
                    <td className="muted">{formatDate(u.last_login_at)}</td>
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
                          <span style={{ display: "inline-flex", gap: 6 }}>
                            <button
                              className="btn sm"
                              onClick={() => {
                                const password = window.prompt(
                                  `Parolă nouă pentru ${u.full_name} (minim ${MIN_PASSWORD} caractere):`,
                                );
                                if (password) reset.mutate({ id: u.id, password });
                              }}
                            >
                              Resetează parola
                            </button>
                            <button
                              className="btn sm ghost"
                              onClick={() => {
                                if (window.confirm(`Arhivezi contul lui ${u.full_name}?`))
                                  archive.mutate(u.id);
                              }}
                            >
                              Arhivează
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

function NewUserForm({ onCreated }: { onCreated: (user: UserOut) => void }) {
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [role, setRole] = useState<UserRole>("contabil");
  const [password, setPassword] = useState("");
  const create = useMutation({
    mutationFn: () => api.post<UserOut>("/api/users", { email, full_name: name, role, password }),
    onSuccess: (user) => {
      setEmail("");
      setName("");
      setPassword("");
      onCreated(user);
    },
  });

  return (
    <form
      className="card card-b"
      style={{ marginBottom: 16 }}
      onSubmit={(e) => {
        e.preventDefault();
        create.mutate();
      }}
    >
      <div className="strong" style={{ marginBottom: 10 }}>
        Cont nou
      </div>
      {create.error && (
        <div className="error" style={{ marginBottom: 10 }}>
          {create.error.message}
        </div>
      )}
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <input
          className="input"
          placeholder="Nume Prenume"
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
        />
        <input
          className="input"
          type="email"
          placeholder="email@birou.md"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
        />
        <select
          className="input"
          value={role}
          onChange={(e) => setRole(e.target.value as UserRole)}
        >
          <option value="contabil">Contabil</option>
          <option value="director">Director</option>
          <option value="admin">Admin</option>
        </select>
        <input
          className="input"
          type="password"
          autoComplete="new-password"
          placeholder={`Parolă inițială (min. ${MIN_PASSWORD})`}
          minLength={MIN_PASSWORD}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />
        <button className="btn primary" type="submit" disabled={create.isPending}>
          Creează
        </button>
      </div>
      <div className="hint muted" style={{ fontSize: 12, marginTop: 8 }}>
        Comunică parola personal; utilizatorul va fi obligat s-o schimbe la prima logare.
      </div>
    </form>
  );
}
