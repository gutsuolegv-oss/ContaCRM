import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, Navigate, useNavigate } from "react-router";

import { api } from "../api/client";
import type { ClientCreate, ClientSaveOut } from "../api/types";
import { isEditor, useMe } from "../auth/useAuth";
import { Icon } from "../components/Icon";
import { initials } from "../format";

const EMPTY: ClientCreate = {
  name: "",
  idno: "",
  legal_form: "SRL",
  is_vat_payer: false,
  has_employees: false,
  is_it_park_resident: false,
  has_transport: false,
};

type FlagKey = "is_vat_payer" | "has_employees" | "is_it_park_resident" | "has_transport";
const FLAGS: [FlagKey, string, string][] = [
  ["is_vat_payer", "Plătitor de TVA", "Rapoartele de TVA"],
  ["has_employees", "Are angajați", "Rapoartele salariale"],
  ["is_it_park_resident", "Rezident IT Park", "Regimul IT Park"],
  ["has_transport", "Are transport", "Activează tab-ul Parc auto"],
];

/** Doar admin și director adaugă clienți; contabilul e trimis înapoi la listă. */
export function NewClientPage() {
  const me = useMe();
  if (!isEditor(me)) return <Navigate to="/clienti" replace />;
  return <NewClientForm />;
}

function NewClientForm() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [form, setForm] = useState<ClientCreate>(EMPTY);
  const set = <K extends keyof ClientCreate>(key: K, value: ClientCreate[K]) =>
    setForm((f) => ({ ...f, [key]: value }));

  const create = useMutation({
    mutationFn: () => api.post<ClientSaveOut>("/api/clients", form),
    onSuccess: (result) => {
      void queryClient.invalidateQueries({ queryKey: ["clients"] });
      navigate(`/clienti/${result.client.id}`);
    },
  });

  const idnoOk = /^\d{13}$/.test(form.idno);

  return (
    <>
      <div className="crumbs">
        <Link to="/clienti">
          <Icon name="back" size={14} /> Clienți
        </Link>
        <span className="sep">/</span>
        <span>Client nou</span>
      </div>
      <div className="page-head">
        <div>
          <h1>Client nou</h1>
          <p>Clientul pornește în „onboarding”; rapoartele se calculează automat.</p>
        </div>
      </div>
      <form
        className="card"
        onSubmit={(e) => {
          e.preventDefault();
          create.mutate();
        }}
      >
        <div className="card-b" style={{ padding: 24 }}>
          {create.error && (
            <div className="error" style={{ marginBottom: 16 }}>
              {create.error.message}
            </div>
          )}

          <div className="form-section">
            <div>
              <h3>Identificare</h3>
              <p>Datele din registrul de stat. Restul le completezi apoi în cartela clientului.</p>
              {form.name && (
                <div className="person" style={{ marginTop: 16 }}>
                  <span
                    className="client-logo"
                    style={{ width: 44, height: 44, fontSize: 15, borderRadius: 12 }}
                  >
                    {initials(form.name)}
                  </span>
                  <div className="grow">
                    <div className="strong">{form.name}</div>
                    <div className="sub mono">{form.idno || "IDNO —"}</div>
                  </div>
                </div>
              )}
            </div>
            <div className="form">
              <div className="field full">
                <label>Denumire</label>
                <input
                  className="input"
                  placeholder="ex. Print Studio SRL"
                  value={form.name}
                  onChange={(e) => set("name", e.target.value)}
                  required
                  autoFocus
                />
              </div>
              <div className="field">
                <label>IDNO</label>
                <input
                  className="input mono"
                  maxLength={13}
                  inputMode="numeric"
                  placeholder="13 cifre"
                  value={form.idno}
                  onChange={(e) => set("idno", e.target.value)}
                  required
                />
                <div
                  className="hint"
                  style={form.idno && !idnoOk ? { color: "var(--warn)" } : undefined}
                >
                  {form.idno.length}/13 cifre
                </div>
              </div>
              <div className="field">
                <label>Formă juridică</label>
                <select
                  className="input"
                  value={form.legal_form}
                  onChange={(e) => set("legal_form", e.target.value as ClientCreate["legal_form"])}
                >
                  <option value="SRL">SRL</option>
                  <option value="SA">SA</option>
                  <option value="II">ÎI</option>
                  <option value="GT">GȚ</option>
                  <option value="ONG">ONG</option>
                </select>
              </div>
              <div className="field">
                <label>Localitate</label>
                <input
                  className="input"
                  placeholder="ex. Chișinău"
                  value={form.locality ?? ""}
                  onChange={(e) => set("locality", e.target.value || null)}
                />
              </div>
            </div>
          </div>

          <div className="form-section">
            <div>
              <h3>Atribute fiscale</h3>
              <p>Decid ce rapoarte primește clientul. Le poți schimba oricând.</p>
            </div>
            <div className="stack">
              <div className="flag-grid">
                {FLAGS.map(([key, label, sub]) => (
                  <label key={key} className={`flag-toggle${form[key] ? " on" : ""}`}>
                    <input
                      type="checkbox"
                      checked={Boolean(form[key])}
                      onChange={(e) => set(key, e.target.checked)}
                    />
                    <span>
                      {label}
                      <span className="sub">{sub}</span>
                    </span>
                  </label>
                ))}
              </div>
              {form.is_vat_payer && (
                <div className="field" style={{ maxWidth: 260 }}>
                  <label>Cod TVA (7 cifre, opțional)</label>
                  <input
                    className="input mono"
                    value={form.vat_code ?? ""}
                    onChange={(e) => set("vat_code", e.target.value || null)}
                  />
                </div>
              )}
            </div>
          </div>

          <div className="form-actions">
            <Link className="btn" to="/clienti">
              Renunță
            </Link>
            <button className="btn primary" type="submit" disabled={create.isPending}>
              <Icon name="check" size={16} /> Creează clientul
            </button>
          </div>
        </div>
      </form>
    </>
  );
}
