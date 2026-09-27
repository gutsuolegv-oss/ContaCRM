// Condițiile regulilor (report_rules.conditions) spuse în cuvinte.

export interface ConditionLeaf {
  field: string;
  op: string;
  value?: unknown;
}
export interface ConditionGroup {
  all?: Condition[] | null;
  any?: Condition[] | null;
}
export type Condition = ConditionLeaf | ConditionGroup;

const BOOL_FIELDS: Record<string, [string, string]> = {
  is_vat_payer: ["plătitor de TVA", "neplătitor de TVA"],
  has_employees: ["are angajați", "nu are angajați"],
  is_it_park_resident: ["rezident IT Park", "nerezident IT Park"],
  has_transport: ["are transport", "nu are transport"],
};
const FIELD_LABEL: Record<string, string> = {
  legal_form: "forma juridică",
  tax_regime: "regimul fiscal",
};
const LEGAL_FORM: Record<string, string> = { II: "ÎI", GT: "GȚ" };
const OP_LABEL: Record<string, string> = {
  eq: "este",
  ne: "nu este",
  in: "este una din",
  not_in: "nu este una din",
  gt: ">",
  gte: "≥",
  lt: "<",
  lte: "≤",
};

function show(value: unknown): string {
  if (Array.isArray(value)) return value.map(show).join(", ");
  if (value === null || value === undefined) return "necompletat";
  const text = String(value);
  return LEGAL_FORM[text] ?? text;
}

function leaf({ field, op, value }: ConditionLeaf): string {
  const bool = BOOL_FIELDS[field];
  if (bool && (op === "eq" || op === "ne") && typeof value === "boolean") {
    return bool[(value === true) === (op === "eq") ? 0 : 1];
  }
  const label = FIELD_LABEL[field] ?? field;
  if (op === "is_null") return `${label} ${value ? "necompletat" : "completat"}`;
  return `${label} ${OP_LABEL[op] ?? op} ${show(value)}`;
}

export function describeCondition(condition: Condition, nested = false): string {
  if ("field" in condition) return leaf(condition);
  const [items, joiner] = condition.all
    ? [condition.all, " și "]
    : condition.any
      ? [condition.any, " sau "]
      : [null, ""];
  if (items === null) return "toți clienții";
  if (items.length === 0) return condition.all ? "toți clienții" : "niciun client";
  const text = items.map((c) => describeCondition(c, true)).join(joiner);
  return nested && items.length > 1 ? `(${text})` : text;
}
