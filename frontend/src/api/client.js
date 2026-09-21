/**
 * Backend API client.
 *
 * In the browser, paths are relative ("/api/...") and Vite proxies them to
 * the FastAPI backend on 127.0.0.1:8000 (see vite.config.js).
 *
 * In Node (used by tests), the base defaults to the same backend URL so
 * the exact same functions work without any code changes.
 */

const IS_BROWSER = typeof window !== "undefined";
const API_BASE = IS_BROWSER
  ? ""
  : (typeof process !== "undefined" && process.env && process.env.QUANTPULSE_API) ||
    "http://127.0.0.1:8000";

async function apiFetch(path, options = {}) {
  const url = `${API_BASE}${path}`;
  const res = await fetch(url, {
    headers: { Accept: "application/json", ...(options.headers || {}) },
    ...options,
  });

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body?.detail || detail;
    } catch {
      // response wasn't JSON — keep statusText
    }
    const err = new Error(`API ${res.status} ${path}: ${detail}`);
    err.status = res.status;
    throw err;
  }
  return res.json();
}

const enc = encodeURIComponent;

// --- health ---
export const getHealth = () => apiFetch("/api/health");

// --- securities ---
export const listSecurities = () => apiFetch("/api/securities");
export const getSecurity = (ticker) => apiFetch(`/api/securities/${enc(ticker)}`);

// --- history ---
export const getPrices = (ticker, range = "1y") =>
  apiFetch(`/api/securities/${enc(ticker)}/prices?range=${enc(range)}`);

export const getFeatures = (ticker, range = "1y") =>
  apiFetch(`/api/securities/${enc(ticker)}/features?range=${enc(range)}`);

// --- snapshot, stats, fundamentals ---
export const getSnapshot = (ticker) =>
  apiFetch(`/api/securities/${enc(ticker)}/snapshot`);

export const getStats = (ticker) =>
  apiFetch(`/api/securities/${enc(ticker)}/stats`);

export const getFundamentals = (ticker) =>
  apiFetch(`/api/securities/${enc(ticker)}/fundamentals`);

// --- news ---
export const getNews = (ticker, limit = 20, minImportance = 0) => {
  const params = new URLSearchParams();
  params.set("limit", String(limit));
  if (minImportance > 0) params.set("min_importance", String(minImportance));
  return apiFetch(`/api/securities/${enc(ticker)}/news?${params.toString()}`);
};

// --- market ---
export const getIndicesSnapshot = () => apiFetch("/api/indices/snapshot");
export const getMovers = (limit = 10) => apiFetch(`/api/movers?limit=${limit}`);