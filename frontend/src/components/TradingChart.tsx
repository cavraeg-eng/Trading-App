import { useCallback, useEffect, useMemo, useRef, memo, Component, useState } from 'react';
import type { ErrorInfo, ReactNode } from 'react';
import {
  CandlestickSeries,
  ColorType,
  CrosshairMode,
  LineStyle,
  createChart,
} from 'lightweight-charts';
import type {
  CandlestickData,
  IChartApi,
  IPriceLine,
  ISeriesApi,
  UTCTimestamp,
} from 'lightweight-charts';
import type {
  ForexPair,
  ChartSignalMarker,
  ActivePositionOverlay,
  GhostTradeOverlay,
  TradeLevelOverlayKind,
  TradeLevelOverlayStatus,
} from '../types';
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

const EMPTY_TRADE_LEVELS: ChartSignalMarker[] = [];

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

type PriceLineSpec = {
  key: string;
  price: number;
  color: string;
  title: string;
  style?: LineStyle;
  width?: 1 | 2 | 3 | 4;
};

type LiveCandle = CandlestickData<UTCTimestamp>;

interface OverlayLine {
  key: string;
  label: string;
  value: number;
  kind: TradeLevelOverlayKind;
  status: TradeLevelOverlayStatus;
  lineClassName: string;
  badgeClassName: string;
  dashed?: boolean;
  stripeClassName?: string;
  opacityClassName?: string;
}

function isFinitePrice(value: number | null | undefined): value is number {
  return typeof value === 'number' && Number.isFinite(value) && value > 0;
}

function clampPercent(value: number) {
  return Math.min(Math.max(value, 0), 100);
}

function getSignalSetupStatus(signal: ChartSignalMarker): TradeLevelOverlayStatus {
  if (signal.setupStatus) return signal.setupStatus;
  if (signal.status === 'EXPIRED') return 'closed';
  return 'pending';
}

function getOverlayStatusClasses(status: TradeLevelOverlayStatus) {
  if (status === 'active') {
    return {
      dashed: false,
      opacityClassName: 'opacity-100',
      suffixClassName: 'bg-emerald-500/15 text-emerald-200 border border-emerald-400/20',
    };
  }

  if (status === 'closed') {
    return {
      dashed: true,
      opacityClassName: 'opacity-45',
      suffixClassName: 'bg-slate-500/15 text-slate-300 border border-slate-400/15',
    };
  }

  return {
    dashed: true,
    opacityClassName: 'opacity-70',
    suffixClassName: 'bg-amber-500/15 text-amber-200 border border-amber-400/20',
  };
}

function getOverlayLineClasses(kind: TradeLevelOverlayKind, status: TradeLevelOverlayStatus) {
  const statusClasses = getOverlayStatusClasses(status);
  const classesByKind = {
    entry: {
      lineClassName: 'border-[#4fc3f7]/65',
      badgeClassName: 'bg-[#4fc3f7] text-[#0b0e14]',
      stripeClassName: 'bg-[#4fc3f7]/70',
    },
    stop_loss: {
      lineClassName: 'border-[#ef5350]/70',
      badgeClassName: 'bg-[#ef5350] text-white',
      stripeClassName: 'bg-[#ef5350]',
    },
    take_profit: {
      lineClassName: 'border-[#66bb6a]/70',
      badgeClassName: 'bg-[#66bb6a] text-[#0b0e14]',
      stripeClassName: 'bg-[#66bb6a]',
    },
    current: {
      lineClassName: 'border-slate-300/60',
      badgeClassName: 'bg-slate-300 text-[#0b0e14]',
      stripeClassName: 'bg-slate-300',
    },
    exit: {
      lineClassName: 'border-orange-400/60',
      badgeClassName: 'bg-orange-400 text-[#0b0e14]',
      stripeClassName: 'bg-orange-400',
    },
  } satisfies Record<TradeLevelOverlayKind, {
    lineClassName: string;
    badgeClassName: string;
    stripeClassName: string;
  }>;

  return {
    ...classesByKind[kind],
    dashed: statusClasses.dashed,
    opacityClassName: statusClasses.opacityClassName,
  };
}

function renderTradeLevelLine(
  key: string,
  kind: TradeLevelOverlayKind,
  status: TradeLevelOverlayStatus,
  label: string,
  value: number,
  formatPrice: (value: number) => string,
  getPriceOffsetPercent: (value: number) => number,
  labelPosition: 'left' | 'right' = 'right'
) {
  const style = getOverlayLineClasses(kind, status);
  const statusStyle = getOverlayStatusClasses(status);
  const labelPlacement = labelPosition === 'left'
    ? 'left-1 rounded-sm'
    : 'right-0 rounded-l-sm';

  return (
    <div
      key={key}
      className={`absolute left-0 right-0 -translate-y-1/2 ${style.opacityClassName}`}
      style={{ top: `${getPriceOffsetPercent(value)}%` }}
    >
      <div className={`w-full border-t ${style.dashed ? 'border-dashed' : 'border-solid'} ${style.lineClassName}`} />
      <div className={`absolute top-0 -translate-y-1/2 ${labelPlacement}`}>
        <div className="flex items-center">
          {labelPosition === 'right' && (
            <span className={`mr-1 hidden rounded px-1 py-[1px] text-[8px] font-bold uppercase tracking-wide sm:inline ${statusStyle.suffixClassName}`}>
              {status}
            </span>
          )}
          <div className={`px-1.5 py-[2px] text-[9px] font-bold tabular-nums ${labelPlacement} ${style.badgeClassName}`}>
            {label} {formatPrice(value)}
          </div>
          {labelPosition === 'left' && (
            <span className={`ml-1 hidden rounded px-1 py-[1px] text-[8px] font-bold uppercase tracking-wide sm:inline ${statusStyle.suffixClassName}`}>
              {status}
            </span>
          )}
        </div>
      </div>
    </div>
  );
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

function getSignalFeedLabel(pair: ForexPair, timeframe: string, tradeStyle: string) {
  if (pair.symbol === 'XAU/USD') {
    return `Backend XAU/USD · ${timeframe.toUpperCase()} ${tradeStyle}`;
  }
  return `Backend ${pair.symbol} · ${timeframe.toUpperCase()} ${tradeStyle}`;
}

function getPricePrecision(pair: ForexPair) {
  if (pair.basePriceApprox < 10) return 5;
  if (pair.basePriceApprox < 200) return 3;
  return 2;
}

function toChartCandle(candle: CandlePoint): LiveCandle {
  return {
    time: Math.floor(candle.time) as UTCTimestamp,
    open: candle.open,
    high: candle.high,
    low: candle.low,
    close: candle.close,
  };
}

function normalizeCandles(candles: CandlePoint[]) {
  return [...candles]
    .filter((candle) =>
      Number.isFinite(candle.time)
      && isFinitePrice(candle.open)
      && isFinitePrice(candle.high)
      && isFinitePrice(candle.low)
      && isFinitePrice(candle.close)
    )
    .sort((a, b) => a.time - b.time)
    .filter((candle, index, sorted) => index === sorted.length - 1 || candle.time !== sorted[index + 1].time);
}

function getBarStartSeconds(timeframe: string, nowMs = Date.now()) {
  const durationSeconds = Math.floor((BAR_DURATION_MS[timeframe] ?? BAR_DURATION_MS['1h']) / 1000);
  const nowSeconds = Math.floor(nowMs / 1000);
  return nowSeconds - (nowSeconds % durationSeconds);
}

function getPriceTitle(label: string, price: number | null | undefined, formatPrice: (value: number) => string) {
  return isFinitePrice(price) ? `${label} ${formatPrice(price)}` : label;
}

function upsertLiveQuote(candles: CandlePoint[], price: number, timeframe: string) {
  if (!isFinitePrice(price)) return candles;
  const barTime = getBarStartSeconds(timeframe);
  const previous = candles[candles.length - 1];

  if (!previous || previous.time < barTime) {
    return [
      ...candles,
      {
        time: barTime,
        open: previous?.close ?? price,
        high: price,
        low: price,
        close: price,
        volume: 0,
      },
    ].slice(-240);
  }

  if (previous.time > barTime) return candles;

  const updated = {
    ...previous,
    high: Math.max(previous.high, price),
    low: Math.min(previous.low, price),
    close: price,
  };
  return [...candles.slice(0, -1), updated];
}

function getAxisLabelTextColor(color: string) {
  return color === '#4fc3f7' || color === '#66bb6a' || color === '#34d399'
    ? '#0b0e14'
    : '#ffffff';
}

function syncPriceLines(
  series: ISeriesApi<'Candlestick'>,
  existingLines: Map<string, IPriceLine>,
  priceLineSpecs: PriceLineSpec[]
) {
  const nextKeys = new Set(priceLineSpecs.map((spec) => spec.key));

  existingLines.forEach((line, key) => {
    if (!nextKeys.has(key)) {
      series.removePriceLine(line);
      existingLines.delete(key);
    }
  });

  priceLineSpecs.forEach((spec) => {
    const options = {
      price: spec.price,
      color: spec.color,
      lineWidth: spec.width ?? 1,
      lineStyle: spec.style ?? LineStyle.Solid,
      title: spec.title,
      axisLabelVisible: true,
      axisLabelColor: spec.color,
      axisLabelTextColor: getAxisLabelTextColor(spec.color),
    };
    const current = existingLines.get(spec.key);
    if (current) {
      current.applyOptions(options);
      return;
    }

    existingLines.set(spec.key, series.createPriceLine({
      ...options,
      lineVisible: true,
    }));
  });
}

const CHART_AREA_TOP_PX = 0;
const CHART_AREA_BOTTOM_PX = 24;
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
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const priceLineRefs = useRef<Map<string, IPriceLine>>(new Map());
  const autoScrollRef = useRef(true);
  const chartCandlesRef = useRef<CandlePoint[]>([]);
  const safeSignals = signals ?? EMPTY_TRADE_LEVELS;

  const chartAreaStyle: React.CSSProperties = {
    position: 'absolute',
    top: CHART_AREA_TOP_PX,
    bottom: CHART_AREA_BOTTOM_PX,
    left: 0,
    right: 0,
    pointerEvents: 'none' as const,
    overflow: 'hidden',
    zIndex: 10,
  };

  const effectiveTf = interval || timeframe;
  const resolvedTradeStyle = tradeStyle ?? inferTradeStyle(effectiveTf);
  const resolvedSignalTimeframe = signalTimeframe || effectiveTf;
  const resolvedSignalTradeStyle = signalTradeStyle || resolvedTradeStyle;
  const [barCloseCountdown, setBarCloseCountdown] = useState(() =>
    formatCountdown(getRemainingBarCloseMs(effectiveTf))
  );
  const [candles, setCandles] = useState<CandlePoint[]>([]);
  const latestSignal = safeSignals[0];
  const pricePrecision = getPricePrecision(pair);
  const formatPrice = (value: number) => value.toFixed(pricePrecision);
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

    const setupStatus = getSignalSetupStatus(latestSignal);
    const lines: OverlayLine[] = [];

    if (isFinitePrice(latestSignal.entry)) {
      const style = getOverlayLineClasses('entry', setupStatus);
      lines.push({
        key: 'entry',
        label: 'Entry',
        value: latestSignal.entry,
        kind: 'entry',
        status: setupStatus,
        ...style,
      });
    }

    if (isFinitePrice(latestSignal.stopLoss)) {
      const style = getOverlayLineClasses('stop_loss', setupStatus);
      lines.push({
        key: 'stop-loss',
        label: 'SL',
        value: latestSignal.stopLoss,
        kind: 'stop_loss',
        status: setupStatus,
        ...style,
      });
    }

    [
      latestSignal.takeProfit1,
      latestSignal.takeProfit2,
      latestSignal.takeProfit3,
    ].forEach((price, index) => {
      if (!isFinitePrice(price)) return;
      const targetIndex = index + 1;
      const style = getOverlayLineClasses('take_profit', setupStatus);
      lines.push({
        key: `take-profit-${targetIndex}`,
        label: `TP${targetIndex}`,
        value: price,
        kind: 'take_profit',
        status: setupStatus,
        ...style,
      });
    });

    return lines;
  }, [latestSignal]);

  const activeLevelLines = useMemo<OverlayLine[]>(() => {
    if (!activePosition) return [];
    const latestSignalStatus = latestSignal ? getSignalSetupStatus(latestSignal) : null;
    if (latestSignalStatus === 'active' || latestSignalStatus === 'pending') return [];
    const status = activePosition.status ?? 'active';
    const lines: OverlayLine[] = [];

    if (isFinitePrice(activePosition.stopLoss)) {
      lines.push({
        key: 'active-stop-loss',
        label: 'SL',
        value: activePosition.stopLoss,
        kind: 'stop_loss',
        status,
        ...getOverlayLineClasses('stop_loss', status),
      });
    }

    [
      activePosition.takeProfit1,
      activePosition.takeProfit2,
      activePosition.takeProfit3,
    ].forEach((price, index) => {
      if (!isFinitePrice(price)) return;
      const targetIndex = index + 1;
      lines.push({
        key: `active-take-profit-${targetIndex}`,
        label: `TP${targetIndex}`,
        value: price,
        kind: 'take_profit',
        status,
        ...getOverlayLineClasses('take_profit', status),
      });
    });

    return lines;
  }, [activePosition, latestSignal?.setupStatus, latestSignal?.status]);

  const priceLineSpecs = useMemo<PriceLineSpec[]>(() => {
    const specs: PriceLineSpec[] = [];
    const addSpec = (
      key: string,
      price: number | null | undefined,
      title: string,
      color: string,
      style: LineStyle = LineStyle.Solid,
      width: 1 | 2 | 3 | 4 = 1
    ) => {
      if (!isFinitePrice(price)) return;
      specs.push({ key, price, title, color, style, width });
    };

    overlayLines.forEach((line) => {
      const color = line.kind === 'entry'
        ? '#4fc3f7'
        : line.kind === 'stop_loss'
          ? '#ef5350'
          : '#66bb6a';
      addSpec(line.key, line.value, `${line.label} ${formatPrice(line.value)}`, color, line.dashed ? LineStyle.Dashed : LineStyle.Solid);
    });

    activeLevelLines.forEach((line) => {
      const color = line.kind === 'stop_loss' ? '#ef5350' : '#66bb6a';
      addSpec(line.key, line.value, `${line.label} ${formatPrice(line.value)}`, color, line.dashed ? LineStyle.Dashed : LineStyle.Solid);
    });

    if (activePosition) {
      addSpec(
        'active-entry',
        activePosition.entryPrice,
        `${activePosition.side === 'long' ? 'BUY' : 'SELL'} ${formatPrice(activePosition.entryPrice)}`,
        activePosition.side === 'long' ? '#42a5f5' : '#ef5350',
        LineStyle.Solid,
        2
      );
      addSpec(
        'active-current',
        activePosition.currentPrice,
        formatSignedPnl(activePosition.unrealizedPnl),
        activePosition.unrealizedPnl >= 0 ? '#34d399' : '#ef4444',
        LineStyle.Dashed
      );
    }

    if (!activePosition && ghostTrade) {
      addSpec('ghost-entry', ghostTrade.entryPrice, `Entry ${formatPrice(ghostTrade.entryPrice)}`, '#4fc3f7', LineStyle.Dashed);
      addSpec('ghost-exit', ghostTrade.exitPrice, `Exit ${formatSignedPnl(ghostTrade.realizedPnl)}`, '#fb923c', LineStyle.Dashed);
      addSpec('ghost-stop-loss', ghostTrade.stopLoss, getPriceTitle('SL', ghostTrade.stopLoss, formatPrice), '#ef5350', LineStyle.Dashed);
      [ghostTrade.takeProfit1, ghostTrade.takeProfit2, ghostTrade.takeProfit3].forEach((price, index) => {
        addSpec(`ghost-take-profit-${index + 1}`, price, getPriceTitle(`TP${index + 1}`, price, formatPrice), '#66bb6a', LineStyle.Dashed);
      });
    }

    return specs;
  }, [activeLevelLines, activePosition, formatPrice, ghostTrade, overlayLines]);

  const overlayPriceRange = useMemo(() => {
    const pricePoints: number[] = [];

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
      if (isFinitePrice(ghostTrade.stopLoss)) pricePoints.push(ghostTrade.stopLoss);
      if (isFinitePrice(ghostTrade.takeProfit1)) pricePoints.push(ghostTrade.takeProfit1);
      if (isFinitePrice(ghostTrade.takeProfit2)) pricePoints.push(ghostTrade.takeProfit2);
      if (isFinitePrice(ghostTrade.takeProfit3)) pricePoints.push(ghostTrade.takeProfit3);
    }

    if (!pricePoints.length) return null;

    const minPrice = Math.min(...pricePoints);
    const maxPrice = Math.max(...pricePoints);
    const span = maxPrice - minPrice;
    const baseline = span > 0 ? span : Math.max(minPrice * 0.0025, 0.01);
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

  const applyCandlesToChart = useCallback((nextCandles: CandlePoint[]) => {
    const series = seriesRef.current;
    if (!series) return;

    const chartData = nextCandles.map(toChartCandle);
    chartCandlesRef.current = nextCandles;
    series.setData(chartData);
    if (chartData.length && autoScrollRef.current) {
      const visibleFrom = Math.max(0, chartData.length - VISIBLE_CANDLE_ESTIMATE);
      chartRef.current?.timeScale().setVisibleLogicalRange({
        from: visibleFrom,
        to: chartData.length + 8,
      });
    }
  }, []);

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
          setCandles(normalizeCandles(data.candles ?? []));
        }
      } catch {
        if (!cancelled) {
          setCandles([]);
        }
      }
    };

    setCandles([]);
    applyCandlesToChart([]);
    chartCandlesRef.current = [];
    autoScrollRef.current = true;
    void fetchCandles();
    const intervalId = window.setInterval(() => void fetchCandles(), 15_000);

    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, [applyCandlesToChart, effectiveTf, pair.symbol, resolvedTradeStyle]);

  useEffect(() => {
    applyCandlesToChart(candles);
  }, [applyCandlesToChart, candles]);

  useEffect(() => {
    let cancelled = false;
    let inFlight = false;

    const fetchQuote = async () => {
      if (inFlight) return;
      inFlight = true;
      try {
        const quote = await api.fetchQuote(pair.symbol, effectiveTf, resolvedTradeStyle);
        if (cancelled || !isFinitePrice(quote.currentPrice)) return;

        const updatedCandles = upsertLiveQuote(chartCandlesRef.current, quote.currentPrice, effectiveTf);
        const latestCandle = updatedCandles[updatedCandles.length - 1];
        chartCandlesRef.current = updatedCandles;
        if (latestCandle) {
          seriesRef.current?.update(toChartCandle(latestCandle));
        }
      } catch {
      } finally {
        inFlight = false;
      }
    };

    void fetchQuote();
    const intervalId = window.setInterval(() => void fetchQuote(), 2_000);

    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, [effectiveTf, pair.symbol, resolvedTradeStyle]);

  useEffect(() => {
    const series = seriesRef.current;
    if (!series) return;

    syncPriceLines(series, priceLineRefs.current, priceLineSpecs);
  }, [priceLineSpecs]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const precision = pricePrecision;
    const minMove = 1 / 10 ** precision;
    const chart = createChart(container, {
      autoSize: true,
      layout: {
        background: { type: ColorType.Solid, color: '#0b0e14' },
        textColor: '#5c6a7e',
        fontSize: 11,
        fontFamily: 'Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, sans-serif',
      },
      grid: {
        vertLines: { color: '#161b26', style: LineStyle.Solid, visible: true },
        horzLines: { color: '#161b26', style: LineStyle.Solid, visible: true },
      },
      rightPriceScale: {
        borderVisible: false,
        textColor: '#7b8798',
      },
      timeScale: {
        borderVisible: false,
        timeVisible: true,
        secondsVisible: effectiveTf === '1m',
        rightOffset: 8,
        barSpacing: 7,
        minBarSpacing: 3,
      },
      crosshair: {
        mode: CrosshairMode.MagnetOHLC,
        vertLine: {
          color: '#4fc3f7',
          labelBackgroundColor: '#1f2937',
          style: LineStyle.Dashed,
          visible: true,
        },
        horzLine: {
          color: '#4fc3f7',
          labelBackgroundColor: '#1f2937',
          style: LineStyle.Dashed,
          visible: true,
        },
      },
      handleScroll: true,
      handleScale: true,
    });

    const series = chart.addSeries(CandlestickSeries, {
      upColor: '#26a69a',
      downColor: '#ef5350',
      borderUpColor: '#26a69a',
      borderDownColor: '#ef5350',
      wickUpColor: '#26a69a',
      wickDownColor: '#ef5350',
      priceLineVisible: true,
      priceLineColor: '#d1d5db',
      priceLineStyle: LineStyle.Dashed,
      priceFormat: {
        type: 'price',
        precision,
        minMove,
      },
    });

    chartRef.current = chart;
    seriesRef.current = series;
    priceLineRefs.current = new Map();

    chartCandlesRef.current = [];
    autoScrollRef.current = true;
    series.setData([]);
    syncPriceLines(series, priceLineRefs.current, priceLineSpecs);
    const visibleRangeSubscription = () => {
      autoScrollRef.current = chart.timeScale().scrollPosition() <= 10;
    };
    chart.timeScale().subscribeVisibleLogicalRangeChange(visibleRangeSubscription);

    return () => {
      chart.timeScale().unsubscribeVisibleLogicalRangeChange(visibleRangeSubscription);
      priceLineRefs.current.forEach((line) => series.removePriceLine(line));
      priceLineRefs.current.clear();
      seriesRef.current = null;
      chartRef.current = null;
      chart.remove();
    };
  }, [effectiveTf, pair.symbol, pricePrecision]);

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
              className={`absolute left-0 right-0 -translate-y-1/2 ${line.opacityClassName ?? ''}`}
              style={{ top: `${getPriceOffsetPercent(line.value)}%` }}
            >
              <div className={`w-full border-t ${line.dashed ? 'border-dashed' : 'border-solid'} ${line.lineClassName}`} />
              {/* MT5-style axis label - small solid badge on right edge */}
              <div className="absolute right-0 top-0 -translate-y-1/2">
                <div className="flex items-center">
                  <span className={`mr-1 hidden rounded px-1 py-[1px] text-[8px] font-bold uppercase tracking-wide sm:inline ${getOverlayStatusClasses(line.status).suffixClassName}`}>
                    {line.status}
                  </span>
                  <div className={`px-1.5 py-[2px] text-[9px] font-bold tabular-nums rounded-l-sm ${line.badgeClassName}`}>
                    {line.label} {formatPrice(line.value)}
                  </div>
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
          {activeLevelLines.map((line) => renderTradeLevelLine(
            line.key,
            line.kind,
            line.status,
            line.label,
            line.value,
            formatPrice,
            getPriceOffsetPercent
          ))}
        </div>
      )}
      {/* MT5-style ghost trade overlay (closed trade from history) */}
      {overlayPriceRange && ghostTrade && isFinitePrice(ghostTrade.entryPrice) && isFinitePrice(ghostTrade.exitPrice) && (
        <div style={chartAreaStyle}>
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
          {renderTradeLevelLine(
            'ghost-entry',
            'entry',
            'closed',
            'Entry',
            ghostTrade.entryPrice,
            formatPrice,
            getPriceOffsetPercent
          )}
          {/* Exit line */}
          {renderTradeLevelLine(
            'ghost-exit',
            'exit',
            'closed',
            `Exit (${formatSignedPnl(ghostTrade.realizedPnl)})`,
            ghostTrade.exitPrice,
            formatPrice,
            getPriceOffsetPercent
          )}
          {isFinitePrice(ghostTrade.stopLoss) && renderTradeLevelLine(
            'ghost-stop-loss',
            'stop_loss',
            'closed',
            'SL',
            ghostTrade.stopLoss,
            formatPrice,
            getPriceOffsetPercent
          )}
          {[
            ghostTrade.takeProfit1,
            ghostTrade.takeProfit2,
            ghostTrade.takeProfit3,
          ].map((price, index) => (
            isFinitePrice(price)
              ? renderTradeLevelLine(
                `ghost-take-profit-${index + 1}`,
                'take_profit',
                'closed',
                `TP${index + 1}`,
                price,
                formatPrice,
                getPriceOffsetPercent
              )
              : null
          ))}
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
          Chart feed: <span className="text-slate-200">{pair.symbol} · {effectiveTf.toUpperCase()} {resolvedTradeStyle}</span>
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
