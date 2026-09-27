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

export function toggleTheme(): void {
  const root = document.documentElement;
  const dark =
    root.dataset.theme === "dark" ||
    (!root.dataset.theme && window.matchMedia("(prefers-color-scheme: dark)").matches);
  root.dataset.theme = dark ? "light" : "dark";
  try {
    localStorage.setItem(KEY, root.dataset.theme);
  } catch {
    // ignorăm: tema rămâne până la reîncărcare
  }
}
