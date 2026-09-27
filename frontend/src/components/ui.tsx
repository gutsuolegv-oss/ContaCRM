// Componente mici, reutilizate în toate paginile.
import { useState, type InputHTMLAttributes, type ReactNode } from "react";

import { Icon, type IconName } from "./Icon";

const AVATAR_COLORS = [
  "#4f46e5",
  "#0891b2",
  "#059669",
  "#d97706",
  "#db2777",
  "#7c3aed",
  "#2563eb",
  "#65a30d",
];

export function avatarColor(name: string): string {
  let h = 0;
  for (const ch of name) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return AVATAR_COLORS[h % AVATAR_COLORS.length]!;
}

export function personInitials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w.charAt(0).toUpperCase())
    .join("");
}

export function Avatar({
  name,
  size = 28,
  square,
  text,
}: {
  name: string;
  size?: number;
  square?: boolean;
  text?: string;
}) {
  return (
    <span
      className={`avatar${square ? " sq" : ""}`}
      style={{ width: size, height: size, fontSize: size * 0.38, background: avatarColor(name) }}
      title={name}
    >
      {text ?? personInitials(name)}
    </span>
  );
}

/** Copiere în clipboard; merge și pe http:// în rețeaua locală. */
export async function copyText(text: string): Promise<void> {
  if (navigator.clipboard && window.isSecureContext) {
    await navigator.clipboard.writeText(text);
    return;
  }
  const ta = document.createElement("textarea");
  ta.value = text;
  ta.style.position = "fixed";
  ta.style.opacity = "0";
  document.body.appendChild(ta);
  ta.select();
  document.execCommand("copy");
  ta.remove();
}

export function CopyButton({ value, label = "Copiază" }: { value: string; label?: string }) {
  const [done, setDone] = useState(false);
  return (
    <button
      type="button"
      className={`copy-btn${done ? " done" : ""}`}
      title={done ? "Copiat" : label}
      aria-label={label}
      onClick={(e) => {
        e.stopPropagation();
        void copyText(value).then(() => {
          setDone(true);
          window.setTimeout(() => setDone(false), 1400);
        });
      }}
    >
      <Icon name={done ? "check" : "copy"} size={14} />
    </button>
  );
}

export function Empty({
  icon,
  title,
  hint,
  action,
}: {
  icon: IconName;
  title: string;
  hint?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="empty-state">
      <span className="empty-ico">
        <Icon name={icon} />
      </span>
      <div className="strong">{title}</div>
      {hint && <div>{hint}</div>}
      {action}
    </div>
  );
}

export function Kpi({
  label,
  value,
  sub,
  icon,
  tone,
  progress,
}: {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  icon: IconName;
  tone?: "ok" | "bad" | "warn";
  progress?: number;
}) {
  return (
    <div className="kpi">
      <div className="lbl">
        {label}
        <span className={`ico${tone ? ` ${tone}` : ""}`}>
          <Icon name={icon} size={17} />
        </span>
      </div>
      <div className="val">{value}</div>
      {sub && <div className="sub">{sub}</div>}
      {progress !== undefined && (
        <div className={`bar${tone === "ok" ? " ok" : ""}`}>
          <span style={{ width: `${Math.max(0, Math.min(100, progress))}%` }} />
        </div>
      )}
    </div>
  );
}

export function PasswordInput(props: InputHTMLAttributes<HTMLInputElement>) {
  const [show, setShow] = useState(false);
  return (
    <div className="pw-field">
      <input
        {...props}
        className={`input lg ${props.className ?? ""}`}
        type={show ? "text" : "password"}
      />
      <button
        type="button"
        onClick={() => setShow((s) => !s)}
        aria-label={show ? "Ascunde parola" : "Arată parola"}
        title={show ? "Ascunde parola" : "Arată parola"}
      >
        <Icon name={show ? "eyeOff" : "eye"} size={16} />
      </button>
    </div>
  );
}
