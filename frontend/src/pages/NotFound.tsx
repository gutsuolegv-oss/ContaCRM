import { Link } from "react-router";

import { Empty } from "../components/ui";

export function NotFound() {
  return (
    <div className="card" style={{ marginTop: 40 }}>
      <Empty
        icon="search"
        title="Pagina nu există"
        hint="Verifică adresa sau alege o pagină din meniu."
        action={
          <Link className="btn primary" to="/clienti">
            Înapoi la clienți
          </Link>
        }
      />
    </div>
  );
}
