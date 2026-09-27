// Restanțele clienților din 1C (ultima sincronizare). Doar admin și director.

import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router";

import { api } from "../api/client";
import type { DebtsOut } from "../api/types";
import { ErrorBox } from "../components/ErrorBox";
import { Icon } from "../components/Icon";
import { Avatar, CopyButton, Empty, Kpi } from "../components/ui";
import { formatDate, initials } from "../format";

const MDL = new Intl.NumberFormat("ro-MD", {
  style: "currency",
  currency: "MDL",
  currencyDisplay: "code",
});

export function DebtsPage() {
  const debts = useQuery({
    queryKey: ["onec-debts"],
    queryFn: () => api.get<DebtsOut>("/api/onec/debts"),
  });

  if (debts.error) return <ErrorBox error={debts.error} />;
  if (!debts.data) return <div className="loading">Se încarcă…</div>;
  const { run, clients, unmatched } = debts.data;
  const total = clients.reduce((s, c) => s + c.debit, 0);

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Restanțe 1C</h1>
          <p>Cât datorează clienții biroului, după soldurile din 1C. Contabilii nu văd pagina.</p>
        </div>
        <Link className="btn" to="/setari?tab=1c">
          <Icon name="settings" size={16} /> Configurare 1C
        </Link>
      </div>

      {!run ? (
        <div className="card">
          <Empty
            icon="database"
            title="Nicio sincronizare cu 1C încă"
            hint="Instalează scriptul pe calculatorul cu 1C din Setări → 1C; după prima rulare, restanțele apar aici."
          />
        </div>
      ) : (
        <>
          <div className="kpi-row compact">
            <Kpi
              label="Datorii în total"
              value={MDL.format(total)}
              sub={`${clients.length} clienți cu datorii`}
              icon="coin"
              tone={clients.length ? "bad" : "ok"}
            />
            <Kpi
              label="Soldurile la"
              value={formatDate(run.as_of)}
              sub={`primite ${new Date(run.received_at).toLocaleString("ro-MD")}`}
              icon="calendar"
            />
            <Kpi
              label="Contragenți din 1C"
              value={run.rows}
              sub={`${run.matched} potriviți cu clienți`}
              icon="database"
            />
            <Kpi
              label="Negăsiți în CRM"
              value={unmatched.length}
              sub={unmatched.length ? "cu sold, fără cartelă" : "toți potriviți"}
              icon="alert"
              tone={unmatched.length ? "warn" : "ok"}
            />
          </div>

          <div className="card" style={{ marginBottom: 16 }}>
            <div className="card-h">
              <h3>Clienți cu datorii</h3>
            </div>
            {clients.length === 0 ? (
              <Empty icon="check" title="Niciun client nu are datorii" />
            ) : (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Client</th>
                      <th>IDNO</th>
                      <th>Contabil</th>
                      <th className="num">Datorie</th>
                      <th className="num">Avans</th>
                    </tr>
                  </thead>
                  <tbody>
                    {clients.map((c) => (
                      <tr key={c.client_id}>
                        <td>
                          <Link className="person" to={`/clienti/${c.client_id}`}>
                            <Avatar name={c.name} text={initials(c.name)} size={28} square />
                            <span className="strong">{c.name}</span>
                          </Link>
                        </td>
                        <td className="mono">{c.idno}</td>
                        <td>
                          {c.accountants.join(", ") || <span className="muted">fără contabil</span>}
                        </td>
                        <td className="num mono strong" style={{ color: "var(--bad)" }}>
                          {MDL.format(c.debit)}
                        </td>
                        <td className="num mono muted">{c.credit ? MDL.format(c.credit) : "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {unmatched.length > 0 && (
            <div className="card">
              <div className="card-h">
                <h3>Contragenți din 1C negăsiți în CRM</h3>
              </div>
              <div className="card-b muted" style={{ fontSize: 13, paddingBottom: 0 }}>
                Au sold în 1C, dar niciun client din CRM nu are acest IDNO (sau IDNO-ul lipsește în
                1C). Verifică IDNO-ul în 1C sau adaugă clientul.
              </div>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Denumire în 1C</th>
                      <th>IDNO în 1C</th>
                      <th className="num">Datorie</th>
                      <th className="num">Avans</th>
                    </tr>
                  </thead>
                  <tbody>
                    {unmatched.map((u, i) => (
                      <tr key={`${u.idno}-${i}`}>
                        <td>{u.name}</td>
                        <td className="mono">
                          {u.idno ? (
                            <>
                              {u.idno} <CopyButton value={u.idno} label="Copiază IDNO" />
                            </>
                          ) : (
                            <span className="muted">lipsește</span>
                          )}
                        </td>
                        <td className="num mono">{u.debit ? MDL.format(u.debit) : "—"}</td>
                        <td className="num mono muted">{u.credit ? MDL.format(u.credit) : "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </>
      )}
    </>
  );
}
