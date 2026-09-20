import { useQuery } from "@tanstack/react-query";

import { getStats } from "../api/client.js";

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

function pctTone(v) {
  if (v == null) return "text-ink-400";
  if (v > 0) return "text-accent-up";
  if (v < 0) return "text-accent-down";
  return "text-ink-400";
}

function fmtPct(v) {
  if (v == null) return "—";
  const sign = v > 0 ? "+" : "";
  return `${sign}${v.toFixed(2)}%`;
}

function Cell({ label, value, tone = "neutral" }) {
  const valueCls =
    tone === "up"
      ? "text-accent-up"
      : tone === "down"
        ? "text-accent-down"
        : tone === "muted"
          ? "text-ink-400"
          : "text-ink-200";
  return (
    <div className="bg-ink-800 border border-ink-700 rounded-lg px-4 py-3">
      <div className="text-xs font-mono text-ink-500 tracking-wider">
        {label}
      </div>
      <div className={`mt-1.5 text-base tabular-nums ${valueCls}`}>{value}</div>
    </div>
  );
}

export default function StatsGrid({ ticker }) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["stats", ticker],
    queryFn: () => getStats(ticker),
    staleTime: 60_000,
    enabled: Boolean(ticker),
  });

  if (isLoading) {
    return (
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
        {Array.from({ length: 9 }).map((_, i) => (
          <div
            key={i}
            className="h-[68px] rounded-lg bg-ink-800 border border-ink-700 animate-pulse"
          />
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-lg bg-ink-800 border border-accent-down/40 px-5 py-4 text-sm text-accent-down">
        Failed to load stats: {error.message}
      </div>
    );
  }

  const tone = (v) => (v > 0 ? "up" : v < 0 ? "down" : "neutral");

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
      <Cell
        label="52-WEEK RANGE"
        value={`₹${fmtPrice(data.low_52w)} → ₹${fmtPrice(data.high_52w)}`}
      />
      <Cell
        label="FROM 52W HIGH"
        value={fmtPct(data.pct_from_52w_high)}
        tone={data.pct_from_52w_high < 0 ? "down" : "neutral"}
      />
      <Cell
        label="FROM 52W LOW"
        value={fmtPct(data.pct_from_52w_low)}
        tone={data.pct_from_52w_low > 0 ? "up" : "neutral"}
      />

      <Cell
        label="1-DAY RETURN"
        value={fmtPct(data.ret_1d_pct)}
        tone={tone(data.ret_1d_pct)}
      />
      <Cell
        label="20-DAY RETURN"
        value={fmtPct(data.ret_20d_pct)}
        tone={tone(data.ret_20d_pct)}
      />
      <Cell
        label="YTD RETURN"
        value={fmtPct(data.ret_ytd_pct)}
        tone={tone(data.ret_ytd_pct)}
      />

      <Cell
        label="1-YEAR RETURN"
        value={fmtPct(data.ret_1y_pct)}
        tone={tone(data.ret_1y_pct)}
      />
      <Cell label="AVG VOLUME (20D)" value={fmtVolume(data.avg_volume_20d)} />
      <Cell
        label="ALL-TIME RANGE"
        value={`₹${fmtPrice(data.all_time_low)} → ₹${fmtPrice(data.all_time_high)}`}
      />
    </div>
  );
}
