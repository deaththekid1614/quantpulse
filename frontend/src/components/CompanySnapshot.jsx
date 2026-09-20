import { useFundamentals } from "../api/hooks.js";

// ---------- formatting helpers ----------

function fmtInrCr(v) {
  if (v == null) return "—";
  // v is in INR. 1 Cr = 1e7 INR.
  const cr = v / 1e7;
  return `₹${cr.toLocaleString("en-IN", {
    maximumFractionDigits: 0,
  })} Cr`;
}

function fmtPct(v, digits = 2) {
  if (v == null) return "—";
  return `${(v * 100).toFixed(digits)}%`;
}

function fmtYieldPct(v) {
  // dividend_yield is already a percent (3.09 = 3.09%)
  if (v == null) return "—";
  return `${v.toFixed(2)}%`;
}

function fmtNum(v, digits = 2) {
  if (v == null) return "—";
  return v.toFixed(digits);
}

// ---------- interpretation rules ----------

function profitability(d) {
  const pm  = d.profit_margin;
  const roe = d.return_on_equity;
  const ni  = d.net_income;

  // Trailing net income is the ground truth. If it's negative, the
  // company is loss-making, period. Yahoo's profit_margin field can be
  // inconsistent with trailing net income during corporate actions
  // (demergers, one-off charges), so we don't trust it alone.
  if (ni != null && ni < 0) {
    let note = "Trailing twelve months were loss-making.";
    if (pm != null && pm > 0) {
      note += " Reported margin reflects a mixed period.";
    }
    if (roe != null) {
      note += ` Return on equity ${(roe * 100).toFixed(1)}%.`;
    }
    return { label: "Loss-making", note };
  }

  if (pm == null) {
    if (ni != null && ni > 0) {
      return { label: "Profitable", note: "Net income is positive; margin not reported." };
    }
    return { label: "—", note: "Not reported." };
  }

  let label, note;
  if (pm >= 0.20)      { label = "Strong";   note = "Healthy net margin."; }
  else if (pm >= 0.10) { label = "Moderate"; note = "Reasonable net margin."; }
  else if (pm >= 0.03) { label = "Modest";   note = "Thin but positive net margin."; }
  else if (pm >= 0)    { label = "Thin";     note = "Very narrow net margin."; }
  else                 { label = "Negative"; note = "Net margin is negative."; }

  if (roe != null) {
    note += ` Return on equity ${(roe * 100).toFixed(1)}%.`;
  }
  return { label, note };
}

function valuation(d) {
  const pe = d.pe_trailing;
  if (pe == null) return { label: "—", note: "Not reported." };

  if (pe < 15) return { label: "Low",      note: `Trailing P/E ${pe.toFixed(1)}.` };
  if (pe < 25) return { label: "Moderate", note: `Trailing P/E ${pe.toFixed(1)}.` };
  if (pe < 40) return { label: "Elevated", note: `Trailing P/E ${pe.toFixed(1)}.` };
  return { label: "High", note: `Trailing P/E ${pe.toFixed(1)}.` };
}

function balanceSheet(sector, d) {
  const dte = d.debt_to_equity;
  if (dte == null) return { label: "—", note: "Not reported." };

  // Financials are structurally leveraged — deposits and borrowings are
  // core to the business model, so the usual bands don't apply.
  if (sector === "Financial Services") {
    return {
      label: "Typical for financials",
      note: `Debt/Equity ${dte.toFixed(1)}%.`,
    };
  }

  if (dte <= 30)  return { label: "Conservative", note: `Low leverage (${dte.toFixed(1)}%).` };
  if (dte <= 80)  return { label: "Moderate",     note: `Manageable leverage (${dte.toFixed(1)}%).` };
  if (dte <= 200) return { label: "Elevated",     note: `Higher leverage (${dte.toFixed(1)}%).` };
  return { label: "Leveraged", note: `Heavy leverage (${dte.toFixed(1)}%).` };
}

function dividend(d) {
  const y = d.dividend_yield;
  if (y == null) return { label: "—", note: "Not reported." };
  if (y === 0)   return { label: "None",     note: "No dividend paid." };
  if (y < 1.0)   return { label: "Modest",   note: `Yield ${y.toFixed(2)}%.` };
  if (y < 3.0)   return { label: "Moderate", note: `Yield ${y.toFixed(2)}%.` };
  return { label: "High", note: `Yield ${y.toFixed(2)}%.` };
}

// ---------- subcomponents ----------

function Metric({ label, value }) {
  return (
    <div className="bg-ink-800 border border-ink-700 rounded-lg px-4 py-3">
      <div className="text-xs font-mono text-ink-500 tracking-wider">
        {label}
      </div>
      <div className="mt-1.5 text-base tabular-nums text-ink-200">{value}</div>
    </div>
  );
}

function InterpretationCard({ title, label, note }) {
  return (
    <div className="bg-ink-800 border border-ink-700 rounded-lg px-4 py-3">
      <div className="text-xs font-mono text-ink-500 tracking-wider">
        {title}
      </div>
      <div className="mt-1.5 text-base text-white">{label}</div>
      <div className="mt-1 text-xs text-ink-400 leading-relaxed">{note}</div>
    </div>
  );
}

// ---------- main ----------

export default function CompanySnapshot({ ticker }) {
  const { data, isLoading, error } = useFundamentals(ticker);

  if (isLoading) {
    return (
      <div className="space-y-3">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="h-[100px] rounded-lg bg-ink-800 border border-ink-700 animate-pulse" />
          ))}
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {Array.from({ length: 9 }).map((_, i) => (
            <div key={i} className="h-[68px] rounded-lg bg-ink-800 border border-ink-700 animate-pulse" />
          ))}
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-lg bg-ink-800 border border-accent-down/40 px-5 py-4 text-sm text-accent-down">
        Failed to load fundamentals: {error.message}
      </div>
    );
  }

  const profit = profitability(data);
  const val    = valuation(data);
  const bs     = balanceSheet(data.sector, data);
  const div    = dividend(data);

  return (
    <div className="space-y-4">
      {/* Interpretation row */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
        <InterpretationCard
          title="PROFITABILITY"
          label={profit.label}
          note={profit.note}
        />
        <InterpretationCard
          title="VALUATION"
          label={val.label}
          note={val.note}
        />
        <InterpretationCard
          title="BALANCE SHEET"
          label={bs.label}
          note={bs.note}
        />
        <InterpretationCard
          title="DIVIDEND"
          label={div.label}
          note={div.note}
        />
      </div>

      {/* Metric grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
        <Metric label="MARKET CAP"     value={fmtInrCr(data.market_cap)} />
        <Metric label="P/E (TTM)"      value={fmtNum(data.pe_trailing, 2)} />
        <Metric label="EPS (TTM)"      value={data.eps_trailing != null ? `₹${fmtNum(data.eps_trailing, 2)}` : "—"} />

        <Metric label="REVENUE (TTM)"  value={fmtInrCr(data.total_revenue)} />
        <Metric label="NET INCOME"     value={fmtInrCr(data.net_income)} />
        <Metric label="PROFIT MARGIN"  value={fmtPct(data.profit_margin, 2)} />

        <Metric label="DIVIDEND YIELD" value={fmtYieldPct(data.dividend_yield)} />
        <Metric label="DEBT / EQUITY"  value={fmtNum(data.debt_to_equity, 2)} />
        <Metric label="BETA (YAHOO)"   value={fmtNum(data.beta_yf, 2)} />
      </div>

      {/* Footnote */}
      <div className="text-[11px] text-ink-500 leading-relaxed">
        Figures from Yahoo Finance, captured {data.as_of ?? "—"}. Debt/equity
        is Yahoo's raw value for NSE equities (typically a percent). Not
        every metric is reported for every company.
      </div>
    </div>
  );
}