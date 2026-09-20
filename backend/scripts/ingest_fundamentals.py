#!/usr/bin/env python3
"""
Populate the `fundamentals` table from Yahoo Finance.

One row per security. Upserts on every run. Missing fields stay NULL —
they are not invented.

Usage:
    python backend/scripts/ingest_fundamentals.py --ticker TCS.NS
    python backend/scripts/ingest_fundamentals.py --universe nifty50

Idempotent. Safe to re-run.
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from sqlalchemy import select  # noqa: E402

from app.core.log_config import get_logger, setup_logging  # noqa: E402
from app.db.models import FundamentalsRow, IngestLog, Security  # noqa: E402
from app.db.session import init_db, session_scope  # noqa: E402
from app.providers.base import Fundamentals  # noqa: E402
from app.providers.yahoo import YahooMarketDataProvider  # noqa: E402

setup_logging("INFO")
log = get_logger("quantpulse.ingest.fundamentals")

# Maps provider dataclass fields to ORM column names (they're identical
# except for a couple of renames). Kept explicit rather than dynamic for
# clarity and safety.
FIELD_MAP: tuple[tuple[str, str], ...] = (
    ("current_price",      "current_price"),
    ("previous_close",     "previous_close"),
    ("market_cap",         "market_cap"),
    ("enterprise_value",   "enterprise_value"),
    ("high_52w",           "high_52w"),
    ("low_52w",            "low_52w"),
    ("shares_outstanding", "shares_outstanding"),
    ("pe_trailing",        "pe_trailing"),
    ("price_to_book",      "price_to_book"),
    ("price_to_sales",     "price_to_sales"),
    ("eps_trailing",       "eps_trailing"),
    ("total_revenue",      "total_revenue"),
    ("gross_profits",      "gross_profits"),
    ("net_income",         "net_income"),
    ("profit_margin",      "profit_margin"),
    ("return_on_equity",   "return_on_equity"),
    ("return_on_assets",   "return_on_assets"),
    ("total_debt",         "total_debt"),
    ("total_cash",         "total_cash"),
    ("debt_to_equity",     "debt_to_equity"),
    ("dividend_rate",      "dividend_rate"),
    ("dividend_yield",     "dividend_yield"),
    ("payout_ratio",       "payout_ratio"),
    ("long_name",          "long_name"),
    ("yf_sector",          "yf_sector"),
    ("industry",           "industry"),
    ("employees",          "employees"),
    ("city",               "city"),
    ("country",            "country"),
    ("website",            "website"),
    ("description",        "description"),
    ("beta_yf",            "beta_yf"),
)


# ---------------------------------------------------------------------------
# log helpers (same shape as every other ingest script)
# ---------------------------------------------------------------------------

def _open_log(ticker: str) -> int:
    with session_scope() as db:
        row = IngestLog(ticker=ticker, status="running", started_at=datetime.now(timezone.utc))
        db.add(row)
        db.flush()
        return row.id


def _close_log(log_id: int, status: str, added: int = 0, updated: int = 0, error: str | None = None) -> None:
    with session_scope() as db:
        row = db.get(IngestLog, log_id)
        if row is None:
            return
        row.status = status
        row.rows_added = added
        row.rows_updated = updated
        row.error = error
        row.finished_at = datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# upsert
# ---------------------------------------------------------------------------

def upsert_fundamentals(security_id: int, f: Fundamentals) -> tuple[int, int]:
    """
    Insert or update the fundamentals row for one security.
    Returns (rows_added, rows_updated).
    """
    as_of = datetime.now(timezone.utc).date()

    with session_scope() as db:
        existing = db.execute(
            select(FundamentalsRow).where(FundamentalsRow.security_id == security_id)
        ).scalar_one_or_none()

        if existing is None:
            row = FundamentalsRow(security_id=security_id, as_of=as_of)
            for src, dst in FIELD_MAP:
                setattr(row, dst, getattr(f, src))
            db.add(row)
            return 1, 0

        for src, dst in FIELD_MAP:
            setattr(existing, dst, getattr(f, src))
        existing.as_of = as_of
        existing.updated_at = datetime.now(timezone.utc)
        return 0, 1


# ---------------------------------------------------------------------------
# per-security driver
# ---------------------------------------------------------------------------

def ingest_one(provider: YahooMarketDataProvider, ticker: str) -> tuple[int, int]:
    log_id = _open_log(ticker)
    try:
        with session_scope() as db:
            sec = db.execute(
                select(Security).where(Security.ticker == ticker)
            ).scalar_one_or_none()
            if sec is None:
                _close_log(log_id, status="error", error=f"security {ticker} not in DB")
                log.warning("%-15s not in securities table — skipping", ticker)
                return 0, 0
            security_id = sec.id

        f = provider.get_fundamentals(ticker)
        added, updated = upsert_fundamentals(security_id, f)

        # Report coverage so gaps are visible in the log.
        fields = [src for src, _ in FIELD_MAP]
        present = sum(1 for src in fields if getattr(f, src) is not None)
        total = len(fields)

        _close_log(log_id, status="ok", added=added, updated=updated)
        log.info(
            "%-15s +%-2d ~%-2d  (%d/%d fields)",
            ticker, added, updated, present, total,
        )
        return added, updated

    except Exception as exc:
        log.exception("%-15s FAILED: %s", ticker, exc)
        _close_log(log_id, status="error", error=str(exc))
        return 0, 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Quantpulse fundamentals ingestion")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--ticker",   help="single Yahoo ticker, e.g. TCS.NS")
    g.add_argument("--universe", choices=["nifty50"], help="ingest every security in the DB")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    init_db()

    provider = YahooMarketDataProvider()

    if args.ticker:
        tickers = [args.ticker]
    else:
        with session_scope() as db:
            tickers = [t for (t,) in db.execute(
                select(Security.ticker).order_by(Security.id)
            ).all()]

    log.info("Ingesting fundamentals for %d ticker(s)", len(tickers))

    t0 = time.perf_counter()
    total_added = total_updated = 0

    for i, ticker in enumerate(tickers, 1):
        log.info("[%d/%d] %s", i, len(tickers), ticker)
        added, updated = ingest_one(provider, ticker)
        total_added   += added
        total_updated += updated

    elapsed = time.perf_counter() - t0
    log.info("=" * 60)
    log.info("Done in %.1fs", elapsed)
    log.info("  tickers       : %d", len(tickers))
    log.info("  rows added    : %d", total_added)
    log.info("  rows updated  : %d", total_updated)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
