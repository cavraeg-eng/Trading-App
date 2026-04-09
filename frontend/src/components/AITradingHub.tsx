import { useState, useMemo } from 'react'
import {
  TrendingUp,
  TrendingDown,
  Activity,
  Zap,
  AlertTriangle,
  Target,
  Shield,
  BarChart3,
  Clock,
  ChevronRight,
  Loader2,
  Copy,
  X,
} from 'lucide-react'
import type { AIScoreData, DetectedPattern, ForexPair, SignalStatus } from '../types'

/* ────────────────────────────────────────────────────────────
   Copy Trading Types
   ──────────────────────────────────────────────────────────── */
interface CopiedPosition {
  copy_trade_id: string
  symbol: string
  direction: string
  quantity: number
  entry_price: number
  current_price: number
  stop_loss: number
  take_profit1: number
  unrealized_pnl: number
  status: string
  created_at: number
  confidence: number
}

interface CopyStats {
  total_trades: number
  open_trades: number
  win_rate: number
  total_pnl: number
}

/* ────────────────────────────────────────────────────────────
   Props
   ──────────────────────────────────────────────────────────── */
interface AITradingHubProps {
  signalDetails: {
    signal: 'buy' | 'sell' | 'hold' | 'strong_buy' | 'strong_sell'
    confidence: number
    reason: string
    entryRange: { min: number; max: number }
    stopLoss: number
    takeProfit1: number
    takeProfit2: number
    takeProfit3: number
    riskReward: number
    timeframe: string
    marketRegime: 'trending_up' | 'trending_down' | 'ranging' | 'volatile'
    indicators: { name: string; value: string; signal: 'bullish' | 'bearish' | 'neutral' }[]
    aiScore?: AIScoreData
    patterns?: DetectedPattern[]
    patternAccuracy?: number | null
  }
  currentPrice: number
  priceChange: number
  priceChangePercent: number
  selectedPair: ForexPair
  accountBalance: number
  isLoading: boolean
  onBuy: () => void
  onSell: () => void
  tradeStyle: 'scalp' | 'swing'
  onTradeStyleChange: (style: 'scalp' | 'swing') => void
  signalStatus?: string
  multiTimeframe?: { tf: string; signal: 'BUY' | 'SELL' | 'HOLD'; alignment: number }[]
  // Copy trading props
  copyTradingEnabled?: boolean
  onToggleCopyTrading?: (enabled: boolean) => void
  copiedPositions?: CopiedPosition[]
  copyStats?: CopyStats | null
  onCopySignal?: () => void
  onCloseCopyTrade?: (copyTradeId: string) => void
  copyTradeLoading?: boolean
  dataFreshness?: 'live' | 'delayed' | 'stale'
  lastUpdatedMs?: number
  quoteSource?: 'live' | 'mock' | 'unknown'
  activeTimeframe?: string
}

/* ────────────────────────────────────────────────────────────
   Helpers
   ──────────────────────────────────────────────────────────── */
const getPipSize = (price: number) => {
  if (price < 10) return 0.0001
  if (price < 200) return 0.01
  if (price < 5000) return 0.10
  return 1.0
}

const toPips = (distance: number, pair: ForexPair) =>
  Math.abs(distance) / getPipSize(pair.basePriceApprox)

const fmtPrice = (price: number, pair: ForexPair) =>
  price.toFixed(pair.basePriceApprox < 10 ? 4 : 2)

const isBuyish = (s: string) => s === 'buy' || s === 'strong_buy'
const isSellish = (s: string) => s === 'sell' || s === 'strong_sell'

const signalLabel = (s: string) => {
  switch (s) {
    case 'strong_buy': return 'STRONG BUY'
    case 'strong_sell': return 'STRONG SELL'
    default: return s.toUpperCase()
  }
}

type AnalysisTab = 'indicators' | 'multitf' | 'analysis' | 'copyhistory'

/* ────────────────────────────────────────────────────────────
   Component
   ──────────────────────────────────────────────────────────── */
function AITradingHub({
  signalDetails,
  currentPrice,
  priceChange,
  priceChangePercent,
  selectedPair,
  accountBalance,
  isLoading,
  onBuy,
  onSell,
  tradeStyle,
  onTradeStyleChange,
  signalStatus,
  multiTimeframe,
  copyTradingEnabled,
  onToggleCopyTrading,
  copiedPositions,
  copyStats,
  onCopySignal,
  onCloseCopyTrade,
  copyTradeLoading,
  dataFreshness = 'stale',
  lastUpdatedMs,
  quoteSource = 'unknown',
  activeTimeframe,
}: AITradingHubProps) {
  const [riskPct, setRiskPct] = useState(1)
  const [activeTab, setActiveTab] = useState<AnalysisTab>('indicators')

  /* ── derived values ── */
  const displayConf = useMemo(
    () =>
      signalDetails.confidence > 1
        ? Math.round(signalDetails.confidence)
        : Math.round(signalDetails.confidence * 100),
    [signalDetails.confidence],
  )

  const entryMid = (signalDetails.entryRange.min + signalDetails.entryRange.max) / 2

  const hasValidData =
    signalDetails.stopLoss !== 0 &&
    signalDetails.stopLoss !== signalDetails.entryRange.min &&
    signalDetails.entryRange.min !== signalDetails.entryRange.max

  /* position sizing */
  const riskAmount = accountBalance * (riskPct / 100)
  const stopDistance = Math.abs(entryMid - signalDetails.stopLoss)
  const stopPips = toPips(stopDistance, selectedPair)
  const pipValuePerStandardLot = selectedPair.basePriceApprox < 10 ? 10 : 1
  const posSizeLots = stopPips > 0 ? riskAmount / (stopPips * pipValuePerStandardLot) : 0

  /* pip distances */
  const slPips = toPips(entryMid - signalDetails.stopLoss, selectedPair)
  const tp1Pips = toPips(signalDetails.takeProfit1 - entryMid, selectedPair)
  const tp2Pips = toPips(signalDetails.takeProfit2 - entryMid, selectedPair)
  const tp3Pips = toPips(signalDetails.takeProfit3 - entryMid, selectedPair)

  /* risk / reward */
  const riskDist = Math.abs(entryMid - signalDetails.stopLoss)
  const rr1 = riskDist > 0 ? Math.abs(signalDetails.takeProfit1 - entryMid) / riskDist : 1
  const rr2 = signalDetails.riskReward
  const rr3 = riskDist > 0 ? Math.abs(signalDetails.takeProfit3 - entryMid) / riskDist : 3

  const rrQuality = useMemo(() => {
    if (rr2 >= 3) return { label: 'Excellent', cls: 'text-emerald-300', bg: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/30' }
    if (rr2 >= 2) return { label: 'Good', cls: 'text-emerald-400', bg: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/30' }
    if (rr2 >= 1) return { label: 'Decent', cls: 'text-yellow-400', bg: 'bg-yellow-500/20 text-yellow-300 border-yellow-500/30' }
    return { label: 'Poor', cls: 'text-red-400', bg: 'bg-red-500/20 text-red-300 border-red-500/30' }
  }, [rr2])

  /* price ladder percentages */
  const allPrices = [signalDetails.stopLoss, entryMid, signalDetails.takeProfit1, signalDetails.takeProfit2, signalDetails.takeProfit3]
  const ladderMin = Math.min(...allPrices)
  const ladderMax = Math.max(...allPrices)
  const ladderRange = ladderMax - ladderMin || 1
  const pct = (v: number) => ((v - ladderMin) / ladderRange) * 100
  const slPct = pct(signalDetails.stopLoss)
  const entryMinPct = pct(signalDetails.entryRange.min)
  const entryMaxPct = pct(signalDetails.entryRange.max)
  const tp1Pct = pct(signalDetails.takeProfit1)
  const tp2Pct = pct(signalDetails.takeProfit2)
  const tp3Pct = pct(signalDetails.takeProfit3)
  const currentPct = Math.max(0, Math.min(100, pct(currentPrice)))

  const leftZoneEnd = Math.min(entryMinPct, entryMaxPct)
  const rightZoneStart = Math.max(entryMinPct, entryMaxPct)

  const isBuy = isBuyish(signalDetails.signal)
  const isExpired = signalStatus === 'EXPIRED'

  /* indicator consensus */
  const { bullish, bearish, neutral } = useMemo(() => {
    let b = 0, be = 0, n = 0
    signalDetails.indicators.forEach((i) => {
      if (i.signal === 'bullish') b++
      else if (i.signal === 'bearish') be++
      else n++
    })
    return { bullish: b, bearish: be, neutral: n }
  }, [signalDetails.indicators])

  const totalIndicators = bullish + bearish + neutral || 1
  const aiScore = signalDetails.aiScore
  const topPatterns = signalDetails.patterns ?? []

  const freshnessMeta = useMemo(() => {
    if (dataFreshness === 'live') return { dot: 'bg-emerald-400', text: 'text-emerald-300', label: 'Live' }
    if (dataFreshness === 'delayed') return { dot: 'bg-yellow-400', text: 'text-yellow-300', label: 'Delayed' }
    return { dot: 'bg-red-400', text: 'text-red-300', label: 'Stale' }
  }, [dataFreshness])

  const patternBadgeTone = (pattern: DetectedPattern) =>
    pattern.direction === 'bullish'
      ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300'
      : 'border-red-500/30 bg-red-500/10 text-red-300'

  const lastUpdatedLabel = useMemo(() => {
    if (!lastUpdatedMs) return 'unknown'
    const ageSeconds = Math.max(0, Math.round((Date.now() - lastUpdatedMs) / 1000))
    if (ageSeconds <= 1) return 'just now'
    return `${ageSeconds}s ago`
  }, [lastUpdatedMs])

  /* ── loading state ── */
  if (!hasValidData) {
    return (
      <article className="bg-trading-card border border-trading-border rounded-xl p-8 text-center">
        <Loader2 className="animate-spin mx-auto mb-3 text-slate-400" size={28} />
        <p className="text-slate-300 text-base">Awaiting market data…</p>
      </article>
    )
  }

  /* ── signal hero gradient ── */
  const heroGradient = isBuy
    ? 'bg-gradient-to-r from-emerald-500/5 to-transparent'
    : isSellish(signalDetails.signal)
      ? 'bg-gradient-to-r from-red-500/5 to-transparent'
      : 'bg-gradient-to-r from-amber-500/5 to-transparent'

  const badgeColor = isBuy
    ? 'bg-emerald-500 text-white shadow-emerald-500/30'
    : isSellish(signalDetails.signal)
      ? 'bg-red-500 text-white shadow-red-500/30'
      : 'bg-amber-500 text-white shadow-amber-500/30'

  const confBarColor = displayConf >= 70
    ? 'from-emerald-500 to-emerald-400'
    : displayConf >= 40
      ? 'from-yellow-500 to-yellow-400'
      : 'from-red-500 to-red-400'

  /* ── status helpers ── */
  const statusDot = () => {
    switch (signalStatus as SignalStatus | undefined) {
      case 'OPTIMAL_ENTRY':
        return <span className="relative flex h-2.5 w-2.5"><span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" /><span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-emerald-500" /></span>
      case 'VALID':
        return <span className="inline-flex rounded-full h-2.5 w-2.5 bg-blue-500" />
      case 'ABOUT_TO_EXPIRE':
        return <span className="inline-flex rounded-full h-2.5 w-2.5 bg-amber-500 animate-pulse" />
      case 'EXPIRED':
        return <span className="inline-flex rounded-full h-2.5 w-2.5 bg-gray-500" />
      default:
        return null
    }
  }

  const statusLabel = () => {
    switch (signalStatus) {
      case 'OPTIMAL_ENTRY': return 'Optimal Entry — act now'
      case 'VALID': return 'Valid signal'
      case 'ABOUT_TO_EXPIRE': return 'Expiring soon'
      case 'EXPIRED': return 'Signal expired'
      default: return null
    }
  }

  const regimeIcon = () => {
    switch (signalDetails.marketRegime) {
      case 'trending_up': return <TrendingUp size={14} className="text-emerald-400" />
      case 'trending_down': return <TrendingDown size={14} className="text-red-400" />
      case 'volatile': return <Zap size={14} className="text-yellow-400" />
      default: return <Activity size={14} className="text-blue-400" />
    }
  }

  const regimeLabel = () => {
    switch (signalDetails.marketRegime) {
      case 'trending_up': return 'Trending Up'
      case 'trending_down': return 'Trending Down'
      case 'volatile': return 'Volatile'
      default: return 'Ranging'
    }
  }

  /* ═══════════════════════════════════════════════════════════
     RENDER
     ═══════════════════════════════════════════════════════════ */
  return (
    <article className="bg-trading-card border border-trading-border rounded-xl overflow-hidden transition-all duration-200">

      {/* ────────────────────────────────────────────────
          SECTION 1 — Signal Hero
          ──────────────────────────────────────────────── */}
      <section className={`px-5 py-4 ${heroGradient}`}>
        {/* Top row */}
        <div className="flex items-center gap-3 flex-wrap">
          {/* Signal badge */}
          <span className={`inline-flex items-center gap-1.5 px-4 py-2 rounded-lg font-extrabold text-lg leading-tight shadow-lg ${badgeColor}`}>
            {signalLabel(signalDetails.signal)}
          </span>

          {/* Pair + price */}
          <div className="flex items-baseline gap-2">
            <span className="text-xl font-bold text-trading-text">{selectedPair.symbol}</span>
            <span className="text-xl font-bold text-trading-text">{fmtPrice(currentPrice, selectedPair)}</span>
            <span className={`text-sm font-semibold ${priceChange >= 0 ? 'text-trading-buy' : 'text-trading-sell'}`}>
              {priceChange >= 0 ? '+' : ''}{fmtPrice(priceChange, selectedPair)} ({priceChangePercent >= 0 ? '+' : ''}{priceChangePercent.toFixed(2)}%)
            </span>
          </div>

          {isLoading && <Loader2 size={16} className="animate-spin text-trading-accent" />}

          {/* Trade style toggle — pushed right */}
          <div className="ml-auto flex items-center gap-1 bg-trading-bg rounded-lg p-1" role="radiogroup" aria-label="Trade style">
            <button
              role="radio"
              aria-checked={tradeStyle === 'scalp'}
              onClick={() => onTradeStyleChange('scalp')}
              className={`px-3 py-1.5 rounded-md text-sm font-semibold transition-all duration-200 ${
                tradeStyle === 'scalp'
                  ? 'bg-trading-accent text-white shadow-md'
                  : 'text-slate-400 hover:text-trading-text hover:bg-trading-border/50'
              }`}
            >
              Scalp
            </button>
            <button
              role="radio"
              aria-checked={tradeStyle === 'swing'}
              onClick={() => onTradeStyleChange('swing')}
              className={`px-3 py-1.5 rounded-md text-sm font-semibold transition-all duration-200 ${
                tradeStyle === 'swing'
                  ? 'bg-trading-accent text-white shadow-md'
                  : 'text-slate-400 hover:text-trading-text hover:bg-trading-border/50'
              }`}
            >
              Swing
            </button>
          </div>

          {/* Copy Trading Toggle */}
          {onToggleCopyTrading && (
            <div className="flex items-center gap-2 ml-2">
              <button
                onClick={() => onToggleCopyTrading(!copyTradingEnabled)}
                className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors duration-200 ${
                  copyTradingEnabled ? 'bg-emerald-500' : 'bg-slate-600'
                }`}
                role="switch"
                aria-checked={copyTradingEnabled}
                aria-label="Toggle copy trading"
              >
                <span className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform duration-200 ${
                  copyTradingEnabled ? 'translate-x-6' : 'translate-x-1'
                }`} />
              </button>
              <span className="text-xs font-semibold text-trading-muted">
                {copyTradingEnabled ? (
                  <span className="text-emerald-400">Copy Active</span>
                ) : (
                  'Auto Copy'
                )}
              </span>
            </div>
          )}
        </div>

        {/* Confidence bar */}
        <div className="mt-3 flex items-center gap-3">
          <span className="text-xs text-trading-muted uppercase tracking-wider font-semibold w-20">Confidence</span>
          <div className="flex-1 h-2.5 bg-trading-bg rounded-full overflow-hidden max-w-xs">
            <div
              className={`h-full rounded-full bg-gradient-to-r ${confBarColor} transition-all duration-500`}
              style={{ width: `${displayConf}%` }}
              role="progressbar"
              aria-valuenow={displayConf}
              aria-valuemin={0}
              aria-valuemax={100}
            />
          </div>
          <span className="text-sm font-bold text-trading-text w-10">{displayConf}%</span>

          {/* Regime */}
          <span className="hidden sm:flex items-center gap-1.5 text-xs text-trading-muted ml-2">
            {regimeIcon()} {regimeLabel()}
          </span>
        </div>

        {/* Reason + status */}
        <div className="mt-2 flex items-center gap-3 flex-wrap">
          <p className="text-sm text-trading-muted italic leading-snug">"{signalDetails.reason}"</p>
          {signalStatus && (
            <span className="flex items-center gap-1.5 text-xs font-semibold text-trading-muted">
              {statusDot()} {statusLabel()}
            </span>
          )}
        </div>

        <div className="mt-2 flex items-center gap-3 flex-wrap text-xs">
          <span className={`inline-flex items-center gap-1.5 font-semibold ${freshnessMeta.text}`}>
            <span className={`inline-flex h-2.5 w-2.5 rounded-full ${freshnessMeta.dot}`} />
            {freshnessMeta.label}
          </span>
          <span className="text-trading-muted">
            Updated {lastUpdatedLabel}
          </span>
          {activeTimeframe && (
            <span className="text-trading-muted">
              · TF {activeTimeframe}
            </span>
          )}
          <span className="text-trading-muted">
            · Source {quoteSource}
          </span>
        </div>

        {(aiScore || topPatterns.length > 0) && (
          <div className="mt-3 grid grid-cols-1 lg:grid-cols-[minmax(0,220px)_1fr] gap-3">
            {aiScore && (
              <div className="rounded-xl border border-trading-border bg-trading-bg/70 px-3 py-3">
                <div className="text-[11px] uppercase tracking-wider text-trading-muted font-semibold">AI Score</div>
                <div className="mt-1 flex items-end gap-2">
                  <span className="text-2xl font-extrabold text-trading-text">{aiScore.value}</span>
                  <span className="text-sm font-semibold text-trading-accent">{aiScore.label}</span>
                </div>
                <div className="mt-2 h-2 rounded-full bg-trading-card overflow-hidden">
                  <div
                    className={`h-full rounded-full bg-gradient-to-r ${
                      aiScore.value >= 75 ? 'from-emerald-500 to-emerald-400' : aiScore.value >= 55 ? 'from-yellow-500 to-yellow-400' : 'from-red-500 to-red-400'
                    }`}
                    style={{ width: `${aiScore.value}%` }}
                  />
                </div>
                <div className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 text-[11px] text-trading-muted">
                  <span>Model {Math.round(aiScore.factors.modelConfidence)}</span>
                  <span>Consensus {Math.round(aiScore.factors.indicatorConsensus)}</span>
                  <span>Regime {Math.round(aiScore.factors.marketRegimeFit)}</span>
                  <span>Pattern {Math.round(aiScore.factors.patternStrength)}</span>
                </div>
              </div>
            )}

            {topPatterns.length > 0 && (
              <div className="rounded-xl border border-trading-border bg-trading-bg/70 px-3 py-3">
                <div className="flex items-center justify-between gap-2">
                  <div className="text-[11px] uppercase tracking-wider text-trading-muted font-semibold">Pattern Recognition</div>
                  {signalDetails.patternAccuracy != null && (
                    <span className="text-[11px] text-trading-muted">Hit rate {signalDetails.patternAccuracy}%</span>
                  )}
                </div>
                <div className="mt-2 flex flex-wrap gap-2">
                  {topPatterns.slice(0, 3).map((pattern) => (
                    <div key={pattern.name} className={`rounded-lg border px-2.5 py-2 min-w-[150px] ${patternBadgeTone(pattern)}`}>
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-xs font-bold">{pattern.name}</span>
                        <span className="text-[11px] font-semibold">{pattern.confidence}%</span>
                      </div>
                      <div className="mt-1 text-[11px] opacity-80">{pattern.description}</div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </section>

      {/* ────────────────────────────────────────────────
          SECTION 2 — Trade Levels (two-column)
          ──────────────────────────────────────────────── */}
      <section className="border-t border-trading-border px-5 py-4">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-5">

          {/* LEFT — Price Levels */}
          <div>
            <h3 className="text-xs font-bold text-trading-muted uppercase tracking-wider mb-3 flex items-center gap-1.5">
              <Target size={14} /> Price Levels
            </h3>

            {/* Vertical level list */}
            <div className="space-y-2">
              {/* SL */}
              <div className="flex items-center gap-3 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2">
                <span className="text-xs font-bold text-red-400 uppercase w-10">SL</span>
                <span className="text-sm font-bold text-trading-text flex-1">{fmtPrice(signalDetails.stopLoss, selectedPair)}</span>
                <span className="text-xs text-red-400 font-medium">-{slPips.toFixed(1)} pips</span>
              </div>

              {/* Entry */}
              <div className="flex items-center gap-3 bg-blue-500/10 border border-blue-500/20 rounded-lg px-3 py-2">
                <span className="text-xs font-bold text-blue-400 uppercase w-10">Entry</span>
                <span className="text-sm font-bold text-trading-text flex-1">
                  {fmtPrice(signalDetails.entryRange.min, selectedPair)} — {fmtPrice(signalDetails.entryRange.max, selectedPair)}
                </span>
              </div>

              {/* TP1 */}
              <div className="flex items-center gap-3 bg-emerald-500/8 border border-emerald-500/20 rounded-lg px-3 py-2">
                <span className="text-xs font-bold text-emerald-300 uppercase w-10">TP1</span>
                <span className="text-sm font-bold text-trading-text flex-1">{fmtPrice(signalDetails.takeProfit1, selectedPair)}</span>
                <span className="text-xs text-emerald-300 font-medium">+{tp1Pips.toFixed(1)} pips</span>
              </div>

              {/* TP2 */}
              <div className="flex items-center gap-3 bg-emerald-500/10 border border-emerald-500/20 rounded-lg px-3 py-2">
                <span className="text-xs font-bold text-emerald-400 uppercase w-10">TP2</span>
                <span className="text-sm font-bold text-trading-text flex-1">{fmtPrice(signalDetails.takeProfit2, selectedPair)}</span>
                <span className="text-xs text-emerald-400 font-medium">+{tp2Pips.toFixed(1)} pips</span>
              </div>

              {/* TP3 */}
              <div className="flex items-center gap-3 bg-emerald-500/15 border border-emerald-500/25 rounded-lg px-3 py-2">
                <span className="text-xs font-bold text-emerald-400 uppercase w-10">TP3</span>
                <span className="text-sm font-bold text-trading-text flex-1">{fmtPrice(signalDetails.takeProfit3, selectedPair)}</span>
                <span className="text-xs text-emerald-400 font-medium">+{tp3Pips.toFixed(1)} pips</span>
              </div>
            </div>

            {/* Price ladder bar */}
            <div className="relative h-4 mt-4 mb-1 rounded-full overflow-hidden bg-trading-bg" role="img" aria-label="Visual price ladder">
              <div className={`absolute top-0 bottom-0 ${isBuy ? 'bg-red-500/25' : 'bg-emerald-500/25'}`} style={{ left: 0, width: `${leftZoneEnd}%` }} />
              <div className="absolute top-0 bottom-0 bg-blue-500/25" style={{ left: `${leftZoneEnd}%`, width: `${rightZoneStart - leftZoneEnd}%` }} />
              <div className={`absolute top-0 bottom-0 ${isBuy ? 'bg-emerald-500/25' : 'bg-red-500/25'}`} style={{ left: `${rightZoneStart}%`, width: `${100 - rightZoneStart}%` }} />
              <div className="absolute top-0 bottom-0 w-1 bg-red-500 rounded" style={{ left: `${slPct}%` }} />
              <div className="absolute top-0 bottom-0 w-1 bg-emerald-400 rounded" style={{ left: `${tp1Pct}%` }} />
              <div className="absolute top-0 bottom-0 w-1 bg-emerald-500 rounded" style={{ left: `${tp2Pct}%` }} />
              <div className="absolute top-0 bottom-0 w-1 bg-emerald-600 rounded" style={{ left: `${tp3Pct}%` }} />
              <div className="absolute -top-0.5 -bottom-0.5 w-1 bg-white z-10 rounded" style={{ left: `${currentPct}%` }}>
                <div className="absolute -top-5 left-1/2 -translate-x-1/2 text-[10px] font-bold text-white bg-trading-accent px-1.5 py-0.5 rounded whitespace-nowrap shadow">Now</div>
              </div>
            </div>
          </div>

          {/* RIGHT — Risk / Reward */}
          <div>
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-xs font-bold text-trading-muted uppercase tracking-wider flex items-center gap-1.5">
                <Shield size={14} /> Risk / Reward
              </h3>
              <span className={`px-2.5 py-1 rounded-md text-xs font-bold border ${rrQuality.bg}`}>
                {rrQuality.label} ({rr2.toFixed(1)} R:R)
              </span>
            </div>

            {/* R:R cards */}
            <div className="space-y-2">
              {[
                { label: 'TP1', rr: rr1, pips: tp1Pips, fill: 33 },
                { label: 'TP2', rr: rr2, pips: tp2Pips, fill: 67 },
                { label: 'TP3', rr: rr3, pips: tp3Pips, fill: 100 },
              ].map((tp) => (
                <div key={tp.label} className="bg-trading-bg border border-trading-border rounded-lg px-3 py-2 flex items-center gap-3">
                  <span className="text-xs font-bold text-emerald-400 w-8">{tp.label}</span>
                  <span className="text-sm font-bold text-trading-text w-12">1:{tp.rr.toFixed(1)}</span>
                  <div className="flex-1 h-2 bg-trading-card rounded-full overflow-hidden">
                    <div
                      className="h-full rounded-full bg-gradient-to-r from-emerald-500/60 to-emerald-400 transition-all duration-300"
                      style={{ width: `${tp.fill}%` }}
                    />
                  </div>
                  <span className="text-xs text-trading-muted w-16 text-right">{tp.pips.toFixed(1)} pips</span>
                </div>
              ))}
            </div>

            {/* Position sizing */}
            <div className="mt-4 bg-trading-bg border border-trading-border rounded-lg px-4 py-3">
              <h4 className="text-xs font-bold text-trading-muted uppercase tracking-wider mb-2">Account Risk</h4>
              <div className="flex items-baseline gap-2 flex-wrap">
                <span className="text-lg font-bold text-trading-text">{posSizeLots.toFixed(2)} lots</span>
                <span className="text-trading-muted">·</span>
                <span className="text-sm text-trading-text font-semibold">${riskAmount.toFixed(0)}</span>
                <span className="text-xs text-trading-muted">({riskPct}% risk)</span>
              </div>
            </div>

            {/* Copy Trading Status — shown when copy trading is enabled */}
            {copyTradingEnabled && (
              <div className="mt-3 bg-emerald-500/5 border border-emerald-500/20 rounded-lg px-4 py-3">
                <div className="flex items-center justify-between mb-2">
                  <h4 className="text-xs font-bold text-emerald-400 uppercase tracking-wider flex items-center gap-1.5">
                    <Copy size={12} /> Copy Trading Active
                  </h4>
                  {copyStats && (
                    <span className="text-xs text-trading-muted">
                      {copyStats.open_trades} open · {copyStats.win_rate.toFixed(0)}% win
                    </span>
                  )}
                </div>
                
                {/* Quick stats row */}
                {copyStats && (
                  <div className="flex gap-3 text-xs mb-2">
                    <span className="text-trading-muted">
                      Trades: <span className="text-trading-text font-semibold">{copyStats.total_trades}</span>
                    </span>
                    <span className="text-trading-muted">
                      P&L: <span className={`font-semibold ${copyStats.total_pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                        {copyStats.total_pnl >= 0 ? '+' : ''}${copyStats.total_pnl.toFixed(2)}
                      </span>
                    </span>
                  </div>
                )}

                {/* Open copied positions */}
                {copiedPositions && copiedPositions.length > 0 && (
                  <div className="space-y-1.5 mt-2">
                    {copiedPositions.slice(0, 3).map((pos) => (
                      <div key={pos.copy_trade_id} className="flex items-center gap-2 bg-trading-bg/50 rounded-md px-2.5 py-1.5">
                        <span className={`text-xs font-bold ${pos.direction === 'BUY' ? 'text-emerald-400' : 'text-red-400'}`}>
                          {pos.direction}
                        </span>
                        <span className="text-xs text-trading-text">{pos.symbol}</span>
                        <span className="text-xs text-trading-muted">{pos.quantity.toFixed(2)}L</span>
                        <span className="flex-1" />
                        <span className={`text-xs font-semibold ${pos.unrealized_pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                          {pos.unrealized_pnl >= 0 ? '+' : ''}{pos.unrealized_pnl.toFixed(2)}
                        </span>
                        <button
                          onClick={() => onCloseCopyTrade?.(pos.copy_trade_id)}
                          className="text-xs text-slate-500 hover:text-red-400 transition-colors"
                          aria-label={`Close ${pos.symbol} copy trade`}
                        >
                          ✕
                        </button>
                      </div>
                    ))}
                  </div>
                )}

                {/* Copy signal button */}
                {onCopySignal && !isExpired && (
                  <button
                    onClick={onCopySignal}
                    disabled={copyTradeLoading}
                    className="mt-2 w-full py-2 rounded-lg text-xs font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 hover:bg-emerald-500/30 transition-all duration-200 disabled:opacity-50 flex items-center justify-center gap-1.5"
                  >
                    {copyTradeLoading ? (
                      <><Loader2 size={12} className="animate-spin" /> Copying...</>
                    ) : (
                      <><Copy size={12} /> Copy This Signal</>
                    )}
                  </button>
                )}
              </div>
            )}
          </div>
        </div>
      </section>

      {/* ────────────────────────────────────────────────
          SECTION 3 — Analysis & Action (tabbed)
          ──────────────────────────────────────────────── */}
      <section className="border-t border-trading-border">
        {/* Tabs */}
        <div className="flex border-b border-trading-border">
          {([
            { key: 'indicators' as AnalysisTab, label: 'Indicators', icon: <BarChart3 size={14} /> },
            { key: 'multitf' as AnalysisTab, label: 'Multi-TF', icon: <Clock size={14} /> },
            { key: 'analysis' as AnalysisTab, label: 'Analysis', icon: <ChevronRight size={14} /> },
            { key: 'copyhistory' as AnalysisTab, label: 'Copy Trades', icon: <Copy size={14} /> },
          ]).map((tab) => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`flex items-center gap-1.5 px-5 py-2.5 text-sm font-semibold transition-all duration-200 border-b-2 ${
                activeTab === tab.key
                  ? 'border-trading-accent text-trading-accent'
                  : 'border-transparent text-trading-muted hover:text-trading-text'
              }`}
            >
              {tab.icon} {tab.label}
            </button>
          ))}
        </div>

        {/* Tab content */}
        <div className="px-5 py-4 transition-all duration-200">

          {/* ── Indicators tab ── */}
          {activeTab === 'indicators' && (
            <div>
              <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-2">
                {signalDetails.indicators.map((ind) => {
                  const dotColor = ind.signal === 'bullish' ? 'bg-emerald-500' : ind.signal === 'bearish' ? 'bg-red-500' : 'bg-yellow-500'
                  const borderColor = ind.signal === 'bullish' ? 'border-emerald-500/20' : ind.signal === 'bearish' ? 'border-red-500/20' : 'border-yellow-500/20'
                  return (
                    <div key={ind.name} className={`bg-trading-bg border ${borderColor} rounded-lg px-3 py-2.5 text-center`}>
                      <div className="text-xs font-bold text-trading-muted uppercase tracking-wide">{ind.name}</div>
                      <div className="text-sm font-bold text-trading-text mt-1">{ind.value}</div>
                      <div className="flex justify-center mt-1.5">
                        <span className={`inline-block h-2.5 w-2.5 rounded-full ${dotColor}`} />
                      </div>
                    </div>
                  )
                })}
              </div>

              {/* Consensus bar */}
              <div className="mt-4 flex items-center gap-3">
                <span className="text-xs font-semibold text-trading-muted uppercase tracking-wide">Consensus</span>
                <div className="flex-1 h-3 bg-trading-bg rounded-full overflow-hidden flex">
                  {bullish > 0 && (
                    <div className="bg-emerald-500 h-full transition-all duration-300" style={{ width: `${(bullish / totalIndicators) * 100}%` }} />
                  )}
                  {neutral > 0 && (
                    <div className="bg-yellow-500 h-full transition-all duration-300" style={{ width: `${(neutral / totalIndicators) * 100}%` }} />
                  )}
                  {bearish > 0 && (
                    <div className="bg-red-500 h-full transition-all duration-300" style={{ width: `${(bearish / totalIndicators) * 100}%` }} />
                  )}
                </div>
                <span className="text-xs text-trading-muted whitespace-nowrap">
                  <span className="text-emerald-400 font-semibold">{bullish}</span> Bull · <span className="text-red-400 font-semibold">{bearish}</span> Bear · <span className="text-yellow-400 font-semibold">{neutral}</span> Neutral
                </span>
              </div>
            </div>
          )}

          {/* ── Multi-TF tab ── */}
          {activeTab === 'multitf' && (
            <div>
              {multiTimeframe && multiTimeframe.length > 0 ? (
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                  {multiTimeframe.map((mtf) => {
                    const tfColor = mtf.signal === 'BUY' ? 'border-emerald-500/30 bg-emerald-500/5' : mtf.signal === 'SELL' ? 'border-red-500/30 bg-red-500/5' : 'border-yellow-500/30 bg-yellow-500/5'
                    const tfTextColor = mtf.signal === 'BUY' ? 'text-emerald-400' : mtf.signal === 'SELL' ? 'text-red-400' : 'text-yellow-400'
                    return (
                      <div key={mtf.tf} className={`border rounded-lg px-4 py-3 text-center ${tfColor}`}>
                        <div className="text-xs font-bold text-trading-muted uppercase">{mtf.tf}</div>
                        <div className={`text-lg font-extrabold mt-1 ${tfTextColor}`}>{mtf.signal}</div>
                        <div className="mt-2 h-1.5 bg-trading-bg rounded-full overflow-hidden">
                          <div
                            className={`h-full rounded-full transition-all duration-300 ${mtf.signal === 'BUY' ? 'bg-emerald-500' : mtf.signal === 'SELL' ? 'bg-red-500' : 'bg-yellow-500'}`}
                            style={{ width: `${mtf.alignment}%` }}
                          />
                        </div>
                        <div className="text-xs text-trading-muted mt-1">{mtf.alignment}%</div>
                      </div>
                    )
                  })}
                </div>
              ) : (
                <p className="text-sm text-trading-muted text-center py-4">No multi-timeframe data available</p>
              )}
            </div>
          )}

          {/* ── Analysis tab ── */}
          {activeTab === 'analysis' && (
            <div className="space-y-4">
              <div className="bg-trading-bg border border-trading-border rounded-lg px-4 py-3">
                <h4 className="text-xs font-bold text-trading-muted uppercase tracking-wider mb-2">AI Analysis</h4>
                <p className="text-sm text-trading-text leading-relaxed">{signalDetails.reason}</p>
              </div>

              {/* Consensus stacked bar */}
              <div>
                <h4 className="text-xs font-bold text-trading-muted uppercase tracking-wider mb-2">Indicator Consensus</h4>
                <div className="flex items-center gap-3">
                  <div className="flex-1 h-4 bg-trading-bg rounded-full overflow-hidden flex">
                    {bullish > 0 && (
                      <div className="bg-emerald-500 h-full flex items-center justify-center transition-all duration-300" style={{ width: `${(bullish / totalIndicators) * 100}%` }}>
                        <span className="text-[10px] font-bold text-white">{Math.round((bullish / totalIndicators) * 100)}%</span>
                      </div>
                    )}
                    {neutral > 0 && (
                      <div className="bg-yellow-500 h-full flex items-center justify-center transition-all duration-300" style={{ width: `${(neutral / totalIndicators) * 100}%` }}>
                        <span className="text-[10px] font-bold text-white">{Math.round((neutral / totalIndicators) * 100)}%</span>
                      </div>
                    )}
                    {bearish > 0 && (
                      <div className="bg-red-500 h-full flex items-center justify-center transition-all duration-300" style={{ width: `${(bearish / totalIndicators) * 100}%` }}>
                        <span className="text-[10px] font-bold text-white">{Math.round((bearish / totalIndicators) * 100)}%</span>
                      </div>
                    )}
                  </div>
                </div>
                <div className="flex gap-4 mt-2 text-xs text-trading-muted">
                  <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-emerald-500" /> Bullish ({bullish})</span>
                  <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-yellow-500" /> Neutral ({neutral})</span>
                  <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-red-500" /> Bearish ({bearish})</span>
                </div>
              </div>

              {/* Market regime */}
              <div className="flex items-center gap-2 text-sm text-trading-muted">
                {regimeIcon()} Market Regime: <span className="text-trading-text font-semibold">{regimeLabel()}</span>
                <span className="text-trading-muted">·</span>
                Timeframe: <span className="text-trading-text font-semibold">{signalDetails.timeframe.toUpperCase()}</span>
              </div>

              {topPatterns.length > 0 && (
                <div className="bg-trading-bg border border-trading-border rounded-lg px-4 py-3">
                  <h4 className="text-xs font-bold text-trading-muted uppercase tracking-wider mb-3">Detected Patterns</h4>
                  <div className="space-y-2">
                    {topPatterns.map((pattern) => (
                      <div key={`${pattern.name}-${pattern.targetPrice}`} className="rounded-lg border border-trading-border bg-trading-card px-3 py-2">
                        <div className="flex items-center justify-between gap-3">
                          <div>
                            <div className="text-sm font-semibold text-trading-text">{pattern.name}</div>
                            <div className="text-xs text-trading-muted">{pattern.description}</div>
                          </div>
                          <div className="text-right">
                            <div className={`text-sm font-bold ${pattern.direction === 'bullish' ? 'text-emerald-400' : 'text-red-400'}`}>
                              {pattern.confidence}%
                            </div>
                            <div className="text-xs text-trading-muted">Target {fmtPrice(pattern.targetPrice, selectedPair)}</div>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* ── Copy History tab ── */}
          {activeTab === 'copyhistory' && (
            <div>
              {copiedPositions && copiedPositions.length > 0 ? (
                <div className="space-y-2">
                  {copiedPositions.map((pos) => (
                    <div key={pos.copy_trade_id} className="bg-trading-bg border border-trading-border rounded-lg px-3 py-2.5 flex items-center gap-3">
                      <span className={`text-xs font-bold px-2 py-0.5 rounded ${
                        pos.direction === 'BUY' ? 'bg-emerald-500/20 text-emerald-400' : 'bg-red-500/20 text-red-400'
                      }`}>
                        {pos.direction}
                      </span>
                      <div className="flex-1 min-w-0">
                        <div className="text-sm font-semibold text-trading-text">{pos.symbol}</div>
                        <div className="text-xs text-trading-muted">
                          {pos.quantity.toFixed(2)} lots @ {fmtPrice(pos.entry_price, selectedPair)} · Conf {pos.confidence}%
                        </div>
                      </div>
                      <div className="text-right">
                        <div className={`text-sm font-bold ${pos.unrealized_pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                          {pos.unrealized_pnl >= 0 ? '+' : ''}${pos.unrealized_pnl.toFixed(2)}
                        </div>
                        <div className="text-xs text-trading-muted">
                          {fmtPrice(pos.current_price, selectedPair)}
                        </div>
                      </div>
                      <button
                        onClick={() => onCloseCopyTrade?.(pos.copy_trade_id)}
                        className="p-1.5 rounded hover:bg-red-500/20 text-slate-500 hover:text-red-400 transition-colors"
                        aria-label="Close position"
                      >
                        <X size={14} />
                      </button>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-center py-6">
                  <Copy size={24} className="mx-auto text-slate-600 mb-2" />
                  <p className="text-sm text-trading-muted">No copied trades yet</p>
                  <p className="text-xs text-slate-600 mt-1">Enable copy trading and click "Copy This Signal" to start</p>
                </div>
              )}
              
              {/* Stats summary */}
              {copyStats && copyStats.total_trades > 0 && (
                <div className="mt-3 grid grid-cols-4 gap-2">
                  <div className="bg-trading-bg rounded-lg px-2 py-1.5 text-center">
                    <div className="text-xs text-trading-muted">Total</div>
                    <div className="text-sm font-bold text-trading-text">{copyStats.total_trades}</div>
                  </div>
                  <div className="bg-trading-bg rounded-lg px-2 py-1.5 text-center">
                    <div className="text-xs text-trading-muted">Win Rate</div>
                    <div className="text-sm font-bold text-trading-text">{copyStats.win_rate.toFixed(0)}%</div>
                  </div>
                  <div className="bg-trading-bg rounded-lg px-2 py-1.5 text-center">
                    <div className="text-xs text-trading-muted">Open</div>
                    <div className="text-sm font-bold text-trading-text">{copyStats.open_trades}</div>
                  </div>
                  <div className="bg-trading-bg rounded-lg px-2 py-1.5 text-center">
                    <div className="text-xs text-trading-muted">P&L</div>
                    <div className={`text-sm font-bold ${copyStats.total_pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                      ${copyStats.total_pnl.toFixed(0)}
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        {/* ── Action Bar ── */}
        <div className="border-t border-trading-border px-5 py-4">
          {/* Signal status alert */}
          {signalStatus === 'OPTIMAL_ENTRY' && (
            <div className="flex items-center gap-2 text-sm text-emerald-300 mb-3 bg-emerald-500/10 border border-emerald-500/20 rounded-lg px-3 py-2">
              <Zap size={16} className="text-emerald-400 shrink-0" />
              <span className="font-medium">Optimal entry window — act now</span>
            </div>
          )}
          {signalStatus === 'ABOUT_TO_EXPIRE' && (
            <div className="flex items-center gap-2 text-sm text-amber-300 mb-3 bg-amber-500/10 border border-amber-500/20 rounded-lg px-3 py-2">
              <AlertTriangle size={16} className="text-amber-400 shrink-0" />
              <span className="font-medium">Signal expiring soon</span>
            </div>
          )}
          {signalStatus === 'EXPIRED' && (
            <div className="flex items-center gap-2 text-sm text-gray-300 mb-3 bg-gray-500/10 border border-gray-500/20 rounded-lg px-3 py-2">
              <AlertTriangle size={16} className="text-gray-400 shrink-0" />
              <span className="font-medium">Signal expired — wait for fresh signal</span>
            </div>
          )}

          <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3">
            {/* Risk slider */}
            <div className="flex items-center gap-3 flex-1 min-w-0">
              <label htmlFor="ai-hub-risk" className="text-xs text-trading-muted whitespace-nowrap font-semibold">
                Risk: <span className="text-trading-text">{riskPct}%</span>
              </label>
              <input
                id="ai-hub-risk"
                type="range"
                min="0.5"
                max="5"
                step="0.5"
                value={riskPct}
                onChange={(e) => setRiskPct(parseFloat(e.target.value))}
                className="flex-1 h-2 min-w-[80px] accent-trading-accent cursor-pointer"
                aria-label={`Risk percentage: ${riskPct}%`}
              />
              <span className="text-xs text-trading-muted whitespace-nowrap">
                {posSizeLots.toFixed(2)} lots · ${riskAmount.toFixed(0)} risk
              </span>
            </div>

            {/* Trade buttons */}
            <div className="flex gap-2 shrink-0 w-full sm:w-auto">
              <button
                onClick={onBuy}
                disabled={isExpired}
                aria-label={isExpired ? 'Buy — Signal Expired' : `Buy ${selectedPair.symbol}`}
                className={`btn-buy flex-1 sm:flex-initial px-6 min-h-[48px] text-base font-bold rounded-lg flex items-center justify-center gap-2 transition-all duration-200 ${
                  isBuyish(signalDetails.signal) && !isExpired
                    ? 'ring-2 ring-emerald-400 shadow-lg shadow-emerald-500/25'
                    : ''
                } ${isExpired ? 'opacity-50 cursor-not-allowed' : 'hover:brightness-110 active:scale-[0.98]'}`}
              >
                <TrendingUp size={18} />
                {isExpired ? 'Expired' : 'BUY'}
              </button>
              <button
                onClick={onSell}
                disabled={isExpired}
                aria-label={isExpired ? 'Sell — Signal Expired' : `Sell ${selectedPair.symbol}`}
                className={`btn-sell flex-1 sm:flex-initial px-6 min-h-[48px] text-base font-bold rounded-lg flex items-center justify-center gap-2 transition-all duration-200 ${
                  isSellish(signalDetails.signal) && !isExpired
                    ? 'ring-2 ring-red-400 shadow-lg shadow-red-500/25'
                    : ''
                } ${isExpired ? 'opacity-50 cursor-not-allowed' : 'hover:brightness-110 active:scale-[0.98]'}`}
              >
                <TrendingDown size={18} />
                {isExpired ? 'Expired' : 'SELL'}
              </button>
            </div>
          </div>
        </div>
      </section>
    </article>
  )
}

export default AITradingHub
export { AITradingHub }
