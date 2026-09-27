import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useSearchParams } from "react-router";

import { api } from "../api/client";
import type { EntryOut, GenerationOut, GridOut, StatusSetOut } from "../api/types";
import { isEditor, useMe } from "../auth/useAuth";
import { ErrorBox } from "../components/ErrorBox";
import { Icon } from "../components/Icon";
import { Avatar, Empty, Kpi } from "../components/ui";
import { formatDate, formatMonth, initials } from "../format";

type Filter = "all" | "open" | "overdue";

const PERIOD_LABEL: Record<string, (no: number) => string> = {
  lunar: () => "Lunar",
  trimestrial: (no) => `Trimestrul ${["I", "II", "III", "IV"][no - 1]}`,
  semestrial: (no) => `Semestrul ${no === 1 ? "I" : "II"}`,
  anual: () => "Anual",
};

/** Luna din URL (?an=2026&luna=9); implicit luna curentă. */
function useMonth(): [number, number, (year: number, month: number) => void] {
  const [params, setParams] = useSearchParams();
  const now = new Date();
  const year = Number(params.get("an")) || now.getFullYear();
  const month = Number(params.get("luna")) || now.getMonth() + 1;
  const go = (y: number, m: number) => setParams({ an: String(y), luna: String(m) });
  return [year, month, go];
}

const fetchGrid = (year: number, month: number, filter: Filter) =>
  api.get<GridOut>("/api/grid", {
    year,
    month,
    only_open: filter === "open",
    only_overdue: filter === "overdue",
  });

export function GridPage() {
  const me = useMe();
  const queryClient = useQueryClient();
  const [year, month, go] = useMonth();
  const [filter, setFilter] = useState<Filter>("all");
  const [generated, setGenerated] = useState<GenerationOut | null>(null);

  const key = ["grid", year, month, filter];
  const grid = useQuery({ queryKey: key, queryFn: () => fetchGrid(year, month, filter) });
  // indicatorii se calculează mereu pe toată luna (aceeași cheie ca filtrul „Toate”, deci fără cerere dublă)
  const all = useQuery({
    queryKey: ["grid", year, month, "all"],
    queryFn: () => fetchGrid(year, month, "all"),
  });
  const statusSets = useQuery({
    queryKey: ["status-sets"],
    queryFn: () => api.get<StatusSetOut[]>("/api/classifiers/status-sets"),
    staleTime: Infinity,
  });

  const refresh = () => queryClient.invalidateQueries({ queryKey: ["grid", year, month] });
  const generate = useMutation({
    mutationFn: () => api.post<GenerationOut>("/api/grid/generate", undefined, { year, month }),
    onSuccess: (result) => {
      setGenerated(result);
      void refresh();
    },
  });
  const togglePeriod = useMutation({
    mutationFn: ({ id, closed }: { id: number; closed: boolean }) =>
      api.post(`/api/grid/periods/${id}/${closed ? "reopen" : "close"}`),
    onSuccess: () => void refresh(),
  });

  const shift = (delta: number) => {
    const index = year * 12 + (month - 1) + delta;
    setGenerated(null);
    go(Math.floor(index / 12), (index % 12) + 1);
  };
  const now = new Date();
  const isCurrent = year === now.getFullYear() && month === now.getMonth() + 1;

  const cells = all.data?.rows.flatMap((r) => r.entries) ?? [];
  const done = cells.filter((e) => e.is_completed).length;
  const overdue = cells.filter((e) => e.is_overdue).length;
  const open = cells.length - done;
  const pct = cells.length ? Math.round((done / cells.length) * 100) : 0;

  const seg = (value: Filter, label: string, n?: number) => (
    <button className={filter === value ? "on" : ""} onClick={() => setFilter(value)}>
      {label}
      {n !== undefined && all.data && <span className="n">{n}</span>}
    </button>
  );

  return (
    <div className="grid-page">
      <div className="page-head">
        <div>
          <h1>Grila lunii</h1>
          <p>Rapoartele pentru perioadele care se încheie în luna aleasă.</p>
        </div>
        <div className="page-actions">
          <div className="month-nav">
            <button className="btn" onClick={() => shift(-1)} aria-label="Luna anterioară">
              <Icon name="chevronLeft" size={16} />
            </button>
            <span className="label">
              <Icon name="calendar" size={15} />
              {formatMonth(year, month)}
            </span>
            <button className="btn" onClick={() => shift(1)} aria-label="Luna următoare">
              <Icon name="chevron" size={16} />
            </button>
          </div>
          {!isCurrent && (
            <button
              className="btn"
              onClick={() => {
                setGenerated(null);
                go(now.getFullYear(), now.getMonth() + 1);
              }}
            >
              Azi
            </button>
          )}
          {isEditor(me) && (
            <button
              className="btn primary"
              disabled={generate.isPending}
              onClick={() => generate.mutate()}
            >
              <Icon name="sparkle" size={16} />
              {generate.isPending ? "Se generează…" : "Generează grila"}
            </button>
          )}
        </div>
      </div>

      <div className="kpi-row compact">
        <Kpi
          label="Celule în lună"
          value={cells.length}
          sub={`${all.data?.rows.length ?? 0} clienți`}
          icon="grid"
        />
        <Kpi
          label="Complete"
          value={`${pct}%`}
          sub={`${done} din ${cells.length}`}
          icon="check"
          tone="ok"
          progress={pct}
        />
        <Kpi label="De lucru" value={open} sub="necompletate" icon="clock" tone="warn" />
        <Kpi
          label="Întârziate"
          value={overdue}
          sub={overdue ? "termen depășit" : "totul la zi"}
          icon="alert"
          tone={overdue ? "bad" : "ok"}
        />
      </div>

      {generate.error && (
        <div className="error" style={{ marginBottom: 16 }}>
          {generate.error.message}
        </div>
      )}
      {generated && <GenerationNotice result={generated} onClose={() => setGenerated(null)} />}

      <div className="card grid-card">
        <div className="toolbar">
          <div className="seg">
            {seg("all", "Toate", cells.length)}
            {seg("open", "Necompletate", open)}
            {seg("overdue", "Întârziate", overdue)}
          </div>
          <span className="spacer" />
          <div className="period-chips">
            {grid.data?.periods.map((p) => (
              <span key={p.id} className="who" style={{ fontSize: 13 }}>
                <span className={`badge ${p.is_closed ? "b-grey" : "b-ok"}`}>
                  {PERIOD_LABEL[p.period_type]?.(p.period_no)} {p.is_closed ? "închis" : "deschis"}
                </span>
                {isEditor(me) && (
                  <button
                    className="btn sm ghost"
                    disabled={togglePeriod.isPending}
                    onClick={() => togglePeriod.mutate({ id: p.id, closed: p.is_closed })}
                  >
                    <Icon name={p.is_closed ? "key" : "lock"} size={12} />
                    {p.is_closed ? "Redeschide" : "Închide"}
                  </button>
                )}
              </span>
            ))}
          </div>
        </div>
        {togglePeriod.error && <ErrorBox error={togglePeriod.error} />}
        {grid.error ? (
          <ErrorBox error={grid.error} />
        ) : !grid.data || !statusSets.data ? (
          <div className="loading">Se încarcă…</div>
        ) : grid.data.rows.length === 0 ? (
          grid.data.periods.length === 0 ? (
            <Empty
              icon="grid"
              title="Grila acestei luni nu a fost generată încă"
              hint={
                isEditor(me)
                  ? "Generează celulele pentru toți clienții activi."
                  : "Cere unui director sau admin să o genereze."
              }
              action={
                isEditor(me) && (
                  <button
                    className="btn primary"
                    disabled={generate.isPending}
                    onClick={() => generate.mutate()}
                  >
                    <Icon name="sparkle" size={16} /> Generează grila
                  </button>
                )
              }
            />
          ) : (
            <Empty
              icon={filter === "overdue" ? "check" : "search"}
              title={
                filter === "overdue"
                  ? "Nicio celulă întârziată"
                  : "Nicio celulă pentru filtrul ales"
              }
            />
          )
        ) : (
          <GridTable grid={grid.data} statusSets={statusSets.data} queryKey={key} />
        )}
        {grid.data && grid.data.rows.length > 0 && (
          <div className="grid-foot legend">
            <span>
              <i style={{ background: "var(--ok)" }} />
              finalizat
            </span>
            <span>
              <i style={{ background: "var(--info)" }} />
              în lucru
            </span>
            <span>
              <i style={{ background: "var(--warn)" }} />
              neachitat
            </span>
            <span>
              <i style={{ background: "var(--border-strong)" }} />
              neînceput
            </span>
            <span>
              <i style={{ background: "var(--bad)" }} />
              termen depășit
            </span>
            <span className="grid-foot-note">
              Termenul comun e în capul coloanei; în celulă apare doar cel diferit sau depășit.
            </span>
          </div>
        )}
      </div>
    </div>
  );
}

function GenerationNotice({ result, onClose }: { result: GenerationOut; onClose: () => void }) {
  const later = result.periods.reduce((n, p) => n + p.starting_later.length, 0);
  return (
    <div className={`callout ${later ? "warn" : "ok"}`} style={{ marginBottom: 16 }}>
      <Icon name={later ? "alert" : "check"} />
      <div style={{ flex: 1, fontSize: 13 }}>
        <b>{result.created} celule noi</b> create
        {result.periods.some((p) => p.closed) && " (perioadele închise au fost sărite)"}.
        {later > 0 && (
          <>
            {" "}
            <b>{later} obligații active încep după această lună</b> și nu au intrat în grilă:
            recalculează obligațiile clienților respectivi cu o dată mai veche.
          </>
        )}
      </div>
      <button className="btn sm ghost" onClick={onClose}>
        OK
      </button>
    </div>
  );
}

/** „2026-10-26” → „26.10”. */
function shortDate(iso: string): string {
  return formatDate(iso).slice(0, 5);
}

/** Termenul cel mai des întâlnit pe fiecare coloană (tip de raport); `null` = fără termen. */
function commonDeadlines(grid: GridOut): Map<number, string | null> {
  const counts = new Map<number, Map<string | null, number>>();
  for (const row of grid.rows)
    for (const e of row.entries) {
      const byDate = counts.get(e.report_type_id) ?? new Map<string | null, number>();
      byDate.set(e.deadline, (byDate.get(e.deadline) ?? 0) + 1);
      counts.set(e.report_type_id, byDate);
    }
  const result = new Map<number, string | null>();
  for (const [rt, byDate] of counts) result.set(rt, [...byDate].sort((a, b) => b[1] - a[1])[0]![0]);
  return result;
}

function GridTable({
  grid,
  statusSets,
  queryKey,
}: {
  grid: GridOut;
  statusSets: StatusSetOut[];
  queryKey: unknown[];
}) {
  const closed = new Set(grid.periods.filter((p) => p.is_closed).map((p) => p.id));
  const common = commonDeadlines(grid);
  // coloana foilor de parcurs apare doar dacă cel puțin un client are automobile
  const hasFleet = grid.rows.some((r) => r.fleet);
  const monthEnd = `${new Date(grid.year, grid.month, 0).getDate()}.${String(grid.month).padStart(2, "0")}`;
  return (
    <div className="table-wrap">
      <table className="matrix">
        <thead>
          <tr>
            <th>Client</th>
            {grid.report_types.map((rt) => {
              const deadline = common.get(rt.id);
              return (
                <th key={rt.id} title={rt.name}>
                  <div className="col-code">{rt.code}</div>
                  <div className="col-sub">
                    {deadline ? `termen ${shortDate(deadline)}` : "fără termen"}
                  </div>
                </th>
              );
            })}
            {hasFleet && (
              <th className="fleet-col" title="Odometrul la sfârșitul lunii și foile de parcurs">
                <div className="col-code">Foi de parcurs</div>
                <div className="col-sub">date până {monthEnd}</div>
              </th>
            )}
          </tr>
        </thead>
        <tbody>
          {grid.rows.map((row) => {
            const byType = new Map(row.entries.map((e) => [e.report_type_id, e]));
            const rowDone = row.entries.filter((e) => e.is_completed).length;
            const rowLate = row.entries.some((e) => e.is_overdue);
            return (
              <tr key={row.client.id}>
                <td className="strong" style={{ whiteSpace: "nowrap" }}>
                  <Link to={`/clienti/${row.client.id}`}>
                    <Avatar
                      name={row.client.name}
                      text={initials(row.client.name)}
                      size={28}
                      square
                    />
                    <span className="row-text">
                      {row.client.name}
                      <span className="row-sub">
                        <Accountants people={row.accountants} />
                        <span
                          className="row-count"
                          title={`${rowDone} din ${row.entries.length} rapoarte complete`}
                          style={rowLate ? { color: "var(--bad)" } : undefined}
                        >
                          {rowDone}/{row.entries.length}
                        </span>
                      </span>
                    </span>
                  </Link>
                </td>
                {grid.report_types.map((rt) => {
                  const entry = byType.get(rt.id);
                  return entry ? (
                    <Cell
                      key={rt.id}
                      entry={entry}
                      commonDeadline={common.get(rt.id) ?? null}
                      statusSets={statusSets}
                      readOnly={closed.has(entry.period_id)}
                      queryKey={queryKey}
                    />
                  ) : (
                    <td key={rt.id} className="na">
                      —
                    </td>
                  );
                })}
                {hasFleet &&
                  (row.fleet ? (
                    <FleetCell
                      clientId={row.client.id}
                      fleet={row.fleet}
                      year={grid.year}
                      month={grid.month}
                    />
                  ) : (
                    <td className="na">—</td>
                  ))}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

type FleetSummary = NonNullable<GridOut["rows"][number]["fleet"]>;

const FLEET_DOT: Record<FleetSummary["items"][number]["status"], string> = {
  issued: "var(--ok)",
  received: "var(--info)",
  late: "var(--bad)",
  waiting: "var(--border-strong)",
};
const FLEET_LABEL: Record<FleetSummary["items"][number]["status"], string> = {
  issued: "foaie emisă",
  received: "date primite, foaie de emis",
  late: "fără date, luna s-a încheiat",
  waiting: "așteptăm datele",
};

// ordinea segmentelor în bară: gata → de emis → lipsă
const FLEET_ORDER: FleetSummary["items"][number]["status"][] = [
  "issued",
  "received",
  "late",
  "waiting",
];
const FLEET_SHORT: Record<FleetSummary["items"][number]["status"], string> = {
  issued: "emise",
  received: "de emis",
  late: "lipsă",
  waiting: "în așteptare",
};

/** Foile de parcurs ale clientului pe lună: starea pe scurt, automobilele și emiterea foilor. */
function FleetCell({
  clientId,
  fleet,
  year,
  month,
}: {
  clientId: number;
  fleet: FleetSummary;
  year: number;
  month: number;
}) {
  const queryClient = useQueryClient();
  const issue = useMutation({
    mutationFn: () => api.post(`/api/clients/${clientId}/fleet/${year}/${month}/waybills`),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["grid", year, month] });
      void queryClient.invalidateQueries({ queryKey: ["fleet", clientId] });
      void queryClient.invalidateQueries({ queryKey: ["waybills", clientId] });
    },
  });
  const [text, tone] =
    fleet.issued === fleet.vehicles
      ? [`${fleet.issued}/${fleet.vehicles} emise`, "ok"]
      : fleet.late
        ? [`${fleet.missing} fără date`, "bad"]
        : fleet.received > 0
          ? [`${fleet.received} de emis`, "info"]
          : [`așteptăm ${fleet.missing}`, "grey"];
  // până la 3 automobile se văd numerele; peste, o bară pe segmente și totalurile
  const compact = fleet.items.length <= 3;
  const counts = FLEET_ORDER.map((status) => ({
    status,
    n: fleet.items.filter((v) => v.status === status).length,
  })).filter((c) => c.n > 0);
  const details = fleet.items.map((v) => `${v.plate}: ${FLEET_LABEL[v.status]}`).join("\n");

  return (
    <td className={`fleet-cell${fleet.late ? " cell-overdue" : ""}`}>
      <Link
        className={`fleet-pill ${tone}`}
        to={`/clienti/${clientId}?tab=parc&an=${year}&luna=${month}`}
        title="Deschide parcul auto al clientului pe această lună"
      >
        <Icon name="truck" size={13} /> {text}
      </Link>
      {compact ? (
        <div className="fleet-plates">
          {fleet.items.map((v) => (
            <span key={v.vehicle_id} title={`${v.plate}: ${FLEET_LABEL[v.status]}`}>
              <i style={{ background: FLEET_DOT[v.status] }} />
              {v.plate}
            </span>
          ))}
        </div>
      ) : (
        <div className="fleet-summary" title={details}>
          <div className="fleet-bar">
            {counts.map((c) => (
              <span key={c.status} style={{ flexGrow: c.n, background: FLEET_DOT[c.status] }} />
            ))}
          </div>
          <div className="fleet-counts">
            {counts.map((c) => (
              <span key={c.status}>
                <i style={{ background: FLEET_DOT[c.status] }} />
                {c.n} {FLEET_SHORT[c.status]}
              </span>
            ))}
          </div>
        </div>
      )}
      {fleet.received > 0 && (
        <button
          className="btn sm fleet-issue"
          disabled={issue.isPending}
          onClick={() => issue.mutate()}
          title="Emite foile de parcurs pentru automobilele cu date primite"
        >
          Emite {fleet.received}
        </button>
      )}
      {issue.error && (
        <div className="cell-meta" style={{ color: "var(--bad)" }}>
          {issue.error.message}
        </div>
      )}
    </td>
  );
}

/** Contabilii clientului, sub denumire: mini-avatar și nume; „+N” când sunt mai mulți. */
function Accountants({ people = [] }: { people?: GridOut["rows"][number]["accountants"] }) {
  if (people.length === 0)
    return (
      <span className="row-acc none">
        <Icon name="user" size={12} /> fără contabil
      </span>
    );
  const [first, ...rest] = people;
  return (
    <span className="row-acc" title={people.map((p) => p.full_name).join(", ")}>
      <span className="avatar-stack">
        {people.slice(0, 3).map((p) => (
          <Avatar key={p.id} name={p.full_name} size={16} />
        ))}
      </span>
      <span className="row-acc-name">{first!.full_name}</span>
      {rest.length > 0 && <span className="row-acc-more">+{rest.length}</span>}
    </span>
  );
}

function Cell({
  entry,
  commonDeadline,
  statusSets,
  readOnly,
  queryKey,
}: {
  entry: EntryOut;
  commonDeadline: string | null;
  statusSets: StatusSetOut[];
  readOnly: boolean;
  queryKey: unknown[];
}) {
  const queryClient = useQueryClient();
  const setStatus = useMutation({
    mutationFn: ({ stepId, statusId }: { stepId: number; statusId: number }) =>
      api.put<EntryOut>(`/api/grid/entries/${entry.id}/steps/${stepId}`, {
        status_id: statusId,
      }),
    onSuccess: (updated) => {
      // Înlocuim celula în grila din cache, fără să reîncărcăm toată luna.
      const patch = (grid: GridOut | undefined) =>
        grid && {
          ...grid,
          rows: grid.rows.map((r) => ({
            ...r,
            entries: r.entries.map((e) => (e.id === updated.id ? updated : e)),
          })),
        };
      queryClient.setQueryData<GridOut>(queryKey, patch);
      // și în grila completă, din care vin indicatorii de sus
      const [, year, month] = queryKey;
      queryClient.setQueryData<GridOut>(["grid", year, month, "all"], patch);
    },
  });

  const cls = entry.is_completed ? "cell-done" : entry.is_overdue ? "cell-overdue" : "";
  return (
    <td className={cls}>
      <div className="cell-steps">
        {entry.steps.map((step) => {
          const options = statusSets.find((s) => s.id === step.status_set_id)?.statuses ?? [];
          return (
            <label key={step.step_id} className="cell-step" title={step.name}>
              <select
                aria-label={step.name}
                value={step.status.id}
                data-status={step.status.name}
                disabled={readOnly || setStatus.isPending}
                onChange={(e) =>
                  setStatus.mutate({ stepId: step.step_id, statusId: Number(e.target.value) })
                }
              >
                {options.map((o) => (
                  <option key={o.id} value={o.id}>
                    {o.name}
                  </option>
                ))}
              </select>
            </label>
          );
        })}
      </div>
      {/* termenul comun e în capul coloanei; aici doar cel diferit sau depășit */}
      {(entry.deadline !== commonDeadline || entry.is_overdue) && (
        <div className="cell-meta">
          {entry.deadline ? `termen ${formatDate(entry.deadline)}` : "fără termen"}
        </div>
      )}
      {setStatus.error && (
        <div className="cell-meta" style={{ color: "var(--bad)" }}>
          {setStatus.error.message}
        </div>
      )}
    </td>
  );
}
