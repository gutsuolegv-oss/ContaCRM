import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate } from "react-router";

import { api } from "../api/client";
import type { ClientListItem, ClientListOut } from "../api/types";
import { isEditor, useMe } from "../auth/useAuth";
import { ErrorBox } from "../components/ErrorBox";

const PAGE = 50;
type VatFilter = "all" | "vat" | "novat";

export function ClientsPage() {
  const me = useMe();
  const navigate = useNavigate();
  const [q, setQ] = useState("");
  const [vat, setVat] = useState<VatFilter>("all");
  const [offset, setOffset] = useState(0);

  const query = useQuery({
    queryKey: ["clients", q, vat, offset],
    queryFn: () =>
      api.get<ClientListOut>("/api/clients", {
        q,
        is_vat_payer: vat === "all" ? undefined : vat === "vat",
        limit: PAGE,
        offset,
      }),
    placeholderData: (previous) => previous,
  });

  const seg = (value: VatFilter, label: string) => (
    <button
      className={vat === value ? "on" : ""}
      onClick={() => {
        setVat(value);
        setOffset(0);
      }}
    >
      {label}
    </button>
  );

  const total = query.data?.total ?? 0;
  return (
    <>
      <div className="page-head">
        <div>
          <h1>Clienți</h1>
          <p>
            {total} {isEditor(me) ? "clienți în portofoliu" : "clienți repartizați ție"}
          </p>
        </div>
        <Link className="btn primary" to="/clienti/nou">
          Client nou
        </Link>
      </div>
      <div className="card">
        <div className="toolbar">
          <input
            className="input"
            placeholder="Caută după nume sau IDNO"
            value={q}
            onChange={(e) => {
              setQ(e.target.value);
              setOffset(0);
            }}
            style={{ minWidth: 260 }}
          />
          <div className="seg">
            {seg("all", "Toți")}
            {seg("vat", "Plătitori TVA")}
            {seg("novat", "Non-TVA")}
          </div>
        </div>
        {query.error ? (
          <ErrorBox error={query.error} />
        ) : !query.data ? (
          <div className="loading">Se încarcă…</div>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Denumire</th>
                  <th>IDNO</th>
                  <th>Regim</th>
                  <th>Localitate</th>
                  <th>Contabil</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {query.data.items.map((c) => (
                  <tr key={c.id} className="link" onClick={() => navigate(`/clienti/${c.id}`)}>
                    <td className="strong">{c.name}</td>
                    <td className="mono muted">{c.idno}</td>
                    <td>
                      <VatBadge vat={c.is_vat_payer} />
                    </td>
                    <td>{c.locality ?? "—"}</td>
                    <td>{accountants(c)}</td>
                    <td>
                      <ClientStatusBadge status={c.client_status} />
                    </td>
                  </tr>
                ))}
                {query.data.items.length === 0 && (
                  <tr>
                    <td colSpan={6} className="empty">
                      Niciun client găsit
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
        {total > PAGE && (
          <div className="pager">
            <span>
              {offset + 1}–{Math.min(offset + PAGE, total)} din {total}
            </span>
            <span style={{ display: "flex", gap: 8 }}>
              <button
                className="btn sm"
                disabled={offset === 0}
                onClick={() => setOffset(offset - PAGE)}
              >
                Înapoi
              </button>
              <button
                className="btn sm"
                disabled={offset + PAGE >= total}
                onClick={() => setOffset(offset + PAGE)}
              >
                Înainte
              </button>
            </span>
          </div>
        )}
      </div>
    </>
  );
}

function accountants(c: ClientListItem): string {
  return c.accountants.map((a) => a.full_name).join(", ") || "nerepartizat";
}

export function VatBadge({ vat }: { vat: boolean }) {
  return vat ? (
    <span className="badge b-pri">Plătitor TVA</span>
  ) : (
    <span className="badge b-grey">Non-TVA</span>
  );
}

export function ClientStatusBadge({ status }: { status: string }) {
  return status === "active" ? (
    <span className="badge b-ok">Activ</span>
  ) : (
    <span className="badge b-info">Onboarding</span>
  );
}
