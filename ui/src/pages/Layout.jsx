import { Link, NavLink, Outlet } from "react-router-dom";
import { cn } from "@/lib/utils";

function navLinkClass({ isActive }) {
  return cn(
    "px-3 py-1.5 rounded-md text-sm font-medium",
    isActive ? "bg-neutral-900 text-white" : "text-neutral-700 hover:bg-neutral-100",
  );
}

export default function Layout() {
  return (
    <div className="min-h-full flex flex-col">
      <header className="border-b border-neutral-200 bg-white">
        <div className="mx-auto max-w-6xl px-6 py-4 flex items-center justify-between">
          <Link to="/" className="font-serif text-xl font-semibold text-neutral-900 tracking-tight">
            The Daily Crosswire
          </Link>
          <nav className="flex items-center gap-1">
            <NavLink to="/" end className={navLinkClass}>
              Newspapers
            </NavLink>
            <NavLink to="/configs" className={navLinkClass}>
              Configs
            </NavLink>
          </nav>
        </div>
      </header>
      <main className="flex-1 bg-neutral-50">
        <div className="mx-auto max-w-6xl px-6 py-8">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
