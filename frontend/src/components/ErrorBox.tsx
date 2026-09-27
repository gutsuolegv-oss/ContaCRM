import { Icon } from "./Icon";

export function ErrorBox({ error }: { error: unknown }) {
  const message = error instanceof Error ? error.message : "Eroare neașteptată";
  return (
    <div className="card-b">
      <div className="error" style={{ display: "flex", gap: 10, alignItems: "center" }}>
        <Icon name="alert" size={16} />
        {message}
      </div>
    </div>
  );
}
