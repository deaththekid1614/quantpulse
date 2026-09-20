import { useIndicesSnapshot } from "../api/hooks.js";

function fmt(n, digits = 2) {
  return n.toLocaleString("en-IN", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

function tone(v) {
  if (v > 0) return "text-accent-up";
  if (v < 0) return "text-accent-down";
  return "text-ink-400";
}

function arrow(v) {
  if (v > 0) return "▲";
  if (v < 0) return "▼";
  return "·";
}

export default function MarketStrip() {
  const { data, isLoading, error } = useIndicesSnapshot();

  if (isLoading) {
    return (
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        {[0, 1, 2].map((i) => (
          <div
            key={i}
            className="h-20 rounded-lg bg-ink-800 border border-ink-700 animate-pulse"
          />
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-lg bg-ink-800 border border-accent-down/40 px-4 py-3 text-sm text-accent-down">
        Failed to load indices: {error.message}
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
      {data.indices.map((ix) => (
        <div
          key={ix.symbol}
          className="rounded-lg bg-ink-800 border border-ink-700 px-4 py-3"
        >
          <div className="text-xs font-mono text-ink-400 tracking-wider">
            {ix.name}
          </div>
          <div className="mt-1 flex items-baseline justify-between gap-3">
            <div className="text-xl text-white font-medium tabular-nums">
              {fmt(ix.close, ix.name === "INDIA VIX" ? 2 : 2)}
            </div>
            <div className={`text-sm tabular-nums ${tone(ix.change_1d_pct)}`}>
              {arrow(ix.change_1d_pct)}{" "}
              {ix.change_1d_pct > 0 ? "+" : ""}
              {ix.change_1d_pct.toFixed(2)}%
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
