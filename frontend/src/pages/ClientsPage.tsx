import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router";

import { api } from "../api/client";
import type { ClientListItem, ClientListOut } from "../api/types";
import { isEditor, useMe } from "../auth/useAuth";
import { ErrorBox } from "../components/ErrorBox";
import { Icon } from "../components/Icon";
import { Avatar, CopyButton, Empty } from "../components/ui";
import { initials } from "../format";

const PAGE = 50;
type VatFilter = "all" | "vat" | "novat";

export function ClientsPage() {
  const me = useMe();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const urlQ = params.get("q") ?? "";
  const [q, setQ] = useState(urlQ);
  const [vat, setVat] = useState<VatFilter>("all");
  const [offset, setOffset] = useState(0);

  // căutarea din bara de sus ajunge aici prin ?q=
  const [seenQ, setSeenQ] = useState(urlQ);
  if (seenQ !== urlQ) {
    setSeenQ(urlQ);
    setQ(urlQ);
    setOffset(0);
  }

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
  const filtered = q !== "" || vat !== "all";
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
          <Icon name="plus" size={16} /> Client nou
        </Link>
      </div>
      <div className="card">
        <div className="toolbar">
          <div className="input-icon" style={{ flex: "1 1 260px", maxWidth: 380 }}>
            <Icon name="search" size={16} />
            <input
              className="input"
              placeholder="Caută după nume sau IDNO"
              value={q}
              onChange={(e) => {
                setQ(e.target.value);
                setOffset(0);
                if (urlQ) setParams({}, { replace: true });
              }}
            />
          </div>
          <div className="seg">
            {seg("all", "Toți")}
            {seg("vat", "Plătitori TVA")}
            {seg("novat", "Non-TVA")}
          </div>
          <span className="spacer" />
          {query.isFetching && query.data && (
            <span className="muted" style={{ fontSize: 12 }}>
              Se actualizează…
            </span>
          )}
        </div>
        {query.error ? (
          <ErrorBox error={query.error} />
        ) : !query.data ? (
          <div className="loading">Se încarcă…</div>
        ) : query.data.items.length === 0 ? (
          <Empty
            icon={filtered ? "search" : "clients"}
            title={filtered ? "Niciun client găsit" : "Încă nu ai clienți"}
            hint={filtered ? "Încearcă alt nume, alt IDNO sau scoate filtrul." : undefined}
            action={
              filtered ? (
                <button
                  className="btn"
                  onClick={() => {
                    setQ("");
                    setVat("all");
                    setParams({}, { replace: true });
                  }}
                >
                  Șterge filtrele
                </button>
              ) : (
                <Link className="btn primary" to="/clienti/nou">
                  <Icon name="plus" size={16} /> Adaugă primul client
                </Link>
              )
            }
          />
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Client</th>
                  <th>IDNO</th>
                  <th>Regim</th>
                  <th>Contabil</th>
                  <th>Status</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {query.data.items.map((c) => (
                  <tr key={c.id} className="link" onClick={() => navigate(`/clienti/${c.id}`)}>
                    <td>
                      <div className="person">
                        <Avatar name={c.name} text={initials(c.name)} size={34} square />
                        <div className="grow">
                          <div className="strong">{c.name}</div>
                          <div className="sub">
                            {c.locality ? (
                              <>
                                <Icon name="pin" size={12} /> {c.locality}
                              </>
                            ) : (
                              "—"
                            )}
                          </div>
                        </div>
                      </div>
                    </td>
                    <td>
                      <span className="idno-cell">
                        <span className="mono muted">{c.idno}</span>
                        <CopyButton value={c.idno} label="Copiază IDNO" />
                      </span>
                    </td>
                    <td>
                      <VatBadge vat={c.is_vat_payer} />
                    </td>
                    <td>
                      <Accountants c={c} />
                    </td>
                    <td>
                      <ClientStatusBadge status={c.client_status} />
                    </td>
                    <td className="num">
                      <span className="row-arrow">
                        <Icon name="chevron" size={16} />
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {total > PAGE && (
          <div className="pager">
            <span>
              {offset + 1}–{Math.min(offset + PAGE, total)} din {total}
            </span>
            <span style={{ display: "flex", gap: 6 }}>
              <button
                className="btn sm"
                disabled={offset === 0}
                onClick={() => setOffset(offset - PAGE)}
              >
                <Icon name="chevronLeft" size={14} /> Înapoi
              </button>
              <button
                className="btn sm"
                disabled={offset + PAGE >= total}
                onClick={() => setOffset(offset + PAGE)}
              >
                Înainte <Icon name="chevron" size={14} />
              </button>
            </span>
          </div>
        )}
      </div>
    </>
  );
}

function Accountants({ c }: { c: ClientListItem }) {
  if (c.accountants.length === 0) return <span className="badge b-warn">nerepartizat</span>;
  return (
    <span className="person">
      <span className="avatar-stack">
        {c.accountants.map((a) => (
          <Avatar key={a.full_name} name={a.full_name} size={26} />
        ))}
      </span>
      <span style={{ fontSize: 13 }}>{c.accountants.map((a) => a.full_name).join(", ")}</span>
    </span>
  );
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
