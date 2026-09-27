import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router";

import { api } from "../api/client";
import type { OrganizationOut } from "../api/types";
import { ROLE_LABEL, isEditor, useAuth, useMe } from "../auth/useAuth";
import { isDarkTheme, toggleTheme } from "../theme";
import { Icon, type IconName } from "./Icon";
import { Avatar } from "./ui";

interface NavItem {
  to: string;
  label: string;
  icon: IconName;
}

export function Layout() {
  const me = useMe();
  const { logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [open, setOpen] = useState(false);
  const [dark, setDark] = useState(isDarkTheme);
  const [q, setQ] = useState("");
  const searchRef = useRef<HTMLInputElement>(null);
  const org = useQuery({
    queryKey: ["organization"],
    queryFn: () => api.get<OrganizationOut>("/api/settings/organization"),
    staleTime: Infinity,
  });

  const work: NavItem[] = [
    { to: "/grila", label: "Grila lunii", icon: "grid" },
    { to: "/clienti", label: "Clienți", icon: "clients" },
  ];
  // Configurarea: doar admin și director (contabilul nu vede secțiunea)
  const admin: NavItem[] = [
    { to: "/clasificator", label: "Clasificator", icon: "layers" },
    { to: "/utilizatori", label: "Utilizatori", icon: "team" },
    { to: "/setari", label: "Setări", icon: "settings" },
  ];

  // meniul mobil se închide la schimbarea paginii
  const [shownPath, setShownPath] = useState(location.pathname);
  if (shownPath !== location.pathname) {
    setShownPath(location.pathname);
    setOpen(false);
  }

  // Ctrl/⌘ + K → căutare
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        searchRef.current?.focus();
      }
      if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const links = (items: NavItem[]) =>
    items.map((i) => (
      <NavLink key={i.to} to={i.to}>
        <Icon name={i.icon} />
        {i.label}
      </NavLink>
    ));

  return (
    <div className="app">
      <aside className={`sidebar${open ? " open" : ""}`}>
        <div className="brand">
          <div className="brand-mark">C</div>
          <div>
            ContaCRM
            <small>{org.data?.name ?? "Birou contabil"}</small>
          </div>
        </div>
        <div className="nav-label">Lucru</div>
        <nav className="nav">{links(work)}</nav>
        {isEditor(me) && (
          <>
            <div className="nav-label">Configurare</div>
            <nav className="nav">{links(admin)}</nav>
          </>
        )}

        <div className="user-card">
          <Avatar name={me.full_name} size={34} />
          <div className="grow">
            <div className="name">{me.full_name}</div>
            <div className="role" title={me.username}>
              {ROLE_LABEL[me.role]} · {me.username}
            </div>
          </div>
          <button
            className="icon-btn"
            onClick={() => void logout()}
            title="Ieșire"
            aria-label="Ieșire"
          >
            <Icon name="logout" size={17} />
          </button>
        </div>
      </aside>
      <div className={`scrim${open ? " open" : ""}`} onClick={() => setOpen(false)} />

      <div className="main">
        <header className="topbar">
          <button className="icon-btn menu-btn" onClick={() => setOpen(true)} aria-label="Meniu">
            <Icon name="menu" />
          </button>
          <form
            className="search"
            onSubmit={(e) => {
              e.preventDefault();
              const term = q.trim();
              navigate(term ? `/clienti?q=${encodeURIComponent(term)}` : "/clienti");
              setQ("");
              searchRef.current?.blur();
            }}
          >
            <Icon name="search" size={16} />
            <input
              ref={searchRef}
              placeholder="Caută client după nume sau IDNO…"
              value={q}
              onChange={(e) => setQ(e.target.value)}
            />
            <kbd>Ctrl K</kbd>
          </form>
          <div className="spacer" />
          <button
            className="icon-btn"
            onClick={() => setDark(toggleTheme())}
            title={dark ? "Temă deschisă" : "Temă întunecată"}
            aria-label="Schimbă tema"
          >
            <Icon name={dark ? "sun" : "moon"} />
          </button>
        </header>
        <main className="content" key={location.pathname}>
          <Outlet />
        </main>
      </div>
    </div>
  );
}
