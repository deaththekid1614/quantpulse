/**
 * Rule-based performance narrative.
 *
 * Pure function. Same inputs → same text. No randomness, no time, no
 * external state. Reads five features from a `/snapshot` response and
 * produces three sentences of plain English.
 *
 * Returns null if any required feature is missing or non-finite — the
 * caller decides how to display the fallback.
 */

const REQUIRED = [
  "px_over_sma_50",
  "px_over_sma_200",
  "rsi_14",
  "ret_20d",
  "vol_20d",
];

function momentumLabel(rsi) {
  if (rsi >= 70) return "strong";
  if (rsi >= 55) return "positive";
  if (rsi >= 45) return "neutral";
  if (rsi >= 30) return "weak";
  return "very weak";
}

function volatilityLabel(annualVol) {
  if (annualVol < 0.18) return "low";
  if (annualVol < 0.30) return "moderate";
  if (annualVol < 0.45) return "elevated";
  return "high";
}

export function buildNarrative(symbol, features) {
  if (!features || typeof features !== "object") return null;

  for (const k of REQUIRED) {
    const v = features[k];
    if (typeof v !== "number" || !Number.isFinite(v)) return null;
  }

  const f = features;
  const sentences = [];

  // --- sentence 1: trend, from price vs SMAs ---
  const vs200 = f.px_over_sma_200;
  const vs50 = f.px_over_sma_50;

  if (vs200 > 1.02 && vs50 > 1.02) {
    sentences.push(
      `${symbol} is trading above both its medium- and long-term averages, ` +
        `consistent with an uptrend.`,
    );
  } else if (vs200 < 0.98 && vs50 < 0.98) {
    sentences.push(
      `${symbol} is trading below both its medium- and long-term averages, ` +
        `consistent with a downtrend.`,
    );
  } else if (vs200 > 1.02) {
    sentences.push(
      `${symbol} is above its long-term average, but has slipped below its ` +
        `medium-term average.`,
    );
  } else if (vs200 < 0.98) {
    sentences.push(
      `${symbol} is below its long-term average, though recent trading has ` +
        `held up better than the longer trend.`,
    );
  } else {
    sentences.push(
      `${symbol} is trading close to its long-term average, with no clear ` +
        `directional trend.`,
    );
  }

  // --- sentence 2: momentum + 20-day performance ---
  const mom = momentumLabel(f.rsi_14);
  // ret_20d is a log return. Convert to simple percent for display.
  const ret20Pct = (Math.exp(f.ret_20d) - 1) * 100;
  const abs20 = Math.abs(ret20Pct);

  if (abs20 < 1.0) {
    sentences.push(
      `Momentum is ${mom}, and the stock has been roughly flat over the ` +
        `past month.`,
    );
  } else {
    const verb = ret20Pct >= 0 ? "gained" : "lost";
    sentences.push(
      `Momentum is ${mom}, and the stock has ${verb} ${abs20.toFixed(1)}% ` +
        `over the past month.`,
    );
  }

  // --- sentence 3: volatility ---
  // vol_20d is the daily standard deviation of log returns.
  // Annualised ≈ daily × sqrt(252). Daily % is more intuitive for readers.
  const annualVol = f.vol_20d * Math.sqrt(252);
  const volLabel = volatilityLabel(annualVol);
  const dailyPct = (f.vol_20d * 100).toFixed(2);

  sentences.push(
    `Recent volatility has been ${volLabel}, with daily moves averaging ` +
      `around ${dailyPct}%.`,
  );

  return sentences.join(" ");
}
