const DATE = new Intl.DateTimeFormat("ro-MD", {
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
});
const MONTH = new Intl.DateTimeFormat("ro-MD", { month: "long", year: "numeric" });

/** "2026-10-26" → "26.10.2026" (fără conversie de fus orar). */
export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  return DATE.format(new Date(y!, m! - 1, d!));
}

export function formatMonth(year: number, month: number): string {
  const text = MONTH.format(new Date(year, month - 1, 1));
  return text.charAt(0).toUpperCase() + text.slice(1);
}

export function initials(name: string): string {
  return name
    .replace(/^ÎI /, "")
    .split(/\s+/)
    .slice(0, 2)
    .map((w) => w.charAt(0).toUpperCase())
    .join("");
}
