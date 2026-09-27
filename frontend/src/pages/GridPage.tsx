import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useSearchParams } from "react-router";

import { api } from "../api/client";
import type { EntryOut, GenerationOut, GridOut, StatusSetOut } from "../api/types";
import { isEditor, useMe } from "../auth/useAuth";
import { ErrorBox } from "../components/ErrorBox";
import { Icon } from "../components/Icon";
import { formatDate, formatMonth } from "../format";

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

export function GridPage() {
  const me = useMe();
  const queryClient = useQueryClient();
  const [year, month, go] = useMonth();
  const [filter, setFilter] = useState<Filter>("all");
  const [generated, setGenerated] = useState<GenerationOut | null>(null);

  const key = ["grid", year, month, filter];
  const grid = useQuery({
    queryKey: key,
    queryFn: () =>
      api.get<GridOut>("/api/grid", {
        year,
        month,
        only_open: filter === "open",
        only_overdue: filter === "overdue",
      }),
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
  const seg = (value: Filter, label: string) => (
    <button className={filter === value ? "on" : ""} onClick={() => setFilter(value)}>
      {label}
    </button>
  );

  const cells = grid.data?.rows.flatMap((r) => r.entries) ?? [];
  const done = cells.filter((e) => e.is_completed).length;
  const overdue = cells.filter((e) => e.is_overdue).length;

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Grila lunii</h1>
          <p>
            Rapoartele pentru perioadele care se încheie în luna aleasă. {cells.length} celule ·{" "}
            {done} complete · {overdue} întârziate
          </p>
        </div>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <button className="btn" onClick={() => shift(-1)} aria-label="Luna anterioară">
            <Icon name="back" />
          </button>
          <span className="strong" style={{ minWidth: 150, textAlign: "center" }}>
            {formatMonth(year, month)}
          </span>
          <button className="btn" onClick={() => shift(1)} aria-label="Luna următoare">
            <span style={{ transform: "scaleX(-1)", display: "inline-flex" }}>
              <Icon name="back" />
            </span>
          </button>
          {isEditor(me) && (
            <button
              className="btn primary"
              disabled={generate.isPending}
              onClick={() => generate.mutate()}
            >
              Generează grila
            </button>
          )}
        </div>
      </div>

      {generate.error && <div className="error">{generate.error.message}</div>}
      {generated && <GenerationNotice result={generated} onClose={() => setGenerated(null)} />}

      <div className="card">
        <div className="toolbar">
          <div className="seg">
            {seg("all", "Toate")}
            {seg("open", "Necompletate")}
            {seg("overdue", "Întârziate")}
          </div>
          <span className="spacer" style={{ flex: 1 }} />
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
                  {p.is_closed ? "Redeschide" : "Închide"}
                </button>
              )}
            </span>
          ))}
        </div>
        {togglePeriod.error && <ErrorBox error={togglePeriod.error} />}
        {grid.error ? (
          <ErrorBox error={grid.error} />
        ) : !grid.data || !statusSets.data ? (
          <div className="loading">Se încarcă…</div>
        ) : grid.data.rows.length === 0 ? (
          <div className="empty">
            {grid.data.periods.length === 0
              ? isEditor(me)
                ? "Grila acestei luni nu a fost generată încă. Apasă „Generează grila”."
                : "Grila acestei luni nu a fost generată încă."
              : "Nicio celulă pentru filtrul ales."}
          </div>
        ) : (
          <GridTable grid={grid.data} statusSets={statusSets.data} queryKey={key} />
        )}
      </div>
    </>
  );
}

function GenerationNotice({ result, onClose }: { result: GenerationOut; onClose: () => void }) {
  const later = result.periods.reduce((n, p) => n + p.starting_later.length, 0);
  return (
    <div className="callout" style={{ marginBottom: 16 }}>
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
  return (
    <div className="table-wrap">
      <table className="matrix">
        <thead>
          <tr>
            <th>Client</th>
            {grid.report_types.map((rt) => (
              <th key={rt.id} title={rt.name}>
                {rt.code}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {grid.rows.map((row) => {
            const byType = new Map(row.entries.map((e) => [e.report_type_id, e]));
            return (
              <tr key={row.client.id}>
                <td className="strong" style={{ whiteSpace: "nowrap" }}>
                  <Link to={`/clienti/${row.client.id}`}>{row.client.name}</Link>
                </td>
                {grid.report_types.map((rt) => {
                  const entry = byType.get(rt.id);
                  return entry ? (
                    <Cell
                      key={rt.id}
                      entry={entry}
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
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function Cell({
  entry,
  statusSets,
  readOnly,
  queryKey,
}: {
  entry: EntryOut;
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
      queryClient.setQueryData<GridOut>(
        queryKey,
        (grid) =>
          grid && {
            ...grid,
            rows: grid.rows.map((r) => ({
              ...r,
              entries: r.entries.map((e) => (e.id === updated.id ? updated : e)),
            })),
          },
      );
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
      <div className="cell-meta">
        {entry.deadline ? `termen ${formatDate(entry.deadline)}` : "fără termen"}
      </div>
      {setStatus.error && (
        <div className="cell-meta" style={{ color: "var(--bad)" }}>
          {setStatus.error.message}
        </div>
      )}
    </td>
  );
}
