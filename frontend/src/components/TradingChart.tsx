import { useEffect, useMemo, useRef, memo, Component, useState } from 'react';
import type { ErrorInfo, ReactNode } from 'react';
import type { ForexPair, ChartSignalMarker, ActivePositionOverlay, GhostTradeOverlay } from '../types';
import { getTradingViewSymbol, getTradingViewInterval } from '../config/forexPairs';
import { api } from '../lib/api';

interface TradingChartProps {
  pair: ForexPair;
  timeframe?: string;
  interval?: string;
  chartType?: 'candlestick' | 'line' | 'area';
  signals?: ChartSignalMarker[];
  tradeStyle?: 'scalp' | 'swing';
  signalTimeframe?: string;
  signalTradeStyle?: 'scalp' | 'swing' | string;
  signalMode?: 'strict' | 'actionable';
  activePosition?: ActivePositionOverlay | null;
  ghostTrade?: GhostTradeOverlay | null;
}

const BAR_DURATION_MS: Record<string, number> = {
  '1m': 60_000,
  '5m': 300_000,
  '15m': 900_000,
  '1h': 3_600_000,
  '4h': 14_400_000,
  '1d': 86_400_000,
};

interface CandlePoint {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

interface OverlayLine {
  key: string;
  label: string;
  value: number;
  lineClassName: string;
  badgeClassName: string;
  dashed?: boolean;
  stripeClassName?: string;
}

function isFinitePrice(value: number | null | undefined): value is number {
  return typeof value === 'number' && Number.isFinite(value) && value > 0;
}

function clampPercent(value: number) {
  return Math.min(Math.max(value, 0), 100);
}

function inferTradeStyle(timeframe: string): 'scalp' | 'swing' {
  return ['1m', '5m', '15m'].includes(timeframe) ? 'scalp' : 'swing';
}

function getRemainingBarCloseMs(timeframe: string, nowMs = Date.now()) {
  const durationMs = BAR_DURATION_MS[timeframe] ?? BAR_DURATION_MS['1h'];
  const elapsedMs = nowMs % durationMs;
  return elapsedMs === 0 ? durationMs : durationMs - elapsedMs;
}

function formatCountdown(remainingMs: number) {
  const totalSeconds = Math.max(0, Math.ceil(remainingMs / 1000));
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;

  if (hours > 0) {
    return `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
  }

  return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
}

function formatSignedPnl(value: number) {
  const magnitude = Math.abs(value);
  const fractionDigits = magnitude >= 1 ? 2 : magnitude >= 0.01 ? 4 : 5;
  return `${value >= 0 ? '+' : '-'}$${magnitude.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: fractionDigits })}`;
}

function getEmbeddableTradingViewSymbol(pair: ForexPair) {
  return getTradingViewSymbol(pair);
}

function getSignalFeedLabel(pair: ForexPair, timeframe: string, tradeStyle: string) {
  if (pair.symbol === 'XAU/USD') {
    return `Backend XAU/USD · ${timeframe.toUpperCase()} ${tradeStyle}`;
  }
  return `Backend ${pair.symbol} · ${timeframe.toUpperCase()} ${tradeStyle}`;
}

// TradingView widget internal layout offsets (px).
// These account for the header toolbar, OHLC legend, and time axis so
// our price-mapped overlay aligns with the chart's actual price area.
const TV_CHART_TOP_PX = 56;   // toolbar + symbol/OHLC header
const TV_CHART_BOTTOM_PX = 28; // time axis
// Approximate number of candles visible in the TradingView viewport.
// TV shows the most-recent candles that fit on screen; older candles
// scroll out of view. Using only the tail matches TV's auto-scale range.
const VISIBLE_CANDLE_ESTIMATE = 80;

function TradingChart({
  pair,
  timeframe = '1h',
  interval,
  chartType: _chartType,
  signals,
  tradeStyle,
  signalTimeframe,
  signalTradeStyle,
  signalMode = 'strict',
  activePosition,
  ghostTrade,
}: TradingChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const widgetRef = useRef<any>(null);

  // Style applied to all price-mapped overlay containers so they
  // align with the TradingView chart area (excludes header + time axis).
  const chartAreaStyle: React.CSSProperties = {
    position: 'absolute',
    top: TV_CHART_TOP_PX,
    bottom: TV_CHART_BOTTOM_PX,
    left: 0,
    right: 0,
    pointerEvents: 'none' as const,
    overflow: 'hidden',
    zIndex: 10,
  };

  const effectiveTf = interval || timeframe;
  const resolvedTradeStyle = tradeStyle ?? inferTradeStyle(effectiveTf);
  const tvSymbol = getEmbeddableTradingViewSymbol(pair);
  const tvInterval = getTradingViewInterval(effectiveTf);
  const resolvedSignalTimeframe = signalTimeframe || effectiveTf;
  const resolvedSignalTradeStyle = signalTradeStyle || resolvedTradeStyle;
  const [barCloseCountdown, setBarCloseCountdown] = useState(() =>
    formatCountdown(getRemainingBarCloseMs(effectiveTf))
  );
  const [candles, setCandles] = useState<CandlePoint[]>([]);
  const latestSignal = signals?.[0];
  const formatPrice = (value: number) => value.toFixed(
    pair.basePriceApprox < 10 ? 5 : pair.basePriceApprox < 200 ? 3 : 2
  );
  const signalTone =
    latestSignal?.direction === 'BUY'
      ? 'text-emerald-300 border-emerald-500/30 bg-emerald-500/15'
      : latestSignal?.direction === 'SELL'
        ? 'text-red-300 border-red-500/30 bg-red-500/15'
        : 'text-slate-300 border-slate-500/30 bg-slate-500/15';

  const entryZone = useMemo(() => {
    if (!latestSignal) return null;
    if (!isFinitePrice(latestSignal.entryMin) || !isFinitePrice(latestSignal.entryMax)) return null;

    const min = Math.min(latestSignal.entryMin, latestSignal.entryMax);
    const max = Math.max(latestSignal.entryMin, latestSignal.entryMax);

    if (Math.abs(max - min) < Number.EPSILON) return null;

    return {
      min,
      max,
      mid: (min + max) / 2,
    };
  }, [latestSignal]);

  const overlayLines = useMemo<OverlayLine[]>(() => {
    if (!latestSignal || latestSignal.direction === 'HOLD') return [];

    const lines: OverlayLine[] = [];

    if (isFinitePrice(latestSignal.entry)) {
      lines.push({
        key: 'entry',
        label: 'Entry',
        value: latestSignal.entry,
        lineClassName: 'border-[#4fc3f7]/60',
        badgeClassName: 'bg-[#4fc3f7] text-[#0b0e14]',
        dashed: true,
        stripeClassName: 'bg-[#4fc3f7]/70',
      });
    }

    if (isFinitePrice(latestSignal.stopLoss)) {
      lines.push({
        key: 'stop-loss',
        label: 'SL',
        value: latestSignal.stopLoss,
        lineClassName: 'border-[#ef5350]/60',
        badgeClassName: 'bg-[#ef5350] text-white',
        stripeClassName: 'bg-[#ef5350]',
      });
    }

    if (isFinitePrice(latestSignal.takeProfit1)) {
      lines.push({
        key: 'take-profit-1',
        label: 'TP1',
        value: latestSignal.takeProfit1,
        lineClassName: 'border-[#66bb6a]/60',
        badgeClassName: 'bg-[#66bb6a] text-[#0b0e14]',
        stripeClassName: 'bg-[#66bb6a]',
      });
    }

    if (isFinitePrice(latestSignal.takeProfit2)) {
      lines.push({
        key: 'take-profit-2',
        label: 'TP2',
        value: latestSignal.takeProfit2,
        lineClassName: 'border-[#66bb6a]/50',
        badgeClassName: 'bg-[#4caf50] text-[#0b0e14]',
        stripeClassName: 'bg-[#4caf50]',
      });
    }

    if (isFinitePrice(latestSignal.takeProfit3)) {
      lines.push({
        key: 'take-profit-3',
        label: 'TP3',
        value: latestSignal.takeProfit3,
        lineClassName: 'border-[#388e3c]/50',
        badgeClassName: 'bg-[#388e3c] text-white',
        stripeClassName: 'bg-[#388e3c]',
      });
    }

    return lines;
  }, [latestSignal]);

  const overlayPriceRange = useMemo(() => {
    const pricePoints: number[] = [];

    // Only use the most-recent candles that approximate what TradingView
    // actually shows on screen.  Using all 200 fetched candles includes
    // data that has scrolled out of view, producing a much wider range
    // than TradingView's auto-scaled viewport.
    const visibleCandles = candles.slice(-VISIBLE_CANDLE_ESTIMATE);
    visibleCandles.forEach((candle) => {
      if (isFinitePrice(candle.low)) pricePoints.push(candle.low);
      if (isFinitePrice(candle.high)) pricePoints.push(candle.high);
    });

    if (latestSignal) {
      [
        latestSignal.entry,
        latestSignal.entryMin,
        latestSignal.entryMax,
        latestSignal.stopLoss,
        latestSignal.takeProfit1,
        latestSignal.takeProfit2,
        latestSignal.takeProfit3,
      ].forEach((value) => {
        if (isFinitePrice(value)) pricePoints.push(value);
      });
    }

    // Include active position prices in range
    if (activePosition) {
      if (isFinitePrice(activePosition.entryPrice)) pricePoints.push(activePosition.entryPrice);
      if (isFinitePrice(activePosition.currentPrice)) pricePoints.push(activePosition.currentPrice);
      if (isFinitePrice(activePosition.stopLoss)) pricePoints.push(activePosition.stopLoss!);
      if (isFinitePrice(activePosition.takeProfit1)) pricePoints.push(activePosition.takeProfit1!);
      if (isFinitePrice(activePosition.takeProfit2)) pricePoints.push(activePosition.takeProfit2!);
      if (isFinitePrice(activePosition.takeProfit3)) pricePoints.push(activePosition.takeProfit3!);
    }

    // Include ghost trade prices in range
    if (ghostTrade) {
      if (isFinitePrice(ghostTrade.entryPrice)) pricePoints.push(ghostTrade.entryPrice);
      if (isFinitePrice(ghostTrade.exitPrice)) pricePoints.push(ghostTrade.exitPrice);
    }

    if (!pricePoints.length) return null;

    const minPrice = Math.min(...pricePoints);
    const maxPrice = Math.max(...pricePoints);
    const span = maxPrice - minPrice;
    const baseline = span > 0 ? span : Math.max(minPrice * 0.0025, 0.01);
    // TradingView uses ~5-10% padding above/below the visible range;
    // 8% closely matches the default auto-scale behaviour.
    const padding = baseline * 0.08;

    return {
      min: Math.max(0, minPrice - padding),
      max: maxPrice + padding,
    };
  }, [candles, latestSignal, activePosition, ghostTrade]);

  const getPriceOffsetPercent = (value: number) => {
    if (!overlayPriceRange) return 50;
    const range = overlayPriceRange.max - overlayPriceRange.min;
    if (range <= 0) return 50;
    return clampPercent(((overlayPriceRange.max - value) / range) * 100);
  };

  useEffect(() => {
    const updateCountdown = () => {
      setBarCloseCountdown(formatCountdown(getRemainingBarCloseMs(effectiveTf)));
    };

    updateCountdown();
    const intervalId = window.setInterval(updateCountdown, 1000);
    return () => window.clearInterval(intervalId);
  }, [effectiveTf]);

  useEffect(() => {
    let cancelled = false;

    const fetchCandles = async () => {
      try {
        const data = await api.fetchCandles(pair.symbol, effectiveTf, 200, resolvedTradeStyle);
        if (!cancelled) {
          setCandles(data.candles ?? []);
        }
      } catch {
        if (!cancelled) {
          setCandles([]);
        }
      }
    };

    void fetchCandles();
    const intervalId = window.setInterval(() => void fetchCandles(), 30_000);

    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, [effectiveTf, pair.symbol, resolvedTradeStyle]);

  useEffect(() => {
    if (!containerRef.current) return;

    // Guard against StrictMode double-invocation: if the effect cleanup
    // runs before the async script loads, `cancelled` prevents the stale
    // closure from creating a second widget.
    let cancelled = false;

    // Clear previous widget
    const container = containerRef.current;
    container.innerHTML = '';

    // Load TradingView widget script if not already loaded
    const scriptId = 'tradingview-widget-script';
    let script = document.getElementById(scriptId) as HTMLScriptElement | null;

    const createWidget = () => {
      if (cancelled) return;
      if (!containerRef.current || !(window as any).TradingView) return;

      // Create a unique container ID
      const containerId = `tv-chart-${Date.now()}`;
      const widgetContainer = document.createElement('div');
      widgetContainer.id = containerId;
      widgetContainer.style.width = '100%';
      widgetContainer.style.height = '100%';
      containerRef.current.appendChild(widgetContainer);

      widgetRef.current = new (window as any).TradingView.widget({
        container_id: containerId,
        symbol: tvSymbol,
        interval: tvInterval,
        timezone: 'Etc/UTC',
        theme: 'dark',
        style: '1', // Candlestick
        locale: 'en',
        toolbar_bg: '#0b0e14',
        enable_publishing: false,
        allow_symbol_change: false,
        hide_top_toolbar: false,
        hide_legend: false,
        save_image: false,
        autosize: true,
        backgroundColor: '#0b0e14',
        gridColor: '#161b26',
        studies_overrides: {},
        overrides: {
          'mainSeriesProperties.showCountdown': true,
          'mainSeriesProperties.candleStyle.upColor': '#26a69a',
          'mainSeriesProperties.candleStyle.downColor': '#ef5350',
          'mainSeriesProperties.candleStyle.borderUpColor': '#26a69a',
          'mainSeriesProperties.candleStyle.borderDownColor': '#ef5350',
          'mainSeriesProperties.candleStyle.wickUpColor': '#26a69a',
          'mainSeriesProperties.candleStyle.wickDownColor': '#ef5350',
          'paneProperties.background': '#0b0e14',
          'paneProperties.backgroundType': 'solid',
          'paneProperties.vertGridProperties.color': '#161b26',
          'paneProperties.horzGridProperties.color': '#161b26',
          'scalesProperties.textColor': '#5c6a7e',
          'scalesProperties.lineColor': '#161b26',
        },
        loading_screen: { backgroundColor: '#0b0e14', foregroundColor: '#4fc3f7' },
        disabled_features: [
          'use_localstorage_for_settings',
          'header_symbol_search',
          'header_compare',
        ],
        enabled_features: [
          'countdown',
          'hide_left_toolbar_by_default',
        ],
      });
    };

    if (script && (window as any).TradingView) {
      createWidget();
    } else if (!script) {
      script = document.createElement('script');
      script.id = scriptId;
      script.src = 'https://s3.tradingview.com/tv.js';
      script.async = true;
      script.onload = createWidget;
      document.head.appendChild(script);
    } else {
      // Script exists but TradingView not loaded yet — wait
      script.addEventListener('load', createWidget);
    }

    return () => {
      cancelled = true;
      if (widgetRef.current && typeof widgetRef.current.remove === 'function') {
        try { widgetRef.current.remove(); } catch {}
      }
      widgetRef.current = null;
      if (containerRef.current) {
        containerRef.current.innerHTML = '';
      }
    };
  }, [tvSymbol, tvInterval]);

  return (
    <div className="relative w-full h-full min-h-[400px]">
      <div
        ref={containerRef}
        className="w-full h-full min-h-[400px]"
        style={{ background: '#0b0e14' }}
      />
      {overlayPriceRange && latestSignal && latestSignal.direction !== 'HOLD' && (
        <div style={chartAreaStyle}>
          {/* MT5-style entry zone band */}
          {entryZone && (
            <>
              <div
                className="absolute left-0 right-0 bg-[#4fc3f7]/6 border-y border-dashed border-[#4fc3f7]/25"
                style={{
                  top: `${getPriceOffsetPercent(entryZone.max)}%`,
                  height: `${Math.max(
                    Math.abs(getPriceOffsetPercent(entryZone.min) - getPriceOffsetPercent(entryZone.max)),
                    1
                  )}%`,
                }}
              />
            </>
          )}
          {/* MT5-style price level lines with right-edge axis labels */}
          {overlayLines.map((line) => (
            <div
              key={line.key}
              className="absolute left-0 right-0 -translate-y-1/2"
              style={{ top: `${getPriceOffsetPercent(line.value)}%` }}
            >
              <div className={`w-full border-t ${line.dashed ? 'border-dashed' : 'border-dotted'} ${line.lineClassName}`} />
              {/* MT5-style axis label - small solid badge on right edge */}
              <div className="absolute right-0 top-0 -translate-y-1/2">
                <div className={`px-1.5 py-[2px] text-[9px] font-bold tabular-nums rounded-l-sm ${line.badgeClassName}`}>
                  {line.label} {formatPrice(line.value)}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
      {/* MT5-style active position P&L zone overlay */}
      {overlayPriceRange && activePosition && isFinitePrice(activePosition.entryPrice) && isFinitePrice(activePosition.currentPrice) && (
        <div style={chartAreaStyle}>
          {/* Shaded P&L zone between entry and current price */}
          {(() => {
            const entryPct = getPriceOffsetPercent(activePosition.entryPrice);
            const currentPct = getPriceOffsetPercent(activePosition.currentPrice);
            const topPct = Math.min(entryPct, currentPct);
            const heightPct = Math.max(Math.abs(currentPct - entryPct), 0.5);
            const isProfit = activePosition.unrealizedPnl >= 0;
            return (
              <div
                className={`absolute left-0 right-0 ${isProfit ? 'bg-emerald-500/8' : 'bg-red-500/8'}`}
                style={{ top: `${topPct}%`, height: `${heightPct}%` }}
              />
            );
          })()}
          {/* Entry price line with arrow marker */}
          <div
            className="absolute left-0 right-0 -translate-y-1/2"
            style={{ top: `${getPriceOffsetPercent(activePosition.entryPrice)}%` }}
          >
            <div className={`w-full border-t border-solid ${
              activePosition.side === 'long' ? 'border-[#42a5f5]/70' : 'border-[#ef5350]/70'
            }`} />
            {/* Arrow marker + label on left */}
            <div className="absolute left-1 top-0 -translate-y-1/2 flex items-center gap-1">
              <span className={`text-[8px] ${
                activePosition.side === 'long' ? 'text-[#42a5f5]' : 'text-[#ef5350]'
              }`}>{activePosition.side === 'long' ? '\u25B2' : '\u25BC'}</span>
              <span className={`px-1 py-[1px] text-[9px] font-bold tabular-nums rounded-sm ${
                activePosition.side === 'long'
                  ? 'bg-[#42a5f5] text-[#0b0e14]'
                  : 'bg-[#ef5350] text-white'
              }`}>
                {activePosition.side === 'long' ? 'BUY' : 'SELL'} {activePosition.quantity} @ {formatPrice(activePosition.entryPrice)}
              </span>
            </div>
          </div>
          {/* Current price / P&L line */}
          <div
            className="absolute left-0 right-0 -translate-y-1/2"
            style={{ top: `${getPriceOffsetPercent(activePosition.currentPrice)}%` }}
          >
            <div className={`w-full border-t border-dashed ${
              activePosition.unrealizedPnl >= 0 ? 'border-emerald-400/60' : 'border-red-400/60'
            }`} />
            <div className="absolute right-0 top-0 -translate-y-1/2">
              <div className={`px-1.5 py-[2px] text-[9px] font-bold tabular-nums rounded-l-sm ${
                activePosition.unrealizedPnl >= 0
                  ? 'bg-emerald-500 text-[#0b0e14]'
                  : 'bg-red-500 text-white'
              }`}>
                {formatSignedPnl(activePosition.unrealizedPnl)}
              </div>
            </div>
          </div>
        </div>
      )}
      {/* MT5-style ghost trade overlay (closed trade from history) */}
      {overlayPriceRange && ghostTrade && isFinitePrice(ghostTrade.entryPrice) && isFinitePrice(ghostTrade.exitPrice) && (
        <div style={{ ...chartAreaStyle, opacity: 0.5 }}>
          {/* Shaded zone */}
          {(() => {
            const entryPct = getPriceOffsetPercent(ghostTrade.entryPrice);
            const exitPct = getPriceOffsetPercent(ghostTrade.exitPrice);
            const topPct = Math.min(entryPct, exitPct);
            const heightPct = Math.max(Math.abs(exitPct - entryPct), 0.5);
            const isWin = ghostTrade.realizedPnl >= 0;
            return (
              <div
                className={`absolute left-0 right-0 ${isWin ? 'bg-emerald-500/10' : 'bg-red-500/10'} border-y border-dashed ${
                  isWin ? 'border-emerald-500/20' : 'border-red-500/20'
                }`}
                style={{ top: `${topPct}%`, height: `${heightPct}%` }}
              />
            );
          })()}
          {/* Entry line */}
          <div className="absolute left-0 right-0 -translate-y-1/2" style={{ top: `${getPriceOffsetPercent(ghostTrade.entryPrice)}%` }}>
            <div className="w-full border-t border-dashed border-[#4fc3f7]/40" />
            <div className="absolute right-0 top-0 -translate-y-1/2">
              <div className="px-1.5 py-[1px] text-[9px] font-bold tabular-nums rounded-l-sm bg-[#4fc3f7]/60 text-[#0b0e14]">
                Entry {formatPrice(ghostTrade.entryPrice)}
              </div>
            </div>
          </div>
          {/* Exit line */}
          <div className="absolute left-0 right-0 -translate-y-1/2" style={{ top: `${getPriceOffsetPercent(ghostTrade.exitPrice)}%` }}>
            <div className="w-full border-t border-dashed border-orange-400/40" />
            <div className="absolute right-0 top-0 -translate-y-1/2">
              <div className="px-1.5 py-[1px] text-[9px] font-bold tabular-nums rounded-l-sm bg-orange-400/60 text-[#0b0e14]">
                Exit {formatPrice(ghostTrade.exitPrice)} ({formatSignedPnl(ghostTrade.realizedPnl)})
              </div>
            </div>
          </div>
        </div>
      )}
      {/* MT5-style bar countdown - compact bottom-left */}
      <div className="pointer-events-none absolute bottom-2 left-2 z-20 rounded bg-[#0b0e14]/85 px-2 py-1 backdrop-blur-sm">
        <div className="flex items-center gap-1.5">
          <span className="text-[9px] font-semibold uppercase tracking-wide text-slate-500">{effectiveTf}</span>
          <span className="text-[11px] font-bold tabular-nums text-[#4fc3f7]">{barCloseCountdown}</span>
        </div>
      </div>
      {/* MT5-style compact signal badge - top-left */}
      {latestSignal && latestSignal.direction !== 'HOLD' && (
        <div className="pointer-events-none absolute top-2 left-2 z-20">
          <div className={`inline-flex items-center gap-1.5 rounded px-2 py-1 text-[10px] font-bold backdrop-blur-sm ${signalTone}`}>
            {latestSignal.direction} {latestSignal.confidence}%
            <span className="text-[9px] font-normal opacity-60">{latestSignal.status.replace(/_/g, ' ')}</span>
          </div>
        </div>
      )}
      <div className="pointer-events-none absolute bottom-2 right-2 z-20 max-w-[70%] rounded bg-[#0b0e14]/85 px-2 py-1 text-right text-[9px] text-slate-400 backdrop-blur-sm">
        <div>
          Chart feed: <span className="text-slate-200">{tvSymbol}</span>
        </div>
        <div>
          Signal feed: <span className="text-slate-200">{getSignalFeedLabel(pair, resolvedSignalTimeframe, resolvedSignalTradeStyle)}</span>
          {signalMode === 'actionable' && <span className="text-amber-300"> · actionable</span>}
        </div>
      </div>
      {/* MT5-style active trade status badge - top-right */}
      {activePosition && (
        <div className="pointer-events-none absolute top-2 right-2 z-20">
          <div className={`inline-flex items-center gap-1.5 rounded px-2 py-1 text-[10px] font-bold backdrop-blur-sm border ${
            activePosition.unrealizedPnl >= 0
              ? 'bg-emerald-500/15 border-emerald-500/30 text-emerald-300'
              : 'bg-red-500/15 border-red-500/30 text-red-300'
          }`}>
            {activePosition.side === 'long' ? 'LONG' : 'SHORT'} {formatSignedPnl(activePosition.unrealizedPnl)}
          </div>
        </div>
      )}
      {/* Ghost trade badge - top-right */}
      {!activePosition && ghostTrade && (
        <div className="pointer-events-none absolute top-2 right-2 z-20">
          <div className={`inline-flex items-center gap-1.5 rounded px-2 py-1 text-[10px] font-bold backdrop-blur-sm border opacity-60 ${
            ghostTrade.realizedPnl >= 0
              ? 'bg-emerald-500/15 border-emerald-500/30 text-emerald-300'
              : 'bg-red-500/15 border-red-500/30 text-red-300'
          }`}>
            CLOSED {formatSignedPnl(ghostTrade.realizedPnl)}
          </div>
        </div>
      )}
      {/* Entry zone pulse animation for OPTIMAL_ENTRY */}
      {latestSignal?.status === 'OPTIMAL_ENTRY' && entryZone && overlayPriceRange && (
        <div style={chartAreaStyle}>
          <div
            className="absolute left-0 right-0 animate-pulse"
            style={{
              top: `${getPriceOffsetPercent(entryZone.max)}%`,
              height: `${Math.max(
                Math.abs(getPriceOffsetPercent(entryZone.min) - getPriceOffsetPercent(entryZone.max)),
                1
              )}%`,
              background: 'linear-gradient(90deg, transparent, rgba(79,195,247,0.12), transparent)',
            }}
          />
        </div>
      )}
    </div>
  );
}

export default memo(TradingChart);
// Named export for compatibility
export { TradingChart };

class ChartErrorBoundary extends Component<
  { children: ReactNode; onRetry?: () => void },
  { hasError: boolean; error: Error | null }
> {
  constructor(props: any) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error: Error) {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('Chart error:', error, errorInfo)
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="w-full h-full min-h-[400px] flex items-center justify-center bg-slate-900 rounded-lg">
          <div className="text-center">
            <p className="text-slate-400 mb-2">Chart unavailable</p>
            <button
              onClick={() => this.setState({ hasError: false, error: null })}
              className="px-4 py-2 bg-trading-accent text-white rounded-lg text-sm hover:bg-blue-600 transition-colors"
            >
              Click to retry
            </button>
          </div>
        </div>
      )
    }
    return this.props.children
  }
}

export { ChartErrorBoundary };
