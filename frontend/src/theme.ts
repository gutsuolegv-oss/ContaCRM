// Tema (deschisă / întunecată), ținută doar în browserul utilizatorului.
const KEY = "contacrm.theme";

export function applySavedTheme(): void {
  try {
    const saved = localStorage.getItem(KEY);
    if (saved === "light" || saved === "dark") document.documentElement.dataset.theme = saved;
  } catch {
    // stocare indisponibilă (ex. navigare privată): tema sistemului
  }
}

export function isDarkTheme(): boolean {
  const root = document.documentElement;
  return (
    root.dataset.theme === "dark" ||
    (!root.dataset.theme && window.matchMedia("(prefers-color-scheme: dark)").matches)
  );
}

/** Comută tema și întoarce true dacă noua temă e cea întunecată. */
export function toggleTheme(): boolean {
  const root = document.documentElement;
  root.dataset.theme = isDarkTheme() ? "light" : "dark";
  try {
    localStorage.setItem(KEY, root.dataset.theme);
  } catch {
    // ignorăm: tema rămâne până la reîncărcare
  }
  return root.dataset.theme === "dark";
}
