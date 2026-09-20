import { Link } from "react-router-dom";

import { useMovers } from "../api/hooks.js";

function tone(v) {
  if (v > 0) return "text-accent-up";
  if (v < 0) return "text-accent-down";
  return "text-ink-400";
}

function fmtPrice(n) {
  return n.toLocaleString("en-IN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

export default function TopMovers({ limit = 10 }) {
  const { data, isLoading, error } = useMovers(limit);

  if (isLoading) {
    return (
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
        {Array.from({ length: limit }).map((_, i) => (
          <div
            key={i}
            className="h-14 rounded-md bg-ink-800 border border-ink-700 animate-pulse"
          />
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-lg bg-ink-800 border border-accent-down/40 px-4 py-3 text-sm text-accent-down">
        Failed to load movers: {error.message}
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
      {data.movers.map((m) => (
        <Link
          key={m.ticker}
          to={`/stock/${m.ticker}`}
          className="rounded-md bg-ink-800 border border-ink-700 hover:border-ink-500 px-4 py-2.5 transition-colors"
        >
          <div className="flex items-baseline justify-between gap-3">
            <span className="font-mono text-sm text-white">{m.symbol}</span>
            <span className={`text-sm tabular-nums ${tone(m.change_1d_pct)}`}>
              {m.change_1d_pct > 0 ? "+" : ""}
              {m.change_1d_pct.toFixed(2)}%
            </span>
          </div>
          <div className="mt-0.5 flex items-baseline justify-between gap-3">
            <span className="text-xs text-ink-400 truncate">{m.name}</span>
            <span className="text-xs text-ink-300 tabular-nums">
              ₹{fmtPrice(m.close)}
            </span>
          </div>
        </Link>
      ))}
    </div>
  );
}
