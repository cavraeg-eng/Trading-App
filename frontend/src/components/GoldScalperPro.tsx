import { useState, useEffect, useCallback, useMemo } from 'react'
import { Zap, TrendingUp, TrendingDown, Activity, Minus } from 'lucide-react'

/* ────────────────────────────────────────────────────────────
   Types
   ──────────────────────────────────────────────────────────── */
export interface ScalpTradeData {
  symbol: string
  quantity: number
  price: number
  stopLoss: number
  takeProfit1: number
  takeProfit2?: number
  riskPercent: number
  tradeStyle: 'scalp'
  confidence: number
  timeframe: string
}

export interface GoldScalperProProps {
  accountBalance: number
  onExecuteTrade: (side: 'buy' | 'sell', data: ScalpTradeData) => void
  onActivateGoldMode?: (timeframe: '1m' | '5m') => void
}

/* ────────────────────────────────────────────────────────────
   Component
   ──────────────────────────────────────────────────────────── */
function GoldScalperPro({ accountBalance, onExecuteTrade, onActivateGoldMode }: GoldScalperProProps) {
  /* ── UI state ── */
  const [isExpanded, setIsExpanded] = useState(false)
  const [scalpTF, setScalpTF] = useState<'1m' | '5m'>('1m')
  const [riskPct, setRiskPct] = useState(0.5)

  /* ── Market data state ── */
  const [goldPrice, setGoldPrice] = useState(0)
  const [priceChange, setPriceChange] = useState(0)
  const [priceChangePct, setPriceChangePct] = useState(0)
  const [signal, setSignal] = useState<'buy' | 'sell' | 'hold'>('hold')
  const [confidence, setConfidence] = useState(0)
  const [reason, setReason] = useState('')
  const [entryRange, setEntryRange] = useState({ min: 0, max: 0 })
  const [stopLoss, setStopLoss] = useState(0)
  const [tp1, setTp1] = useState(0)
  const [atr, setAtr] = useState(0)
  const [indicators, setIndicators] = useState<{ name: string; value: string; signal: string }[]>([])
  const [marketRegime, setMarketRegime] = useState('ranging')
  const [isLoading, setIsLoading] = useState(false)
  const [hasActiveSignal, setHasActiveSignal] = useState(false)

  /* ── Data fetching ── */
  const fetchScalpData = useCallback(async () => {
    setIsLoading(true)
    try {
      const res = await fetch(
        `/api/market/analysis/XAU%2FUSD?timeframe=${scalpTF}&trade_style=scalp`
      )
      if (res.ok) {
        const d = await res.json()
        setGoldPrice(d.currentPrice ?? 0)
        setPriceChange(d.priceChange ?? 0)
        setPriceChangePct(d.priceChangePercent ?? 0)

        const rawSignal = (d.signal ?? 'hold').toLowerCase().replace('strong_', '')
        const normalized: 'buy' | 'sell' | 'hold' =
          rawSignal === 'buy' ? 'buy' : rawSignal === 'sell' ? 'sell' : 'hold'
        setSignal(normalized)

        const conf = d.confidence > 1 ? Math.round(d.confidence) : Math.round(d.confidence * 100)
        setConfidence(conf)
        setReason(d.reason ?? '')
        setEntryRange(d.entryRange ?? { min: 0, max: 0 })
        setStopLoss(d.stopLoss ?? 0)
        setTp1(d.takeProfit1 ?? 0)
        setIndicators(d.indicators ?? [])
        setMarketRegime(d.marketRegime ?? 'ranging')

        // ATR: look in indicators array first, fallback to top-level
        const atrInd = (d.indicators ?? []).find(
          (i: { name: string }) => i.name.toUpperCase() === 'ATR'
        )
        setAtr(atrInd ? parseFloat(atrInd.value) : d.atr ?? 0)

        setHasActiveSignal(normalized !== 'hold' && conf >= 50)
      }
    } catch (err) {
      console.error('[MIDAS] fetch error', err)
    } finally {
      setIsLoading(false)
    }
  }, [scalpTF])

  useEffect(() => {
    fetchScalpData()
    const id = setInterval(fetchScalpData, 2000)
    return () => clearInterval(id)
  }, [fetchScalpData])

  useEffect(() => {
    if (isExpanded) {
      onActivateGoldMode?.(scalpTF)
    }
  }, [isExpanded, scalpTF, onActivateGoldMode])

  /* ── Derived calculations ── */
  const spread = useMemo(
    () => Math.abs(entryRange.max - entryRange.min).toFixed(2),
    [entryRange]
  )

  const momentum = useMemo(() => {
    const rsiInd = indicators.find((i) => i.name.toUpperCase() === 'RSI')
    const macdInd = indicators.find((i) => i.name.toUpperCase() === 'MACD')
    const rsiVal = rsiInd ? parseFloat(rsiInd.value) : 50
    const macdSignal = macdInd?.signal ?? 'neutral'

    if (rsiVal < 40 && macdSignal === 'bearish')
      return { label: '▼ Strong', color: 'text-red-400' }
    if (rsiVal > 60 && macdSignal === 'bullish')
      return { label: '▲ Strong', color: 'text-emerald-400' }
    if (rsiVal >= 40 && rsiVal <= 60)
      return { label: '→ Neutral', color: 'text-yellow-400' }
    if (rsiVal > 60) return { label: '▲ Moderate', color: 'text-emerald-300' }
    return { label: '▼ Moderate', color: 'text-red-300' }
  }, [indicators])

  /* Position sizing (gold-specific) */
  const pipSize = 0.1
  const entryMid = (entryRange.min + entryRange.max) / 2
  const stopDist = Math.abs(entryMid - stopLoss)
  const stopPips = stopDist / pipSize
  const riskAmount = accountBalance * (riskPct / 100)
  const pipValue = 1
  const lots = stopPips > 0 ? riskAmount / (stopPips * pipValue) : 0

  const slPips = stopDist / pipSize
  const tp1Pips = Math.abs(tp1 - entryMid) / pipSize

  const rr = slPips > 0 ? tp1Pips / slPips : 0
  const rrQuality =
    rr >= 3 ? 'Excellent' : rr >= 2 ? 'Good' : rr >= 1 ? 'Decent' : 'Poor'
  const rrColor =
    rr >= 2
      ? 'text-emerald-400'
      : rr >= 1
        ? 'text-yellow-400'
        : 'text-red-400'

  const fmtPrice = (p: number) => p.toFixed(2)

  /* ── Trade handler ── */
  const handleTrade = (side: 'buy' | 'sell') => {
    onExecuteTrade(side, {
      symbol: 'XAU/USD',
      quantity: Math.round(lots * 100) / 100,
      price: goldPrice,
      stopLoss,
      takeProfit1: tp1,
      riskPercent: riskPct,
      tradeStyle: 'scalp',
      confidence,
      timeframe: scalpTF,
    })
  }

  const isHold = signal === 'hold'

  /* ═══════════════════════════════════════════════════════════
     COLLAPSED STATE — Floating button
     ═══════════════════════════════════════════════════════════ */
  if (!isExpanded) {
    return (
      <div className="fixed bottom-6 right-6 z-50 flex flex-col items-center gap-1">
        <button
          onClick={() => {
            onActivateGoldMode?.(scalpTF)
            setIsExpanded(true)
          }}
          aria-label="Open MIDAS Gold Scalper Pro"
          className="relative w-14 h-14 sm:w-14 sm:h-14 w-12 h-12 rounded-full bg-gradient-to-br from-amber-500 to-amber-600 shadow-lg shadow-amber-500/25 flex items-center justify-center hover:scale-105 active:scale-95 transition-transform focus:outline-none focus:ring-2 focus:ring-amber-400 focus:ring-offset-2 focus:ring-offset-slate-900"
        >
          <Zap size={24} className="text-white" />
          {hasActiveSignal && (
            <span className="absolute -top-0.5 -right-0.5 w-3.5 h-3.5">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
              <span className="relative inline-flex rounded-full h-3.5 w-3.5 bg-emerald-500 border-2 border-slate-900" />
            </span>
          )}
        </button>
        <span className="text-[10px] font-bold text-amber-400 tracking-widest select-none">
          MIDAS
        </span>
      </div>
    )
  }

  /* ═══════════════════════════════════════════════════════════
     EXPANDED STATE — Panel
     ═══════════════════════════════════════════════════════════ */
  return (
    <div
      className="fixed bottom-6 right-6 z-50 w-[360px] sm:w-[380px] max-h-[480px] overflow-y-auto rounded-2xl shadow-2xl shadow-amber-500/10 bg-slate-900/95 backdrop-blur-sm border border-amber-500/30 flex flex-col transition-all duration-300 dark-scrollbar"
      role="dialog"
      aria-label="MIDAS Gold Scalper Pro"
    >
      {/* ── Header ── */}
      <header className="flex items-center justify-between px-4 py-3 bg-gradient-to-r from-amber-500/10 to-transparent border-b border-amber-500/20 shrink-0">
        <div className="flex items-center gap-2 min-w-0">
          <Zap size={18} className="text-amber-400 shrink-0" />
          <h2 className="text-sm font-extrabold text-amber-300 tracking-wide truncate">
            MIDAS — Gold Scalper Pro
          </h2>
        </div>
        <div className="flex items-center gap-1 shrink-0">
          {isLoading && (
            <span className="w-2 h-2 rounded-full bg-amber-400 animate-pulse mr-1" />
          )}
          <button
            onClick={() => setIsExpanded(false)}
            aria-label="Collapse MIDAS panel"
            className="w-8 h-8 flex items-center justify-center rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
          >
            <Minus size={16} />
          </button>
        </div>
      </header>

      {/* ── Sub-header: pair & timeframe ── */}
      <div className="px-4 pt-2 pb-1 flex items-center justify-between text-xs text-slate-400">
        <span className="font-semibold">XAU/USD · {scalpTF}</span>
        <span className="flex items-center gap-1">
          {marketRegime === 'trending_up' && <TrendingUp size={12} className="text-emerald-400" />}
          {marketRegime === 'trending_down' && <TrendingDown size={12} className="text-red-400" />}
          {marketRegime === 'volatile' && <Zap size={12} className="text-yellow-400" />}
          {marketRegime === 'ranging' && <Activity size={12} className="text-blue-400" />}
          <span className="capitalize">{marketRegime.replace('_', ' ')}</span>
        </span>
      </div>

      {/* ── Timeframe selector ── */}
      <div className="px-4 pt-1 pb-2 flex items-center gap-2">
        <span className="text-[10px] font-semibold text-slate-500 uppercase mr-1">
          Timeframe
        </span>
        {(['1m', '5m'] as const).map((tf) => (
          <button
            key={tf}
            onClick={() => setScalpTF(tf)}
            aria-pressed={scalpTF === tf}
            className={`px-3 py-1 rounded-md text-xs font-bold transition-colors ${
              scalpTF === tf
                ? 'bg-amber-500 text-white shadow-sm shadow-amber-500/25'
                : 'bg-slate-800 text-slate-400 hover:text-white hover:bg-slate-700'
            }`}
          >
            {tf}
          </button>
        ))}
      </div>

      {/* ── Price + Signal ── */}
      <section className="px-4 py-2">
        {/* Price row */}
        <div className="flex items-baseline gap-2">
          <span className="text-2xl font-extrabold text-slate-50">
            {goldPrice > 0 ? fmtPrice(goldPrice) : '—'}
          </span>
          {goldPrice > 0 && (
            <span
              className={`text-sm font-semibold ${priceChange >= 0 ? 'text-emerald-400' : 'text-red-400'}`}
            >
              {priceChange >= 0 ? '+' : ''}
              {fmtPrice(priceChange)} ({priceChangePct >= 0 ? '+' : ''}
              {priceChangePct.toFixed(2)}%)
            </span>
          )}
        </div>

        {/* Signal badge + confidence */}
        <div className="flex items-center gap-2 mt-2">
          <span
            className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-md text-xs font-extrabold uppercase tracking-wide ${
              signal === 'buy'
                ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
                : signal === 'sell'
                  ? 'bg-red-500/20 text-red-400 border border-red-500/30'
                  : 'bg-slate-700/60 text-slate-400 border border-slate-600/40'
            }`}
          >
            <span
              className={`w-2 h-2 rounded-full ${
                signal === 'buy'
                  ? 'bg-emerald-400'
                  : signal === 'sell'
                    ? 'bg-red-400'
                    : 'bg-slate-500'
              }`}
            />
            {signal === 'hold' ? 'HOLD' : `SCALP ${signal.toUpperCase()}`}
          </span>
          <span className="text-sm font-bold text-slate-200">{confidence}%</span>
        </div>

        {/* Confidence bar (gold gradient) */}
        <div className="mt-2 h-2 rounded-full overflow-hidden bg-slate-800">
          <div
            className="h-full rounded-full transition-all duration-500"
            style={{
              width: `${confidence}%`,
              background: 'linear-gradient(90deg, #d97706, #f59e0b, #fbbf24)',
            }}
            role="progressbar"
            aria-valuenow={confidence}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-label={`Signal confidence ${confidence}%`}
          />
        </div>

        {/* Reason */}
        {reason && (
          <p className="mt-1.5 text-xs text-slate-400 italic leading-snug line-clamp-2">
            &ldquo;{reason}&rdquo;
          </p>
        )}
      </section>

      {/* ── Scalp Metrics ── */}
      <section className="px-4 py-2 border-t border-slate-700/50">
        <h3 className="text-[10px] font-bold text-amber-400/80 uppercase tracking-widest mb-2">
          Scalp Metrics
        </h3>
        <div className="grid grid-cols-3 gap-2">
          {[
            { label: 'Spread', value: spread },
            { label: 'ATR', value: atr > 0 ? atr.toFixed(2) : '—' },
            { label: 'Momentum', value: momentum.label, color: momentum.color },
          ].map((m) => (
            <div
              key={m.label}
              className="bg-slate-800/50 border border-slate-700/50 rounded-lg px-2 py-2 text-center"
            >
              <div className="text-[10px] font-semibold text-slate-500 uppercase">
                {m.label}
              </div>
              <div
                className={`text-sm font-bold mt-0.5 ${
                  'color' in m && m.color ? m.color : 'text-slate-200'
                }`}
              >
                {m.value}
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* ── Levels ── */}
      <section className="px-4 py-2 border-t border-slate-700/50">
        <h3 className="text-[10px] font-bold text-amber-400/80 uppercase tracking-widest mb-2">
          Levels
        </h3>
        <div className="space-y-1 text-xs">
          {/* SL */}
          <div className="flex items-center justify-between">
            <span className="font-bold text-red-400 w-12">SL</span>
            <span className="text-slate-200 font-semibold">
              {stopLoss > 0 ? fmtPrice(stopLoss) : '—'}
            </span>
            <span className="text-red-400 font-medium w-20 text-right">
              {slPips > 0 ? `-${slPips.toFixed(1)} pips` : ''}
            </span>
          </div>
          {/* Entry */}
          <div className="flex items-center justify-between">
            <span className="font-bold text-blue-400 w-12">Entry</span>
            <span className="text-slate-200 font-semibold">
              {entryRange.min > 0
                ? `${fmtPrice(entryRange.min)} — ${fmtPrice(entryRange.max)}`
                : '—'}
            </span>
            <span className="w-20" />
          </div>
          {/* TP1 */}
          <div className="flex items-center justify-between">
            <span className="font-bold text-emerald-300 w-12">TP1</span>
            <span className="text-slate-200 font-semibold">
              {tp1 > 0 ? fmtPrice(tp1) : '—'}
            </span>
            <span className="text-emerald-300 font-medium w-20 text-right">
              {tp1Pips > 0 ? `+${tp1Pips.toFixed(1)} pips` : ''}
            </span>
          </div>
        </div>

        {/* R:R summary */}
        <div className="mt-2 flex items-center gap-2 text-xs">
          <span className="text-slate-400">R:R</span>
          <span className={`font-bold ${rrColor}`}>1:{rr.toFixed(1)}</span>
          <span className="text-slate-500">·</span>
          <span className={`font-semibold ${rrColor}`}>{rrQuality}</span>
        </div>
      </section>

      {/* ── Controls: Risk + Buttons ── */}
      <section className="px-4 py-3 border-t border-slate-700/50 mt-auto shrink-0">
        {/* Risk slider */}
        <div className="flex items-center gap-2 mb-3">
          <label
            htmlFor="midas-risk"
            className="text-[10px] font-semibold text-slate-500 uppercase whitespace-nowrap"
          >
            Risk: <span className="text-amber-300">{riskPct}%</span>
          </label>
          <input
            id="midas-risk"
            type="range"
            min="0.25"
            max="2"
            step="0.25"
            value={riskPct}
            onChange={(e) => setRiskPct(parseFloat(e.target.value))}
            className="flex-1 h-1.5 accent-amber-500 cursor-pointer"
            aria-label={`Risk percentage: ${riskPct}%`}
          />
          <span className="text-[11px] text-slate-400 font-semibold whitespace-nowrap">
            {lots.toFixed(2)} lots
          </span>
        </div>

        {/* Buy / Sell buttons */}
        <div className="flex gap-2">
          <button
            onClick={() => handleTrade('buy')}
            disabled={isHold}
            aria-label={isHold ? 'Buy disabled — no active signal' : 'Scalp Buy XAU/USD'}
            className={`btn-buy flex-1 min-h-[44px] text-sm font-extrabold rounded-lg flex items-center justify-center gap-1.5 transition-all duration-200 ${
              signal === 'buy'
                ? 'ring-2 ring-emerald-400 shadow-lg shadow-emerald-500/25'
                : ''
            } ${isHold ? 'opacity-40 cursor-not-allowed' : 'hover:brightness-110 active:scale-[0.97]'}`}
          >
            <TrendingUp size={16} />
            SCALP BUY
          </button>
          <button
            onClick={() => handleTrade('sell')}
            disabled={isHold}
            aria-label={isHold ? 'Sell disabled — no active signal' : 'Scalp Sell XAU/USD'}
            className={`btn-sell flex-1 min-h-[44px] text-sm font-extrabold rounded-lg flex items-center justify-center gap-1.5 transition-all duration-200 ${
              signal === 'sell'
                ? 'ring-2 ring-red-400 shadow-lg shadow-red-500/25'
                : ''
            } ${isHold ? 'opacity-40 cursor-not-allowed' : 'hover:brightness-110 active:scale-[0.97]'}`}
          >
            <TrendingDown size={16} />
            SCALP SELL
          </button>
        </div>
      </section>
    </div>
  )
}

export default GoldScalperPro
export { GoldScalperPro }
