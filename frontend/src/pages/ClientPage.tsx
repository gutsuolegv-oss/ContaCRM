import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router";

import { api } from "../api/client";
import type {
  AssignmentOut,
  ClientOut,
  ClientReportTypeOut,
  ClientSaveOut,
  ClientUpdate,
  RecalculateDiff,
} from "../api/types";
import { isEditor, useMe } from "../auth/useAuth";
import { ErrorBox } from "../components/ErrorBox";
import { Icon } from "../components/Icon";
import { formatDate, initials } from "../format";
import { ClientStatusBadge, VatBadge } from "./ClientsPage";
import { FleetTab } from "./FleetTab";

type Tab = "legal" | "bank" | "contacts" | "reports" | "fleet" | "team";

const LEGAL_FORM: Record<string, string> = {
  SRL: "SRL",
  SA: "SA",
  II: "ÎI",
  GT: "GȚ",
  ONG: "ONG",
};

export function ClientPage() {
  const id = Number(useParams().id);
  const me = useMe();
  const [tab, setTab] = useState<Tab>("legal");
  const [diff, setDiff] = useState<RecalculateDiff | null>(null);
  const client = useQuery({
    queryKey: ["client", id],
    queryFn: () => api.get<ClientOut>(`/api/clients/${id}`),
  });

  if (client.error) return <ErrorBox error={client.error} />;
  if (!client.data) return <div className="loading">Se încarcă…</div>;
  const c = client.data;
  // Parcul auto: doar la clienții cu transport (bifa din „Date legale”), nearhivați.
  const hasFleet = c.has_transport && c.status === "active";

  const tabButton = (value: Tab, label: string) => (
    <button className={tab === value ? "on" : ""} onClick={() => setTab(value)}>
      {label}
    </button>
  );

  return (
    <>
      <div className="crumbs">
        <Link to="/clienti">Clienți</Link> / {c.name}
      </div>
      {diff && <DiffNotice diff={diff} onClose={() => setDiff(null)} />}
      <div className="card" style={{ marginBottom: 16 }}>
        <div className="client-head">
          <div className="client-logo">{initials(c.name)}</div>
          <div style={{ flex: 1, minWidth: 200 }}>
            <h1 style={{ margin: "0 0 6px", fontSize: 22 }}>{c.name}</h1>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
              <VatBadge vat={c.is_vat_payer} />
              <ClientStatusBadge status={c.client_status} />
              {c.status === "archived" && <span className="badge b-bad">Arhivat</span>}
              <span className="muted mono">IDNO {c.idno}</span>
              {c.locality && (
                <span className="muted">
                  <Icon name="pin" size={14} /> {c.locality}
                </span>
              )}
            </div>
          </div>
          <div>
            <div className="muted" style={{ fontSize: 12, marginBottom: 4 }}>
              Contabil responsabil
            </div>
            <div className="strong">
              {c.accountants.map((a) => a.full_name).join(", ") || "nerepartizat"}
            </div>
          </div>
        </div>
        <div className="tabs">
          {tabButton("legal", "Date legale")}
          {tabButton("bank", "Conturi bancare")}
          {tabButton("contacts", "Contacte")}
          {tabButton("reports", "Rapoarte")}
          {hasFleet && tabButton("fleet", "Parc auto")}
          {tabButton("team", "Contabili")}
        </div>
        <div className="card-b" style={{ padding: 20 }}>
          {tab === "legal" && <LegalTab client={c} canActivate={isEditor(me)} onSaved={setDiff} />}
          {tab === "bank" && <BankTab client={c} />}
          {tab === "contacts" && <ContactsTab client={c} />}
          {tab === "reports" && <ReportsTab clientId={c.id} />}
          {tab === "fleet" && hasFleet && <FleetTab client={c} />}
          {tab === "team" && <TeamTab clientId={c.id} />}
        </div>
      </div>
    </>
  );
}

// --- Rezultatul recalculării automate ---

function DiffNotice({ diff, onClose }: { diff: RecalculateDiff; onClose: () => void }) {
  const added = diff.to_add.map((r) => r.code);
  const removed = diff.to_deactivate.map((r) => r.code);
  return (
    <div className="callout" style={{ marginBottom: 16 }}>
      <Icon name="info" />
      <div style={{ flex: 1, fontSize: 13 }}>
        <b>Obligațiile clientului s-au recalculat automat</b> (de la {formatDate(diff.as_of)}).
        {added.length > 0 && (
          <>
            {" "}
            Adăugate: <b>{added.join(", ")}</b>.
          </>
        )}
        {removed.length > 0 && (
          <>
            {" "}
            Scoase: <b>{removed.join(", ")}</b>.
          </>
        )}
        {added.length === 0 && removed.length === 0 && " Nicio schimbare."}
      </div>
      <button className="btn sm ghost" onClick={onClose}>
        OK
      </button>
    </div>
  );
}

// --- Date legale (vizualizare + editare) ---

const RULE_FLAGS = [
  ["is_vat_payer", "Plătitor de TVA"],
  ["has_employees", "Are angajați"],
  ["is_it_park_resident", "Rezident IT Park"],
  ["has_transport", "Are transport"],
] as const;

function LegalTab({
  client,
  canActivate,
  onSaved,
}: {
  client: ClientOut;
  canActivate: boolean;
  onSaved: (diff: RecalculateDiff | null) => void;
}) {
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState<ClientUpdate>({});
  const save = useMutation({
    mutationFn: (body: ClientUpdate) => api.patch<ClientSaveOut>(`/api/clients/${client.id}`, body),
    onSuccess: (result) => {
      queryClient.setQueryData(["client", client.id], result.client);
      void queryClient.invalidateQueries({ queryKey: ["clients"] });
      void queryClient.invalidateQueries({ queryKey: ["obligations", client.id] });
      onSaved(result.recalculation ?? null);
      setEditing(false);
    },
  });

  if (!editing) {
    return (
      <>
        <dl className="dl">
          <dt>Denumire completă</dt>
          <dd>{client.full_name ?? "—"}</dd>
          <dt>IDNO</dt>
          <dd className="mono">{client.idno}</dd>
          <dt>Formă juridică</dt>
          <dd>{LEGAL_FORM[client.legal_form]}</dd>
          <dt>Regim fiscal</dt>
          <dd>
            {client.is_vat_payer
              ? `Plătitor TVA${client.vat_code ? ` · cod TVA ${client.vat_code}` : ""}`
              : "Neînregistrat ca plătitor TVA"}
          </dd>
          <dt>Atribute pentru rapoarte</dt>
          <dd>
            {RULE_FLAGS.filter(([key]) => client[key])
              .map(([, label]) => label)
              .join(" · ") || "—"}
          </dd>
          <dt>Adresă juridică</dt>
          <dd>{client.legal_address ?? "—"}</dd>
          <dt>Activitate (CAEM)</dt>
          <dd>{[client.caem_code, client.activity].filter(Boolean).join(" ") || "—"}</dd>
          <dt>Data înregistrării</dt>
          <dd>{formatDate(client.registered_on)}</dd>
          <dt>Client din</dt>
          <dd>{formatDate(client.client_since)}</dd>
          <dt>Note</dt>
          <dd>{client.notes ?? "—"}</dd>
        </dl>
        {client.status === "active" && (
          <div style={{ marginTop: 20, display: "flex", gap: 8 }}>
            <button
              className="btn"
              onClick={() => {
                setForm({});
                setEditing(true);
              }}
            >
              Modifică
            </button>
            {canActivate && client.client_status === "onboarding" && (
              <button
                className="btn primary"
                disabled={save.isPending}
                onClick={() => save.mutate({ client_status: "active" })}
              >
                Activează clientul
              </button>
            )}
          </div>
        )}
      </>
    );
  }

  const value = <K extends keyof ClientUpdate>(key: K) =>
    (key in form ? form[key] : client[key as keyof ClientOut]) as ClientUpdate[K];
  const set = <K extends keyof ClientUpdate>(key: K, v: ClientUpdate[K]) =>
    setForm((f) => ({ ...f, [key]: v }));
  const text = (key: "name" | "full_name" | "locality" | "legal_address" | "notes") => (
    <input
      className="input"
      value={(value(key) as string | null) ?? ""}
      onChange={(e) => set(key, e.target.value || null)}
    />
  );

  return (
    <form
      className="stack"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate(form);
      }}
    >
      {save.error && <div className="error">{save.error.message}</div>}
      <div className="form">
        <div className="field">
          <label>Denumire</label>
          {text("name")}
        </div>
        <div className="field">
          <label>Localitate</label>
          {text("locality")}
        </div>
        <div className="field full">
          <label>Denumire completă</label>
          {text("full_name")}
        </div>
        <div className="field full">
          <label>Adresă juridică</label>
          {text("legal_address")}
        </div>
        {RULE_FLAGS.map(([key, label]) => (
          <label key={key} className="field" style={{ flexDirection: "row", gap: 8 }}>
            <input
              type="checkbox"
              checked={Boolean(value(key))}
              onChange={(e) => set(key, e.target.checked)}
            />
            {label}
          </label>
        ))}
        {value("is_vat_payer") && (
          <div className="field">
            <label>Cod TVA (7 cifre)</label>
            <input
              className="input mono"
              value={(value("vat_code") as string | null) ?? ""}
              onChange={(e) => set("vat_code", e.target.value || null)}
            />
          </div>
        )}
        <div className="field full">
          <label>Note</label>
          {text("notes")}
          <div className="hint">
            Plătitor TVA, angajați, IT Park și transport decid rapoartele clientului: dacă le
            schimbi, obligațiile se recalculează automat.
          </div>
        </div>
      </div>
      <div style={{ display: "flex", gap: 8 }}>
        <button className="btn primary" type="submit" disabled={save.isPending}>
          Salvează
        </button>
        <button className="btn" type="button" onClick={() => setEditing(false)}>
          Renunță
        </button>
      </div>
    </form>
  );
}

// --- Conturi bancare și contacte ---

function useCardMutation<T>(clientId: number, fn: (body: T) => Promise<ClientOut>) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: (card) => queryClient.setQueryData(["client", clientId], card),
  });
}

function BankTab({ client }: { client: ClientOut }) {
  const [bank, setBank] = useState("");
  const [iban, setIban] = useState("");
  const add = useCardMutation(client.id, () =>
    api.post<ClientOut>(`/api/clients/${client.id}/bank-accounts`, {
      bank_name: bank,
      iban,
      is_primary: client.bank_accounts.length === 0,
    }),
  );
  const remove = useCardMutation(client.id, (id: number) =>
    api.del<ClientOut>(`/api/bank-accounts/${id}`),
  );
  const makePrimary = useCardMutation(client.id, (id: number) =>
    api.patch<ClientOut>(`/api/bank-accounts/${id}`, { is_primary: true }),
  );
  const error = add.error ?? remove.error ?? makePrimary.error;

  return (
    <div className="stack">
      {error && <div className="error">{error.message}</div>}
      {client.bank_accounts.length === 0 && <div className="muted">Niciun cont bancar.</div>}
      {client.bank_accounts.map((a) => (
        <div key={a.id} className="list-item" style={{ padding: "8px 0" }}>
          <Icon name="bank" />
          <div className="grow">
            <div className="t">
              {a.bank_name} {a.is_primary && <span className="badge plain b-ok">Principal</span>}
            </div>
            <div className="s mono">
              {a.iban} · {a.currency}
            </div>
          </div>
          {!a.is_primary && (
            <button className="btn sm" onClick={() => makePrimary.mutate(a.id)}>
              Fă principal
            </button>
          )}
          <button className="btn sm ghost" onClick={() => remove.mutate(a.id)}>
            Șterge
          </button>
        </div>
      ))}
      {client.status === "active" && (
        <form
          style={{ display: "flex", gap: 8, flexWrap: "wrap" }}
          onSubmit={(e) => {
            e.preventDefault();
            add.mutate(undefined, {
              onSuccess: () => {
                setBank("");
                setIban("");
              },
            });
          }}
        >
          <input
            className="input"
            placeholder="Bancă"
            value={bank}
            onChange={(e) => setBank(e.target.value)}
            required
          />
          <input
            className="input mono"
            placeholder="IBAN (MD…)"
            value={iban}
            onChange={(e) => setIban(e.target.value)}
            required
            style={{ minWidth: 280 }}
          />
          <button className="btn" type="submit" disabled={add.isPending}>
            <Icon name="plus" /> Adaugă cont
          </button>
        </form>
      )}
    </div>
  );
}

function ContactsTab({ client }: { client: ClientOut }) {
  const [name, setName] = useState("");
  const [position, setPosition] = useState("");
  const [phone, setPhone] = useState("");
  const add = useCardMutation(client.id, () =>
    api.post<ClientOut>(`/api/clients/${client.id}/contacts`, {
      full_name: name,
      position: position || null,
      phone: phone || null,
      is_primary: client.contacts.length === 0,
    }),
  );
  const remove = useCardMutation(client.id, (id: number) =>
    api.del<ClientOut>(`/api/contacts/${id}`),
  );
  const error = add.error ?? remove.error;

  return (
    <div className="stack">
      {error && <div className="error">{error.message}</div>}
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Nume</th>
              <th>Rol</th>
              <th>Telefon</th>
              <th>Email</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {client.contacts.map((c) => (
              <tr key={c.id}>
                <td className="strong">
                  {c.full_name}{" "}
                  {c.is_primary && <span className="badge plain b-ok">Principal</span>}
                </td>
                <td>{c.position ?? "—"}</td>
                <td className="mono">{c.phone ?? "—"}</td>
                <td>{c.email ?? "—"}</td>
                <td className="num">
                  <button className="btn sm ghost" onClick={() => remove.mutate(c.id)}>
                    Șterge
                  </button>
                </td>
              </tr>
            ))}
            {client.contacts.length === 0 && (
              <tr>
                <td colSpan={5} className="empty">
                  Niciun contact
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      {client.status === "active" && (
        <form
          style={{ display: "flex", gap: 8, flexWrap: "wrap" }}
          onSubmit={(e) => {
            e.preventDefault();
            add.mutate(undefined, {
              onSuccess: () => {
                setName("");
                setPosition("");
                setPhone("");
              },
            });
          }}
        >
          <input
            className="input"
            placeholder="Nume Prenume"
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
          />
          <input
            className="input"
            placeholder="Rol (ex. Administrator)"
            value={position}
            onChange={(e) => setPosition(e.target.value)}
          />
          <input
            className="input"
            placeholder="Telefon"
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
          />
          <button className="btn" type="submit" disabled={add.isPending}>
            <Icon name="plus" /> Adaugă contact
          </button>
        </form>
      )}
    </div>
  );
}

// --- Rapoarte (obligațiile clientului) și contabili ---

function ReportsTab({ clientId }: { clientId: number }) {
  const obligations = useQuery({
    queryKey: ["obligations", clientId],
    queryFn: () =>
      api.get<ClientReportTypeOut[]>(`/api/classifiers/clients/${clientId}/report-types`),
  });
  if (obligations.error) return <ErrorBox error={obligations.error} />;
  if (!obligations.data) return <div className="loading">Se încarcă…</div>;
  const active = obligations.data.filter((o) => o.is_active);
  const inactive = obligations.data.filter((o) => !o.is_active);

  const rows = (list: ClientReportTypeOut[]) =>
    list.map((o) => (
      <tr key={o.id}>
        <td>
          <span className="chip-r b-pri">{o.report_type.code}</span>
        </td>
        <td>{o.report_type.name}</td>
        <td>
          {o.source === "auto" ? (
            <span className="badge b-grey">după reguli</span>
          ) : (
            <span className="badge b-warn">manual</span>
          )}
        </td>
        <td>{formatDate(o.valid_from)}</td>
        <td>{formatDate(o.valid_to)}</td>
      </tr>
    ));

  return (
    <div className="stack">
      <div className="muted" style={{ fontSize: 13 }}>
        Rapoartele pe care clientul trebuie să le depună. Cele „după reguli” se calculează automat
        din atributele clientului; cele „manual” le-a stabilit un om.
      </div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Cod</th>
              <th>Raport</th>
              <th>Sursă</th>
              <th>De la</th>
              <th>Până la</th>
            </tr>
          </thead>
          <tbody>
            {rows(active)}
            {active.length === 0 && (
              <tr>
                <td colSpan={5} className="empty">
                  Nicio obligație activă
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      {inactive.length > 0 && (
        <details>
          <summary className="muted">Obligații încheiate ({inactive.length})</summary>
          <table>
            <tbody>{rows(inactive)}</tbody>
          </table>
        </details>
      )}
    </div>
  );
}

function TeamTab({ clientId }: { clientId: number }) {
  const history = useQuery({
    queryKey: ["assignments", clientId],
    queryFn: () => api.get<AssignmentOut[]>(`/api/clients/${clientId}/assignments`),
  });
  if (history.error) return <ErrorBox error={history.error} />;
  if (!history.data) return <div className="loading">Se încarcă…</div>;
  if (history.data.length === 0) return <div className="muted">Niciun contabil repartizat.</div>;
  return (
    <div className="timeline">
      {history.data.map((a) => (
        <div className="tl" key={a.id}>
          <div>
            {a.user.full_name}{" "}
            {a.unassigned_at ? (
              <span className="badge b-grey">până la {formatDate(a.unassigned_at)}</span>
            ) : (
              <span className="badge b-ok">actual</span>
            )}
          </div>
          <div className="s">repartizat din {formatDate(a.assigned_at)}</div>
        </div>
      ))}
    </div>
  );
}
