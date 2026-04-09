import { useEffect, useRef, memo, Component } from 'react';
import type { ErrorInfo, ReactNode } from 'react';
import type { ForexPair, ChartSignalMarker } from '../types';
import { getTradingViewSymbol, getTradingViewInterval } from '../config/forexPairs';

interface TradingChartProps {
  pair: ForexPair;
  timeframe?: string;
  interval?: string;
  chartType?: 'candlestick' | 'line' | 'area';
  signals?: ChartSignalMarker[];
}

function TradingChart({
  pair,
  timeframe = '1h',
  interval,
  chartType: _chartType,
  signals,
}: TradingChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const widgetRef = useRef<any>(null);

  const effectiveTf = interval || timeframe;
  const tvSymbol = getTradingViewSymbol(pair);
  const tvInterval = getTradingViewInterval(effectiveTf);
  const latestSignal = signals?.[0];
  const formatPrice = (value: number) => value.toFixed(pair.basePriceApprox < 10 ? 4 : 2);
  const signalTone =
    latestSignal?.direction === 'BUY'
      ? 'text-emerald-300 border-emerald-500/30 bg-emerald-500/15'
      : latestSignal?.direction === 'SELL'
        ? 'text-red-300 border-red-500/30 bg-red-500/15'
        : 'text-slate-300 border-slate-500/30 bg-slate-500/15';

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
        toolbar_bg: '#0f172a',
        enable_publishing: false,
        allow_symbol_change: false,
        hide_top_toolbar: false,
        hide_legend: false,
        save_image: false,
        autosize: true,
        backgroundColor: '#0f172a',
        gridColor: '#1e293b',
        studies_overrides: {},
        overrides: {
          'mainSeriesProperties.candleStyle.upColor': '#22c55e',
          'mainSeriesProperties.candleStyle.downColor': '#ef4444',
          'mainSeriesProperties.candleStyle.borderUpColor': '#22c55e',
          'mainSeriesProperties.candleStyle.borderDownColor': '#ef4444',
          'mainSeriesProperties.candleStyle.wickUpColor': '#22c55e',
          'mainSeriesProperties.candleStyle.wickDownColor': '#ef4444',
          'paneProperties.background': '#0f172a',
          'paneProperties.backgroundType': 'solid',
          'paneProperties.vertGridProperties.color': '#1e293b',
          'paneProperties.horzGridProperties.color': '#1e293b',
          'scalesProperties.textColor': '#94a3b8',
          'scalesProperties.lineColor': '#1e293b',
        },
        loading_screen: { backgroundColor: '#0f172a', foregroundColor: '#3b82f6' },
        disabled_features: [
          'use_localstorage_for_settings',
          'header_symbol_search',
          'header_compare',
        ],
        enabled_features: [
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
        style={{ background: '#0f172a' }}
      />
      {latestSignal && latestSignal.direction !== 'HOLD' && (
        <div className="pointer-events-none absolute top-3 right-3 z-10 max-w-[260px] rounded-lg border border-trading-border bg-slate-950/85 px-3 py-2 shadow-xl backdrop-blur-sm">
          <div className="flex items-center justify-between gap-3">
            <span className={`inline-flex items-center rounded-md border px-2 py-1 text-[11px] font-bold ${signalTone}`}>
              {latestSignal.direction} · {latestSignal.confidence}%
            </span>
            <span className="text-[10px] font-semibold text-slate-400">
              {latestSignal.status.replace(/_/g, ' ')}
            </span>
          </div>
          <div className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-[11px]">
            <span className="text-slate-400">Entry</span>
            <span className="text-right font-semibold text-slate-100">
              {formatPrice(latestSignal.entryMin)} - {formatPrice(latestSignal.entryMax)}
            </span>
            <span className="text-slate-400">SL</span>
            <span className="text-right font-semibold text-red-300">
              {formatPrice(latestSignal.stopLoss)}
            </span>
            <span className="text-slate-400">TP1</span>
            <span className="text-right font-semibold text-emerald-300">
              {formatPrice(latestSignal.takeProfit1)}
            </span>
            <span className="text-slate-400">TP2</span>
            <span className="text-right font-semibold text-emerald-300">
              {formatPrice(latestSignal.takeProfit2)}
            </span>
            <span className="text-slate-400">TP3</span>
            <span className="text-right font-semibold text-emerald-300">
              {formatPrice(latestSignal.takeProfit3)}
            </span>
          </div>
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
