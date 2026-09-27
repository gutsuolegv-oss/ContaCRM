export function ErrorBox({ error }: { error: unknown }) {
  const message = error instanceof Error ? error.message : "Eroare neașteptată";
  return (
    <div className="card-b">
      <div className="error">{message}</div>
    </div>
  );
}
