import { useVolForecast } from "../api/hooks.js";

/**
 * Volatility forecast panel — honest UI.
 *
 * Displays the model's probability that a security's forward realized
 * volatility over the next N days will be above its own recent median.
 *
 * Colours are deliberately neutral: bar magnitude conveys the number,
 * and the numeric percentage confirms it. We do NOT encode "good" or
 * "bad" in colour, because high volatility is not inherently bad and
 * low volatility is not inherently good — the panel is descriptive.
 */

function fmtPct(v, digits = 1) {
  return `${(v * 100).toFixed(digits)}%`;
}

function fmtVol(v) {
  if (v == null) return "—";
  return `${(v * 100).toFixed(1)}%`;
}

function quality(auc) {
  if (auc == null) return { label: "unknown", tone: "text-ink-400" };
  if (auc >= 0.70) return { label: "strong",       tone: "text-accent-up" };
  if (auc >= 0.65) return { label: "good",         tone: "text-accent-up" };
  if (auc >= 0.60) return { label: "moderate",     tone: "text-ink-200" };
  if (auc >= 0.55) return { label: "weak",         tone: "text-ink-400" };
  return { label: "no signal", tone: "text-accent-down" };
}

function HorizonRow({ h }) {
  const p = h.prob_high_vol;
  const q = quality(h.model_auc);

  // Neutral bar colour: magnitude is conveyed by length, not hue.
  const barColor = "bg-ink-300";

  return (
    <div className="grid grid-cols-[64px_1fr_auto] items-center gap-4 py-3 border-b border-ink-700 last:border-b-0">
      <div className="text-xs font-mono text-ink-400 tracking-wider">
        {h.horizon_days}D
      </div>

      <div className="space-y-1.5">
        <div className="flex items-center gap-3">
          <div className="flex-1 h-2 rounded-full bg-ink-700 overflow-hidden">
            <div
              className={`h-full ${barColor} transition-all`}
              style={{ width: `${(p * 100).toFixed(1)}%` }}
            />
          </div>
          <span className="text-sm tabular-nums text-ink-200 w-14 text-right">
            {fmtPct(p, 1)}
          </span>
        </div>
        <div className="text-[11px] text-ink-500">
          probability of above-median volatility
        </div>
      </div>

      <div className="text-right text-[11px] font-mono text-ink-500 tracking-wider">
        <div className={q.tone}>AUC {h.model_auc?.toFixed(2) ?? "—"}</div>
        <div className="text-ink-600">{q.label}</div>
      </div>
    </div>
  );
}

export default function VolForecastPanel({ ticker }) {
  const { data, isLoading, error } = useVolForecast(ticker);

  if (isLoading) {
    return (
      <div className="rounded-lg bg-ink-800 border border-ink-700 px-5 py-4 space-y-3">
        <div className="h-4 bg-ink-700 rounded animate-pulse w-40" />
        {[0, 1, 2].map((i) => (
          <div key={i} className="h-12 bg-ink-700/60 rounded animate-pulse" />
        ))}
      </div>
    );
  }

  if (error) {
    if (error.status === 404) {
      return (
        <div className="rounded-lg bg-ink-800 border border-ink-700 px-5 py-4 text-sm text-ink-400">
          Volatility forecast not yet available for this security.
        </div>
      );
    }
    return (
      <div className="rounded-lg bg-ink-800 border border-accent-down/40 px-5 py-4 text-sm text-accent-down">
        Failed to load volatility forecast: {error.message}
      </div>
    );
  }

  const horizons = data.horizons || [];
  const currentVol = horizons[0]?.current_vol_20d ?? null;
  const medianVol  = horizons[0]?.threshold ?? null;

  return (
    <div className="rounded-lg bg-ink-800 border border-ink-700 px-5 py-4">
      <div className="flex items-baseline justify-between mb-1 flex-wrap gap-2">
        <div className="text-xs font-mono text-ink-500 tracking-wider">
          AS OF {data.as_of}
        </div>
        {currentVol != null && medianVol != null && (
          <div className="text-[11px] text-ink-500">
            current 20-day vol <span className="text-ink-300">{fmtVol(currentVol)}</span>
            {" · "}
            historical median <span className="text-ink-300">{fmtVol(medianVol)}</span>
          </div>
        )}
      </div>

      <div className="mb-2" />

      {horizons.map((h) => (
        <HorizonRow key={h.horizon_days} h={h} />
      ))}

      <div className="mt-3 pt-3 border-t border-ink-700 text-[11px] text-ink-500 leading-relaxed">
        Forecasts are the model's probability that realized volatility
        over the next N days will be above this stock's historical median.
        <span className="text-ink-400"> We do not predict price direction.</span>
        {" "}Model AUC shown per horizon is the validation ROC AUC —
        higher is better, 0.50 means indistinguishable from random.
      </div>
    </div>
  );
}