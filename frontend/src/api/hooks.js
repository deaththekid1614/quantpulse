/**
 * React Query hooks — one per backend endpoint.
 *
 * staleTime is 60 s, matching the backend's in-memory cache TTL. Data
 * only changes once per trading day, so this is generous.
 *
 * `enabled` guards prevent queries from firing before a ticker is known.
 */
import { useQuery } from "@tanstack/react-query";

import * as client from "./client.js";

export const queryKeys = {
  health: () => ["health"],
  securities: () => ["securities"],
  security: (ticker) => ["security", ticker],
  prices: (ticker, range) => ["prices", ticker, range],
  features: (ticker, range) => ["features", ticker, range],
  snapshot: (ticker) => ["snapshot", ticker],
  stats: (ticker) => ["stats", ticker],
  fundamentals: (ticker) => ["fundamentals", ticker],
  news: (ticker, limit, minImportance) => ["news", ticker, limit, minImportance],
  indicesSnapshot: () => ["indices", "snapshot"],
  movers: (limit) => ["movers", limit],
};

const STALE_MS = 60_000;

export function useHealth() {
  return useQuery({
    queryKey: queryKeys.health(),
    queryFn: client.getHealth,
    staleTime: STALE_MS,
  });
}

export function useSecurities() {
  return useQuery({
    queryKey: queryKeys.securities(),
    queryFn: client.listSecurities,
    staleTime: STALE_MS,
  });
}

export function useSecurity(ticker) {
  return useQuery({
    queryKey: queryKeys.security(ticker),
    queryFn: () => client.getSecurity(ticker),
    enabled: Boolean(ticker),
    staleTime: STALE_MS,
  });
}

export function usePrices(ticker, range = "1y") {
  return useQuery({
    queryKey: queryKeys.prices(ticker, range),
    queryFn: () => client.getPrices(ticker, range),
    enabled: Boolean(ticker),
    staleTime: STALE_MS,
  });
}

export function useFeatures(ticker, range = "1y") {
  return useQuery({
    queryKey: queryKeys.features(ticker, range),
    queryFn: () => client.getFeatures(ticker, range),
    enabled: Boolean(ticker),
    staleTime: STALE_MS,
  });
}

export function useSnapshot(ticker) {
  return useQuery({
    queryKey: queryKeys.snapshot(ticker),
    queryFn: () => client.getSnapshot(ticker),
    enabled: Boolean(ticker),
    staleTime: STALE_MS,
  });
}

export function useStats(ticker) {
  return useQuery({
    queryKey: queryKeys.stats(ticker),
    queryFn: () => client.getStats(ticker),
    enabled: Boolean(ticker),
    staleTime: STALE_MS,
  });
}

export function useFundamentals(ticker) {
  return useQuery({
    queryKey: queryKeys.fundamentals(ticker),
    queryFn: () => client.getFundamentals(ticker),
    enabled: Boolean(ticker),
    staleTime: STALE_MS,
  });
}

export function useNews(ticker, limit = 20, minImportance = 0) {
  return useQuery({
    queryKey: queryKeys.news(ticker, limit, minImportance),
    queryFn: () => client.getNews(ticker, limit, minImportance),
    enabled: Boolean(ticker),
    staleTime: STALE_MS,
  });
}

export function useIndicesSnapshot() {
  return useQuery({
    queryKey: queryKeys.indicesSnapshot(),
    queryFn: client.getIndicesSnapshot,
    staleTime: STALE_MS,
  });
}

export function useMovers(limit = 10) {
  return useQuery({
    queryKey: queryKeys.movers(limit),
    queryFn: () => client.getMovers(limit),
    staleTime: STALE_MS,
  });
}