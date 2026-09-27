export function Placeholder({ title }: { title: string }) {
  return (
    <div className="page-head">
      <div>
        <h1>{title}</h1>
        <p>Pagina urmează în commit-urile următoare.</p>
      </div>
    </div>
  );
}
