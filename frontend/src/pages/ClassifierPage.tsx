import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router";

import { api } from "../api/client";
import type { CategoryOut, ReportTypeDetailOut, ReportTypeOut, StatusSetOut } from "../api/types";
import { isEditor, useMe } from "../auth/useAuth";
import { ErrorBox } from "../components/ErrorBox";
import { Icon } from "../components/Icon";
import { Empty } from "../components/ui";
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
  const [filter, setFilter] = useState("");
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

  const term = filter.trim().toLowerCase();
  const visible = types.data.filter(
    (t) => !term || t.code.toLowerCase().includes(term) || t.name.toLowerCase().includes(term),
  );

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Clasificator de rapoarte</h1>
          <p>
            Catalogul rapoartelor, termenele lor și regulile care decid ce client ce raport are.
          </p>
        </div>
        <div className="page-actions">
          <label className="check">
            <input
              type="checkbox"
              checked={showRetired}
              onChange={(e) => setShowRetired(e.target.checked)}
            />
            arată și rapoartele retrase
          </label>
          {isEditor(me) && (
            <button className="btn primary" onClick={() => setCreating(true)}>
              <Icon name="plus" size={16} /> Raport nou
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
          <div className="input-icon" style={{ maxWidth: 360 }}>
            <Icon name="search" size={16} />
            <input
              className="input"
              placeholder="Filtrează după cod sau denumire"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
            />
          </div>
          {visible.length === 0 && (
            <div className="card">
              <Empty icon="search" title="Niciun raport găsit" />
            </div>
          )}
          {categories.data.map((cat) => {
            const inCategory = visible.filter((t) => t.category_id === cat.id);
            if (inCategory.length === 0) return null;
            return (
              <div className="card" key={cat.id}>
                <div className="card-h">
                  <h3>
                    <Icon name="layers" size={16} />
                    {cat.name}
                  </h3>
                  <span className="count">{inCategory.length} rapoarte</span>
                </div>
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Cod</th>
                        <th>Raport</th>
                        <th>Periodicitate</th>
                        <th className="hide-sm">Termen</th>
                      </tr>
                    </thead>
                    <tbody>
                      {inCategory.map((rt) => (
                        <tr
                          key={rt.id}
                          className={`link${selected === rt.id ? " selected" : ""}`}
                          onClick={() => setSelected(rt.id)}
                          style={!rt.is_active ? { opacity: 0.6 } : undefined}
                        >
                          <td>
                            <span className="chip-r b-pri">{rt.code}</span>
                          </td>
                          <td className="strong">
                            {rt.name}
                            {!rt.is_active && (
                              <span className="badge b-grey" style={{ marginLeft: 6 }}>
                                retras
                              </span>
                            )}
                          </td>
                          <td>
                            <span className="badge plain b-grey">
                              {PERIODICITY[rt.periodicity]}
                            </span>
                          </td>
                          <td className="muted hide-sm" style={{ fontSize: 13 }}>
                            {deadlineText(rt)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            );
          })}
        </div>
        <div className="card detail-panel">
          {selected === null ? (
            <Empty
              icon="reports"
              title="Niciun raport ales"
              hint="Alege un raport din listă ca să-i vezi etapele și regulile."
            />
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
        <div className="person" style={{ alignItems: "flex-start" }}>
          <span className="chip-r b-pri" style={{ height: 32, minWidth: 52, fontSize: 13 }}>
            {rt.code}
          </span>
          <div className="grow">
            <div className="strong" style={{ fontSize: 16, lineHeight: 1.3 }}>
              {rt.name}
            </div>
            {rt.full_name && (
              <div className="muted" style={{ marginTop: 2, fontSize: 13 }}>
                {rt.full_name}
              </div>
            )}
          </div>
        </div>
        {editor && (
          <div style={{ display: "flex", gap: 4, alignItems: "start" }}>
            <button className="btn sm" onClick={() => setEditing(true)}>
              <Icon name="edit" size={14} /> Editează
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
      <div>
        <div className="kv">
          <div className="k">Autoritate</div>
          <div className="v">{rt.authority ?? <span className="nil">—</span>}</div>
        </div>
        <div className="kv">
          <div className="k">Bază legală</div>
          <div className="v">{rt.legal_reference ?? <span className="nil">—</span>}</div>
        </div>
        <div className="kv">
          <div className="k">Periodicitate</div>
          <div className="v">{PERIODICITY[rt.periodicity]}</div>
        </div>
        <div className="kv">
          <div className="k">Termen</div>
          <div className="v">
            {deadlineText(rt)}
            <span className="muted" style={{ fontWeight: 400, fontSize: 12 }}>
              (mutat pe prima zi lucrătoare)
            </span>
          </div>
        </div>
        <div className="kv">
          <div className="k">Plată</div>
          <div className="v">
            {rt.requires_payment ? (
              <span className="badge b-warn">necesită plată</span>
            ) : (
              <span className="badge b-grey">nu</span>
            )}
          </div>
        </div>
        <div className="kv">
          <div className="k">Notificări</div>
          <div className="v">
            {rt.notify_days_before.length ? (
              `cu ${rt.notify_days_before.join(", ")} zile înainte`
            ) : (
              <span className="nil">—</span>
            )}
          </div>
        </div>
        <div className="kv">
          <div className="k">Valabil</div>
          <div className="v">
            din {formatDate(rt.valid_from)}
            {rt.valid_to && ` până la ${formatDate(rt.valid_to)}`}
          </div>
        </div>
      </div>

      <div className="detail-block">
        <div className="section-title">
          <Icon name="grid" size={15} /> Etape în grilă
        </div>
        {editor && statusSets.data ? (
          <StepsEditor rt={rt} statusSets={statusSets.data} />
        ) : (
          <>
            {rt.steps.length === 0 && <div className="muted">Nicio etapă.</div>}
            {rt.steps.map((s, i) => (
              <div key={s.id} className="step-line">
                <span className="n">{i + 1}</span>
                <div>
                  <div className="strong">{s.name}</div>
                  <div className="muted" style={{ fontSize: 12 }}>
                    {setName(s.status_set_id)
                      ?.statuses.map((st) => st.name)
                      .join(" → ")}
                  </div>
                </div>
              </div>
            ))}
          </>
        )}
      </div>

      <div className="detail-block">
        <div className="section-title">
          <Icon name="clients" size={15} /> Cui se aplică
        </div>
        {rt.rules.length === 0 && (
          <div className="muted" style={{ fontSize: 13, marginBottom: 8 }}>
            Fără reguli: se atribuie doar manual, din cartela clientului.
          </div>
        )}
        {rt.rules.map((rule) => (
          <div
            key={rule.id}
            className="rule-line"
            style={!rule.is_active ? { opacity: 0.6 } : undefined}
          >
            <span className={`badge ${rule.action === "assign" ? "b-ok" : "b-bad"}`}>
              {rule.action === "assign" ? "se atribuie" : "se exclude"}
            </span>
            <span>
              când <b>{describeCondition(rule.conditions as Condition)}</b>
            </span>
            <span className="muted">
              · prioritate {rule.priority}
              {!rule.is_active && " · inactivă"}
            </span>
            {editor && <RuleActions rule={rule} />}
          </div>
        ))}
        {rt.rules.some((r) => r.action === "exclude") && (
          <div className="hint" style={{ marginBottom: 8 }}>
            O regulă de excludere care se potrivește câștigă întotdeauna.
          </div>
        )}
        {editor && <AddRuleButton rt={rt} />}
      </div>

      {editor && rt.rules.length > 0 && (
        <div className="detail-block">
          <button className="btn sm" disabled={preview.isPending} onClick={() => preview.mutate()}>
            <Icon name="search" size={14} /> Cui s-ar aplica acum?
          </button>
          {preview.error && (
            <div className="error" style={{ marginTop: 8 }}>
              {preview.error.message}
            </div>
          )}
          {preview.data && (
            <div style={{ fontSize: 13, marginTop: 10 }}>
              {preview.data.length === 0 ? (
                <span className="muted">Niciun client activ.</span>
              ) : (
                <div className="pill-row">
                  {preview.data.map((c) => (
                    <Link key={c.id} className="pill" to={`/clienti/${c.id}`}>
                      {c.name}
                    </Link>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
