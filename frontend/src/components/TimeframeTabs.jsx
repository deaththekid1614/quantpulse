/**
 * Timeframe switcher.
 *
 * Renders a row of pill buttons. The active pill is emphasised. Clicking
 * a pill invokes onChange(range) with one of the supported tokens.
 *
 * Ranges supported by the backend: 1w, 1m, 3m, 6m, 1y, 3y, 5y, max.
 * We expose a curated subset — 1w and 1m are omitted because they show
 * fewer candles than fit comfortably on the chart.
 */

export const TIMEFRAMES = [
  { key: "3m",  label: "3M" },
  { key: "6m",  label: "6M" },
  { key: "1y",  label: "1Y" },
  { key: "3y",  label: "3Y" },
  { key: "5y",  label: "5Y" },
  { key: "max", label: "MAX" },
];

export default function TimeframeTabs({ value, onChange }) {
  return (
    <div className="inline-flex rounded-md bg-ink-800 border border-ink-700 p-0.5">
      {TIMEFRAMES.map((tf) => {
        const active = tf.key === value;
        return (
          <button
            key={tf.key}
            type="button"
            onClick={() => onChange(tf.key)}
            className={
              "px-3 py-1 text-xs font-mono tracking-wider rounded " +
              (active
                ? "bg-ink-600 text-white"
                : "text-ink-400 hover:text-white")
            }
          >
            {tf.label}
          </button>
        );
      })}
    </div>
  );
}
