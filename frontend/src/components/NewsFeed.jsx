import { useNews } from "../api/hooks.js";

// Google News appends " - <Publisher>" to titles. We strip it for display
// so the publisher isn't shown twice (once in the title, once in `source`).
const PUBLISHER_SUFFIX = /\s+[-–—]\s+[^-–—]{2,60}$/;

function cleanTitle(t) {
  return t.replace(PUBLISHER_SUFFIX, "").trim();
}

function timeAgo(iso) {
  // The API serializes naive UTC (no "Z"). Append if missing so the
  // browser doesn't misinterpret as local time.
  const hasTz = iso.endsWith("Z") || /[+-]\d{2}:?\d{2}$/.test(iso);
  const dt = new Date(hasTz ? iso : iso + "Z");

  const sec = Math.max(1, Math.floor((Date.now() - dt.getTime()) / 1000));
  if (sec < 60) return `${sec}s ago`;
  const min = Math.floor(sec / 60);
  if (min < 60) return `${min}m ago`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr}h ago`;
  const d = Math.floor(hr / 24);
  if (d < 7) return `${d}d ago`;
  const w = Math.floor(d / 7);
  if (w < 5) return `${w}w ago`;
  return dt.toLocaleDateString("en-IN", { day: "2-digit", month: "short" });
}

function sentimentStyle(label) {
  if (label === "positive") {
    return { dot: "bg-accent-up", text: "text-accent-up", label: "POSITIVE" };
  }
  if (label === "negative") {
    return { dot: "bg-accent-down", text: "text-accent-down", label: "NEGATIVE" };
  }
  return { dot: "bg-ink-500", text: "text-ink-400", label: "NEUTRAL" };
}

function ImportanceBar({ value }) {
  const v = value == null ? 0 : Math.max(0, Math.min(1, value));
  return (
    <div className="flex items-center gap-2">
      <span className="text-[10px] font-mono text-ink-500 tracking-wider">
        IMPACT
      </span>
      <div className="w-16 h-1 rounded-full bg-ink-700 overflow-hidden">
        <div
          className="h-full bg-ink-400"
          style={{ width: `${(v * 100).toFixed(0)}%` }}
        />
      </div>
    </div>
  );
}

function SentimentChip({ label }) {
  const s = sentimentStyle(label);
  return (
    <div className="flex items-center gap-1.5">
      <span className={`w-1.5 h-1.5 rounded-full ${s.dot}`} />
      <span className={`text-[10px] font-mono tracking-wider ${s.text}`}>
        {s.label}
      </span>
    </div>
  );
}

function ArticleCard({ a }) {
  return (
    <a
      href={a.url}
      target="_blank"
      rel="noopener noreferrer"
      className="block rounded-lg bg-ink-800 border border-ink-700 hover:border-ink-500 px-4 py-3 transition-colors"
    >
      <div className="text-[15px] text-ink-200 leading-snug">
        {cleanTitle(a.title)}
      </div>
      <div className="mt-2 flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-2 text-xs text-ink-500">
          <span className="text-ink-400">{a.source || "Unknown"}</span>
          <span>·</span>
          <span>{timeAgo(a.published_at)}</span>
        </div>
        <div className="flex items-center gap-4">
          <SentimentChip label={a.sentiment_label} />
          <ImportanceBar value={a.importance_score} />
        </div>
      </div>
    </a>
  );
}

export default function NewsFeed({ ticker, limit = 15 }) {
  const { data, isLoading, error } = useNews(ticker, limit, 0);

  if (isLoading) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 4 }).map((_, i) => (
          <div
            key={i}
            className="h-[76px] rounded-lg bg-ink-800 border border-ink-700 animate-pulse"
          />
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-lg bg-ink-800 border border-accent-down/40 px-5 py-4 text-sm text-accent-down">
        Failed to load news: {error.message}
      </div>
    );
  }

  if (!data.articles || data.articles.length === 0) {
    return (
      <div className="rounded-lg bg-ink-800 border border-ink-700 px-5 py-4 text-sm text-ink-400">
        No recent news found for this security.
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {data.articles.map((a, i) => (
        <ArticleCard key={`${a.url}-${i}`} a={a} />
      ))}
    </div>
  );
}
