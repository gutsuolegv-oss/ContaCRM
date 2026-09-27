// Parc auto în cartela clientului: automobilele, odometrul lunar și foile de parcurs.
// Datele de la client se introduc manual (Telegram vine mai târziu).

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api } from "../api/client";
import type {
  ClientOut,
  FleetMonthOut,
  FleetRowOut,
  ReadingIn,
  TelegramStatusOut,
  VehicleCreate,
  VehicleOut,
  WaybillOut,
} from "../api/types";
import { ErrorBox } from "../components/ErrorBox";
import { Icon } from "../components/Icon";
import { CopyButton } from "../components/ui";
import { formatDate, formatMonth } from "../format";

const FUEL: Record<VehicleCreate["fuel_type"], string> = {
  benzina: "Benzină",
  motorina: "Motorină",
  gpl: "GPL",
  hibrid: "Hibrid",
};
const SOURCE: Record<NonNullable<ReadingIn["source"]>, string> = {
  email: "Email",
  phone: "Telefon",
  telegram: "Telegram",
  other: "Altă cale",
};
const STATUS: Record<FleetRowOut["status"], [string, string]> = {
  waiting: ["Așteptăm date", "b-grey"],
  late: ["Întârziat", "b-bad"],
  received: ["Date primite", "b-info"],
  issued: ["Foaie emisă", "b-ok"],
};

const NUMBER = new Intl.NumberFormat("ro-MD");
const km = (value: number) => `${NUMBER.format(value)} km`;
const liters = (value: number) => `${NUMBER.format(value)} l`;

function todayIso(): string {
  const d = new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

type Period = { year: number; month: number };

/** Luna curentă și cele două dinainte, cea mai recentă prima. */
function recentMonths(): Period[] {
  const now = new Date();
  return [0, 1, 2].map((back) => {
    const d = new Date(now.getFullYear(), now.getMonth() - back, 1);
    return { year: d.getFullYear(), month: d.getMonth() + 1 };
  });
}

type Modal =
  | { kind: "vehicle"; vehicle?: VehicleOut }
  | { kind: "reading"; row: FleetRowOut }
  | { kind: "waybill"; id: number };

export function FleetTab({ client }: { client: ClientOut }) {
  const queryClient = useQueryClient();
  const months = recentMonths();
  const [period, setPeriod] = useState<Period>(months[0]!);
  const [modal, setModal] = useState<Modal | null>(null);

  const fleet = useQuery({
    queryKey: ["fleet", client.id, period.year, period.month],
    queryFn: () =>
      api.get<FleetMonthOut>(`/api/clients/${client.id}/fleet`, {
        year: period.year,
        month: period.month,
      }),
  });
  const waybills = useQuery({
    queryKey: ["waybills", client.id],
    queryFn: () => api.get<WaybillOut[]>(`/api/clients/${client.id}/waybills`),
  });
  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: ["fleet", client.id] });
    void queryClient.invalidateQueries({ queryKey: ["waybills", client.id] });
  };

  const issue = useMutation({
    mutationFn: (vehicleId: number) =>
      api.post<WaybillOut>(
        `/api/vehicles/${vehicleId}/readings/${period.year}/${period.month}/waybill`,
      ),
    onSuccess: (w) => {
      refresh();
      setModal({ kind: "waybill", id: w.id });
    },
  });
  const issueAll = useMutation({
    mutationFn: () =>
      api.post<WaybillOut[]>(
        `/api/clients/${client.id}/fleet/${period.year}/${period.month}/waybills`,
      ),
    onSuccess: refresh,
  });

  if (fleet.error) return <ErrorBox error={fleet.error} />;
  if (!fleet.data) return <div className="loading">Se încarcă…</div>;
  const rows = fleet.data.rows;
  const received = rows.filter((r) => r.status === "received").length;
  const late = rows.filter((r) => r.status === "late").length;
  const deadlinePassed = rows.length > 0 && todayIso() > fleet.data.deadline;
  const error = issue.error ?? issueAll.error;

  const modals = (
    <>
      {modal?.kind === "vehicle" && (
        <VehicleModal
          clientId={client.id}
          vehicle={modal.vehicle}
          onClose={() => setModal(null)}
          onSaved={() => {
            refresh();
            setModal(null);
          }}
        />
      )}
      {modal?.kind === "reading" && (
        <ReadingModal
          row={modal.row}
          period={period}
          onClose={() => setModal(null)}
          onSaved={(waybillId) => {
            refresh();
            setModal(waybillId ? { kind: "waybill", id: waybillId } : null);
          }}
        />
      )}
      {modal?.kind === "waybill" && (
        <WaybillModal
          id={modal.id}
          onClose={() => setModal(null)}
          onCancelled={() => {
            refresh();
            setModal(null);
          }}
        />
      )}
    </>
  );

  if (rows.length === 0)
    return (
      <div className="empty" style={{ textAlign: "center", padding: "32px 16px" }}>
        <Icon name="truck" size={32} />
        <div style={{ margin: "12px 0 16px" }}>Clientul nu are automobile în evidență.</div>
        <button className="btn primary" onClick={() => setModal({ kind: "vehicle" })}>
          <Icon name="plus" /> Adaugă automobil
        </button>
        {modals}
      </div>
    );

  return (
    <div className="stack">
      <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
        <div className="seg">
          {months.map((m) => (
            <button
              key={`${m.year}-${m.month}`}
              className={m.year === period.year && m.month === period.month ? "on" : ""}
              onClick={() => setPeriod(m)}
            >
              {formatMonth(m.year, m.month)}
            </button>
          ))}
        </div>
        <span className="muted" style={{ fontSize: 13 }}>
          {deadlinePassed ? "Luna s-a încheiat la " : "Termen: "}
          <b>{formatDate(fleet.data.deadline)}</b>
        </span>
        <div style={{ flex: 1 }} />
        {received > 0 && (
          <button
            className="btn sm primary"
            disabled={issueAll.isPending}
            onClick={() => issueAll.mutate()}
          >
            <Icon name="reports" size={14} /> Generează foile ({received})
          </button>
        )}
        <button className="btn sm" onClick={() => setModal({ kind: "vehicle" })}>
          <Icon name="plus" size={14} /> Adaugă automobil
        </button>
      </div>

      {error && <div className="error">{error.message}</div>}
      {late > 0 && (
        <div className="callout" style={{ background: "var(--bad-soft)" }}>
          <Icon name="alert" />
          <div style={{ fontSize: 13 }}>
            <b>
              {late} {late === 1 ? "automobil" : "automobile"} fără date la odometru
            </b>{" "}
            după încheierea lunii. Cere-le clientului și introdu-le manual.
          </div>
        </div>
      )}

      <div className="card" style={{ boxShadow: "none" }}>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Automobil</th>
                <th>Șofer</th>
                <th>Normă</th>
                <th className="num">Odometru început</th>
                <th className="num">Odometru sfârșit</th>
                <th className="num">Km</th>
                <th className="num">Consum</th>
                <th>Primit</th>
                <th>Status</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => {
                const v = row.vehicle;
                const [label, cls] = STATUS[row.status];
                return (
                  <tr key={v.id}>
                    <td style={{ whiteSpace: "nowrap" }}>
                      <button
                        className="btn ghost sm"
                        style={{ padding: 0 }}
                        title="Editează automobilul"
                        onClick={() => setModal({ kind: "vehicle", vehicle: v })}
                      >
                        <span className="plate">{v.plate}</span>
                      </button>
                      <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>
                        {v.model} · {FUEL[v.fuel_type]}
                      </div>
                    </td>
                    <td style={{ whiteSpace: "nowrap" }}>{v.driver ?? "—"}</td>
                    <td className="mono" style={{ whiteSpace: "nowrap" }}>
                      {NUMBER.format(v.fuel_norm)} l/100
                    </td>
                    <td className="num mono">{km(row.start_odometer)}</td>
                    <td className="num mono">
                      {row.reading ? (
                        km(row.reading.end_odometer)
                      ) : (
                        <span className="muted">—</span>
                      )}
                    </td>
                    <td className="num mono strong">
                      {row.km !== null ? km(row.km) : <span className="muted">—</span>}
                    </td>
                    <td className="num mono" style={{ whiteSpace: "nowrap" }}>
                      {row.fuel_liters !== null ? (
                        liters(row.fuel_liters)
                      ) : (
                        <span className="muted">—</span>
                      )}
                    </td>
                    <td style={{ fontSize: 12, whiteSpace: "nowrap" }}>
                      {row.reading ? (
                        <>
                          {formatDate(row.reading.received_on)}
                          <div className="muted">{SOURCE[row.reading.source]}</div>
                        </>
                      ) : (
                        <span className="muted">—</span>
                      )}
                    </td>
                    <td>
                      <span className={`badge ${cls}`}>{label}</span>
                    </td>
                    <td className="num">
                      <span style={{ display: "inline-flex", gap: 6 }}>
                        {row.waybill ? (
                          <button
                            className="btn sm"
                            onClick={() => setModal({ kind: "waybill", id: row.waybill!.id })}
                          >
                            Vezi foaia
                          </button>
                        ) : (
                          <>
                            <button
                              className={`btn sm ${row.reading ? "" : "primary"}`}
                              onClick={() => setModal({ kind: "reading", row })}
                            >
                              {row.reading ? "Corectează" : "Introdu date"}
                            </button>
                            {row.reading && (
                              <button
                                className="btn sm primary"
                                disabled={issue.isPending}
                                onClick={() => issue.mutate(v.id)}
                              >
                                Generează foaia
                              </button>
                            )}
                          </>
                        )}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      <div className="grid g2" style={{ alignItems: "start" }}>
        <div className="card" style={{ boxShadow: "none" }}>
          <div className="card-h">
            <h3>Foi de parcurs emise</h3>
          </div>
          {waybills.data?.length ? (
            waybills.data.map((w) => (
              <div key={w.id} className="list-item">
                <Icon name="reports" />
                <div className="grow">
                  <div className="t mono">{w.number}</div>
                  <div className="s">
                    {w.plate} · {formatMonth(w.year, w.month)} · {km(w.km)} ·{" "}
                    {liters(w.fuel_liters)}
                  </div>
                </div>
                <button className="btn sm" onClick={() => setModal({ kind: "waybill", id: w.id })}>
                  Deschide
                </button>
              </div>
            ))
          ) : (
            <div className="card-b muted">Nicio foaie emisă încă.</div>
          )}
        </div>
        <TelegramCard clientId={client.id} />
      </div>
      {modals}
    </div>
  );
}

// --- Telegram ---

/** Linkul personal al clientului pentru bot și chat-urile legate de el. */
function TelegramCard({ clientId }: { clientId: number }) {
  const queryClient = useQueryClient();
  const status = useQuery({
    queryKey: ["telegram", clientId],
    queryFn: () => api.get<TelegramStatusOut>(`/api/clients/${clientId}/telegram`),
  });
  const done = (data: TelegramStatusOut) => queryClient.setQueryData(["telegram", clientId], data);
  const regenerate = useMutation({
    mutationFn: () => api.post<TelegramStatusOut>(`/api/clients/${clientId}/telegram/link`),
    onSuccess: done,
  });
  const unlink = useMutation({
    mutationFn: (id: number) => api.del<TelegramStatusOut>(`/api/telegram-chats/${id}`),
    onSuccess: done,
  });
  const error = status.error ?? regenerate.error ?? unlink.error;
  const data = status.data;

  return (
    <div className="card" style={{ boxShadow: "none" }}>
      <div className="card-h">
        <h3>Telegram</h3>
      </div>
      <div className="card-b stack">
        {error && <div className="error">{error.message}</div>}
        {!data ? (
          <div className="loading">Se încarcă…</div>
        ) : !data.bot_configured ? (
          <div className="muted" style={{ fontSize: 13 }}>
            Botul Telegram nu e conectat încă. Adminul îl configurează în Setări → Telegram.
          </div>
        ) : (
          <>
            <div className="muted" style={{ fontSize: 13 }}>
              Trimite-i clientului linkul personal. După ce îl deschide, apasă „Transmite parcurs”
              în bot, iar kilometrajul apare aici, cu sursa Telegram.
            </div>
            {data.link ? (
              <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                <input
                  className="input mono"
                  style={{ flex: 1, minWidth: 0, fontSize: 12 }}
                  value={data.link}
                  readOnly
                  onFocus={(e) => e.target.select()}
                />
                <CopyButton value={data.link} label="Copiază linkul" />
                <button
                  className="btn sm ghost"
                  disabled={regenerate.isPending}
                  onClick={() => {
                    if (
                      window.confirm(
                        "Generezi un link nou? Cel vechi nu va mai lega chat-uri noi; cele deja legate rămân.",
                      )
                    )
                      regenerate.mutate();
                  }}
                >
                  Link nou
                </button>
              </div>
            ) : (
              <div>
                <button
                  className="btn sm primary"
                  disabled={regenerate.isPending}
                  onClick={() => regenerate.mutate()}
                >
                  Generează linkul
                </button>
              </div>
            )}
          </>
        )}
        {data && data.chats.length > 0 && (
          <div>
            <div className="strong" style={{ fontSize: 13, marginBottom: 4 }}>
              Chat-uri legate
            </div>
            {data.chats.map((c) => (
              <div key={c.id} className="list-item" style={{ padding: "6px 0" }}>
                <Icon name="user" />
                <div className="grow">
                  <div className="t">{c.tg_name ?? "Fără nume"}</div>
                  <div className="s">
                    {c.tg_username ? `@${c.tg_username} · ` : ""}legat din{" "}
                    {formatDate(c.created_at)}
                  </div>
                </div>
                <button
                  className="btn sm ghost"
                  disabled={unlink.isPending}
                  onClick={() => {
                    if (
                      window.confirm(
                        `Deconectezi ${c.tg_name ?? "chat-ul"}? Nu va mai putea trimite date.`,
                      )
                    )
                      unlink.mutate(c.id);
                  }}
                >
                  Deconectează
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// --- Automobil ---

type VehicleForm = Omit<VehicleCreate, "fuel_norm" | "initial_odometer"> & {
  fuel_norm: string;
  initial_odometer: string;
};

function VehicleModal({
  clientId,
  vehicle,
  onClose,
  onSaved,
}: {
  clientId: number;
  vehicle?: VehicleOut;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [form, setForm] = useState<VehicleForm>(() => ({
    plate: vehicle?.plate ?? "",
    model: vehicle?.model ?? "",
    fuel_type: vehicle?.fuel_type ?? "motorina",
    fuel_norm: vehicle ? String(vehicle.fuel_norm) : "",
    driver: vehicle?.driver ?? null,
    initial_odometer: vehicle ? String(vehicle.initial_odometer) : "",
  }));
  const set = <K extends keyof VehicleForm>(key: K, value: VehicleForm[K]) =>
    setForm((f) => ({ ...f, [key]: value }));

  const body = (): VehicleCreate => ({
    ...form,
    fuel_norm: form.fuel_norm.replace(",", "."),
    initial_odometer: Number(form.initial_odometer.replace(/\s/g, "")),
  });
  const save = useMutation({
    mutationFn: () => {
      if (!vehicle) return api.post<VehicleOut>(`/api/clients/${clientId}/vehicles`, body());
      const changes: Partial<VehicleCreate> = body();
      // odometrul inițial se trimite doar dacă s-a schimbat (după prima citire e blocat)
      if (changes.initial_odometer === vehicle.initial_odometer) delete changes.initial_odometer;
      return api.patch<VehicleOut>(`/api/vehicles/${vehicle.id}`, changes);
    },
    onSuccess: onSaved,
  });
  const archive = useMutation({
    mutationFn: () => api.del<void>(`/api/vehicles/${vehicle!.id}`),
    onSuccess: onSaved,
  });
  const error = save.error ?? archive.error;

  return (
    <div className="overlay" onClick={onClose}>
      <form
        className="card modal"
        onClick={(e) => e.stopPropagation()}
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate();
        }}
      >
        <div className="card-h">
          <h3>{vehicle ? `Automobil ${vehicle.plate}` : "Automobil nou"}</h3>
        </div>
        <div className="card-b stack">
          {error && <div className="error">{error.message}</div>}
          <div className="form">
            <div className="field">
              <label>Număr de înmatriculare</label>
              <input
                className="input mono"
                placeholder="ex. CDK 540"
                maxLength={15}
                value={form.plate}
                onChange={(e) => set("plate", e.target.value.toUpperCase())}
                required
              />
            </div>
            <div className="field">
              <label>Model</label>
              <input
                className="input"
                placeholder="ex. Dacia Logan"
                maxLength={100}
                value={form.model}
                onChange={(e) => set("model", e.target.value)}
                required
              />
            </div>
            <div className="field">
              <label>Combustibil</label>
              <select
                className="input"
                value={form.fuel_type}
                onChange={(e) => set("fuel_type", e.target.value as VehicleForm["fuel_type"])}
              >
                {Object.entries(FUEL).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </div>
            <div className="field">
              <label>Norma de consum (l / 100 km)</label>
              <input
                className="input mono"
                inputMode="decimal"
                pattern="\d{1,3}([.,]\d{1,2})?"
                title="ex. 7,2"
                placeholder="ex. 7,2"
                value={form.fuel_norm}
                onChange={(e) => set("fuel_norm", e.target.value)}
                required
              />
            </div>
            <div className="field">
              <label>Șofer</label>
              <input
                className="input"
                value={form.driver ?? ""}
                onChange={(e) => set("driver", e.target.value.trim() ? e.target.value : null)}
              />
            </div>
            <div className="field">
              <label>Odometru la luarea în evidență (km)</label>
              <input
                className="input mono"
                inputMode="numeric"
                pattern="[\d\s]+"
                value={form.initial_odometer}
                onChange={(e) => set("initial_odometer", e.target.value)}
                required
              />
              <span className="hint">Punctul de pornire pentru prima lună cu date.</span>
            </div>
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <button className="btn primary" type="submit" disabled={save.isPending}>
              {vehicle ? "Salvează" : "Adaugă automobilul"}
            </button>
            <button className="btn ghost" type="button" onClick={onClose}>
              Renunță
            </button>
            {vehicle && (
              <button
                className="btn ghost"
                type="button"
                style={{ marginLeft: "auto", color: "var(--bad)" }}
                disabled={archive.isPending}
                onClick={() => {
                  if (
                    window.confirm(
                      `Scoți ${vehicle.plate} din evidență? Foile de parcurs emise rămân.`,
                    )
                  )
                    archive.mutate();
                }}
              >
                Scoate din evidență
              </button>
            )}
          </div>
        </div>
      </form>
    </div>
  );
}

// --- Odometru ---

function ReadingModal({
  row,
  period,
  onClose,
  onSaved,
}: {
  row: FleetRowOut;
  period: Period;
  onClose: () => void;
  onSaved: (waybillId: number | null) => void;
}) {
  const v = row.vehicle;
  const [end, setEnd] = useState(row.reading ? String(row.reading.end_odometer) : "");
  const [source, setSource] = useState<NonNullable<ReadingIn["source"]>>(
    row.reading?.source ?? "phone",
  );
  const [receivedOn, setReceivedOn] = useState(row.reading?.received_on ?? todayIso());
  const url = `/api/vehicles/${v.id}/readings/${period.year}/${period.month}`;

  const value = Number(end.replace(/\s/g, ""));
  const driven = end && Number.isFinite(value) ? value - row.start_odometer : null;

  const save = useMutation({
    mutationFn: async (withWaybill: boolean) => {
      await api.put(url, { end_odometer: value, source, received_on: receivedOn });
      if (!withWaybill) return null;
      return (await api.post<WaybillOut>(`${url}/waybill`)).id;
    },
    onSuccess: onSaved,
  });
  const remove = useMutation({
    mutationFn: () => api.del<void>(url),
    onSuccess: () => onSaved(null),
  });
  const error = save.error ?? remove.error;

  return (
    <div className="overlay" onClick={onClose}>
      <form
        className="card modal"
        onClick={(e) => e.stopPropagation()}
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate(false);
        }}
      >
        <div className="card-h">
          <h3>Date odometru — {v.plate}</h3>
        </div>
        <div className="card-b stack">
          <div className="muted">
            {v.model} · {formatMonth(period.year, period.month)}
          </div>
          {error && <div className="error">{error.message}</div>}
          <div className="form">
            <div className="field">
              <label>Odometru la început</label>
              <input className="input mono" value={km(row.start_odometer)} disabled />
            </div>
            <div className="field">
              <label>Odometru la sfârșitul lunii</label>
              <input
                className="input mono"
                inputMode="numeric"
                pattern="[\d\s]+"
                placeholder={`ex. ${NUMBER.format(row.start_odometer + 1500)}`}
                value={end}
                onChange={(e) => setEnd(e.target.value)}
                autoFocus
                required
              />
            </div>
            <div className="field">
              <label>Primit prin</label>
              <select
                className="input"
                value={source}
                onChange={(e) => setSource(e.target.value as typeof source)}
              >
                {Object.entries(SOURCE).map(([key, label]) => (
                  <option key={key} value={key}>
                    {label}
                  </option>
                ))}
              </select>
            </div>
            <div className="field">
              <label>Data primirii</label>
              <input
                className="input"
                type="date"
                max={todayIso()}
                value={receivedOn}
                onChange={(e) => setReceivedOn(e.target.value)}
                required
              />
            </div>
            <div className="field full">
              <div
                className="callout"
                style={driven !== null && driven < 0 ? { background: "var(--bad-soft)" } : {}}
              >
                <Icon name="info" />
                <div style={{ fontSize: 13 }}>
                  {driven === null
                    ? "Introdu valoarea: km parcurși și consumul se calculează automat."
                    : driven < 0
                      ? "Valoarea e mai mică decât odometrul de început."
                      : `${km(driven)} parcurși · consum normat ${liters(
                          Math.round(driven * v.fuel_norm) / 100,
                        )} (${NUMBER.format(v.fuel_norm)} l/100 km)`}
                </div>
              </div>
            </div>
          </div>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <button className="btn" type="submit" disabled={save.isPending}>
              Salvează
            </button>
            <button
              className="btn primary"
              type="button"
              disabled={save.isPending}
              onClick={(e) => {
                if (e.currentTarget.form?.reportValidity()) save.mutate(true);
              }}
            >
              Salvează și generează foaia
            </button>
            <button className="btn ghost" type="button" onClick={onClose}>
              Renunță
            </button>
            {row.reading && (
              <button
                className="btn ghost"
                type="button"
                style={{ marginLeft: "auto", color: "var(--bad)" }}
                disabled={remove.isPending}
                onClick={() => {
                  if (window.confirm("Ștergi datele odometrului pentru această lună?"))
                    remove.mutate();
                }}
              >
                Șterge datele
              </button>
            )}
          </div>
        </div>
      </form>
    </div>
  );
}

// --- Foaia de parcurs ---

function WaybillModal({
  id,
  onClose,
  onCancelled,
}: {
  id: number;
  onClose: () => void;
  onCancelled: () => void;
}) {
  const waybill = useQuery({
    queryKey: ["waybill", id],
    queryFn: () => api.get<WaybillOut>(`/api/waybills/${id}`),
  });
  const cancel = useMutation({
    mutationFn: () => api.del<void>(`/api/waybills/${id}`),
    onSuccess: onCancelled,
  });
  const w = waybill.data;
  const lastDay = w ? new Date(w.year, w.month, 0).getDate() : 0;
  const pad = (n: number) => String(n).padStart(2, "0");

  return (
    <div className="overlay" onClick={onClose}>
      <div className="card modal" onClick={(e) => e.stopPropagation()}>
        <div className="card-h">
          <h3>Foaie de parcurs</h3>
        </div>
        <div className="card-b stack">
          {waybill.error && <div className="error">{waybill.error.message}</div>}
          {cancel.error && <div className="error">{cancel.error.message}</div>}
          {!w ? (
            <div className="loading">Se încarcă…</div>
          ) : (
            <div className="waybill">
              <div style={{ textAlign: "center", marginBottom: 16 }}>
                <div className="strong" style={{ fontSize: 16, letterSpacing: "0.04em" }}>
                  FOAIE DE PARCURS
                </div>
                <div className="mono">nr. {w.number}</div>
                <div className="muted" style={{ fontSize: 12 }}>
                  pentru perioada 01.{pad(w.month)}.{w.year} – {lastDay}.{pad(w.month)}.{w.year}
                </div>
              </div>
              <dl
                className="dl"
                style={{ gridTemplateColumns: "170px 1fr", fontSize: 13, gap: "8px 12px" }}
              >
                <dt>Întreprinderea</dt>
                <dd>{w.client_name}</dd>
                <dt>IDNO</dt>
                <dd className="mono">{w.client_idno}</dd>
                <dt>Automobil</dt>
                <dd>{w.model}</dd>
                <dt>Nr. înmatriculare</dt>
                <dd>
                  <span className="plate">{w.plate}</span>
                </dd>
                <dt>Șofer</dt>
                <dd>{w.driver ?? "—"}</dd>
                <dt>Tip combustibil</dt>
                <dd>{FUEL[w.fuel_type]}</dd>
              </dl>
              <table style={{ marginTop: 16, fontSize: 13 }}>
                <thead>
                  <tr>
                    <th>Indicator</th>
                    <th className="num">Valoare</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td>Odometru la începutul lunii</td>
                    <td className="num mono">{km(w.start_odometer)}</td>
                  </tr>
                  <tr>
                    <td>Odometru la sfârșitul lunii</td>
                    <td className="num mono">{km(w.end_odometer)}</td>
                  </tr>
                  <tr>
                    <td className="strong">Parcurs total</td>
                    <td className="num mono strong">{km(w.km)}</td>
                  </tr>
                  <tr>
                    <td>Norma de consum</td>
                    <td className="num mono">{NUMBER.format(w.fuel_norm)} l / 100 km</td>
                  </tr>
                  <tr>
                    <td className="strong">Consum normat de combustibil</td>
                    <td className="num mono strong">{liters(w.fuel_liters)}</td>
                  </tr>
                </tbody>
              </table>
              <div
                className="muted"
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  gap: 12,
                  flexWrap: "wrap",
                  marginTop: 28,
                  fontSize: 12,
                }}
              >
                <span>
                  Contabil: {w.issued_by_name ?? "________"} · emisă {formatDate(w.issued_at)}
                </span>
                <span>Semnătura șoferului: ________</span>
              </div>
            </div>
          )}
          <div className="no-print" style={{ display: "flex", gap: 8 }}>
            <button className="btn primary" disabled={!w} onClick={() => window.print()}>
              Tipărește
            </button>
            <button className="btn ghost" onClick={onClose}>
              Închide
            </button>
            <button
              className="btn ghost"
              style={{ marginLeft: "auto", color: "var(--bad)" }}
              disabled={!w || cancel.isPending}
              onClick={() => {
                if (
                  window.confirm(
                    `Anulezi foaia ${w!.number}? Datele odometrului rămân și se pot corecta.`,
                  )
                )
                  cancel.mutate();
              }}
            >
              Anulează foaia
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
