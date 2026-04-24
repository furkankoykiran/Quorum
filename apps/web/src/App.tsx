import { NavLink, Outlet } from "react-router-dom";

import ProtocolTelemetryFooter from "./components/ProtocolTelemetryFooter";

const navItems = [
  { to: "/", label: "Observatory", end: true },
  { to: "/debates", label: "Debates" },
  { to: "/shapley", label: "Shapley" },
  { to: "/payout", label: "Payout" },
];

export default function App() {
  return (
    <div className="min-h-screen flex flex-col">
      <header className="border-b border-zinc-800/70 px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-6">
          <span className="text-accent tracking-widest text-sm font-bold">QUORUM OBSERVATORY</span>
          <nav className="flex gap-4 text-sm">
            {navItems.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={({ isActive }) =>
                  `hover:text-accent transition-colors ${
                    isActive ? "text-accent" : "text-zinc-400"
                  }`
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>
        </div>
        <span className="text-xs text-zinc-500">read-only · devnet / fork</span>
      </header>

      <main className="flex-1 px-6 py-6 max-w-7xl w-full mx-auto">
        <Outlet />
      </main>

      <ProtocolTelemetryFooter />

      <a
        href="#feedback"
        aria-disabled="true"
        className="fixed bottom-6 right-6 rounded-full border border-zinc-700 bg-zinc-900 px-4 py-2 text-xs text-zinc-400 hover:text-accent hover:border-accent shadow-lg"
        title="Feedback wiring lands M7"
      >
        feedback
      </a>
    </div>
  );
}
