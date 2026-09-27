import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { Link, useParams, useSearchParams } from "react-router";

import { api } from "../api/client";
import type {
  AssignmentOut,
  ClientOut,
  ClientReportTypeOut,
  ClientSaveOut,
  ClientUpdate,
  RecalculateDiff,
  UserOut,
} from "../api/types";
import { ROLE_LABEL, isEditor, useMe } from "../auth/useAuth";
import { ErrorBox } from "../components/ErrorBox";
import { Icon, type IconName } from "../components/Icon";
import { Avatar, CopyButton, Empty } from "../components/ui";
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

// --- Mici ajutoare vizuale ---

/** IBAN grupat câte 4: MD24AG000225100013104168 → MD24 AG00 0225 1000 1310 4168 */
function formatIban(iban: string): string {
  return iban
    .replace(/\s+/g, "")
    .replace(/(.{4})/g, "$1 ")
    .trim();
}

function Section({
  icon,
  title,
  children,
  wide,
}: {
  icon: IconName;
  title: string;
  children: ReactNode;
  wide?: boolean;
}) {
  return (
    <section className={`info-section${wide ? " wide" : ""}`}>
      <div className="info-section-h">
        <span className="info-ico">
          <Icon name={icon} size={16} />
        </span>
        {title}
      </div>
      {children}
    </section>
  );
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="kv">
      <div className="k">{label}</div>
      <div className="v">{children}</div>
    </div>
  );
}

// --- Pagina ---

export function ClientPage() {
  const id = Number(useParams().id);
  const me = useMe();
  // ?tab=parc deschide direct parcul auto (ex. din grila lunii)
  const [params] = useSearchParams();
  const [tab, setTab] = useState<Tab>(params.get("tab") === "parc" ? "fleet" : "legal");
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

  const tabButton = (value: Tab, label: string, icon: IconName, count?: number) => (
    <button className={tab === value ? "on" : ""} onClick={() => setTab(value)}>
      <Icon name={icon} size={16} />
      {label}
      {count !== undefined && <span className="tab-count">{count}</span>}
    </button>
  );

  return (
    <>
      <div className="crumbs">
        <Link to="/clienti">
          <Icon name="back" size={14} /> Clienți
        </Link>
        <span className="sep">/</span>
        <span>{c.name}</span>
      </div>
      {diff && <DiffNotice diff={diff} onClose={() => setDiff(null)} />}

      <div className={`card client-card${c.status === "archived" ? " archived" : ""}`}>
        <div className="client-hero">
          <div className="client-logo">{initials(c.name)}</div>
          <div className="client-hero-main">
            <h1>{c.name}</h1>
            {c.full_name && c.full_name !== c.name && (
              <div className="client-fullname">{c.full_name}</div>
            )}
            <div className="client-meta">
              <VatBadge vat={c.is_vat_payer} />
              <ClientStatusBadge status={c.client_status} />
              {c.status === "archived" && <span className="badge b-bad">Arhivat</span>}
              <span className="meta-chip mono">
                <span className="muted">IDNO</span> {c.idno}
                <CopyButton value={c.idno} label="Copiază IDNO" />
              </span>
              {c.locality && (
                <span className="meta-chip">
                  <Icon name="pin" size={14} /> {c.locality}
                </span>
              )}
            </div>
          </div>
          <div className="client-owner">
            <div className="owner-label">Contabil responsabil</div>
            {c.accountants.length > 0 ? (
              <div className="owner-list">
                {c.accountants.map((a) => (
                  <span key={a.full_name} className="owner">
                    <Avatar name={a.full_name} size={28} />
                    <span className="strong">{a.full_name}</span>
                  </span>
                ))}
              </div>
            ) : (
              <span className="badge b-warn">nerepartizat</span>
            )}
          </div>
        </div>

        <div className="client-stats">
          <div className="stat">
            <span className="stat-ico">
              <Icon name="briefcase" size={16} />
            </span>
            <div>
              <div className="stat-l">Formă juridică</div>
              <div className="stat-v">{LEGAL_FORM[c.legal_form] ?? c.legal_form}</div>
            </div>
          </div>
          <div className="stat">
            <span className="stat-ico">
              <Icon name="calendar" size={16} />
            </span>
            <div>
              <div className="stat-l">Client din</div>
              <div className="stat-v">{formatDate(c.client_since)}</div>
            </div>
          </div>
          <div className="stat">
            <span className="stat-ico">
              <Icon name="bank" size={16} />
            </span>
            <div>
              <div className="stat-l">Conturi bancare</div>
              <div className="stat-v">{c.bank_accounts.length}</div>
            </div>
          </div>
          <div className="stat">
            <span className="stat-ico">
              <Icon name="user" size={16} />
            </span>
            <div>
              <div className="stat-l">Contacte</div>
              <div className="stat-v">{c.contacts.length}</div>
            </div>
          </div>
        </div>

        <div className="tabs client-tabs">
          {tabButton("legal", "Date legale", "id")}
          {tabButton("bank", "Conturi bancare", "bank", c.bank_accounts.length)}
          {tabButton("contacts", "Contacte", "user", c.contacts.length)}
          {tabButton("reports", "Rapoarte", "reports")}
          {hasFleet && tabButton("fleet", "Parc auto", "truck")}
          {tabButton("team", "Contabili", "team")}
        </div>
        <div className="client-body">
          {tab === "legal" && <LegalTab client={c} canActivate={isEditor(me)} onSaved={setDiff} />}
          {tab === "bank" && <BankTab client={c} />}
          {tab === "contacts" && <ContactsTab client={c} />}
          {tab === "reports" && <ReportsTab clientId={c.id} />}
          {tab === "fleet" && hasFleet && <FleetTab client={c} />}
          {tab === "team" && <TeamTab client={c} canEdit={isEditor(me)} />}
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
      <div className="stack">
        {client.status === "active" && (
          <div className="tab-head">
            <div className="muted">Datele de înregistrare și regimul fiscal al clientului.</div>
            <div className="tab-actions">
              {canActivate && client.client_status === "onboarding" && (
                <button
                  className="btn primary"
                  disabled={save.isPending}
                  onClick={() => save.mutate({ client_status: "active" })}
                >
                  <Icon name="check" size={16} /> Activează clientul
                </button>
              )}
              <button
                className="btn"
                onClick={() => {
                  setForm({});
                  setEditing(true);
                }}
              >
                <Icon name="edit" size={16} /> Modifică
              </button>
            </div>
          </div>
        )}
        {save.error && <div className="error">{save.error.message}</div>}

        <div className="info-grid">
          <Section icon="id" title="Identificare">
            <Row label="Denumire completă">
              {client.full_name ?? <span className="nil">—</span>}
            </Row>
            <Row label="IDNO">
              <span className="mono">{client.idno}</span>
              <CopyButton value={client.idno} label="Copiază IDNO" />
            </Row>
            <Row label="Formă juridică">{LEGAL_FORM[client.legal_form] ?? client.legal_form}</Row>
            <Row label="Data înregistrării">{formatDate(client.registered_on)}</Row>
          </Section>

          <Section icon="reports" title="Regim fiscal">
            <Row label="TVA">
              {client.is_vat_payer ? (
                <span className="badge b-pri">Plătitor TVA</span>
              ) : (
                <span className="badge b-grey">Neînregistrat</span>
              )}
            </Row>
            {client.is_vat_payer && (
              <Row label="Cod TVA">
                {client.vat_code ? (
                  <>
                    <span className="mono">{client.vat_code}</span>
                    <CopyButton value={client.vat_code} label="Copiază codul TVA" />
                  </>
                ) : (
                  <span className="nil">—</span>
                )}
              </Row>
            )}
            <div className="kv col">
              <div className="k">Atribute pentru rapoarte</div>
              <div className="flag-list">
                {RULE_FLAGS.map(([key, label]) => (
                  <span key={key} className={`flag${client[key] ? " on" : ""}`}>
                    <Icon name={client[key] ? "check" : "plus"} size={13} />
                    {label}
                  </span>
                ))}
              </div>
            </div>
          </Section>

          <Section icon="pin" title="Activitate și adresă">
            <Row label="Adresă juridică">
              {client.legal_address ?? <span className="nil">—</span>}
            </Row>
            <Row label="Localitate">{client.locality ?? <span className="nil">—</span>}</Row>
            <Row label="Activitate (CAEM)">
              {client.caem_code || client.activity ? (
                <>
                  {client.caem_code && <span className="chip-r b-pri">{client.caem_code}</span>}{" "}
                  {client.activity}
                </>
              ) : (
                <span className="nil">—</span>
              )}
            </Row>
            <Row label="Client din">{formatDate(client.client_since)}</Row>
          </Section>

          <Section icon="note" title="Note">
            {client.notes ? (
              <div className="note-text">{client.notes}</div>
            ) : (
              <div className="nil">Nicio notă.</div>
            )}
          </Section>
        </div>
      </div>
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
      className="stack edit-form"
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
        <div className="field full">
          <label>Atribute pentru rapoarte</label>
          <div className="flag-grid">
            {RULE_FLAGS.map(([key, label]) => (
              <label key={key} className={`flag-toggle${value(key) ? " on" : ""}`}>
                <input
                  type="checkbox"
                  checked={Boolean(value(key))}
                  onChange={(e) => set(key, e.target.checked)}
                />
                {label}
              </label>
            ))}
          </div>
        </div>
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
      <div className="form-actions">
        <button className="btn" type="button" onClick={() => setEditing(false)}>
          Renunță
        </button>
        <button className="btn primary" type="submit" disabled={save.isPending}>
          <Icon name="check" size={16} /> Salvează
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
  // contul principal primul
  const accounts = [...client.bank_accounts].sort(
    (a, b) => Number(b.is_primary) - Number(a.is_primary),
  );

  return (
    <div className="stack">
      {error && <div className="error">{error.message}</div>}
      {accounts.length === 0 ? (
        <Empty icon="bank" title="Niciun cont bancar" hint="Adaugă primul cont mai jos." />
      ) : (
        <div className="tile-grid">
          {accounts.map((a) => (
            <div key={a.id} className={`tile acct${a.is_primary ? " primary" : ""}`}>
              <div className="tile-top">
                <span className="tile-ico">
                  <Icon name="bank" size={18} />
                </span>
                <div className="grow">
                  <div className="strong">{a.bank_name}</div>
                  <div className="tile-sub">
                    <span className="badge plain b-grey">{a.currency}</span>
                    {a.is_primary && (
                      <span className="badge plain b-ok">
                        <Icon name="star" size={12} /> Principal
                      </span>
                    )}
                  </div>
                </div>
              </div>
              <div className="iban">
                <span className="mono">{formatIban(a.iban)}</span>
                <CopyButton value={a.iban.replace(/\s+/g, "")} label="Copiază IBAN" />
              </div>
              <div className="tile-actions">
                {!a.is_primary && (
                  <button className="btn sm" onClick={() => makePrimary.mutate(a.id)}>
                    <Icon name="star" size={14} /> Fă principal
                  </button>
                )}
                <button className="btn sm ghost danger" onClick={() => remove.mutate(a.id)}>
                  <Icon name="trash" size={14} /> Șterge
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
      {client.status === "active" && (
        <form
          className="add-box"
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
          <div className="add-box-h">
            <Icon name="plus" size={16} /> Cont nou
          </div>
          <div className="add-box-row">
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
              style={{ minWidth: 280, flex: 1 }}
            />
            <button className="btn primary" type="submit" disabled={add.isPending}>
              Adaugă cont
            </button>
          </div>
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
  const contacts = [...client.contacts].sort((a, b) => Number(b.is_primary) - Number(a.is_primary));

  return (
    <div className="stack">
      {error && <div className="error">{error.message}</div>}
      {contacts.length === 0 ? (
        <Empty icon="user" title="Niciun contact" hint="Adaugă persoana de legătură mai jos." />
      ) : (
        <div className="tile-grid">
          {contacts.map((c) => (
            <div key={c.id} className={`tile contact${c.is_primary ? " primary" : ""}`}>
              <div className="tile-top">
                <Avatar name={c.full_name} size={40} />
                <div className="grow">
                  <div className="strong">{c.full_name}</div>
                  <div className="tile-sub">
                    <span className="muted">{c.position ?? "Fără rol"}</span>
                    {c.is_primary && (
                      <span className="badge plain b-ok">
                        <Icon name="star" size={12} /> Principal
                      </span>
                    )}
                  </div>
                </div>
                <button
                  className="icon-btn sm danger"
                  title="Șterge contactul"
                  aria-label="Șterge contactul"
                  onClick={() => remove.mutate(c.id)}
                >
                  <Icon name="trash" size={15} />
                </button>
              </div>
              <div className="contact-lines">
                {c.phone ? (
                  <a className="contact-line mono" href={`tel:${c.phone.replace(/\s+/g, "")}`}>
                    <Icon name="phone" size={15} /> {c.phone}
                  </a>
                ) : (
                  <span className="contact-line nil">
                    <Icon name="phone" size={15} /> —
                  </span>
                )}
                {c.email ? (
                  <a className="contact-line" href={`mailto:${c.email}`}>
                    <Icon name="mail" size={15} /> {c.email}
                  </a>
                ) : (
                  <span className="contact-line nil">
                    <Icon name="mail" size={15} /> —
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
      {client.status === "active" && (
        <form
          className="add-box"
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
          <div className="add-box-h">
            <Icon name="plus" size={16} /> Contact nou
          </div>
          <div className="add-box-row">
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
            <button className="btn primary" type="submit" disabled={add.isPending}>
              Adaugă contact
            </button>
          </div>
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
  const auto = active.filter((o) => o.source === "auto").length;

  const rows = (list: ClientReportTypeOut[]) =>
    list.map((o) => (
      <tr key={o.id}>
        <td>
          <span className="chip-r b-pri">{o.report_type.code}</span>
        </td>
        <td className="strong">{o.report_type.name}</td>
        <td>
          {o.source === "auto" ? (
            <span className="badge b-grey">după reguli</span>
          ) : (
            <span className="badge b-warn">manual</span>
          )}
        </td>
        <td className="mono muted">{formatDate(o.valid_from)}</td>
        <td className="mono muted">{formatDate(o.valid_to)}</td>
      </tr>
    ));

  return (
    <div className="stack">
      <div className="tab-head">
        <div className="muted">
          Rapoartele pe care clientul trebuie să le depună. Cele „după reguli” se calculează automat
          din atributele clientului; cele „manual” le-a stabilit un om.
        </div>
        <div className="pill-row">
          <span className="pill">
            <b>{active.length}</b> active
          </span>
          <span className="pill">
            <b>{auto}</b> după reguli
          </span>
          <span className="pill">
            <b>{active.length - auto}</b> manual
          </span>
        </div>
      </div>
      <div className="table-wrap framed">
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
        <details className="closed-list">
          <summary>Obligații încheiate ({inactive.length})</summary>
          <div className="table-wrap framed">
            <table>
              <tbody>{rows(inactive)}</tbody>
            </table>
          </div>
        </details>
      )}
    </div>
  );
}

function TeamTab({ client, canEdit }: { client: ClientOut; canEdit: boolean }) {
  const queryClient = useQueryClient();
  const [userId, setUserId] = useState("");
  const history = useQuery({
    queryKey: ["assignments", client.id],
    queryFn: () => api.get<AssignmentOut[]>(`/api/clients/${client.id}/assignments`),
  });
  // lista utilizatorilor o văd doar admin și director (ca și repartizarea)
  const users = useQuery({
    queryKey: ["users", false],
    queryFn: () => api.get<UserOut[]>("/api/users"),
    enabled: canEdit,
  });
  const done = (rows: AssignmentOut[]) => {
    queryClient.setQueryData(["assignments", client.id], rows);
    // contabilii apar și în capul cartelei și în lista de clienți
    void queryClient.invalidateQueries({ queryKey: ["client", client.id] });
    void queryClient.invalidateQueries({ queryKey: ["clients"] });
  };
  const assign = useMutation({
    mutationFn: () =>
      api.post<AssignmentOut[]>(`/api/clients/${client.id}/assignments`, {
        user_id: Number(userId),
      }),
    onSuccess: (rows) => {
      setUserId("");
      done(rows);
    },
  });
  const unassign = useMutation({
    mutationFn: (assignmentId: number) =>
      api.del<AssignmentOut[]>(`/api/client-assignments/${assignmentId}`),
    onSuccess: done,
  });

  if (history.error) return <ErrorBox error={history.error} />;
  if (!history.data) return <div className="loading">Se încarcă…</div>;
  const current = new Set(history.data.filter((a) => !a.unassigned_at).map((a) => a.user.id));
  // contabilii primii, apoi ceilalți; fără cei deja repartizați
  const candidates = (users.data ?? [])
    .filter((u) => u.status === "active" && !current.has(u.id))
    .sort(
      (a, b) =>
        Number(b.role === "contabil") - Number(a.role === "contabil") ||
        a.full_name.localeCompare(b.full_name, "ro"),
    );
  const editable = canEdit && client.status === "active";
  const error = assign.error ?? unassign.error;

  return (
    <div className="stack">
      {error && <div className="error">{error.message}</div>}
      {editable && (
        <form
          style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}
          onSubmit={(e) => {
            e.preventDefault();
            assign.mutate();
          }}
        >
          <select
            className="input"
            style={{ minWidth: 260 }}
            value={userId}
            onChange={(e) => setUserId(e.target.value)}
            required
            aria-label="Contabil"
          >
            <option value="" disabled>
              {users.isLoading
                ? "Se încarcă…"
                : candidates.length
                  ? "Alege contabilul…"
                  : "Niciun utilizator disponibil"}
            </option>
            {candidates.map((u) => (
              <option key={u.id} value={u.id}>
                {u.full_name} ({ROLE_LABEL[u.role].toLowerCase()})
              </option>
            ))}
          </select>
          <button className="btn primary" type="submit" disabled={!userId || assign.isPending}>
            <Icon name="plus" size={16} /> Repartizează
          </button>
          {users.data && candidates.length === 0 && (
            <span className="muted" style={{ fontSize: 13 }}>
              Conturi noi se creează din <Link to="/utilizatori">Utilizatori</Link>.
            </span>
          )}
        </form>
      )}
      {history.data.length === 0 ? (
        <Empty
          icon="team"
          title="Niciun contabil repartizat"
          hint={editable ? "Alege contabilul din listă și apasă „Repartizează”." : undefined}
        />
      ) : (
        <div className="timeline team-timeline">
          {history.data.map((a) => (
            <div className={`tl${a.unassigned_at ? " past" : ""}`} key={a.id}>
              <div className="tl-row">
                <Avatar name={a.user.full_name} size={32} />
                <div className="grow">
                  <div className="strong">
                    {a.user.full_name}{" "}
                    {a.unassigned_at ? (
                      <span className="badge b-grey">până la {formatDate(a.unassigned_at)}</span>
                    ) : (
                      <span className="badge b-ok">actual</span>
                    )}
                  </div>
                  <div className="s">repartizat din {formatDate(a.assigned_at)}</div>
                </div>
                {editable && !a.unassigned_at && (
                  <button
                    className="btn sm ghost"
                    disabled={unassign.isPending}
                    onClick={() => {
                      if (
                        window.confirm(
                          `Scoți pe ${a.user.full_name} de la ${client.name}? Rămâne în istoric.`,
                        )
                      )
                        unassign.mutate(a.id);
                    }}
                  >
                    Scoate
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
