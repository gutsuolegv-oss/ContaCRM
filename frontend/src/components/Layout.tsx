import { NavLink, Outlet } from "react-router";

import { ROLE_LABEL, isEditor, useAuth, useMe } from "../auth/useAuth";
import { Icon, type IconName } from "./Icon";
import { toggleTheme } from "../theme";

interface NavItem {
  to: string;
  label: string;
  icon: IconName;
  show?: boolean;
}

export function Layout() {
  const me = useMe();
  const { logout } = useAuth();
  const items: NavItem[] = [
    { to: "/grila", label: "Grila lunii", icon: "grid" },
    { to: "/clienti", label: "Clienți", icon: "clients" },
    { to: "/clasificator", label: "Clasificator", icon: "reports" },
    { to: "/utilizatori", label: "Utilizatori", icon: "team", show: isEditor(me) },
  ];

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">C</div>ContaCRM
        </div>
        <nav className="nav">
          {items
            .filter((i) => i.show !== false)
            .map((i) => (
              <NavLink key={i.to} to={i.to}>
                <Icon name={i.icon} />
                {i.label}
              </NavLink>
            ))}
        </nav>
        <div className="sidebar-foot">
          {me.full_name}
          <br />
          {ROLE_LABEL[me.role]} · {me.email}
        </div>
      </aside>
      <div className="main">
        <header className="topbar">
          <div className="spacer" />
          <button className="icon-btn" onClick={toggleTheme} title="Temă deschisă / întunecată">
            <Icon name="moon" />
          </button>
          <button className="btn" onClick={() => void logout()}>
            <Icon name="logout" />
            Ieșire
          </button>
        </header>
        <main className="content">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
