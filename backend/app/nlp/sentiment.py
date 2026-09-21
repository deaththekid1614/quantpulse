"""
Rule-based sentiment, relevance, and importance scoring for news articles.

All three functions are pure: given the same inputs they return the same
outputs. No state, no network, no DB. This makes them testable and safe
to call from the ingest pipeline or a batch rescoring job.

Sentiment uses VADER — a lexicon-based model tuned for social media and
short text. It runs offline, ~2 MB, no GPU, no model download.

VADER alone underperforms on financial headlines: "profit warning" is
one negative concept, not "profit" (positive) + "warning". We apply a
small financial-lexicon overlay on top of VADER's compound score to
correct for this. The overlay is a weighted sum of unique finance-
negative and finance-positive terms, capped at ±0.5.

Relevance and importance are hand-tuned rules. They are deliberately
conservative: an article with no strong company signal scores below 0.3
and is dropped at ingest time.
"""
from __future__ import annotations

import math
import re
from datetime import datetime, timezone

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

# VADER is stateless once constructed. Build one and reuse.
_vader = SentimentIntensityAnalyzer()

# ---------------------------------------------------------------------------
# constants
# ---------------------------------------------------------------------------

_WORD_RE_CACHE: dict[str, re.Pattern[str]] = {}

_FIN_CONTEXT_TERMS: frozenset[str] = frozenset({
    "stock", "stocks", "share", "shares", "price", "prices",
    "nse", "bse", "sensex", "nifty", "market", "markets",
    "quarter", "q1", "q2", "q3", "q4", "earnings", "revenue", "profit",
})

_TOO_GENERIC: frozenset[str] = frozenset({
    "tata", "reliance", "adani", "bajaj", "hindustan", "sun", "power",
    "bank", "finance", "industries", "group", "limited", "ltd", "ltd.",
    "india", "indian", "the",
})

_IMPACT_TERMS: tuple[str, ...] = (
    "guidance", "downgrade", "downgraded", "upgrade", "upgraded",
    "acquisition", "acquires", "acquired", "merger", "demerger",
    "earnings", "profit warning", "dividend", "buyback", "rights issue",
    "bonus issue", "stock split", "management change", "ceo", "cfo",
    "resigns", "restructuring", "layoffs", "hiring", "contract",
    "order win", "deal", "partnership", "investigation", "penalty",
    "lawsuit", "sebi", "rbi", "regulatory", "block deal", "bulk deal",
    "stake sale", "ipo", "delisting",
)

_TIER_1_SOURCES: frozenset[str] = frozenset({
    "reuters", "bloomberg", "financial times", "ft",
    "the economic times", "economic times", "et markets", "et telecom",
    "mint", "live mint", "livemint", "business standard", "the hindu",
    "hindu businessline", "businessline", "moneycontrol", "moneycontrol.com",
    "cnbc", "cnbc-tv18", "cnbc tv18", "business today", "forbes india",
    "the times of india", "times of india", "the indian express",
    "indian express", "the wire", "scroll.in", "the print",
    "the ken", "the morning context",
    "marketwatch", "yahoo finance", "investing.com", "seeking alpha",
    "barron's", "the wall street journal", "wsj",
})

_TIER_2_SOURCES: frozenset[str] = frozenset({
    "marketsmojo", "trendlyne", "moneyworks4me", "tickertape",
    "scanx.trade", "stockedge", "5paisa", "angel one", "angelone",
    "upstox", "zerodha", "groww", "kotak securities", "icici direct",
    "hdfc securities", "hdfc sky", "motilal oswal", "sharekhan",
    "latestly", "ad hoc", "ad-hoc",
    # Indian retail-portal publishers — legitimate but tier-2.
    "univest.in", "univest", "kalkine.co.in", "kalkine", "sahi",
})

# --- financial lexicon overlay (Stage 7, Chunk D revision) ---

# Finance-negative terms: measured weight 0.35 each, unique.
_FIN_NEG_TERMS: tuple[str, ...] = (
    "fall", "falls", "fell", "falling",
    "drop", "drops", "dropped", "dropping",
    "decline", "declines", "declined", "declining",
    "slump", "slumps", "slumped",
    "plunge", "plunges", "plunged",
    "tumble", "tumbles", "tumbled",
    "slide", "slides", "slid",
    "warning", "warns", "warned",
    "downgrade", "downgrades", "downgraded",
    "loss", "losses",
    "penalty", "fine", "fined",
    "probe", "investigation", "lawsuit", "fraud", "default",
    "miss", "misses", "missed",
    "weak", "weakness", "weakly",
    "cut", "cuts", "slashed",
    "layoff", "layoffs",
    "halt", "halts", "halted",
    "resign", "resigns", "resigned",
    "delay", "delays", "delayed",
    "concern", "concerns", "worry", "worries",
    "risk", "risks", "risky",
    "pressure", "pressured",
    "loss-making",
)

# Finance-positive terms: measured weight 0.15 each, unique.
_FIN_POS_TERMS: tuple[str, ...] = (
    "win", "wins", "won", "winning",
    "gain", "gains", "gained", "gaining",
    "rise", "rises", "rose", "rising",
    "rally", "rallies", "rallied",
    "surge", "surges", "surged",
    "jump", "jumps", "jumped",
    "record",
    "beat", "beats", "beaten",
    "upgrade", "upgrades", "upgraded",
    "buyback", "bonus", "dividend",
    "profit", "profits", "profitable",
    "growth", "grow", "grows", "grew",
    "expand", "expands", "expansion",
    "partnership", "deal", "deals", "contract", "contracts", "order",
    "approval", "approved",
    "launch", "launches", "launched",
    "strong", "strongly",
    "improve", "improves", "improved",
    "recovery", "recovered", "rebound", "rebounds",
    "outperform", "outperforms", "outperformed",
)

_FIN_NEG_WEIGHT = 0.35
_FIN_POS_WEIGHT = 0.15
_FIN_DELTA_CAP  = 0.50


# ---------------------------------------------------------------------------
# sentiment
# ---------------------------------------------------------------------------

def _count_fin_terms(text: str, terms: tuple[str, ...]) -> int:
    """Count how many unique terms from `terms` appear in `text`."""
    hits = 0
    for term in terms:
        if _word_re(term).search(text):
            hits += 1
    return hits


def analyze_sentiment(title: str, summary: str = "") -> tuple[float, str]:
    """
    Return (compound_score, label).

    Pipeline:
      1. VADER on `title + title + summary` (title weighted 2×).
      2. Financial lexicon overlay: unique finance-negative terms add
         -0.35 each; unique finance-positive terms add +0.15 each.
      3. Delta capped at ±0.5 to prevent a single term from dominating.
      4. Clamp to [-1, 1]. Threshold: >= 0.05 positive, <= -0.05 negative.
    """
    t = (title or "").strip()
    s = (summary or "").strip()
    if not t and not s:
        return 0.0, "neutral"

    text = f"{t} {t} {s}".strip()

    vader_compound = float(_vader.polarity_scores(text)["compound"])

    # Overlay uses the same text but only counts each term once (not
    # twice, even though title is duplicated above).
    overlay_text = f"{t} {s}".strip()
    pos_hits = _count_fin_terms(overlay_text, _FIN_POS_TERMS)
    neg_hits = _count_fin_terms(overlay_text, _FIN_NEG_TERMS)

    delta = (pos_hits * _FIN_POS_WEIGHT) - (neg_hits * _FIN_NEG_WEIGHT)
    if delta >  _FIN_DELTA_CAP: delta =  _FIN_DELTA_CAP
    if delta < -_FIN_DELTA_CAP: delta = -_FIN_DELTA_CAP

    compound = vader_compound + delta
    compound = max(-1.0, min(1.0, compound))
    compound = round(compound, 4)

    if compound >= 0.05:
        label = "positive"
    elif compound <= -0.05:
        label = "negative"
    else:
        label = "neutral"

    return compound, label


# ---------------------------------------------------------------------------
# relevance
# ---------------------------------------------------------------------------

def _word_re(word: str) -> re.Pattern[str]:
    """Compile (and cache) a word-boundary regex for a plain text token."""
    cached = _WORD_RE_CACHE.get(word)
    if cached is not None:
        return cached
    escaped = re.escape(word)
    pattern = re.compile(rf"(?<![A-Za-z0-9]){escaped}(?![A-Za-z0-9])", re.IGNORECASE)
    _WORD_RE_CACHE[word] = pattern
    return pattern


def _first_meaningful_word(company_name: str) -> str | None:
    """
    Pick the first non-generic word from a company name.
    Returns None if every word is too generic to be useful.
    """
    if not company_name:
        return None
    tokens = re.split(r"[\s\-]+", company_name.strip())
    for tok in tokens:
        if not tok:
            continue
        cleaned = tok.strip(".,&").lower()
        if len(cleaned) < 3:
            continue
        if cleaned in _TOO_GENERIC:
            continue
        return cleaned
    return None


def compute_relevance(
    title: str,
    summary: str,
    ticker: str,
    company_name: str,
    sector: str,
) -> float:
    """
    Return a relevance score in [0, 1].

    Combines signals in priority order. The score is the sum of matched
    signals, capped at 1.0. Articles scoring below 0.3 are typically
    dropped by the ingest pipeline.
    """
    text = f"{title or ''} {summary or ''}".strip()
    if not text:
        return 0.0

    text_lower = text.lower()
    score = 0.0

    # --- company name full phrase ---
    if company_name:
        name_norm = re.sub(r"\s+", " ", company_name).strip()
        if name_norm and name_norm.lower() in text_lower:
            score += 0.50

    # --- symbol as whole word ---
    symbol = ticker.removesuffix(".NS").removesuffix(".BO")
    if symbol and _word_re(symbol).search(text):
        score += 0.40

    # --- first meaningful name word ---
    first = _first_meaningful_word(company_name)
    if first and _word_re(first).search(text):
        score += 0.20

    # --- sector mention ---
    if sector and sector.lower() in text_lower:
        score += 0.10

    # --- financial context (small signal) ---
    if any(term in text_lower for term in _FIN_CONTEXT_TERMS):
        score += 0.05

    return round(min(score, 1.0), 4)


# ---------------------------------------------------------------------------
# importance
# ---------------------------------------------------------------------------

def _source_tier(source: str | None) -> float:
    if not source:
        return 0.10
    s = source.strip().lower()
    if s in _TIER_1_SOURCES:
        return 0.50
    if s in _TIER_2_SOURCES:
        return 0.30
    return 0.10


def _recency_component(published_at: datetime | None) -> float:
    if published_at is None:
        return 0.0
    if published_at.tzinfo is None:
        published_at = published_at.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    age_days = max(0.0, (now - published_at).total_seconds() / 86400.0)
    # Exponential decay, half-life = 30 days → up to +0.30
    return 0.30 * math.exp(-age_days / 30.0)


def _impact_component(title: str, summary: str) -> float:
    text = f"{title or ''} {summary or ''}".lower()
    matched: set[str] = set()
    for term in _IMPACT_TERMS:
        if _word_re(term).search(text):
            matched.add(term)
        if len(matched) >= 5:
            break
    return min(len(matched) * 0.08, 0.40)


def compute_importance(
    title: str,
    summary: str,
    source: str | None,
    published_at: datetime | None,
) -> float:
    """
    Return an importance score in [0, 1].

    Combines publisher reputation, recency, and market-impact keywords.
    """
    tier = _source_tier(source)
    recency = _recency_component(published_at)
    impact = _impact_component(title, summary)
    return round(min(tier + recency + impact, 1.0), 4)


__all__ = [
    "analyze_sentiment",
    "compute_relevance",
    "compute_importance",
]