// Setările biroului: datele organizației, folosite în toată aplicația.
// Le vede oricine; le modifică doar adminul.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useSearchParams } from "react-router";

import { api } from "../api/client";
import type { BotSettingsOut, OrganizationOut, OrganizationUpdate } from "../api/types";
import { useMe } from "../auth/useAuth";
import { ErrorBox } from "../components/ErrorBox";
import { Icon, type IconName } from "../components/Icon";

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

type SettingsTab = "company" | "telegram";

export function SettingsPage() {
  const me = useMe();
  const canEdit = me.role === "admin";
  // tabul e în adresă (/setari?tab=telegram): rămâne la reîncărcare și se poate trimite ca link
  const [params, setParams] = useSearchParams();
  const fromUrl = params.get("tab");
  const tab: SettingsTab = fromUrl === "telegram" ? "telegram" : "company";
  const tabButton = (value: SettingsTab, label: string, icon: IconName) => (
    <button
      className={tab === value ? "on" : ""}
      onClick={() =>
        setParams(value === "company" ? {} : { tab: value }, {
          replace: true,
        })
      }
    >
      <Icon name={icon} size={16} />
      {label}
    </button>
  );

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Setări</h1>
          <p>
            {canEdit
              ? "Configurarea biroului, folosită în toată aplicația."
              : "Configurarea biroului (doar adminul o modifică)."}
          </p>
        </div>
      </div>
      <div className="card">
        <div className="tabs">
          {tabButton("company", "Date companie", "clients")}
          {tabButton("telegram", "Telegram", "send")}
        </div>
        {tab === "company" && <CompanyTab />}
        {tab === "telegram" && <TelegramBotSection canEdit={canEdit} />}
      </div>
    </>
  );
}

function CompanyTab() {
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
      <form
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

const BOT_STATUS: Record<BotSettingsOut["status"], [string, string]> = {
  not_configured: ["Neconfigurat", "b-grey"],
  pending: ["Se verifică tokenul…", "b-warn"],
  connected: ["Conectat", "b-ok"],
  error: ["Eroare", "b-bad"],
};

/** Tokenul botului (doar adminul îl setează; nu se mai afișează după salvare) și starea lui. */
function TelegramBotSection({ canEdit }: { canEdit: boolean }) {
  const queryClient = useQueryClient();
  const [token, setToken] = useState("");
  const bot = useQuery({
    queryKey: ["telegram-bot"],
    queryFn: () => api.get<BotSettingsOut>("/api/settings/telegram-bot"),
    // cât timp procesul botului verifică tokenul, starea se reîmprospătează des
    refetchInterval: (q) =>
      q.state.data?.configured && q.state.data.status !== "connected" ? 3000 : 30000,
  });
  const save = useMutation({
    mutationFn: (value: string | null) =>
      api.put<BotSettingsOut>("/api/settings/telegram-bot", { token: value }),
    onSuccess: (data) => {
      setToken("");
      queryClient.setQueryData(["telegram-bot"], data);
      // linkurile din cartele depind de starea botului
      void queryClient.invalidateQueries({ queryKey: ["telegram"] });
    },
  });
  const data = bot.data;
  const [label, cls] = data ? BOT_STATUS[data.status] : ["", ""];

  return (
    <div className="card-b" style={{ padding: 24 }}>
      <div className="form-section">
        <div>
          <h3>Bot</h3>
          <p>Clienții își transmit kilometrajul automobilelor prin bot.</p>
        </div>
        <div className="stack">
          {bot.error && <div className="error">{bot.error.message}</div>}
          {save.error && <div className="error">{save.error.message}</div>}
          {!data ? (
            <div className="loading">Se încarcă…</div>
          ) : (
            <>
              <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                <span className={`badge ${cls}`}>{label}</span>
                {data.status === "connected" && data.username && (
                  <a href={`https://t.me/${data.username}`} target="_blank" rel="noreferrer">
                    @{data.username}
                  </a>
                )}
                {data.token_hint && (
                  <span className="muted mono" style={{ fontSize: 12 }}>
                    token {data.token_hint}
                  </span>
                )}
              </div>
              {data.status === "error" && data.status_message && (
                <div className="callout warn">
                  <Icon name="alert" />
                  <div style={{ fontSize: 13 }}>{data.status_message}</div>
                </div>
              )}
              {data.configured && !data.running && (
                <div className="callout warn">
                  <Icon name="alert" />
                  <div style={{ fontSize: 13 }}>
                    Procesul botului nu rulează pe server, deci tokenul nu a fost preluat.
                    Pornește-l cu:{" "}
                    <code>
                      docker compose -f docker-compose.yml -f docker-compose.dev.yml --profile bot
                      up -d bot
                    </code>
                  </div>
                </div>
              )}
              {canEdit ? (
                <form
                  style={{ display: "flex", gap: 8, flexWrap: "wrap" }}
                  onSubmit={(e) => {
                    e.preventDefault();
                    save.mutate(token.trim());
                  }}
                >
                  <input
                    className="input mono"
                    style={{ flex: "1 1 320px" }}
                    type="password"
                    autoComplete="off"
                    placeholder={
                      data.configured
                        ? "Token nou (înlocuiește tokenul salvat)"
                        : "Tokenul de la @BotFather"
                    }
                    value={token}
                    onChange={(e) => setToken(e.target.value)}
                    required
                  />
                  <button className="btn primary" type="submit" disabled={save.isPending}>
                    <Icon name="check" size={16} /> Salvează tokenul
                  </button>
                  {data.configured && (
                    <button
                      className="btn ghost"
                      type="button"
                      disabled={save.isPending}
                      onClick={() => {
                        if (
                          window.confirm(
                            "Oprești botul? Clienții nu vor mai putea transmite kilometrajul până pui un token nou.",
                          )
                        )
                          save.mutate(null);
                      }}
                    >
                      Oprește botul
                    </button>
                  )}
                </form>
              ) : (
                <div className="muted" style={{ fontSize: 13 }}>
                  Doar adminul schimbă tokenul botului.
                </div>
              )}
              {canEdit && !data.configured && (
                <div className="hint muted" style={{ fontSize: 12 }}>
                  Cum obții tokenul: în Telegram deschide @BotFather, trimite /newbot, alege un nume
                  și un nume de utilizator care se termină în „bot”. BotFather îți dă tokenul (ex.
                  123456789:AAH…); lipește-l aici. Nu-l trimite nimănui prin chat.
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
