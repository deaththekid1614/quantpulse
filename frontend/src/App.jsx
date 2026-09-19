import { useEffect, useState } from "react";

export default function App() {
  const [health, setHealth] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetch("/api/health")
      .then((r) => r.json())
      .then(setHealth)
      .catch((e) => setError(String(e)));
  }, []);

  return (
    <div className="min-h-screen flex items-center justify-center">
      <div className="text-center space-y-4">
        <h1 className="text-4xl font-semibold tracking-tight text-white">
          Quantpulse
        </h1>
        <p className="text-sm text-ink-400">
          Post-Market Intelligence &amp; Forecasting Platform
        </p>
        <div className="text-xs font-mono text-ink-400">
          {error && <span className="text-accent-down">backend: {error}</span>}
          {health && (
            <span className="text-accent-up">backend: {health.status}</span>
          )}
          {!health && !error && <span>checking backend…</span>}
        </div>
      </div>
    </div>
  );
}
