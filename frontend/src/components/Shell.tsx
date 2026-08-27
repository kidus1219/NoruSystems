import { useEffect, useState, type ReactNode } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";

import logoLight from "../assets/noru-logo-ink.png";
import logoDark from "../assets/noru-logo.png";
import { useTheme } from "../lib/theme";
import { ThemeToggle } from "./ThemeToggle";

const NAV = [
  { to: "/", label: "Overview", end: true, d: "M2.5 9.5h3l2 4.5 3-11 2 6.5h3" },
  { to: "/employees", label: "Employees", d: "M8 8.5a3 3 0 100-6 3 3 0 000 6zM2.5 14a5.5 5.5 0 0111 0" },
  { to: "/scheduling", label: "Scheduling", d: "M2.5 4h11v10h-11zM2.5 7h11M6 2v3M10 2v3" },
  { to: "/attendance", label: "Attendance", d: "M8 2.5a5.5 5.5 0 100 11 5.5 5.5 0 000-11zM8 5v3.2l2.2 1.6" },
  { to: "/reports", label: "Reports", d: "M4 13.5V8M8 13.5V3.5M12 13.5v-3.5" },
];

export function Shell() {
  const [menuOpen, setMenuOpen] = useState(false);
  const { theme } = useTheme();
  const location = useLocation();

  // Navigating on a phone should put the drawer away again.
  useEffect(() => setMenuOpen(false), [location.pathname]);

  useEffect(() => {
    document.body.style.overflow = menuOpen ? "hidden" : "";
    return () => {
      document.body.style.overflow = "";
    };
  }, [menuOpen]);

  const logo = <img src={theme === "dark" ? logoDark : logoLight} alt="Noru Booking" />;

  return (
    <div className="shell">
      <div className="mobile-bar">
        <button
          type="button"
          className="btn btn-icon"
          aria-label="Menu"
          aria-expanded={menuOpen}
          onClick={() => setMenuOpen((open) => !open)}
        >
          <svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor"
               strokeWidth="1.4" strokeLinecap="round">
            <path d="M2 4h12M2 8h12M2 12h12" />
          </svg>
        </button>
        <div className="mobile-logo">{logo}</div>
        <ThemeToggle />
      </div>

      {menuOpen && <div className="drawer-scrim" onClick={() => setMenuOpen(false)} />}

      <aside className={`sidebar${menuOpen ? " open" : ""}`}>
        <div className="sidebar-logo">{logo}</div>

        <nav className="nav">
          <div className="nav-label">Staff operations</div>
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) => `nav-item${isActive ? " active" : ""}`}
            >
              <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4"
                   strokeLinecap="round" strokeLinejoin="round">
                <path d={item.d} />
              </svg>
              {item.label}
            </NavLink>
          ))}
        </nav>

        <div className="sidebar-end">
          <ThemeToggle />
          <span className="sidebar-version">Staff module · v1.0</span>
        </div>
      </aside>

      <main className="main">
        <Outlet />
      </main>
    </div>
  );
}

export function PageHeader({ title, note, children }: {
  title: string; note?: string; children?: ReactNode;
}) {
  return (
    <header className="topbar">
      <div>
        <h1 className="page-title">{title}</h1>
        {note && <p className="page-note">{note}</p>}
      </div>
      {children}
    </header>
  );
}
