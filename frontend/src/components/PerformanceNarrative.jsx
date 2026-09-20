import { useSnapshot } from "../api/hooks.js";

import { buildNarrative } from "./narrative.js";

export default function PerformanceNarrative({ ticker, symbol }) {
  const { data, isLoading, error } = useSnapshot(ticker);

  if (isLoading) {
    return (
      <div className="rounded-lg bg-ink-800 border border-ink-700 px-5 py-5 space-y-2">
        <div className="h-4 bg-ink-700 rounded animate-pulse w-3/4" />
        <div className="h-4 bg-ink-700 rounded animate-pulse w-5/6" />
        <div className="h-4 bg-ink-700 rounded animate-pulse w-2/3" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-lg bg-ink-800 border border-accent-down/40 px-5 py-4 text-sm text-accent-down">
        Failed to load narrative: {error.message}
      </div>
    );
  }

  const text = buildNarrative(symbol, data.features);

  if (!text) {
    return (
      <div className="rounded-lg bg-ink-800 border border-ink-700 px-5 py-4 text-sm text-ink-400">
        Narrative will appear once sufficient feature history is available.
      </div>
    );
  }

  return (
    <div className="rounded-lg bg-ink-800 border border-ink-700 px-5 py-5">
      <p className="text-ink-200 leading-relaxed text-[15px]">{text}</p>
    </div>
  );
}
