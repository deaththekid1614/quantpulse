import { useEffect, useRef } from "react";
import {
  createChart,
  CrosshairMode,
  LineStyle,
} from "lightweight-charts";

import { usePrices } from "../api/hooks.js";

// Design tokens matched to the Tailwind palette in tailwind.config.js.
const THEME = {
  background: "#111418", // ink-800
  grid:       "#181c22", // ink-700
  border:     "#232830", // ink-600
  text:       "#9ca3af", // ink-300
  up:         "#10b981", // accent-up
  down:       "#ef4444", // accent-down
};

const CHART_HEIGHT = 380;

export default function PriceChart({ ticker, range = "1y" }) {
  const containerRef = useRef(null);
  const chartRef     = useRef(null);
  const seriesRef    = useRef(null);

  const { data, isLoading, error } = usePrices(ticker, range);

  // Create the chart exactly once per mount.
  useEffect(() => {
    if (!containerRef.current) return;

    const chart = createChart(containerRef.current, {
      width: containerRef.current.clientWidth,
      height: CHART_HEIGHT,
      layout: {
        background: { type: "solid", color: THEME.background },
        textColor: THEME.text,
        fontFamily:
          "Inter, system-ui, -apple-system, 'Segoe UI', sans-serif",
      },
      grid: {
        vertLines: { color: THEME.grid },
        horzLines: { color: THEME.grid },
      },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: { color: THEME.border, style: LineStyle.Dashed },
        horzLine: { color: THEME.border, style: LineStyle.Dashed },
      },
      rightPriceScale: {
        borderColor: THEME.border,
        scaleMargins: { top: 0.1, bottom: 0.1 },
      },
      timeScale: {
        borderColor: THEME.border,
        timeVisible: false,
        secondsVisible: false,
      },
    });

    const series = chart.addCandlestickSeries({
      upColor: THEME.up,
      downColor: THEME.down,
      borderVisible: false,
      wickUpColor: THEME.up,
      wickDownColor: THEME.down,
      priceFormat: { type: "price", precision: 2, minMove: 0.01 },
    });

    chartRef.current  = chart;
    seriesRef.current = series;

    // Auto-fit width on container resize.
    const ro = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (!entry || !chartRef.current) return;
      const w = Math.floor(entry.contentRect.width);
      if (w > 0) chartRef.current.applyOptions({ width: w });
    });
    ro.observe(containerRef.current);

    return () => {
      ro.disconnect();
      chart.remove();
      chartRef.current  = null;
      seriesRef.current = null;
    };
  }, []);

  // Push data whenever the query result changes.
  useEffect(() => {
    if (!seriesRef.current) return;
    if (!data || !Array.isArray(data.data)) {
      seriesRef.current.setData([]);
      return;
    }
    const bars = data.data.map((b) => ({
      time:  b.date,       // 'YYYY-MM-DD' is accepted directly by lightweight-charts
      open:  b.open,
      high:  b.high,
      low:   b.low,
      close: b.close,
    }));
    seriesRef.current.setData(bars);
    chartRef.current?.timeScale().fitContent();
  }, [data]);

  return (
    <div className="relative rounded-lg bg-ink-800 border border-ink-700 overflow-hidden">
      {(isLoading || error) && (
        <div className="absolute inset-0 z-10 flex items-center justify-center bg-ink-800/80 text-sm text-ink-400">
          {error ? `Failed to load chart: ${error.message}` : "Loading chart…"}
        </div>
      )}
      <div ref={containerRef} style={{ height: CHART_HEIGHT }} />
    </div>
  );
}
