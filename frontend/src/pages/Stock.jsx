import { Link, useParams } from "react-router-dom";

import { useSnapshot } from "../api/hooks.js";

function fmtPrice(n) {
  return n.toLocaleString("en-IN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function fmtVolume(n) {
  if (n >= 1e7) return `${(n / 1e7).toFixed(2)} Cr`;
  if (n >= 1e5) return `${(n / 1e5).toFixed(2)} L`;
  return n.toLocaleString("en-IN");
}

function fmtDate(iso) {
  const d = new Date(iso + "T00:00:00");
  return d.toLocaleDateString("en-IN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

function BackLink() {
  return (
    <Link
      to="/"
      className="text-ink-400 text-sm hover:text-white inline-block"
    >
      ← Back to market
    </Link>
  );
}

function BigStat({ label, value, tone = "neutral" }) {
  const cls =
    tone === "up"
      ? "text-accent-up"
      : tone === "down"
        ? "text-accent-down"
        : "text-ink-200";
  return (
    <div>
      <div className="text-xs font-mono text-ink-500 tracking-wider">
        {label}
      </div>
      <div className={`mt-0.5 text-sm tabular-nums ${cls}`}>{value}</div>
    </div>
  );
}

export default function Stock() {
  const { ticker } = useParams();
  const { data, isLoading, error } = useSnapshot(ticker);

  if (isLoading) {
    return (
      <div className="space-y-6">
        <BackLink />
        <div className="h-8 w-40 bg-ink-800 rounded animate-pulse" />
        <div className="h-14 w-64 bg-ink-800 rounded animate-pulse" />
        <div className="h-24 bg-ink-800 rounded animate-pulse" />
      </div>
    );
  }

  if (error) {
    const is404 = error.status === 404;
    return (
      <div className="space-y-6">
        <BackLink />
        <div className="rounded-lg bg-ink-800 border border-accent-down/40 px-5 py-4">
          <div className="text-accent-down font-medium">
            {is404 ? `Ticker "${ticker}" not found` : "Failed to load snapshot"}
          </div>
          <div className="text-ink-400 text-sm mt-1">
            {is404
              ? "It may not be in the Nifty 50 universe, or the ticker format may be wrong (should be like TCS.NS)."
              : error.message}
          </div>
        </div>
      </div>
    );
  }

  const { symbol, name, sector, as_of, price, change_1d, change_1d_pct } = data;
  const isUp = (change_1d_pct ?? 0) > 0;
  const isDown = (change_1d_pct ?? 0) < 0;
  const changeTone = isUp ? "up" : isDown ? "down" : "neutral";
  const changeColor =
    changeTone === "up"
      ? "text-accent-up"
      : changeTone === "down"
        ? "text-accent-down"
        : "text-ink-400";

  return (
    <div className="space-y-8">
      <BackLink />

      {/* Header */}
      <div>
        <div className="flex items-baseline gap-4 flex-wrap">
          <h1 className="text-3xl font-semibold text-white tracking-tight font-mono">
            {symbol}
          </h1>
          <span className="text-ink-400 text-sm">{name}</span>
        </div>
        <div className="text-ink-500 text-xs font-mono mt-1.5 tracking-wider">
          {sector.toUpperCase()} · NSE · LAST SESSION {fmtDate(as_of)}
        </div>
      </div>

      {/* Price block */}
      <div className="flex items-end gap-6 flex-wrap">
        <div className="text-4xl font-medium text-white tabular-nums">
          ₹{fmtPrice(price.close)}
        </div>
        <div className={`text-base tabular-nums ${changeColor} pb-1`}>
          {change_1d > 0 ? "+" : ""}
          {fmtPrice(change_1d)} ({change_1d_pct > 0 ? "+" : ""}
          {change_1d_pct.toFixed(2)}%)
        </div>
      </div>

      {/* Session OHLC row */}
      <div className="rounded-lg bg-ink-800 border border-ink-700 px-5 py-4">
        <div className="text-xs font-mono text-ink-500 tracking-wider mb-3">
          TODAY'S SESSION
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-4">
          <BigStat label="OPEN" value={`₹${fmtPrice(price.open)}`} />
          <BigStat label="HIGH" value={`₹${fmtPrice(price.high)}`} />
          <BigStat label="LOW" value={`₹${fmtPrice(price.low)}`} />
          <BigStat label="CLOSE" value={`₹${fmtPrice(price.close)}`} />
          <BigStat label="VOLUME" value={fmtVolume(price.volume)} />
        </div>
      </div>

      {/* Placeholder for Stage 5 */}
      <div className="rounded-lg bg-ink-800 border border-ink-700 px-5 py-6">
        <div className="text-sm text-ink-400">
          The 5-year interactive chart, performance narrative, risk analysis,
          and forecast panels arrive in <span className="text-ink-200">Stage 5</span>{" "}
          onward.
        </div>
      </div>
    </div>
  );
}