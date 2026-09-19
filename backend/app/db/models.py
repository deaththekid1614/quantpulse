"""
ORM models. Stage 1 defines the storage layer for prices only.

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

    id:           Mapped[int]            = mapped_column(Integer, primary_key=True)
    ticker:       Mapped[str]            = mapped_column(String(32), nullable=False, index=True)
    rows_added:   Mapped[int]            = mapped_column(Integer, default=0, nullable=False)
    rows_updated: Mapped[int]            = mapped_column(Integer, default=0, nullable=False)
    status:       Mapped[str]            = mapped_column(String(16), nullable=False)  # 'ok' | 'error'
    error:        Mapped[str | None]     = mapped_column(Text, nullable=True)
    started_at:   Mapped[datetime]       = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    finished_at:  Mapped[datetime | None]= mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<IngestLog {self.ticker} {self.status} +{self.rows_added}/~{self.rows_updated}>"
