// Setările biroului: datele organizației, folosite în toată aplicația.
// Le vede oricine; le modifică doar adminul.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api } from "../api/client";
import type { OrganizationOut, OrganizationUpdate } from "../api/types";
import { useMe } from "../auth/useAuth";
import { ErrorBox } from "../components/ErrorBox";
import { Icon } from "../components/Icon";

type Field = Exclude<keyof OrganizationOut, "id">;
type Form = Record<Field, string>;

const SECTIONS: { title: string; hint: string; fields: [Field, string, string?][] }[] = [
  {
    title: "Compania",
    hint: "Denumirea apare în bara laterală și pe documentele generate.",
    fields: [
      ["name", "Denumire", "ex. Conta Expert SRL"],
      ["full_name", "Denumire juridică completă"],
      ["idno", "IDNO", "13 cifre"],
      ["vat_code", "Cod TVA", "7 cifre, dacă e plătitor"],
      ["director_name", "Director / administrator"],
    ],
  },
  {
    title: "Contact",
    hint: "Datele de contact ale biroului.",
    fields: [
      ["legal_address", "Adresa juridică"],
      ["phone", "Telefon", "ex. +373 22 123 456"],
      ["email", "Email", "ex. office@birou.md"],
      ["website", "Site web"],
    ],
  },
  {
    title: "Cont bancar",
    hint: "Contul principal al biroului.",
    fields: [
      ["bank_name", "Banca", "ex. MAIB"],
      ["iban", "IBAN", "MD…"],
    ],
  },
];
const MONO: Field[] = ["idno", "vat_code", "iban"];
const WIDE: Field[] = ["name", "full_name", "legal_address"];

function toForm(org: OrganizationOut): Form {
  const fields = SECTIONS.flatMap((s) => s.fields.map(([key]) => key));
  return Object.fromEntries(fields.map((k) => [k, org[k] ?? ""])) as Form;
}

export function SettingsPage() {
  const org = useQuery({
    queryKey: ["organization"],
    queryFn: () => api.get<OrganizationOut>("/api/settings/organization"),
  });
  if (org.error) return <ErrorBox error={org.error} />;
  if (!org.data) return <div className="loading">Se încarcă…</div>;
  // key: formularul pornește din nou de la datele salvate după fiecare salvare
  return <SettingsForm key={org.data.id} org={org.data} />;
}

function SettingsForm({ org }: { org: OrganizationOut }) {
  const me = useMe();
  const canEdit = me.role === "admin";
  const queryClient = useQueryClient();
  const [saved, setSaved] = useState(() => toForm(org));
  const [form, setForm] = useState(saved);
  const [message, setMessage] = useState<string | null>(null);

  const changed = (Object.keys(form) as Field[]).filter((k) => form[k] !== saved[k]);
  const save = useMutation({
    mutationFn: () => {
      const body: OrganizationUpdate = {};
      for (const k of changed) {
        const value = form[k].trim();
        (body as Record<Field, string | null>)[k] = value === "" ? null : value;
      }
      return api.patch<OrganizationOut>("/api/settings/organization", body);
    },
    onSuccess: (updated) => {
      queryClient.setQueryData(["organization"], updated);
      const next = toForm(updated);
      setSaved(next);
      setForm(next);
      setMessage("Setările au fost salvate.");
    },
  });

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Setări</h1>
          <p>
            {canEdit
              ? "Datele biroului, folosite în toată aplicația."
              : "Datele biroului (doar adminul le modifică)."}
          </p>
        </div>
      </div>
      <form
        className="card"
        onSubmit={(e) => {
          e.preventDefault();
          setMessage(null);
          save.mutate();
        }}
      >
        <div className="card-b" style={{ padding: 24 }}>
          {save.error && (
            <div className="error" style={{ marginBottom: 16 }}>
              {save.error.message}
            </div>
          )}
          {message && changed.length === 0 && (
            <div className="notice" style={{ marginBottom: 16 }}>
              {message}
            </div>
          )}
          {SECTIONS.map((section) => (
            <div className="form-section" key={section.title}>
              <div>
                <h3>{section.title}</h3>
                <p>{section.hint}</p>
              </div>
              <div className="form">
                {section.fields.map(([key, label, placeholder]) => (
                  <div className={`field${WIDE.includes(key) ? " full" : ""}`} key={key}>
                    <label htmlFor={`org-${key}`}>{label}</label>
                    <input
                      id={`org-${key}`}
                      className={`input${MONO.includes(key) ? " mono" : ""}`}
                      type={key === "email" ? "email" : "text"}
                      placeholder={placeholder}
                      value={form[key]}
                      onChange={(e) => setForm((f) => ({ ...f, [key]: e.target.value }))}
                      required={key === "name"}
                      disabled={!canEdit}
                    />
                  </div>
                ))}
              </div>
            </div>
          ))}
          {canEdit && (
            <div className="form-actions">
              <button
                className="btn"
                type="button"
                disabled={changed.length === 0}
                onClick={() => setForm(saved)}
              >
                Renunță la modificări
              </button>
              <button
                className="btn primary"
                type="submit"
                disabled={changed.length === 0 || save.isPending}
              >
                <Icon name="check" size={16} /> Salvează
              </button>
            </div>
          )}
        </div>
      </form>
    </>
  );
}
