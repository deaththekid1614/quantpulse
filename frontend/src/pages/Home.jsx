import MarketStrip from "../components/MarketStrip.jsx";
import TopMovers from "../components/TopMovers.jsx";

function SectionTitle({ children, hint }) {
  return (
    <div className="flex items-baseline justify-between mb-3">
      <h2 className="text-xs font-mono tracking-wider text-ink-400 uppercase">
        {children}
      </h2>
      {hint && <span className="text-xs text-ink-500">{hint}</span>}
    </div>
  );
}

export default function Home() {
  return (
    <div className="space-y-10">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-semibold text-white tracking-tight">
          Market Overview
        </h1>
        <p className="text-ink-400 text-sm mt-1">
          Indian equities · last session close
        </p>
      </div>

      {/* Market strip */}
      <section>
        <SectionTitle>Indices</SectionTitle>
        <MarketStrip />
      </section>

      {/* Top movers */}
      <section>
        <SectionTitle hint="by absolute 1-day change">Top movers</SectionTitle>
        <TopMovers limit={10} />
      </section>

      {/* Market summary — placeholder for Stage 10 */}
      <section>
        <SectionTitle>Market summary</SectionTitle>
        <div className="rounded-lg bg-ink-800 border border-ink-700 px-5 py-4">
          <p className="text-sm text-ink-400">
            A plain-English read of today's session — what moved, why it
            moved, and what to watch next — will appear here once the
            Explanation Engine is wired in (Stage 10).
          </p>
        </div>
      </section>
    </div>
  );
}
