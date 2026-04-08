import { useEffect, useRef, useCallback } from 'react';
import {
  createChart,
  ColorType,
  CrosshairMode,
  CandlestickSeries,
  HistogramSeries,
  createSeriesMarkers,
  type IChartApi,
  type ISeriesApi,
  type CandlestickData,
  type HistogramData,
  type Time,
  type IPriceLine,
  type SeriesMarker,
  type ISeriesMarkersPluginApi,
} from 'lightweight-charts';
import type { ForexPair, ChartSignalMarker, SignalStatus } from '../types';

// ── Props ────────────────────────────────────────────────────────────────────
interface TradingChartProps {
  pair: ForexPair;
  /** Legacy prop used by Dashboard / ChartToolbar (values like '1m','5m','1H','4H','1D') */
  timeframe?: string;
  /** Alternative interval prop ('1','5','15','60','240','D') */
  interval?: string;
  /** Chart rendering type – kept for future compatibility */
  chartType?: 'candlestick' | 'line' | 'area';
  /** Signal markers to visualise on the chart */
  signals?: ChartSignalMarker[];
}

// ── Helpers ──────────────────────────────────────────────────────────────────

/** Normalise any timeframe/interval string coming from the toolbar or parent
 *  into the API query-param format the backend expects (e.g. '1m','5m','1h','4h','1d'). */
function toApiTimeframe(raw: string): string {
  const map: Record<string, string> = {
    // interval-style values
    '1': '1m',
    '5': '5m',
    '15': '15m',
    '60': '1h',
    '240': '4h',
    'D': '1d',
    // toolbar-style values (case-insensitive handled below)
    '1m': '1m',
    '5m': '5m',
    '15m': '15m',
    '30m': '30m',
    '1h': '1h',
    '1H': '1h',
    '2h': '2h',
    '4h': '4h',
    '4H': '4h',
    '1d': '1d',
    '1D': '1d',
  };
  return map[raw] ?? map[raw.toLowerCase()] ?? '1h';
}

/** Convert pair symbol ("EUR/USD") to the slug the API expects ("EURUSD"). */
function toApiSymbol(pair: ForexPair): string {
  return pair.symbol.replace('/', '');
}

/** Map SignalStatus → colour */
function statusColor(s: SignalStatus): string {
  switch (s) {
    case 'OPTIMAL_ENTRY':
      return '#22c55e';
    case 'VALID':
      return '#3b82f6';
    case 'ABOUT_TO_EXPIRE':
      return '#f59e0b';
    case 'EXPIRED':
      return '#6b7280';
    default:
      return '#94a3b8';
  }
}

// ── Component ────────────────────────────────────────────────────────────────

export function TradingChart({
  pair,
  timeframe = '1h',
  interval,
  chartType: _chartType,
  signals,
}: TradingChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const volumeSeriesRef = useRef<ISeriesApi<'Histogram'> | null>(null);
  const priceLinesRef = useRef<IPriceLine[]>([]);
  const candleDataRef = useRef<CandlestickData<Time>[]>([]);
  const markersPluginRef = useRef<ISeriesMarkersPluginApi<Time> | null>(null);

  // Resolve the effective timeframe – prefer `interval` if supplied
  const effectiveTf = interval ? interval : timeframe;

  // ── 1. Chart creation & resize ──────────────────────────────────────────
  useEffect(() => {
    if (!containerRef.current) return;

    const container = containerRef.current;

    const chart = createChart(container, {
      width: container.clientWidth,
      height: container.clientHeight,
      layout: {
        background: { type: ColorType.Solid, color: '#0f172a' },
        textColor: '#94a3b8',
      },
      grid: {
        vertLines: { color: '#1e293b' },
        horzLines: { color: '#1e293b' },
      },
      crosshair: { mode: CrosshairMode.Normal },
      timeScale: {
        timeVisible: true,
        secondsVisible: false,
        borderColor: '#1e293b',
      },
      rightPriceScale: { borderColor: '#1e293b' },
    });

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: '#22c55e',
      downColor: '#ef4444',
      borderUpColor: '#22c55e',
      borderDownColor: '#ef4444',
      wickUpColor: '#22c55e',
      wickDownColor: '#ef4444',
    });

    const volumeSeries = chart.addSeries(HistogramSeries, {
      priceScaleId: 'volume',
      priceFormat: { type: 'volume' },
    });

    // Push the volume pane to the bottom and keep it small
    chart.priceScale('volume').applyOptions({
      scaleMargins: { top: 0.85, bottom: 0 },
    });

    chartRef.current = chart;
    candleSeriesRef.current = candleSeries;
    volumeSeriesRef.current = volumeSeries;

    // Create markers plugin for signal visualisation
    const markersPlugin = createSeriesMarkers(candleSeries, []);
    markersPluginRef.current = markersPlugin;

    // Resize observer
    const ro = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const { width, height } = entry.contentRect;
        chart.applyOptions({ width, height });
      }
    });
    ro.observe(container);

    return () => {
      ro.disconnect();
      if (markersPluginRef.current) {
        markersPluginRef.current.detach();
        markersPluginRef.current = null;
      }
      chart.remove();
      chartRef.current = null;
      candleSeriesRef.current = null;
      volumeSeriesRef.current = null;
      priceLinesRef.current = [];
      candleDataRef.current = [];
    };
  }, []); // chart created once

  // ── 2. Data fetching ────────────────────────────────────────────────────
  useEffect(() => {
    const chart = chartRef.current;
    const candleSeries = candleSeriesRef.current;
    const volumeSeries = volumeSeriesRef.current;
    if (!chart || !candleSeries || !volumeSeries) return;

    let cancelled = false;

    const fetchCandles = async () => {
      const tf = toApiTimeframe(effectiveTf);
      const sym = toApiSymbol(pair);

      try {
        const res = await fetch(
          `/api/market/candles/${encodeURIComponent(sym)}?timeframe=${tf}&limit=300`,
        );
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data: { time: number; open: number; high: number; low: number; close: number; volume: number }[] =
          await res.json();

        if (cancelled || !data?.length) return;

        const candles: CandlestickData<Time>[] = data.map((c) => ({
          time: c.time as Time,
          open: c.open,
          high: c.high,
          low: c.low,
          close: c.close,
        }));

        const volumes: HistogramData<Time>[] = data.map((c) => ({
          time: c.time as Time,
          value: c.volume,
          color: c.close >= c.open ? 'rgba(34,197,94,0.35)' : 'rgba(239,68,68,0.35)',
        }));

        candleSeries.setData(candles);
        volumeSeries.setData(volumes);
        candleDataRef.current = candles;
        chart.timeScale().fitContent();
      } catch (err) {
        console.error('[TradingChart] Failed to fetch candles:', err);
      }
    };

    fetchCandles();

    return () => {
      cancelled = true;
    };
  }, [pair, effectiveTf]);

  // ── 3. Signal visualisation ─────────────────────────────────────────────

  /** Remove all existing price lines safely */
  const clearPriceLines = useCallback(() => {
    const series = candleSeriesRef.current;
    if (!series) return;
    for (const pl of priceLinesRef.current) {
      try {
        series.removePriceLine(pl);
      } catch {
        // already removed
      }
    }
    priceLinesRef.current = [];
  }, []);

  useEffect(() => {
    const candleSeries = candleSeriesRef.current;
    const markersPlugin = markersPluginRef.current;
    if (!candleSeries || !markersPlugin) return;

    // Always clean up previous price lines & markers before drawing new ones
    clearPriceLines();

    if (!signals || signals.length === 0) {
      markersPlugin.setMarkers([]);
      return;
    }

    const candles = candleDataRef.current;

    // Helper: find the candle time closest to a given ISO timestamp
    const closestTime = (iso: string): Time | null => {
      if (!candles.length) return null;
      const ts = Math.floor(new Date(iso).getTime() / 1000);
      let best = candles[0].time;
      let bestDiff = Math.abs((best as number) - ts);
      for (const c of candles) {
        const diff = Math.abs((c.time as number) - ts);
        if (diff < bestDiff) {
          bestDiff = diff;
          best = c.time;
        }
      }
      return best;
    };

    // ── Markers ───────────────────────────────────────────────────────────
    const markers: SeriesMarker<Time>[] = [];

    for (const sig of signals) {
      const t = closestTime(sig.timestamp);
      if (!t) continue;

      const isBuy = sig.direction === 'BUY';
      markers.push({
        time: t,
        position: isBuy ? 'belowBar' : 'aboveBar',
        color: statusColor(sig.status),
        shape: isBuy ? 'arrowUp' : 'arrowDown',
        text: `${sig.direction} ${sig.confidence}%`,
      });
    }

    // lightweight-charts requires markers sorted ascending by time
    markers.sort((a, b) => (a.time as number) - (b.time as number));
    markersPlugin.setMarkers(markers);

    // ── Price lines for the most recent non-expired signal ─────────────
    const activeSignal = [...signals]
      .filter((s) => s.status !== 'EXPIRED')
      .sort(
        (a, b) =>
          new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime(),
      )[0];

    if (activeSignal) {
      const lineDefaults = {
        lineWidth: 1 as const,
        lineStyle: 2 as const, // Dashed
        axisLabelVisible: true,
      };

      const lines: { price: number; color: string; title: string }[] = [
        { price: activeSignal.stopLoss, color: '#ef4444', title: 'SL' },
        { price: activeSignal.entry, color: '#3b82f6', title: 'Entry' },
        { price: activeSignal.takeProfit1, color: '#22c55e', title: 'TP1' },
        { price: activeSignal.takeProfit2, color: '#16a34a', title: 'TP2' },
        { price: activeSignal.takeProfit3, color: '#15803d', title: 'TP3' },
      ];

      for (const l of lines) {
        const pl = candleSeries.createPriceLine({
          price: l.price,
          color: l.color,
          title: l.title,
          ...lineDefaults,
        });
        priceLinesRef.current.push(pl);
      }
    }

    // Cleanup on signals change
    return () => {
      clearPriceLines();
      markersPlugin.setMarkers([]);
    };
  }, [signals, clearPriceLines]);

  // ── JSX ─────────────────────────────────────────────────────────────────
  return (
    <div
      ref={containerRef}
      className="w-full h-full min-h-[400px]"
      style={{ background: '#0f172a' }}
    />
  );
}

export default TradingChart;
