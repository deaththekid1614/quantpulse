import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { useSecurities } from "../api/hooks.js";

export default function Search() {
  const navigate = useNavigate();
  const { data, isLoading } = useSecurities();
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [highlight, setHighlight] = useState(0);
  const wrapRef = useRef(null);

  const securities = data?.securities ?? [];

  const matches = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return [];
    return securities
      .filter(
        (s) =>
          s.symbol.toLowerCase().includes(q) ||
          s.ticker.toLowerCase().includes(q) ||
          s.name.toLowerCase().includes(q) ||
          s.sector.toLowerCase().includes(q),
      )
      .slice(0, 8);
  }, [query, securities]);

  // Reset highlight whenever the query changes.
  useEffect(() => {
    setHighlight(0);
  }, [query]);

  // Close dropdown on click outside.
  useEffect(() => {
    function onDown(e) {
      if (!wrapRef.current) return;
      if (!wrapRef.current.contains(e.target)) setOpen(false);
    }
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, []);

  function choose(sec) {
    setQuery("");
    setOpen(false);
    navigate(`/stock/${sec.ticker}`);
  }

  function onKeyDown(e) {
    if (e.key === "Escape") {
      setOpen(false);
      return;
    }
    if (matches.length === 0) return;

    if (e.key === "ArrowDown") {
      e.preventDefault();
      setHighlight((h) => (h + 1) % matches.length);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setHighlight((h) => (h - 1 + matches.length) % matches.length);
    } else if (e.key === "Enter") {
      e.preventDefault();
      choose(matches[highlight]);
    }
  }

  const showDropdown = open && matches.length > 0;
  const showEmpty = open && query.trim().length > 0 && matches.length === 0 && !isLoading;

  return (
    <div ref={wrapRef} className="relative w-full max-w-md">
      <input
        type="text"
        value={query}
        onChange={(e) => {
          setQuery(e.target.value);
          setOpen(true);
        }}
        onFocus={() => {
          if (query) setOpen(true);
        }}
        onKeyDown={onKeyDown}
        placeholder="Search TCS, Reliance, Infosys..."
        className="w-full bg-ink-700 border border-ink-600 rounded-md px-3 py-1.5 text-sm text-ink-200 placeholder-ink-500 focus:outline-none focus:border-accent"
        autoComplete="off"
        spellCheck={false}
      />

      {showDropdown && (
        <ul className="absolute top-full mt-1 left-0 right-0 bg-ink-800 border border-ink-600 rounded-md shadow-xl z-30 max-h-80 overflow-auto">
          {matches.map((s, i) => (
            <li
              key={s.ticker}
              onMouseDown={(e) => {
                e.preventDefault();
                choose(s);
              }}
              onMouseEnter={() => setHighlight(i)}
              className={`px-3 py-2 cursor-pointer text-sm ${
                i === highlight ? "bg-ink-700" : ""
              }`}
            >
              <div className="flex justify-between items-baseline gap-3">
                <span className="font-mono text-white">{s.symbol}</span>
                <span className="text-ink-500 text-xs">{s.sector}</span>
              </div>
              <div className="text-ink-400 text-xs mt-0.5">{s.name}</div>
            </li>
          ))}
        </ul>
      )}

      {showEmpty && (
        <div className="absolute top-full mt-1 left-0 right-0 bg-ink-800 border border-ink-600 rounded-md shadow-xl z-30 px-3 py-2 text-xs text-ink-400">
          No matches for &ldquo;{query}&rdquo;
        </div>
      )}
    </div>
  );
}
