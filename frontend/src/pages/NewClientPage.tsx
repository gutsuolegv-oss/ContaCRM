import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate } from "react-router";

import { api } from "../api/client";
import type { ClientCreate, ClientSaveOut } from "../api/types";

const EMPTY: ClientCreate = {
  name: "",
  idno: "",
  legal_form: "SRL",
  is_vat_payer: false,
  has_employees: false,
  is_it_park_resident: false,
  has_transport: false,
};

export function NewClientPage() {
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

  const flag = (
    key: "is_vat_payer" | "has_employees" | "is_it_park_resident" | "has_transport",
    label: string,
  ) => (
    <label className="field" style={{ flexDirection: "row", gap: 8 }}>
      <input
        type="checkbox"
        checked={Boolean(form[key])}
        onChange={(e) => set(key, e.target.checked)}
      />
      {label}
    </label>
  );

  return (
    <>
      <div className="crumbs">
        <Link to="/clienti">Clienți</Link> / Client nou
      </div>
      <div className="page-head">
        <div>
          <h1>Client nou</h1>
          <p>Clientul pornește în „onboarding”; rapoartele se calculează automat.</p>
        </div>
      </div>
      <form
        className="card card-b stack"
        onSubmit={(e) => {
          e.preventDefault();
          create.mutate();
        }}
      >
        {create.error && <div className="error">{create.error.message}</div>}
        <div className="form">
          <div className="field">
            <label>IDNO</label>
            <input
              className="input mono"
              maxLength={13}
              placeholder="13 cifre"
              value={form.idno}
              onChange={(e) => set("idno", e.target.value)}
              required
            />
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
          <div className="field full">
            <label>Denumire</label>
            <input
              className="input"
              placeholder="ex. Print Studio SRL"
              value={form.name}
              onChange={(e) => set("name", e.target.value)}
              required
            />
          </div>
          <div className="field">
            <label>Localitate</label>
            <input
              className="input"
              value={form.locality ?? ""}
              onChange={(e) => set("locality", e.target.value || null)}
            />
          </div>
          <div />
          {flag("is_vat_payer", "Plătitor de TVA")}
          {flag("has_employees", "Are angajați")}
          {flag("is_it_park_resident", "Rezident IT Park")}
          {flag("has_transport", "Are transport")}
          {form.is_vat_payer && (
            <div className="field">
              <label>Cod TVA (7 cifre, opțional)</label>
              <input
                className="input mono"
                value={form.vat_code ?? ""}
                onChange={(e) => set("vat_code", e.target.value || null)}
              />
            </div>
          )}
        </div>
        <div>
          <button className="btn primary" type="submit" disabled={create.isPending}>
            Creează clientul
          </button>
        </div>
      </form>
    </>
  );
}
