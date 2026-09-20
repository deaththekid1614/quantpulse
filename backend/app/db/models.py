"""
ORM models.

Stage 1 defined the storage layer for prices.
Stage 2 adds:
  - market_index_daily  (Nifty 50, Bank Nifty, India VIX)
  - features_daily      (computed features for every security per day)

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
# Same shape as prices_daily, but keyed by index symbol instead of a
# security FK. Indices are not tradeable securities and do not belong in
# `universe.json`. Symbols used: ^NSEI, ^NSEBANK, ^INDIAVIX.

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
# One row per (security, date). Every feature column is NOT NULL — the
# build script drops warm-up rows before writing, so anything that lands
# in the table has a full set of features.

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
    vol_20d: Mapped[float] = mapped_column(Float, nullable=False)   # rolling std of ret_1d
    atr_14d: Mapped[float] = mapped_column(Float, nullable=False)   # average true range

    # --- moving averages (levels) ---
    sma_20:  Mapped[float] = mapped_column(Float, nullable=False)
    sma_50:  Mapped[float] = mapped_column(Float, nullable=False)
    sma_200: Mapped[float] = mapped_column(Float, nullable=False)
    ema_12:  Mapped[float] = mapped_column(Float, nullable=False)
    ema_26:  Mapped[float] = mapped_column(Float, nullable=False)

    # --- price relative to MAs (ratios) ---
    px_over_sma_20:  Mapped[float] = mapped_column(Float, nullable=False)
    px_over_sma_50:  Mapped[float] = mapped_column(Float, nullable=False)
    px_over_sma_200: Mapped[float] = mapped_column(Float, nullable=False)

    # --- momentum ---
    rsi_14:      Mapped[float] = mapped_column(Float, nullable=False)
    macd:        Mapped[float] = mapped_column(Float, nullable=False)
    macd_signal: Mapped[float] = mapped_column(Float, nullable=False)
    macd_hist:   Mapped[float] = mapped_column(Float, nullable=False)
    roc_10:      Mapped[float] = mapped_column(Float, nullable=False)   # rate of change, 10d

    # --- volume ---
    rel_volume_20d: Mapped[float] = mapped_column(Float, nullable=False)  # today / 20d avg
    volume_z_20d:   Mapped[float] = mapped_column(Float, nullable=False)  # (today - mean) / std

    # --- market context ---
    mkt_ret_1d: Mapped[float] = mapped_column(Float, nullable=False)   # Nifty 50, 1d log return
    mkt_ret_5d: Mapped[float] = mapped_column(Float, nullable=False)   # Nifty 50, 5d log return
    beta_60d:   Mapped[float] = mapped_column(Float, nullable=False)   # 60d rolling beta vs Nifty

    # --- sector context ---
    sector_ret_1d: Mapped[float] = mapped_column(Float, nullable=False)  # mean 1d log return of peers

    def __repr__(self) -> str:
        return f"<FeaturesDaily sec={self.security_id} {self.date}>"