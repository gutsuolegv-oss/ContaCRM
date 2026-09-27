import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router";

import { api } from "../api/client";
import type { CategoryOut, ReportTypeDetailOut, ReportTypeOut, StatusSetOut } from "../api/types";
import { isEditor, useMe } from "../auth/useAuth";
import { ErrorBox } from "../components/ErrorBox";
import { formatDate } from "../format";
import { describeCondition, type Condition } from "../rules";
import {
  AddRuleButton,
  MONTHS,
  PERIODICITY,
  ReportTypeFormModal,
  RetireButton,
  RuleActions,
  StepsEditor,
} from "./ReportTypeEditors";

function deadlineText(rt: ReportTypeOut): string {
  if (rt.deadline_rule === "manual") return "fără termen";
  if (rt.deadline_rule === "fixed_date")
    return `${rt.deadline_day} ${MONTHS[(rt.deadline_month ?? 1) - 1]}`;
  const offset = rt.deadline_month_offset;
  const when =
    offset === 0
      ? "din luna în care se încheie perioada"
      : offset === 1
        ? "din luna următoare perioadei"
        : `la ${offset} luni după perioadă`;
  return `ziua ${rt.deadline_day} ${when}`;
}

export function ClassifierPage() {
  const me = useMe();
  const [selected, setSelected] = useState<number | null>(null);
  const [showRetired, setShowRetired] = useState(false);
  const [creating, setCreating] = useState(false);
  const categories = useQuery({
    queryKey: ["categories"],
    queryFn: () => api.get<CategoryOut[]>("/api/classifiers/categories"),
  });
  const types = useQuery({
    queryKey: ["report-types", showRetired],
    queryFn: () =>
      api.get<ReportTypeOut[]>("/api/classifiers/report-types", {
        active: showRetired ? undefined : true,
      }),
  });

  if (categories.error || types.error) return <ErrorBox error={categories.error ?? types.error} />;
  if (!categories.data || !types.data) return <div className="loading">Se încarcă…</div>;

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Clasificator de rapoarte</h1>
          <p>
            Catalogul rapoartelor, termenele lor și regulile care decid ce client ce raport are.
          </p>
        </div>
        <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
          <label className="who" style={{ fontSize: 13 }}>
            <input
              type="checkbox"
              checked={showRetired}
              onChange={(e) => setShowRetired(e.target.checked)}
            />
            arată și rapoartele retrase
          </label>
          {isEditor(me) && (
            <button className="btn primary" onClick={() => setCreating(true)}>
              + Raport nou
            </button>
          )}
        </div>
      </div>
      {creating && (
        <ReportTypeFormModal
          categories={categories.data.filter((c) => c.is_active)}
          onClose={() => setCreating(false)}
          onSaved={(rt) => {
            setCreating(false);
            setSelected(rt.id);
          }}
        />
      )}
      <div className="grid g-main" style={{ alignItems: "start" }}>
        <div className="stack">
          {categories.data.map((cat) => {
            const inCategory = types.data.filter((t) => t.category_id === cat.id);
            if (inCategory.length === 0) return null;
            return (
              <div className="card" key={cat.id}>
                <div className="card-h">
                  <h3>{cat.name}</h3>
                </div>
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Cod</th>
                        <th>Raport</th>
                        <th>Periodicitate</th>
                        <th>Termen</th>
                      </tr>
                    </thead>
                    <tbody>
                      {inCategory.map((rt) => (
                        <tr
                          key={rt.id}
                          className="link"
                          onClick={() => setSelected(rt.id)}
                          style={selected === rt.id ? { background: "var(--primary-soft)" } : {}}
                        >
                          <td>
                            <span className="chip-r b-pri">{rt.code}</span>
                          </td>
                          <td>
                            {rt.name}
                            {!rt.is_active && (
                              <span className="badge b-grey" style={{ marginLeft: 6 }}>
                                retras
                              </span>
                            )}
                          </td>
                          <td>{PERIODICITY[rt.periodicity]}</td>
                          <td className="muted">{deadlineText(rt)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            );
          })}
        </div>
        <div className="card" style={{ position: "sticky", top: 76 }}>
          {selected === null ? (
            <div className="empty">Alege un raport din listă ca să-i vezi etapele și regulile.</div>
          ) : (
            <ReportTypeDetail id={selected} categories={categories.data} />
          )}
        </div>
      </div>
    </>
  );
}

function ReportTypeDetail({ id, categories }: { id: number; categories: CategoryOut[] }) {
  const me = useMe();
  const editor = isEditor(me);
  const [editing, setEditing] = useState(false);
  const detail = useQuery({
    queryKey: ["report-type", id],
    queryFn: () => api.get<ReportTypeDetailOut>(`/api/classifiers/report-types/${id}`),
  });
  const statusSets = useQuery({
    queryKey: ["status-sets"],
    queryFn: () => api.get<StatusSetOut[]>("/api/classifiers/status-sets"),
    staleTime: Infinity,
  });
  const preview = useMutation({
    mutationFn: () =>
      api.post<{ id: number; name: string; idno: string }[]>(
        `/api/classifiers/report-types/${id}/preview`,
      ),
  });

  if (detail.error) return <ErrorBox error={detail.error} />;
  if (!detail.data) return <div className="loading">Se încarcă…</div>;
  const rt = detail.data;
  const setName = (setId: number) => statusSets.data?.find((s) => s.id === setId);

  return (
    <div className="card-b stack">
      <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
        <div>
          <div className="strong" style={{ fontSize: 16 }}>
            {rt.code} · {rt.name}
          </div>
          {rt.full_name && (
            <div className="muted" style={{ marginTop: 4 }}>
              {rt.full_name}
            </div>
          )}
        </div>
        {editor && (
          <div style={{ display: "flex", gap: 4, alignItems: "start" }}>
            <button className="btn sm" onClick={() => setEditing(true)}>
              Editează
            </button>
            <RetireButton rt={rt} />
          </div>
        )}
      </div>
      {editing && (
        <ReportTypeFormModal
          reportType={rt}
          categories={categories.filter((c) => c.is_active || c.id === rt.category_id)}
          onClose={() => setEditing(false)}
          onSaved={() => setEditing(false)}
        />
      )}
      <dl className="dl" style={{ gridTemplateColumns: "120px 1fr", fontSize: 13 }}>
        <dt>Autoritate</dt>
        <dd>{rt.authority ?? "—"}</dd>
        <dt>Bază legală</dt>
        <dd>{rt.legal_reference ?? "—"}</dd>
        <dt>Periodicitate</dt>
        <dd>{PERIODICITY[rt.periodicity]}</dd>
        <dt>Termen</dt>
        <dd>{deadlineText(rt)} (mutat pe prima zi lucrătoare)</dd>
        <dt>Plată</dt>
        <dd>{rt.requires_payment ? "da" : "nu"}</dd>
        <dt>Notificări</dt>
        <dd>
          {rt.notify_days_before.length
            ? `cu ${rt.notify_days_before.join(", ")} zile înainte`
            : "—"}
        </dd>
        <dt>Valabil</dt>
        <dd>
          din {formatDate(rt.valid_from)}
          {rt.valid_to && ` până la ${formatDate(rt.valid_to)}`}
        </dd>
      </dl>

      <div>
        <div className="strong" style={{ marginBottom: 6 }}>
          Etape în grilă
        </div>
        {editor && statusSets.data ? (
          <StepsEditor rt={rt} statusSets={statusSets.data} />
        ) : (
          <>
            {rt.steps.length === 0 && <div className="muted">Nicio etapă.</div>}
            {rt.steps.map((s) => (
              <div key={s.id} style={{ fontSize: 13, marginBottom: 4 }}>
                {s.name}{" "}
                <span className="muted">
                  (
                  {setName(s.status_set_id)
                    ?.statuses.map((st) => st.name)
                    .join(" → ")}
                  )
                </span>
              </div>
            ))}
          </>
        )}
      </div>

      <div>
        <div className="strong" style={{ marginBottom: 6 }}>
          Cui se aplică
        </div>
        {rt.rules.length === 0 && (
          <div className="muted" style={{ fontSize: 13 }}>
            Fără reguli: se atribuie doar manual, din cartela clientului.
          </div>
        )}
        {rt.rules.map((rule) => (
          <div key={rule.id} style={{ fontSize: 13, marginBottom: 6 }}>
            <span className={`badge ${rule.action === "assign" ? "b-ok" : "b-bad"}`}>
              {rule.action === "assign" ? "se atribuie" : "se exclude"}
            </span>{" "}
            când <b>{describeCondition(rule.conditions as Condition)}</b>
            <span className="muted">
              {" "}
              · prioritate {rule.priority}
              {!rule.is_active && " · inactivă"}
            </span>
            {editor && <RuleActions rule={rule} />}
          </div>
        ))}
        {rt.rules.some((r) => r.action === "exclude") && (
          <div className="hint muted" style={{ fontSize: 12 }}>
            O regulă de excludere care se potrivește câștigă întotdeauna.
          </div>
        )}
        {editor && <AddRuleButton rt={rt} />}
      </div>

      {editor && rt.rules.length > 0 && (
        <div>
          <button className="btn sm" disabled={preview.isPending} onClick={() => preview.mutate()}>
            Cui s-ar aplica acum?
          </button>
          {preview.error && <div className="error">{preview.error.message}</div>}
          {preview.data && (
            <div style={{ fontSize: 13, marginTop: 8 }}>
              {preview.data.length === 0
                ? "Niciun client activ."
                : preview.data.map((c, i) => (
                    <span key={c.id}>
                      {i > 0 && ", "}
                      <Link to={`/clienti/${c.id}`}>{c.name}</Link>
                    </span>
                  ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
