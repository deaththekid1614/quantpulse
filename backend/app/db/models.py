"""
ORM models.

Stage 1 defined the storage layer for prices.
Stage 2 added:
  - market_index_daily  (Nifty 50, Bank Nifty, India VIX)
  - features_daily      (computed features for every security per day)
Stage 6 adds:
  - fundamentals        (company fundamentals, one row per security)

Future stages append new tables to this file — never rewrite existing ones.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# securities
# ---------------------------------------------------------------------------

class Security(Base):
    __tablename__ = "securities"

    id:         Mapped[int]      = mapped_column(Integer, primary_key=True)
    ticker:     Mapped[str]      = mapped_column(String(32), unique=True, nullable=False, index=True)
    symbol:     Mapped[str]      = mapped_column(String(32), nullable=False)   # e.g. "TCS" (NSE)
    name:       Mapped[str]      = mapped_column(String(128), nullable=False)
    sector:     Mapped[str]      = mapped_column(String(64),  nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    prices: Mapped[list["PriceDaily"]] = relationship(
        back_populates="security",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        return f"<Security {self.ticker} ({self.symbol})>"


# ---------------------------------------------------------------------------
# prices_daily
# ---------------------------------------------------------------------------

class PriceDaily(Base):
    __tablename__ = "prices_daily"
    __table_args__ = (
        UniqueConstraint("security_id", "date", name="uq_prices_daily_security_date"),
        Index("ix_prices_daily_security_date", "security_id", "date"),
    )

    id:          Mapped[int]   = mapped_column(Integer, primary_key=True)
    security_id: Mapped[int]   = mapped_column(
        ForeignKey("securities.id", ondelete="CASCADE"), nullable=False
    )
    date:        Mapped[date]  = mapped_column(Date, nullable=False)
    open:        Mapped[float] = mapped_column(Float, nullable=False)
    high:        Mapped[float] = mapped_column(Float, nullable=False)
    low:         Mapped[float] = mapped_column(Float, nullable=False)
    close:       Mapped[float] = mapped_column(Float, nullable=False)
    volume:      Mapped[int]   = mapped_column(BigInteger, nullable=False)

    security: Mapped[Security] = relationship(back_populates="prices")

    def __repr__(self) -> str:
        return f"<PriceDaily sec={self.security_id} {self.date} close={self.close}>"


# ---------------------------------------------------------------------------
# ingest_log
# ---------------------------------------------------------------------------

class IngestLog(Base):
    __tablename__ = "ingest_log"

    id:           Mapped[int]             = mapped_column(Integer, primary_key=True)
    ticker:       Mapped[str]             = mapped_column(String(32), nullable=False, index=True)
    rows_added:   Mapped[int]             = mapped_column(Integer, default=0, nullable=False)
    rows_updated: Mapped[int]             = mapped_column(Integer, default=0, nullable=False)
    status:       Mapped[str]             = mapped_column(String(16), nullable=False)  # 'ok' | 'error'
    error:        Mapped[str | None]      = mapped_column(Text, nullable=True)
    started_at:   Mapped[datetime]        = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    finished_at:  Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<IngestLog {self.ticker} {self.status} +{self.rows_added}/~{self.rows_updated}>"


# ---------------------------------------------------------------------------
# market_index_daily  (Stage 2)
# ---------------------------------------------------------------------------

class MarketIndexDaily(Base):
    __tablename__ = "market_index_daily"
    __table_args__ = (
        UniqueConstraint("symbol", "date", name="uq_market_index_daily_symbol_date"),
        Index("ix_market_index_daily_symbol_date", "symbol", "date"),
    )

    id:     Mapped[int]   = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str]   = mapped_column(String(32), nullable=False)
    date:   Mapped[date]  = mapped_column(Date, nullable=False)
    open:   Mapped[float] = mapped_column(Float, nullable=False)
    high:   Mapped[float] = mapped_column(Float, nullable=False)
    low:    Mapped[float] = mapped_column(Float, nullable=False)
    close:  Mapped[float] = mapped_column(Float, nullable=False)
    volume: Mapped[int]   = mapped_column(BigInteger, nullable=False)

    def __repr__(self) -> str:
        return f"<MarketIndexDaily {self.symbol} {self.date} close={self.close}>"


# ---------------------------------------------------------------------------
# features_daily  (Stage 2)
# ---------------------------------------------------------------------------

class FeaturesDaily(Base):
    __tablename__ = "features_daily"
    __table_args__ = (
        UniqueConstraint("security_id", "date", name="uq_features_daily_security_date"),
        Index("ix_features_daily_security_date", "security_id", "date"),
    )

    id:          Mapped[int]  = mapped_column(Integer, primary_key=True)
    security_id: Mapped[int]  = mapped_column(
        ForeignKey("securities.id", ondelete="CASCADE"), nullable=False
    )
    date:        Mapped[date] = mapped_column(Date, nullable=False)

    # --- returns (log) ---
    ret_1d:  Mapped[float] = mapped_column(Float, nullable=False)
    ret_5d:  Mapped[float] = mapped_column(Float, nullable=False)
    ret_20d: Mapped[float] = mapped_column(Float, nullable=False)

    # --- volatility ---
    vol_20d: Mapped[float] = mapped_column(Float, nullable=False)
    atr_14d: Mapped[float] = mapped_column(Float, nullable=False)

    # --- moving averages ---
    sma_20:  Mapped[float] = mapped_column(Float, nullable=False)
    sma_50:  Mapped[float] = mapped_column(Float, nullable=False)
    sma_200: Mapped[float] = mapped_column(Float, nullable=False)
    ema_12:  Mapped[float] = mapped_column(Float, nullable=False)
    ema_26:  Mapped[float] = mapped_column(Float, nullable=False)

    # --- price relative to MAs ---
    px_over_sma_20:  Mapped[float] = mapped_column(Float, nullable=False)
    px_over_sma_50:  Mapped[float] = mapped_column(Float, nullable=False)
    px_over_sma_200: Mapped[float] = mapped_column(Float, nullable=False)

    # --- momentum ---
    rsi_14:      Mapped[float] = mapped_column(Float, nullable=False)
    macd:        Mapped[float] = mapped_column(Float, nullable=False)
    macd_signal: Mapped[float] = mapped_column(Float, nullable=False)
    macd_hist:   Mapped[float] = mapped_column(Float, nullable=False)
    roc_10:      Mapped[float] = mapped_column(Float, nullable=False)

    # --- volume ---
    rel_volume_20d: Mapped[float] = mapped_column(Float, nullable=False)
    volume_z_20d:   Mapped[float] = mapped_column(Float, nullable=False)

    # --- market context ---
    mkt_ret_1d: Mapped[float] = mapped_column(Float, nullable=False)
    mkt_ret_5d: Mapped[float] = mapped_column(Float, nullable=False)
    beta_60d:   Mapped[float] = mapped_column(Float, nullable=False)

    # --- sector context ---
    sector_ret_1d: Mapped[float] = mapped_column(Float, nullable=False)

    def __repr__(self) -> str:
        return f"<FeaturesDaily sec={self.security_id} {self.date}>"


# ---------------------------------------------------------------------------
# fundamentals  (Stage 6)
# ---------------------------------------------------------------------------
# One row per security. All value columns are nullable — NSE-listed equities
# genuinely vary in what they report, and Yahoo does not guarantee every
# field for every ticker. Missing values stay NULL. The API and UI render
# NULL as "—"; they never invent zeros.

class FundamentalsRow(Base):
    __tablename__ = "fundamentals"

    id:          Mapped[int]      = mapped_column(Integer, primary_key=True)
    security_id: Mapped[int]      = mapped_column(
        ForeignKey("securities.id", ondelete="CASCADE"),
        unique=True,              # one row per security
        nullable=False,
    )
    as_of:       Mapped[date | None]     = mapped_column(Date, nullable=True)
    updated_at:  Mapped[datetime]        = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    # --- market data ---
    current_price:      Mapped[float | None] = mapped_column(Float, nullable=True)
    previous_close:     Mapped[float | None] = mapped_column(Float, nullable=True)
    market_cap:         Mapped[float | None] = mapped_column(Float, nullable=True)
    enterprise_value:   Mapped[float | None] = mapped_column(Float, nullable=True)
    high_52w:           Mapped[float | None] = mapped_column(Float, nullable=True)
    low_52w:            Mapped[float | None] = mapped_column(Float, nullable=True)
    shares_outstanding: Mapped[float | None] = mapped_column(Float, nullable=True)

    # --- valuation ---
    pe_trailing:    Mapped[float | None] = mapped_column(Float, nullable=True)
    price_to_book:  Mapped[float | None] = mapped_column(Float, nullable=True)
    price_to_sales: Mapped[float | None] = mapped_column(Float, nullable=True)

    # --- earnings ---
    eps_trailing: Mapped[float | None] = mapped_column(Float, nullable=True)

    # --- revenue / profit ---
    total_revenue:    Mapped[float | None] = mapped_column(Float, nullable=True)
    gross_profits:    Mapped[float | None] = mapped_column(Float, nullable=True)
    net_income:       Mapped[float | None] = mapped_column(Float, nullable=True)
    profit_margin:    Mapped[float | None] = mapped_column(Float, nullable=True)
    return_on_equity: Mapped[float | None] = mapped_column(Float, nullable=True)
    return_on_assets: Mapped[float | None] = mapped_column(Float, nullable=True)

    # --- balance sheet ---
    total_debt:     Mapped[float | None] = mapped_column(Float, nullable=True)
    total_cash:     Mapped[float | None] = mapped_column(Float, nullable=True)
    debt_to_equity: Mapped[float | None] = mapped_column(Float, nullable=True)

    # --- dividends ---
    dividend_rate:  Mapped[float | None] = mapped_column(Float, nullable=True)
    dividend_yield: Mapped[float | None] = mapped_column(Float, nullable=True)
    payout_ratio:   Mapped[float | None] = mapped_column(Float, nullable=True)

    # --- profile ---
    long_name:   Mapped[str | None] = mapped_column(String(256), nullable=True)
    yf_sector:   Mapped[str | None] = mapped_column(String(64),  nullable=True)
    industry:    Mapped[str | None] = mapped_column(String(128), nullable=True)
    employees:   Mapped[int | None] = mapped_column(Integer, nullable=True)
    city:        Mapped[str | None] = mapped_column(String(64),  nullable=True)
    country:     Mapped[str | None] = mapped_column(String(64),  nullable=True)
    website:     Mapped[str | None] = mapped_column(String(256), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- reference ---
    beta_yf: Mapped[float | None] = mapped_column(Float, nullable=True)

    def __repr__(self) -> str:
        return f"<FundamentalsRow sec={self.security_id} as_of={self.as_of}>"