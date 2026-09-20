import { Link, Outlet } from "react-router-dom";

import Search from "./Search.jsx";

export default function Layout() {
  return (
    <div className="min-h-screen flex flex-col">
      <header className="border-b border-ink-700 bg-ink-800/60 backdrop-blur sticky top-0 z-20">
        <div className="max-w-6xl mx-auto px-6 h-14 flex items-center gap-6">
          <Link
            to="/"
            className="text-white font-semibold tracking-tight text-lg hover:text-white/90"
          >
            Quantpulse
          </Link>
          <span className="hidden sm:inline text-ink-500 text-xs font-mono">
            POST-MARKET INTELLIGENCE
          </span>
          <div className="flex-1" />
          <Search />
        </div>
      </header>

      <main className="flex-1 max-w-6xl mx-auto w-full px-6 py-8">
        <Outlet />
      </main>

      <footer className="border-t border-ink-700 text-ink-500 text-xs text-center py-4">
        Quantpulse · NSE post-market analysis
      </footer>
    </div>
  );
}
