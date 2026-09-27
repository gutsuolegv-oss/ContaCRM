// Editarea clasificatorului: tipul de raport (atributele), etapele și regulile lui.
// Doar pentru admin și director (ClassifierEditor în backend).

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api } from "../api/client";
import type {
  CategoryOut,
  ReportTypeCreate,
  ReportTypeDetailOut,
  ReportTypeOut,
  RuleCreate,
  RuleOut,
  StatusSetOut,
  StepCreate,
  StepOut,
} from "../api/types";
import type { ConditionLeaf } from "../rules";

export const PERIODICITY: Record<ReportTypeCreate["periodicity"], string> = {
  lunar: "lunar",
  trimestrial: "trimestrial",
  semestrial: "semestrial",
  anual: "anual",
  la_cerere: "la cerere",
};
export const MONTHS = [
  "ian",
  "feb",
  "mar",
  "apr",
  "mai",
  "iun",
  "iul",
  "aug",
  "sep",
  "oct",
  "nov",
  "dec",
];

/** Data de azi, "YYYY-MM-DD", în fusul local. */
function today(): string {
  const d = new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

/** După orice modificare: lista și detaliul se reîncarcă. */
function useRefresh() {
  const queryClient = useQueryClient();
  return (id?: number) => {
    void queryClient.invalidateQueries({ queryKey: ["report-types"] });
    if (id !== undefined) void queryClient.invalidateQueries({ queryKey: ["report-type", id] });
  };
}

// --- Tipul de raport ---

type Form = Omit<ReportTypeCreate, "notify_days_before"> & { notify: string };

function toForm(rt: ReportTypeOut | undefined, categoryId: number): Form {
  if (!rt)
    return {
      category_id: categoryId,
      code: "",
      name: "",
      full_name: null,
      legal_reference: null,
      authority: null,
      periodicity: "lunar",
      deadline_rule: "day_of_next_period",
      deadline_day: 25,
      deadline_month: null,
      deadline_month_offset: 1,
      requires_payment: false,
      notify: "7, 3, 1",
      valid_from: today(),
      valid_to: null,
      is_active: true,
      sort_order: 0,
    };
  return {
    category_id: rt.category_id,
    code: rt.code,
    name: rt.name,
    full_name: rt.full_name,
    legal_reference: rt.legal_reference,
    authority: rt.authority,
    periodicity: rt.periodicity,
    deadline_rule: rt.deadline_rule,
    deadline_day: rt.deadline_day,
    deadline_month: rt.deadline_month,
    deadline_month_offset: rt.deadline_month_offset,
    requires_payment: rt.requires_payment,
    notify: rt.notify_days_before.join(", "),
    valid_from: rt.valid_from,
    valid_to: rt.valid_to,
    is_active: rt.is_active,
    sort_order: rt.sort_order,
  };
}

function toBody({ notify, ...form }: Form): ReportTypeCreate {
  const manual = form.deadline_rule === "manual";
  return {
    ...form,
    deadline_day: manual ? null : form.deadline_day,
    deadline_month: form.deadline_rule === "fixed_date" ? form.deadline_month : null,
    notify_days_before: notify
      .split(/[\s,;]+/)
      .filter(Boolean)
      .map(Number),
  };
}

/** Raport nou (fără `reportType`) sau editarea atributelor unuia existent. */
export function ReportTypeFormModal({
  reportType,
  categories,
  onClose,
  onSaved,
}: {
  reportType?: ReportTypeOut;
  categories: CategoryOut[];
  onClose: () => void;
  onSaved: (rt: ReportTypeOut) => void;
}) {
  const refresh = useRefresh();
  const queryClient = useQueryClient();
  const [form, setForm] = useState<Form>(() => toForm(reportType, categories[0]?.id ?? 0));
  const set = <K extends keyof Form>(key: K, value: Form[K]) =>
    setForm((f) => ({ ...f, [key]: value }));
  const text = (value: string) => value.trim() || null;

  const save = useMutation({
    mutationFn: () =>
      reportType
        ? api.patch<ReportTypeOut>(`/api/classifiers/report-types/${reportType.id}`, toBody(form))
        : api.post<ReportTypeOut>("/api/classifiers/report-types", toBody(form)),
    onSuccess: (rt) => {
      refresh(rt.id);
      onSaved(rt);
    },
  });
  const newCategory = useMutation({
    mutationFn: (name: string) =>
      api.post<CategoryOut>("/api/classifiers/categories", {
        name,
        code: name
          .normalize("NFD")
          .replace(/[^\w\s]/g, "")
          .trim()
          .replace(/\s+/g, "_")
          .toLowerCase(),
        sort_order: categories.length * 10 + 10,
      }),
    onSuccess: (cat) => {
      void queryClient.invalidateQueries({ queryKey: ["categories"] });
      set("category_id", cat.id);
    },
  });
  const error = save.error ?? newCategory.error;

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
          <h3>{reportType ? `Editează ${reportType.code}` : "Raport nou"}</h3>
        </div>
        <div className="card-b stack">
          {error && <div className="error">{error.message}</div>}
          <div className="form">
            <div className="field">
              <label>Categorie</label>
              <select
                className="input"
                value={form.category_id}
                onChange={(e) => {
                  if (e.target.value === "new") {
                    const name = window.prompt("Denumirea categoriei noi:");
                    if (name?.trim()) newCategory.mutate(name.trim());
                  } else set("category_id", Number(e.target.value));
                }}
              >
                {categories.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
                <option value="new">+ categorie nouă…</option>
              </select>
            </div>
            <div className="field">
              <label>Cod</label>
              <input
                className="input mono"
                placeholder="ex. TVA12"
                pattern="\w+"
                title="Litere latine, cifre și _"
                maxLength={50}
                value={form.code}
                onChange={(e) => set("code", e.target.value)}
                required
              />
            </div>
            <div className="field full">
              <label>Denumire scurtă</label>
              <input
                className="input"
                maxLength={255}
                value={form.name}
                onChange={(e) => set("name", e.target.value)}
                required
              />
            </div>
            <div className="field full">
              <label>Denumire completă</label>
              <input
                className="input"
                value={form.full_name ?? ""}
                onChange={(e) => set("full_name", text(e.target.value))}
              />
            </div>
            <div className="field">
              <label>Autoritate</label>
              <input
                className="input"
                placeholder="ex. SFS, CNAS, BNS"
                maxLength={100}
                value={form.authority ?? ""}
                onChange={(e) => set("authority", text(e.target.value))}
              />
            </div>
            <div className="field">
              <label>Bază legală</label>
              <input
                className="input"
                value={form.legal_reference ?? ""}
                onChange={(e) => set("legal_reference", text(e.target.value))}
              />
            </div>
            <div className="field">
              <label>Periodicitate</label>
              <select
                className="input"
                value={form.periodicity}
                onChange={(e) => set("periodicity", e.target.value as Form["periodicity"])}
              >
                {Object.entries(PERIODICITY).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </div>
            <div className="field">
              <label>Termen</label>
              <select
                className="input"
                value={form.deadline_rule}
                onChange={(e) => set("deadline_rule", e.target.value as Form["deadline_rule"])}
              >
                <option value="day_of_next_period">ziua X după perioadă</option>
                <option value="fixed_date">dată fixă în an</option>
                <option value="manual">fără termen</option>
              </select>
            </div>
            {form.deadline_rule !== "manual" && (
              <div className="field">
                <label>Ziua</label>
                <input
                  className="input"
                  type="number"
                  min={1}
                  max={31}
                  value={form.deadline_day ?? ""}
                  onChange={(e) =>
                    set("deadline_day", e.target.value ? Number(e.target.value) : null)
                  }
                  required
                />
              </div>
            )}
            {form.deadline_rule === "day_of_next_period" && (
              <div className="field">
                <label>Luna termenului</label>
                <select
                  className="input"
                  value={form.deadline_month_offset}
                  onChange={(e) => set("deadline_month_offset", Number(e.target.value))}
                >
                  <option value={0}>luna în care se încheie perioada</option>
                  <option value={1}>luna următoare perioadei</option>
                  {[2, 3, 4, 5, 6].map((n) => (
                    <option key={n} value={n}>
                      la {n} luni după perioadă
                    </option>
                  ))}
                </select>
              </div>
            )}
            {form.deadline_rule === "fixed_date" && (
              <div className="field">
                <label>Luna</label>
                <select
                  className="input"
                  value={form.deadline_month ?? ""}
                  onChange={(e) => set("deadline_month", Number(e.target.value))}
                  required
                >
                  <option value="" disabled>
                    alege…
                  </option>
                  {MONTHS.map((m, i) => (
                    <option key={m} value={i + 1}>
                      {m}
                    </option>
                  ))}
                </select>
              </div>
            )}
            <div className="field">
              <label>Notificări (zile înainte)</label>
              <input
                className="input"
                placeholder="7, 3, 1"
                pattern="[\d\s,;]*"
                value={form.notify}
                onChange={(e) => set("notify", e.target.value)}
              />
            </div>
            <label className="field" style={{ flexDirection: "row", gap: 8, alignSelf: "end" }}>
              <input
                type="checkbox"
                checked={form.requires_payment}
                onChange={(e) => set("requires_payment", e.target.checked)}
              />
              Implică o plată
            </label>
            <div className="field">
              <label>Valabil de la</label>
              <input
                className="input"
                type="date"
                value={form.valid_from}
                onChange={(e) => set("valid_from", e.target.value)}
                required
              />
            </div>
            <div className="field">
              <label>Valabil până la (opțional)</label>
              <input
                className="input"
                type="date"
                value={form.valid_to ?? ""}
                onChange={(e) => set("valid_to", e.target.value || null)}
              />
            </div>
          </div>
          <div className="hint muted" style={{ fontSize: 12 }}>
            Termenul cade pe prima zi lucrătoare dacă e zi liberă.
            {!reportType && " Etapele și regulile se adaugă după salvare, în panoul raportului."}
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <button className="btn primary" type="submit" disabled={save.isPending}>
              {reportType ? "Salvează" : "Creează raportul"}
            </button>
            <button className="btn ghost" type="button" onClick={onClose}>
              Renunță
            </button>
          </div>
        </div>
      </form>
    </div>
  );
}

export function RetireButton({ rt }: { rt: ReportTypeOut }) {
  const refresh = useRefresh();
  const retire = useMutation({
    mutationFn: (validTo: string) =>
      api.post<ReportTypeOut>(`/api/classifiers/report-types/${rt.id}/retire`, {
        valid_to: validTo,
      }),
    onSuccess: () => refresh(rt.id),
    onError: (e) => window.alert(e.message),
  });
  if (!rt.is_active) return null;
  return (
    <button
      className="btn sm ghost"
      disabled={retire.isPending}
      onClick={() => {
        const validTo = window.prompt(
          `Retragi ${rt.code}? Ultima zi în care se mai aplică (AAAA-LL-ZZ):`,
          today(),
        );
        if (validTo) retire.mutate(validTo);
      }}
    >
      Retrage
    </button>
  );
}

// --- Etape ---

export function StepsEditor({
  rt,
  statusSets,
}: {
  rt: ReportTypeDetailOut;
  statusSets: StatusSetOut[];
}) {
  const refresh = useRefresh();
  const empty = (): StepCreate => ({
    status_set_id: statusSets[0]?.id ?? 0,
    code: "",
    name: "",
    is_required: true,
    sort_order: (rt.steps.length + 1) * 10,
  });
  const [form, setForm] = useState<StepCreate | null>(null);

  const create = useMutation({
    mutationFn: (body: StepCreate) =>
      api.post<StepOut>(`/api/classifiers/report-types/${rt.id}/steps`, body),
    onSuccess: () => {
      setForm(null);
      refresh(rt.id);
    },
  });
  const remove = useMutation({
    mutationFn: (id: number) => api.del<void>(`/api/classifiers/steps/${id}`),
    onSuccess: () => refresh(rt.id),
  });
  const error = create.error ?? remove.error;

  return (
    <div className="stack" style={{ gap: 6 }}>
      {error && <div className="error">{error.message}</div>}
      {rt.steps.map((s) => (
        <div key={s.id} style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
          <span style={{ fontSize: 13 }}>
            {s.name} <span className="muted mono">{s.code}</span>
            {!s.is_required && <span className="muted"> · opțională</span>}
          </span>
          <button
            className="btn sm ghost"
            title="Șterge etapa"
            onClick={() => {
              if (window.confirm(`Ștergi etapa „${s.name}”?`)) remove.mutate(s.id);
            }}
          >
            ✕
          </button>
        </div>
      ))}
      {form === null ? (
        <div>
          <button className="btn sm" onClick={() => setForm(empty())}>
            + Etapă
          </button>
        </div>
      ) : (
        <form
          className="stack"
          style={{ gap: 6 }}
          onSubmit={(e) => {
            e.preventDefault();
            create.mutate(form);
          }}
        >
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            <input
              className="input"
              placeholder="Denumire (ex. Depunere)"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              required
            />
            <input
              className="input mono"
              placeholder="cod"
              pattern="\w+"
              style={{ width: 110 }}
              value={form.code}
              onChange={(e) => setForm({ ...form, code: e.target.value })}
              required
            />
            <select
              className="input"
              value={form.status_set_id}
              onChange={(e) => setForm({ ...form, status_set_id: Number(e.target.value) })}
            >
              {statusSets.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
          </div>
          <label style={{ fontSize: 13, display: "flex", gap: 6 }}>
            <input
              type="checkbox"
              checked={form.is_required}
              onChange={(e) => setForm({ ...form, is_required: e.target.checked })}
            />
            obligatorie
          </label>
          <div style={{ display: "flex", gap: 6 }}>
            <button className="btn sm primary" type="submit" disabled={create.isPending}>
              Adaugă
            </button>
            <button className="btn sm ghost" type="button" onClick={() => setForm(null)}>
              Renunță
            </button>
          </div>
        </form>
      )}
    </div>
  );
}

// --- Reguli ---

const BOOL_FIELDS: [string, string][] = [
  ["is_vat_payer", "plătitor de TVA"],
  ["has_employees", "are angajați"],
  ["is_it_park_resident", "rezident IT Park"],
  ["has_transport", "are transport"],
];
const LEGAL_FORMS: [string, string][] = [
  ["SRL", "SRL"],
  ["SA", "SA"],
  ["II", "ÎI"],
  ["GT", "GȚ"],
  ["ONG", "ONG"],
];

function newLeaf(field: string): ConditionLeaf {
  if (field === "legal_form") return { field, op: "in", value: ["SRL"] };
  if (field === "tax_regime") return { field, op: "eq", value: "" };
  return { field, op: "eq", value: true };
}

/** Un rând de condiție: câmpul clientului, operatorul și valoarea. */
function LeafEditor({
  leaf,
  onChange,
  onRemove,
}: {
  leaf: ConditionLeaf;
  onChange: (leaf: ConditionLeaf) => void;
  onRemove: () => void;
}) {
  const isBool = BOOL_FIELDS.some(([f]) => f === leaf.field);
  return (
    <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center" }}>
      <select
        className="input"
        value={leaf.field}
        onChange={(e) => onChange(newLeaf(e.target.value))}
      >
        {BOOL_FIELDS.map(([f, label]) => (
          <option key={f} value={f}>
            {label}
          </option>
        ))}
        <option value="legal_form">forma juridică</option>
        <option value="tax_regime">regimul fiscal</option>
      </select>
      {isBool && (
        <select
          className="input"
          value={String(leaf.value)}
          onChange={(e) => onChange({ ...leaf, value: e.target.value === "true" })}
        >
          <option value="true">da</option>
          <option value="false">nu</option>
        </select>
      )}
      {leaf.field === "legal_form" && (
        <>
          <select
            className="input"
            value={leaf.op}
            onChange={(e) => onChange({ ...leaf, op: e.target.value })}
          >
            <option value="in">este una din</option>
            <option value="not_in">nu este una din</option>
          </select>
          {LEGAL_FORMS.map(([value, label]) => {
            const selected = (leaf.value as string[]).includes(value);
            return (
              <label key={value} style={{ fontSize: 13, display: "flex", gap: 4 }}>
                <input
                  type="checkbox"
                  checked={selected}
                  onChange={() =>
                    onChange({
                      ...leaf,
                      value: selected
                        ? (leaf.value as string[]).filter((v) => v !== value)
                        : [...(leaf.value as string[]), value],
                    })
                  }
                />
                {label}
              </label>
            );
          })}
        </>
      )}
      {leaf.field === "tax_regime" && (
        <>
          <select
            className="input"
            value={leaf.op}
            onChange={(e) =>
              onChange({
                ...leaf,
                op: e.target.value,
                value: e.target.value === "is_null" ? true : "",
              })
            }
          >
            <option value="eq">este</option>
            <option value="ne">nu este</option>
            <option value="is_null">necompletat</option>
          </select>
          {leaf.op !== "is_null" && (
            <input
              className="input"
              style={{ width: 140 }}
              value={String(leaf.value ?? "")}
              onChange={(e) => onChange({ ...leaf, value: e.target.value })}
              required
            />
          )}
        </>
      )}
      <button className="btn sm ghost" type="button" title="Scoate condiția" onClick={onRemove}>
        ✕
      </button>
    </div>
  );
}

/** Formularul unei reguli noi: o listă de condiții legate prin ȘI sau SAU. */
function NewRuleForm({ rt, onDone }: { rt: ReportTypeDetailOut; onDone: () => void }) {
  const refresh = useRefresh();
  const [action, setAction] = useState<RuleCreate["action"]>("assign");
  const [joiner, setJoiner] = useState<"all" | "any">("all");
  const [leaves, setLeaves] = useState<ConditionLeaf[]>([newLeaf("is_vat_payer")]);
  const [priority, setPriority] = useState(100);

  const create = useMutation({
    mutationFn: () =>
      api.post<RuleOut>(`/api/classifiers/report-types/${rt.id}/rules`, {
        name: `${action === "assign" ? "Atribuie" : "Exclude"} ${rt.code}`,
        action,
        priority,
        conditions: leaves.length === 0 ? {} : { [joiner]: leaves },
      }),
    onSuccess: () => {
      refresh(rt.id);
      onDone();
    },
  });

  return (
    <form
      className="stack"
      style={{ gap: 8, padding: 10, border: "1px solid var(--border)", borderRadius: 8 }}
      onSubmit={(e) => {
        e.preventDefault();
        create.mutate();
      }}
    >
      {create.error && <div className="error">{create.error.message}</div>}
      <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
        <select
          className="input"
          value={action}
          onChange={(e) => setAction(e.target.value as RuleCreate["action"])}
        >
          <option value="assign">Se atribuie</option>
          <option value="exclude">Se exclude</option>
        </select>
        <span style={{ fontSize: 13 }}>când clientul îndeplinește</span>
        <select
          className="input"
          value={joiner}
          onChange={(e) => setJoiner(e.target.value as "all" | "any")}
        >
          <option value="all">toate condițiile</option>
          <option value="any">oricare condiție</option>
        </select>
      </div>
      {leaves.map((leaf, i) => (
        <LeafEditor
          key={i}
          leaf={leaf}
          onChange={(next) => setLeaves(leaves.map((l, j) => (j === i ? next : l)))}
          onRemove={() => setLeaves(leaves.filter((_, j) => j !== i))}
        />
      ))}
      {leaves.length === 0 && (
        <div className="muted" style={{ fontSize: 13 }}>
          Fără condiții: regula se aplică tuturor clienților.
        </div>
      )}
      <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
        <button
          className="btn sm"
          type="button"
          onClick={() => setLeaves([...leaves, newLeaf("has_employees")])}
        >
          + Condiție
        </button>
        <span className="muted" style={{ fontSize: 13, marginLeft: "auto" }}>
          prioritate
        </span>
        <input
          className="input"
          type="number"
          style={{ width: 80 }}
          value={priority}
          onChange={(e) => setPriority(Number(e.target.value))}
        />
      </div>
      <div style={{ display: "flex", gap: 6 }}>
        <button className="btn sm primary" type="submit" disabled={create.isPending}>
          Salvează regula
        </button>
        <button className="btn sm ghost" type="button" onClick={onDone}>
          Renunță
        </button>
      </div>
    </form>
  );
}

/** Butoanele de lângă o regulă existentă: activare/dezactivare și ștergere. */
export function RuleActions({ rule }: { rule: RuleOut }) {
  const refresh = useRefresh();
  const toggle = useMutation({
    mutationFn: () =>
      api.patch<RuleOut>(`/api/classifiers/rules/${rule.id}`, { is_active: !rule.is_active }),
    onSuccess: () => refresh(rule.report_type_id),
    onError: (e) => window.alert(e.message),
  });
  const remove = useMutation({
    mutationFn: () => api.del<void>(`/api/classifiers/rules/${rule.id}`),
    onSuccess: () => refresh(rule.report_type_id),
    onError: (e) => window.alert(e.message),
  });
  return (
    <span style={{ display: "inline-flex", gap: 4, marginLeft: 6 }}>
      <button className="btn sm ghost" onClick={() => toggle.mutate()}>
        {rule.is_active ? "dezactivează" : "activează"}
      </button>
      <button
        className="btn sm ghost"
        title="Șterge regula"
        onClick={() => {
          if (window.confirm("Ștergi regula?")) remove.mutate();
        }}
      >
        ✕
      </button>
    </span>
  );
}

export function AddRuleButton({ rt }: { rt: ReportTypeDetailOut }) {
  const [open, setOpen] = useState(false);
  return open ? (
    <NewRuleForm rt={rt} onDone={() => setOpen(false)} />
  ) : (
    <div>
      <button className="btn sm" onClick={() => setOpen(true)}>
        + Regulă
      </button>
    </div>
  );
}
