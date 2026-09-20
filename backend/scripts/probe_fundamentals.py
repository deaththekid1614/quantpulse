#!/usr/bin/env python3
"""
One-off probe: what fields does yfinance actually return for NSE-listed
equities?

Reads nothing from the DB. Writes nothing. Prints a coverage report for a
handful of tickers so we can decide which columns are worth persisting.

Usage:
    .venv/bin/python backend/scripts/probe_fundamentals.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "backend"))

import yfinance as yf  # noqa: E402

# Fields we're considering persisting. Grouped for readability.
CANDIDATES = [
    # --- market data ---
    ("marketCap",         "Market capitalisation"),
    ("enterpriseValue",   "Enterprise value"),
    ("currentPrice",      "Current price"),
    ("previousClose",     "Previous close"),
    ("fiftyTwoWeekHigh",  "52-week high"),
    ("fiftyTwoWeekLow",   "52-week low"),

    # --- valuation ---
    ("trailingPE",        "Trailing P/E"),
    ("forwardPE",         "Forward P/E"),
    ("priceToBook",       "Price/Book"),
    ("priceToSalesTrailing12Months", "Price/Sales"),

    # --- earnings ---
    ("trailingEps",       "Trailing EPS"),
    ("forwardEps",        "Forward EPS"),
    ("earningsQuarterlyGrowth", "Quarterly earnings growth"),

    # --- revenue / profit ---
    ("totalRevenue",      "Total revenue (TTM)"),
    ("grossProfits",      "Gross profits (TTM)"),
    ("netIncomeToCommon", "Net income (TTM)"),
    ("profitMargins",     "Profit margin"),

    # --- balance sheet ---
    ("totalDebt",         "Total debt"),
    ("totalCash",         "Total cash"),
    ("debtToEquity",      "Debt/Equity"),
    ("returnOnEquity",    "Return on equity"),
    ("returnOnAssets",    "Return on assets"),

    # --- dividends ---
    ("dividendRate",      "Dividend rate (annual)"),
    ("dividendYield",     "Dividend yield"),
    ("payoutRatio",       "Payout ratio"),
    ("fiveYearAvgDividendYield", "5y avg dividend yield"),

    # --- profile ---
    ("longName",          "Long name"),
    ("sector",            "Sector (yfinance)"),
    ("industry",          "Industry"),
    ("fullTimeEmployees", "Employee count"),
    ("city",              "City"),
    ("state",             "State"),
    ("country",           "Country"),
    ("website",           "Website"),
    ("longBusinessSummary", "Business description"),

    # --- misc ---
    ("beta",              "Beta (yfinance's own)"),
    ("sharesOutstanding", "Shares outstanding"),
]

PROBE_TICKERS = ["TCS.NS", "RELIANCE.NS", "HDFCBANK.NS", "TMPV.NS"]


def probe_one(ticker: str) -> dict:
    """Fetch .info and return it. Handles failures gracefully."""
    t = yf.Ticker(ticker)
    try:
        info = t.info
    except Exception as exc:  # yfinance can raise various errors
        return {"__error__": f"{type(exc).__name__}: {exc}"}
    return info or {}


def main() -> int:
    print(f"Probing {len(PROBE_TICKERS)} tickers via yfinance .info")
    print("=" * 72)
    print()

    infos: dict[str, dict] = {}
    for tk in PROBE_TICKERS:
        t0 = time.perf_counter()
        info = probe_one(tk)
        dt = time.perf_counter() - t0
        infos[tk] = info
        status = (
            f"ERROR: {info['__error__']}"
            if "__error__" in info
            else f"{len(info)} keys, {dt:.2f}s"
        )
        print(f"{tk:15s} -> {status}")

    print()
    print("=" * 72)
    print("Field coverage (● present, · missing)")
    print("=" * 72)
    print()
    header = f"{'field':40s}  " + "  ".join(tk.replace('.NS', '') for tk in PROBE_TICKERS)
    print(header)
    print("-" * len(header))

    for key, label in CANDIDATES:
        marks = []
        for tk in PROBE_TICKERS:
            v = infos[tk].get(key) if "__error__" not in infos[tk] else None
            marks.append("●" if v not in (None, "", []) else "·")
        print(f"{key:40s}  " + "       ".join(marks))

    print()
    print("=" * 72)
    print("Sample values (TCS.NS only)")
    print("=" * 72)
    print()
    tcs = infos["TCS.NS"]
    for key, label in CANDIDATES:
        v = tcs.get(key)
        if isinstance(v, str) and len(v) > 100:
            v = v[:97] + "..."
        print(f"  {key:40s} = {v!r}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
