import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { useSnapshot } from "../api/hooks.js";
import PriceChart from "../charts/PriceChart.jsx";
import TimeframeTabs from "../components/TimeframeTabs.jsx";
import PerformanceNarrative from "../components/PerformanceNarrative.jsx";
import StatsGrid from "../components/StatsGrid.jsx";
import CompanySnapshot from "../components/CompanySnapshot.jsx";
import CompanyProfile from "../components/CompanyProfile.jsx";

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

function SectionTitle({ children, right }) {
  return (
    <div className="flex items-center justify-between mb-3 flex-wrap gap-3">
      <h2 className="text-xs font-mono tracking-wider text-ink-400 uppercase">
        {children}
      </h2>
      {right}
    </div>
  );
}

function BigStat({ label, value }) {
  return (
    <div>
      <div className="text-xs font-mono text-ink-500 tracking-wider">
        {label}
      </div>
      <div className="mt-0.5 text-sm tabular-nums text-ink-200">{value}</div>
    </div>
  );
}

export default function Stock() {
  const { ticker } = useParams();
  const { data, isLoading, error } = useSnapshot(ticker);
  const [range, setRange] = useState("1y");

  if (isLoading) {
    return (
      <div className="space-y-6">
        <BackLink />
        <div className="h-8 w-40 bg-ink-800 rounded animate-pulse" />
        <div className="h-14 w-64 bg-ink-800 rounded animate-pulse" />
        <div className="h-[380px] bg-ink-800 rounded animate-pulse" />
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
  const changeColor = isUp
    ? "text-accent-up"
    : isDown
      ? "text-accent-down"
      : "text-ink-400";

  return (
    <div className="space-y-10">
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

      {/* Chart */}
      <section>
        <SectionTitle right={<TimeframeTabs value={range} onChange={setRange} />}>
          Price history
        </SectionTitle>
        <PriceChart ticker={ticker} range={range} />
      </section>

      {/* Narrative */}
      <section>
        <SectionTitle>How is {symbol} doing?</SectionTitle>
        <PerformanceNarrative ticker={ticker} symbol={symbol} />
      </section>

      {/* Statistics */}
      <section>
        <SectionTitle>Statistics</SectionTitle>
        <StatsGrid ticker={ticker} />
      </section>

      {/* Fundamentals */}
      <section>
        <SectionTitle>Company snapshot</SectionTitle>
        <CompanySnapshot ticker={ticker} />
      </section>

      {/* Profile */}
      <section>
        <SectionTitle>About {symbol}</SectionTitle>
        <CompanyProfile ticker={ticker} />
      </section>

      {/* Today's OHLC */}
      <section>
        <SectionTitle>Today's session</SectionTitle>
        <div className="rounded-lg bg-ink-800 border border-ink-700 px-5 py-4">
          <div className="grid grid-cols-2 sm:grid-cols-5 gap-4">
            <BigStat label="OPEN" value={`₹${fmtPrice(price.open)}`} />
            <BigStat label="HIGH" value={`₹${fmtPrice(price.high)}`} />
            <BigStat label="LOW" value={`₹${fmtPrice(price.low)}`} />
            <BigStat label="CLOSE" value={`₹${fmtPrice(price.close)}`} />
            <BigStat label="VOLUME" value={fmtVolume(price.volume)} />
          </div>
        </div>
      </section>

      {/* Placeholders */}
      <section className="rounded-lg bg-ink-800 border border-ink-700 px-5 py-5">
        <div className="text-sm text-ink-400 leading-relaxed">
          <div className="mb-2">
            <span className="text-ink-200">Coming next</span> — this page
            continues to grow:
          </div>
          <ul className="space-y-1 text-ink-500">
            <li>· News feed &amp; sentiment — Stage 7</li>
            <li>· 7/15/30-day probabilistic forecasts — Stage 8</li>
            <li>· Risk assessment &amp; stress detection — Stage 9</li>
            <li>· Full plain-English analysis — Stage 10</li>
          </ul>
        </div>
      </section>
    </div>
  );
}