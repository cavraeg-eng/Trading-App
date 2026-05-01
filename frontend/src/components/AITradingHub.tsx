import { useState, useEffect, useMemo, useRef, useCallback } from 'react'
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
  CalendarDays,
  X,
  Minus,
  Play,
  XCircle,
} from 'lucide-react'
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts'
import type { AIScoreData, DetectedPattern, ForexPair, SignalStatus, AlignmentData, SignalBacktestResult, SourceMetadata, CopyTradePosition, CopyTradeStats, NoTradeReasonDetail } from '../types'
import api from '../lib/api'
import { formatDateTimeWithZone } from '../lib/time'
import { DataSourceBadge } from './DataSourceBadge'
import { FreshnessPill } from './FreshnessPill'
import { DataQualityBanner } from './DataQualityBanner'

/* ────────────────────────────────────────────────────────────
   Copy Trading Types
   ──────────────────────────────────────────────────────────── */
/* ────────────────────────────────────────────────────────────
   AI Score API response shape
   ──────────────────────────────────────────────────────────── */
interface AIScoreResponse {
  symbol: string
  score: number
  label: string
  change: number
  dataSource?: string
  dataQuality?: string[]
  freshnessSeconds?: number | null
  factors: {
    modelConfidence: number
    indicatorConsensus: number
    marketRegimeFit: number
    patternStrength: number
    sentimentScore: number
    volumeMomentum: number
  }
  timestamp: string
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
    confidenceBand?: string
    noTradeReasons?: NoTradeReasonDetail[]
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
  copiedPositions?: CopyTradePosition[]
  copyHistory?: CopyTradePosition[]
  copyStats?: CopyTradeStats | null
  copyHistorySymbolFilter?: string
  onCopyHistorySymbolFilterChange?: (value: string) => void
  copyHistoryDirectionFilter?: 'ALL' | 'BUY' | 'SELL'
  onCopyHistoryDirectionFilterChange?: (value: 'ALL' | 'BUY' | 'SELL') => void
  copyHistoryStatusFilter?: string
  onCopyHistoryStatusFilterChange?: (value: string) => void
  copyHistoryRangeFilter?: 'all' | '7d' | '30d' | '90d'
  onCopyHistoryRangeFilterChange?: (value: 'all' | '7d' | '30d' | '90d') => void
  onCopySignal?: () => void
  onCloseCopyTrade?: (copyTradeId: string) => void
  copyTradeLoading?: boolean
  riskPct: number
  onRiskPctChange: (riskPct: number) => void
  copyDisabledReason?: string | null
  dataFreshness?: 'live' | 'delayed' | 'stale'
  lastUpdatedMs?: number
  quoteSource?: string
  activeTimeframe?: string
  sourceMetadata?: SourceMetadata | null
  forceShowTradeControls?: boolean
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

const formatTradeTimestamp = (timestamp?: number | null) => {
  if (!timestamp) return '—'
  return formatDateTimeWithZone(timestamp * 1000)
}

const scoreColor = (v: number) => {
  if (v >= 80) return { ring: 'stroke-emerald-400', text: 'text-emerald-400', bg: 'bg-emerald-500' }
  if (v >= 65) return { ring: 'stroke-emerald-500', text: 'text-emerald-500', bg: 'bg-emerald-500' }
  if (v >= 40) return { ring: 'stroke-amber-400', text: 'text-amber-400', bg: 'bg-amber-400' }
  return { ring: 'stroke-red-400', text: 'text-red-400', bg: 'bg-red-400' }
}

const factorColor = (v: number) => {
  if (v >= 80) return 'bg-emerald-400'
  if (v >= 65) return 'bg-emerald-500'
  if (v >= 40) return 'bg-amber-400'
  return 'bg-red-400'
}

const FACTOR_LABELS: Record<string, string> = {
  modelConfidence: 'Model Confidence',
  indicatorConsensus: 'Indicator Consensus',
  marketRegimeFit: 'Market Regime Fit',
  patternStrength: 'Pattern Strength',
  sentimentScore: 'Sentiment',
  volumeMomentum: 'Volume Momentum',
}

type AnalysisTab = 'indicators' | 'multitf' | 'analysis' | 'copyhistory'

/* ────────────────────────────────────────────────────────────
   Circular Gauge SVG component
   ──────────────────────────────────────────────────────────── */
function ScoreGauge({ score, label }: { score: number; label: string }) {
  const radius = 52
  const stroke = 8
  const circumference = 2 * Math.PI * radius
  const progress = Math.min(100, Math.max(0, score)) / 100
  const offset = circumference * (1 - progress)
  const colors = scoreColor(score)

  return (
    <div className="flex flex-col items-center">
      <svg width={130} height={130} viewBox="0 0 130 130" className="drop-shadow-lg">
        <circle cx="65" cy="65" r={radius} fill="none" stroke="currentColor" strokeWidth={stroke} className="text-trading-bg" />
        <circle
          cx="65" cy="65" r={radius} fill="none"
          strokeWidth={stroke} strokeLinecap="round"
          className={colors.ring}
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          transform="rotate(-90 65 65)"
          style={{ transition: 'stroke-dashoffset 0.6s ease' }}
        />
        <text x="65" y="60" textAnchor="middle" className={`fill-current ${colors.text}`} fontSize="32" fontWeight="800">{score}</text>
        <text x="65" y="80" textAnchor="middle" className="fill-current text-trading-muted" fontSize="11" fontWeight="600">{label}</text>
      </svg>
    </div>
  )
}

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
  copyHistory,
  copyStats,
  copyHistorySymbolFilter = 'all',
  onCopyHistorySymbolFilterChange,
  copyHistoryDirectionFilter = 'ALL',
  onCopyHistoryDirectionFilterChange,
  copyHistoryStatusFilter = 'all',
  onCopyHistoryStatusFilterChange,
  copyHistoryRangeFilter = 'all',
  onCopyHistoryRangeFilterChange,
  onCopySignal,
  onCloseCopyTrade,
  copyTradeLoading,
  riskPct,
  onRiskPctChange,
  copyDisabledReason,
  dataFreshness = 'stale',
  lastUpdatedMs,
  quoteSource = 'unknown',
  activeTimeframe,
  sourceMetadata,
  forceShowTradeControls = false,
}: AITradingHubProps) {
  const [activeTab, setActiveTab] = useState<AnalysisTab>('indicators')

  /* ── AI Score state ── */
  const [aiScoreData, setAiScoreData] = useState<AIScoreResponse | null>(null)
  const [aiScoreLoading, setAiScoreLoading] = useState(false)
  const aiScorePollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  /* ── Alignment state ── */
  const [alignmentData, setAlignmentData] = useState<AlignmentData | null>(null)
  const [alignmentLoading, setAlignmentLoading] = useState(false)
  const alignmentPairRef = useRef<string>('')

  /* ── Backtest state ── */
  const [backtestResult, setBacktestResult] = useState<SignalBacktestResult | null>(null)
  const [backtestLoading, setBacktestLoading] = useState(false)
  const [backtestOpen, setBacktestOpen] = useState(false)

  /* ── Fetch AI Score ── */
  const fetchScore = useCallback(async () => {
    try {
      const data = await api.fetchAIScore(selectedPair.symbol, signalDetails.timeframe, tradeStyle)
      setAiScoreData(data)
    } catch { /* silent */ }
  }, [selectedPair.symbol, signalDetails.timeframe, tradeStyle])

  useEffect(() => {
    setAiScoreLoading(true)
    fetchScore().finally(() => setAiScoreLoading(false))

    if (aiScorePollRef.current) clearInterval(aiScorePollRef.current)
    aiScorePollRef.current = setInterval(fetchScore, 30_000)
    return () => { if (aiScorePollRef.current) clearInterval(aiScorePollRef.current) }
  }, [fetchScore])

  /* ── Fetch Alignment when multitf tab selected ── */
  useEffect(() => {
    if (activeTab !== 'multitf') return
    if (alignmentPairRef.current === selectedPair.symbol && alignmentData) return

    setAlignmentLoading(true)
    api.fetchAlignment(selectedPair.symbol, tradeStyle)
      .then((d) => { setAlignmentData(d); alignmentPairRef.current = selectedPair.symbol })
      .catch(() => { /* silent */ })
      .finally(() => setAlignmentLoading(false))
  }, [activeTab, selectedPair.symbol, tradeStyle])

  // Reset alignment cache on pair change
  useEffect(() => { alignmentPairRef.current = '' }, [selectedPair.symbol])

  /* ── Run Backtest ── */
  const runBacktest = useCallback(async () => {
    setBacktestLoading(true)
    setBacktestOpen(true)
    try {
      const direction = isBuyish(signalDetails.signal) ? 'BUY' : isSellish(signalDetails.signal) ? 'SELL' : 'BUY'
      const result = await api.backtestSignal({
        symbol: selectedPair.symbol,
        timeframe: signalDetails.timeframe,
        direction,
        lookback_days: 90,
        initial_balance: accountBalance,
        risk_percent: riskPct,
      })
      setBacktestResult(result)
    } catch { /* silent */ }
    setBacktestLoading(false)
  }, [selectedPair.symbol, signalDetails.signal, signalDetails.timeframe, accountBalance, riskPct])

  /* ── derived values ── */
  const displayConf = useMemo(
    () =>
      signalDetails.confidence > 1
        ? Math.round(signalDetails.confidence)
        : Math.round(signalDetails.confidence * 100),
    [signalDetails.confidence],
  )

  const entryMid = (signalDetails.entryRange.min + signalDetails.entryRange.max) / 2
  const isNoTrade = signalDetails.signal === 'hold' && Boolean(signalDetails.noTradeReasons?.length)

  const hasValidData =
    isNoTrade || (signalDetails.stopLoss !== 0 &&
    signalDetails.stopLoss !== signalDetails.entryRange.min &&
    signalDetails.entryRange.min !== signalDetails.entryRange.max)

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
  const copyButtonDisabled = Boolean(copyTradeLoading || copyDisabledReason)
  const copyLifecycleTone = (status: string) => {
    if (status === 'closed_tp3') return 'bg-emerald-500/10 text-emerald-300 border-emerald-500/30'
    if (status === 'partial_tp2') return 'bg-blue-500/10 text-blue-300 border-blue-500/30'
    if (status === 'partial_tp1') return 'bg-amber-500/10 text-amber-300 border-amber-500/30'
    return 'bg-slate-500/10 text-slate-300 border-slate-500/30'
  }
  const formatDuration = (seconds?: number | null) => {
    if (seconds == null) return '—'
    if (seconds < 60) return `${Math.round(seconds)}s`
    if (seconds < 3600) return `${Math.round(seconds / 60)}m`
    if (seconds < 86400) return `${(seconds / 3600).toFixed(1)}h`
    return `${(seconds / 86400).toFixed(1)}d`
  }
  const closedHistory = useMemo(
    () => (copyHistory ?? []).filter((trade) => !['open', 'partial_tp1', 'partial_tp2'].includes(trade.status)),
    [copyHistory],
  )
  const exportHref = useMemo(() => {
    const params = new URLSearchParams()
    params.set('limit', '200')
    if (copyHistorySymbolFilter !== 'all') params.set('symbol', copyHistorySymbolFilter)
    if (copyHistoryDirectionFilter !== 'ALL') params.set('direction', copyHistoryDirectionFilter)
    if (copyHistoryStatusFilter !== 'all') params.set('status', copyHistoryStatusFilter)
    const nowSeconds = Math.floor(Date.now() / 1000)
    if (copyHistoryRangeFilter === '7d') params.set('from_ts', String(nowSeconds - 7 * 24 * 60 * 60))
    if (copyHistoryRangeFilter === '30d') params.set('from_ts', String(nowSeconds - 30 * 24 * 60 * 60))
    if (copyHistoryRangeFilter === '90d') params.set('from_ts', String(nowSeconds - 90 * 24 * 60 * 60))
    return `/api/copy-trading/history/export?${params.toString()}`
  }, [copyHistoryDirectionFilter, copyHistoryRangeFilter, copyHistoryStatusFilter, copyHistorySymbolFilter])

  const rrQuality = useMemo(() => {
    if (rr2 >= 3) return { label: 'Excellent', cls: 'text-emerald-300', bg: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/30' }
    if (rr2 >= 2) return { label: 'Good', cls: 'text-emerald-400', bg: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/30' }
    if (rr2 >= 1) return { label: 'Decent', cls: 'text-yellow-400', bg: 'bg-yellow-500/20 text-yellow-300 border-yellow-500/30' }
    return { label: 'Poor', cls: 'text-red-400', bg: 'bg-red-500/20 text-red-300 border-red-500/30' }
  }, [rr2])

  const executionWarning = useMemo(() => {
    if (!sourceMetadata) return null
    if (sourceMetadata.qualityFlags?.includes('stale_data')) {
      return 'Execution risk elevated: data is stale.'
    }
    if (sourceMetadata.isFallback || sourceMetadata.qualityFlags?.includes('fallback_source')) {
      return 'Execution caution: fallback source active.'
    }
    if (sourceMetadata.qualityFlags?.includes('synthetic_spot')) {
      return 'Execution note: synthetic spot derived from futures candles.'
    }
    return null
  }, [sourceMetadata])

  const sourceContextLabel = useMemo(() => {
    if (!sourceMetadata) return null
    if (tradeStyle === 'scalp') return 'Scalp Mode'
    if (selectedPair.symbol === 'XAU/USD') return 'Swing Mode'
    return null
  }, [selectedPair.symbol, sourceMetadata, tradeStyle])

  const sourceContextDescription = useMemo(() => {
    if (!sourceMetadata) return null
    if (tradeStyle === 'scalp') {
      return 'Scalp uses live spot-adjusted XAU pricing on 1m/5m.'
    }
    if (selectedPair.symbol === 'XAU/USD') {
      return 'Swing uses futures-backed XAU context with 15m quote polling.'
    }
    return null
  }, [selectedPair.symbol, sourceMetadata, tradeStyle])

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
  const topPatterns = signalDetails.patterns ?? []
  const noTradeReasons = signalDetails.noTradeReasons ?? []

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
  if (!hasValidData && !forceShowTradeControls) {
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
            {isNoTrade ? 'NO TRADE' : signalLabel(signalDetails.signal)}
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
          {signalDetails.confidenceBand && (
            <span className="rounded-md border border-trading-border bg-trading-bg px-2 py-0.5 text-[11px] font-semibold uppercase text-trading-muted">
              {signalDetails.confidenceBand.replace('_', ' ')}
            </span>
          )}

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
          {sourceMetadata && (
            <>
              <DataSourceBadge
                sourceType={sourceMetadata.sourceType}
                sourceName={sourceMetadata.sourceName}
                contextLabel={sourceContextLabel ?? undefined}
              />
              <FreshnessPill freshnessSeconds={sourceMetadata.freshnessSeconds} marketStatus={sourceMetadata.marketStatus} />
            </>
          )}
          <span className="text-trading-muted">
            Updated {lastUpdatedLabel}
          </span>
          {activeTimeframe && (
            <span className="text-trading-muted">
              · TF {activeTimeframe}
            </span>
          )}
          <span className="text-trading-muted">
            · Source {sourceMetadata?.sourceName ?? quoteSource}
          </span>
        </div>
        {sourceContextDescription && (
          <div className="mt-2 text-xs text-trading-muted">
            {sourceContextDescription}
          </div>
        )}
        {sourceMetadata && <div className="mt-2"><DataQualityBanner qualityFlags={sourceMetadata.qualityFlags} /></div>}
        {executionWarning && (
          <div className="mt-2 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs font-medium text-red-200">
            {executionWarning}
          </div>
        )}

        {/* ── AI Score Hero Display + Patterns ── */}
        <div className="mt-3 grid grid-cols-1 lg:grid-cols-[minmax(0,320px)_1fr] gap-3">
          {/* AI Score Gauge + Factors */}
          <div className="rounded-xl border border-trading-border bg-trading-bg/70 px-4 py-4">
            {aiScoreLoading && !aiScoreData ? (
              <div className="flex items-center justify-center py-6">
                <Loader2 size={24} className="animate-spin text-slate-500" />
              </div>
            ) : aiScoreData ? (
              <>
                <div className="flex items-start gap-4">
                  <ScoreGauge score={aiScoreData.score} label={aiScoreData.label} />
                  <div className="flex-1 min-w-0 pt-2">
                    <div className="text-[11px] uppercase tracking-wider text-trading-muted font-semibold">AI Score</div>
                    {/* Score trend */}
                    <div className="mt-1 flex items-center gap-1.5">
                      {aiScoreData.change > 0 ? (
                        <TrendingUp size={14} className="text-emerald-400" />
                      ) : aiScoreData.change < 0 ? (
                        <TrendingDown size={14} className="text-red-400" />
                      ) : (
                        <Minus size={14} className="text-slate-400" />
                      )}
                      <span className={`text-xs font-semibold ${
                        (aiScoreData.change ?? 0) > 0 ? 'text-emerald-400' : (aiScoreData.change ?? 0) < 0 ? 'text-red-400' : 'text-slate-400'
                      }`}>
                        {(aiScoreData.change ?? 0) > 0 ? 'Improving' : (aiScoreData.change ?? 0) < 0 ? 'Declining' : 'Stable'}
                        {(aiScoreData.change ?? 0) !== 0 && ` (${(aiScoreData.change ?? 0) > 0 ? '+' : ''}${Number(aiScoreData.change ?? 0).toFixed(1)})`}
                      </span>
                    </div>
                  </div>
                </div>
                {/* Factor breakdown — 2-column grid */}
                <div className="mt-3 grid grid-cols-2 gap-x-3 gap-y-2">
                  {Object.entries(aiScoreData.factors).map(([key, val]) => (
                    <div key={key}>
                      <div className="flex items-center justify-between text-[11px] mb-0.5">
                        <span className="text-trading-muted truncate">{FACTOR_LABELS[key] ?? key}</span>
                        <span className="text-trading-text font-semibold ml-1">{Math.round(val)}</span>
                      </div>
                      <div className="h-1.5 bg-trading-card rounded-full overflow-hidden">
                        <div
                          className={`h-full rounded-full transition-all duration-500 ${factorColor(val)}`}
                          style={{ width: `${Math.min(100, val)}%` }}
                        />
                      </div>
                    </div>
                  ))}
                </div>
              </>
            ) : signalDetails.aiScore ? (
              /* Fallback: use aiScore from signalDetails (existing data) */
              <>
                <div className="text-[11px] uppercase tracking-wider text-trading-muted font-semibold">AI Score</div>
                <div className="mt-1 flex items-end gap-2">
                  <span className="text-2xl font-extrabold text-trading-text">{signalDetails.aiScore.value}</span>
                  <span className="text-sm font-semibold text-trading-accent">{signalDetails.aiScore.label}</span>
                </div>
                <div className="mt-2 h-2 rounded-full bg-trading-card overflow-hidden">
                  <div
                    className={`h-full rounded-full bg-gradient-to-r ${
                      signalDetails.aiScore.value >= 75 ? 'from-emerald-500 to-emerald-400' : signalDetails.aiScore.value >= 55 ? 'from-yellow-500 to-yellow-400' : 'from-red-500 to-red-400'
                    }`}
                    style={{ width: `${signalDetails.aiScore.value}%` }}
                  />
                </div>
                <div className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 text-[11px] text-trading-muted">
                  <span>Model {Math.round(signalDetails.aiScore.factors.modelConfidence)}</span>
                  <span>Consensus {Math.round(signalDetails.aiScore.factors.indicatorConsensus)}</span>
                  <span>Regime {Math.round(signalDetails.aiScore.factors.marketRegimeFit)}</span>
                  <span>Pattern {Math.round(signalDetails.aiScore.factors.patternStrength)}</span>
                </div>
              </>
            ) : null}
          </div>

          {/* Pattern recognition */}
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

        {noTradeReasons.length > 0 && (
          <div className="mt-3 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2">
            <div className="flex items-center gap-2 text-sm font-bold text-amber-300">
              <AlertTriangle size={15} /> Stand aside — no-trade gates active
            </div>
            <div className="mt-2 flex flex-wrap gap-2">
              {noTradeReasons.map((reason) => (
                <span key={`${reason.code}-${reason.message}`} className="rounded-md border border-amber-500/20 bg-trading-bg/70 px-2 py-1 text-xs text-trading-text">
                  <span className="font-semibold uppercase text-amber-300">{reason.code.replace(/_/g, ' ')}</span>
                  <span className="text-trading-muted"> · {reason.message}</span>
                </span>
              ))}
            </div>
          </div>
        )}
      </section>

      {/* ────────────────────────────────────────────────
          SECTION 2 — Trade Levels (two-column)
          ──────────────────────────────────────────────── */}
      {!isNoTrade && <section className="border-t border-trading-border px-5 py-4">
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
                        <span className="text-xs text-trading-muted">{(pos.remaining_quantity ?? pos.quantity).toFixed(2)}L live</span>
                        {pos.partial_exit_count ? (
                          <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded border ${copyLifecycleTone(pos.status)}`}>
                            {pos.partial_exit_count} partial
                          </span>
                        ) : null}
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
                {onCopySignal && (
                  <button
                    onClick={onCopySignal}
                    disabled={copyButtonDisabled}
                    title={copyDisabledReason ?? undefined}
                    className="mt-2 w-full py-2 rounded-lg text-xs font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 hover:bg-emerald-500/30 transition-all duration-200 disabled:opacity-50 flex items-center justify-center gap-1.5"
                  >
                    {copyTradeLoading ? (
                      <><Loader2 size={12} className="animate-spin" /> Copying...</>
                    ) : (
                      <><Copy size={12} /> Copy This Signal</>
                    )}
                  </button>
                )}
                {copyDisabledReason && (
                  <p className="mt-2 text-[11px] text-amber-300">{copyDisabledReason}</p>
                )}
              </div>
            )}
          </div>
        </div>
      </section>}

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
            { key: 'copyhistory' as AnalysisTab, label: 'Open Copies', icon: <Copy size={14} /> },
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

          {/* ── Multi-TF tab (Enhanced) ── */}
          {activeTab === 'multitf' && (
            <div>
              {alignmentLoading && !alignmentData ? (
                <div className="flex items-center justify-center py-8">
                  <Loader2 size={24} className="animate-spin text-slate-500" />
                  <span className="ml-2 text-sm text-trading-muted">Loading alignment data…</span>
                </div>
              ) : alignmentData ? (
                <>
                  {/* Alignment badge + Dominant direction */}
                  <div className="flex items-center gap-3 flex-wrap mb-4">
                    <span className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-bold border ${
                      alignmentData.alignmentScore >= 70
                        ? 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30'
                        : alignmentData.alignmentScore >= 50
                          ? 'bg-yellow-500/15 text-yellow-300 border-yellow-500/30'
                          : 'bg-red-500/15 text-red-300 border-red-500/30'
                    }`}>
                      {alignmentData.alignmentScore}% Aligned
                    </span>
                    <span className={`text-xs font-semibold px-2.5 py-1 rounded-md ${
                      alignmentData.alignmentScore >= 70 ? 'bg-emerald-500/10 text-emerald-400' : alignmentData.alignmentScore >= 50 ? 'bg-yellow-500/10 text-yellow-400' : 'bg-red-500/10 text-red-400'
                    }`}>
                      {alignmentData.strength}
                    </span>
                    <span className={`text-sm font-semibold ${
                      alignmentData.dominantDirection.toLowerCase().includes('bull') ? 'text-emerald-400' : alignmentData.dominantDirection.toLowerCase().includes('bear') ? 'text-red-400' : 'text-slate-400'
                    }`}>
                      {alignmentData.dominantDirection}
                    </span>
                    <span className="text-xs text-trading-muted ml-auto">{alignmentData.agreeing}/{alignmentData.total} TFs agree</span>
                  </div>

                  {/* Visual heatmap grid */}
                  <div className="flex gap-2 flex-wrap">
                    {alignmentData.timeframes.map((tf) => {
                      const isAligned = tf.aligned
                      const dir = tf.direction.toLowerCase()
                      const isBullish = dir.includes('bull') || dir === 'up'
                      const isBearish = dir.includes('bear') || dir === 'down'
                      const cellBg = isAligned
                        ? 'bg-emerald-500/15 border-emerald-500/30'
                        : isBearish
                          ? 'bg-red-500/15 border-red-500/30'
                          : 'bg-slate-500/10 border-slate-500/30'
                      const scaleCls = tf.weight >= 0.3 ? 'min-w-[110px] py-3' : 'min-w-[90px] py-2.5'

                      return (
                        <div key={tf.tf} className={`flex-1 border rounded-lg px-3 text-center ${cellBg} ${scaleCls}`}>
                          <div className="text-xs font-bold text-trading-muted uppercase">{tf.tf}</div>
                          <div className="flex justify-center mt-1">
                            {isBullish ? (
                              <TrendingUp size={18} className="text-emerald-400" />
                            ) : isBearish ? (
                              <TrendingDown size={18} className="text-red-400" />
                            ) : (
                              <Minus size={18} className="text-slate-400" />
                            )}
                          </div>
                          <div className={`text-xs font-bold mt-1 ${
                            isBullish ? 'text-emerald-400' : isBearish ? 'text-red-400' : 'text-slate-400'
                          }`}>
                            {tf.confidence}%
                          </div>
                          <div className="text-[10px] text-trading-muted mt-0.5">{tf.signal}</div>
                        </div>
                      )
                    })}
                  </div>
                </>
              ) : multiTimeframe && multiTimeframe.length > 0 ? (
                /* Fallback: existing multiTimeframe data */
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

          {/* ── Analysis tab (Enhanced with Backtest) ── */}
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

              {/* ── Backtest This Signal ── */}
              <div className="border-t border-trading-border pt-4">
                <button
                  onClick={runBacktest}
                  disabled={backtestLoading}
                  className="inline-flex items-center gap-2 px-5 py-2.5 rounded-lg text-sm font-bold border border-trading-accent/40 text-trading-accent bg-trading-accent/10 hover:bg-trading-accent/20 transition-all duration-200 disabled:opacity-50"
                >
                  {backtestLoading ? (
                    <><Loader2 size={16} className="animate-spin" /> Running Backtest...</>
                  ) : (
                    <><Play size={16} /> Backtest This Signal</>
                  )}
                </button>

                {/* Backtest Results */}
                {backtestOpen && backtestResult && (
                  <div className="mt-4 bg-trading-bg border border-trading-border rounded-xl p-4 space-y-4">
                    <div className="flex items-center justify-between">
                      <h4 className="text-sm font-bold text-trading-text">Backtest Results</h4>
                      <button onClick={() => setBacktestOpen(false)} className="text-slate-500 hover:text-trading-text transition-colors">
                        <XCircle size={18} />
                      </button>
                    </div>

                    {/* Stat cards 2x3 */}
                    <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                      {[
                        { label: 'Win Rate', value: `${backtestResult.winRate.toFixed(1)}%`, positive: backtestResult.winRate >= 50 },
                        { label: 'Profit Factor', value: backtestResult.profitFactor.toFixed(2), positive: backtestResult.profitFactor >= 1 },
                        { label: 'Sharpe Ratio', value: backtestResult.sharpeRatio.toFixed(2), positive: backtestResult.sharpeRatio >= 1 },
                        { label: 'Max Drawdown', value: `${backtestResult.maxDrawdown.toFixed(1)}%`, positive: backtestResult.maxDrawdown > -15 },
                        { label: 'Total Return', value: `${backtestResult.totalReturn >= 0 ? '+' : ''}${backtestResult.totalReturn.toFixed(1)}%`, positive: backtestResult.totalReturn >= 0 },
                        { label: 'Num Trades', value: String(backtestResult.numTrades), positive: true },
                      ].map((stat) => (
                        <div key={stat.label} className="bg-trading-card border border-trading-border rounded-lg px-3 py-2.5 text-center">
                          <div className="text-[11px] text-trading-muted uppercase tracking-wide">{stat.label}</div>
                          <div className={`text-lg font-bold mt-0.5 ${stat.positive ? 'text-emerald-400' : 'text-red-400'}`}>
                            {stat.value}
                          </div>
                        </div>
                      ))}
                    </div>

                    {/* Mini equity curve */}
                    {backtestResult.equityCurve.length > 0 && (
                      <div className="h-40">
                        <ResponsiveContainer width="100%" height="100%">
                          <AreaChart data={backtestResult.equityCurve} margin={{ top: 5, right: 5, left: 5, bottom: 5 }}>
                            <defs>
                              <linearGradient id="eqGrad" x1="0" y1="0" x2="0" y2="1">
                                <stop offset="5%" stopColor="#10b981" stopOpacity={0.3} />
                                <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
                              </linearGradient>
                            </defs>
                            <XAxis dataKey="time" hide />
                            <YAxis hide domain={['auto', 'auto']} />
                            <Tooltip
                              contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: '8px', fontSize: '12px' }}
                              labelStyle={{ color: '#94a3b8' }}
                              itemStyle={{ color: '#10b981' }}
                              formatter={(value: number) => [`$${value.toFixed(2)}`, 'Equity']}
                            />
                            <Area type="monotone" dataKey="value" stroke="#10b981" fill="url(#eqGrad)" strokeWidth={2} />
                          </AreaChart>
                        </ResponsiveContainer>
                      </div>
                    )}

                    {/* Signal-specific stats */}
                    <div className="grid grid-cols-3 gap-2 text-xs">
                      <div className="bg-trading-card border border-trading-border rounded-lg px-3 py-2 text-center">
                        <div className="text-trading-muted">Avg Hold</div>
                        <div className="text-trading-text font-semibold mt-0.5">{backtestResult.avgHoldingPeriod}</div>
                      </div>
                      <div className="bg-trading-card border border-trading-border rounded-lg px-3 py-2 text-center">
                        <div className="text-trading-muted">Best Trade</div>
                        <div className="text-emerald-400 font-semibold mt-0.5">+{backtestResult.bestTrade.toFixed(1)}%</div>
                      </div>
                      <div className="bg-trading-card border border-trading-border rounded-lg px-3 py-2 text-center">
                        <div className="text-trading-muted">Worst Trade</div>
                        <div className="text-red-400 font-semibold mt-0.5">{backtestResult.worstTrade.toFixed(1)}%</div>
                      </div>
                    </div>
                    <div className="bg-trading-card border border-trading-border rounded-lg px-3 py-2 text-center text-xs">
                      <div className="text-trading-muted">Avg Risk:Reward</div>
                      <div className="text-trading-text font-semibold mt-0.5">1:{backtestResult.avgRiskReward.toFixed(1)}</div>
                    </div>

                    {/* Confidence calibration */}
                    {backtestResult.confidenceCalibration && (
                      <div className="bg-blue-500/10 border border-blue-500/20 rounded-lg px-4 py-3 flex items-start gap-2">
                        <Zap size={16} className="text-blue-400 mt-0.5 shrink-0" />
                        <div className="text-xs text-blue-200 leading-relaxed">
                          <span className="font-semibold">Confidence Calibration:</span>{' '}
                          {backtestResult.confidenceCalibration.description}
                          {backtestResult.confidenceCalibration.profitablePercent > 0 && (
                            <span className="ml-1 font-bold text-blue-300">
                              ({backtestResult.confidenceCalibration.profitablePercent.toFixed(0)}% profitable)
                            </span>
                          )}
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* ── Copy Monitor tab ── */}
          {activeTab === 'copyhistory' && (
            <div className="space-y-4">
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
                        <div className="text-xs text-trading-muted flex flex-wrap items-center gap-x-2 gap-y-1">
                          <span>{(pos.remaining_quantity ?? pos.quantity).toFixed(2)} / {pos.quantity.toFixed(2)} lots</span>
                          <span>@ {fmtPrice(pos.entry_price, selectedPair)}</span>
                          <span>Conf {pos.confidence}%</span>
                          <span className={`px-1.5 py-0.5 rounded border text-[10px] font-semibold ${copyLifecycleTone(pos.status)}`}>
                            {pos.status.replace(/_/g, ' ')}
                          </span>
                        </div>
                        <div className="mt-1 flex flex-wrap items-center gap-1.5">
                          {pos.tp1_hit && (
                            <span className="px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-300 text-[10px] font-semibold border border-emerald-500/20">
                              TP1 hit
                            </span>
                          )}
                          {pos.tp2_hit && (
                            <span className="px-1.5 py-0.5 rounded bg-blue-500/10 text-blue-300 text-[10px] font-semibold border border-blue-500/20">
                              TP2 hit
                            </span>
                          )}
                          {pos.stop_moved_to_breakeven && (
                            <span className="px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-300 text-[10px] font-semibold border border-amber-500/20">
                              SL at breakeven
                            </span>
                          )}
                          {pos.trailing_stop_active && (
                            <span className="px-1.5 py-0.5 rounded bg-fuchsia-500/10 text-fuchsia-300 text-[10px] font-semibold border border-fuchsia-500/20">
                              Trailing stop
                            </span>
                          )}
                        </div>
                      </div>
                      <div className="text-right">
                        <div className={`text-sm font-bold ${pos.unrealized_pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                          {pos.unrealized_pnl >= 0 ? '+' : ''}${pos.unrealized_pnl.toFixed(2)}
                        </div>
                        <div className="text-xs text-trading-muted">
                          {fmtPrice(pos.current_price, selectedPair)}
                        </div>
                        <div className="text-[10px] text-trading-muted mt-1">
                          SL {fmtPrice(pos.stop_loss, selectedPair)}
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
                  <p className="text-sm text-trading-muted">No open copied trades</p>
                  <p className="text-xs text-slate-600 mt-1">Enable copy trading and click "Copy This Signal" to start</p>
                </div>
              )}
              
              {copyStats && copyStats.total_trades > 0 && (
                <>
                <div className="grid grid-cols-2 lg:grid-cols-4 gap-2">
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
                    <div className="text-xs text-trading-muted">Realized P&L</div>
                    <div className={`text-sm font-bold ${copyStats.total_pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                      ${copyStats.total_pnl.toFixed(0)}
                    </div>
                  </div>
                </div>
                <div className="grid grid-cols-2 lg:grid-cols-4 gap-2">
                  <div className="bg-trading-bg rounded-lg px-3 py-2 text-center">
                    <div className="text-xs text-trading-muted">Open P&L</div>
                    <div className={`text-sm font-bold ${copyStats.total_unrealized_pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                      {copyStats.total_unrealized_pnl >= 0 ? '+' : ''}${copyStats.total_unrealized_pnl.toFixed(2)}
                    </div>
                  </div>
                  <div className="bg-trading-bg rounded-lg px-3 py-2 text-center">
                    <div className="text-xs text-trading-muted">Expectancy</div>
                    <div className={`text-sm font-bold ${copyStats.expectancy >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                      {copyStats.expectancy >= 0 ? '+' : ''}${copyStats.expectancy.toFixed(2)}
                    </div>
                  </div>
                  <div className="bg-trading-bg rounded-lg px-3 py-2 text-center">
                    <div className="text-xs text-trading-muted">Profit Factor</div>
                    <div className="text-sm font-bold text-trading-text">
                      {copyStats.profit_factor != null ? copyStats.profit_factor.toFixed(2) : '∞'}
                    </div>
                  </div>
                  <div className="bg-trading-bg rounded-lg px-3 py-2 text-center">
                    <div className="text-xs text-trading-muted">Avg Hold</div>
                    <div className="text-sm font-bold text-trading-text">
                      {formatDuration(copyStats.avg_hold_seconds)}
                    </div>
                  </div>
                </div>
                <div className="grid grid-cols-3 gap-2">
                  <div className="bg-trading-bg rounded-lg px-3 py-2 text-center">
                    <div className="text-xs text-trading-muted">Best</div>
                    <div className="text-sm font-bold text-emerald-400">
                      +${copyStats.best_trade.toFixed(2)}
                    </div>
                  </div>
                  <div className="bg-trading-bg rounded-lg px-3 py-2 text-center">
                    <div className="text-xs text-trading-muted">Worst</div>
                    <div className="text-sm font-bold text-red-400">
                      ${copyStats.worst_trade.toFixed(2)}
                    </div>
                  </div>
                  <div className="bg-trading-bg rounded-lg px-3 py-2 text-center">
                    <div className="text-xs text-trading-muted">Max DD</div>
                    <div className="text-sm font-bold text-trading-text">
                      ${copyStats.max_drawdown.toFixed(2)}
                    </div>
                  </div>
                </div>
                <div className="grid grid-cols-3 gap-2">
                  <div className="bg-trading-bg rounded-lg px-3 py-2 text-center">
                    <div className="text-xs text-trading-muted">Avg R</div>
                    <div className="text-sm font-bold text-trading-text">
                      {copyStats.avg_r_multiple != null ? `${copyStats.avg_r_multiple.toFixed(2)}R` : '—'}
                    </div>
                  </div>
                  <div className="bg-trading-bg rounded-lg px-3 py-2 text-center">
                    <div className="text-xs text-trading-muted">Loss Streak</div>
                    <div className="text-sm font-bold text-trading-text">
                      {copyStats.current_loss_streak} / {copyStats.max_loss_streak}
                    </div>
                  </div>
                  <div className="bg-trading-bg rounded-lg px-3 py-2 text-center">
                    <div className="text-xs text-trading-muted">Partial exits</div>
                    <div className="text-sm font-bold text-trading-text">
                      {copyStats.partial_exit_trades}
                    </div>
                  </div>
                </div>

                {copyStats.equity_curve.length > 0 && (
                  <div className="bg-trading-bg border border-trading-border rounded-lg px-4 py-3">
                    <div className="text-xs font-bold text-trading-muted uppercase tracking-wider mb-3">Copy Equity Curve</div>
                    <div className="h-40">
                      <ResponsiveContainer width="100%" height="100%">
                        <AreaChart data={copyStats.equity_curve}>
                          <defs>
                            <linearGradient id="copyEqGrad" x1="0" y1="0" x2="0" y2="1">
                              <stop offset="5%" stopColor="#38bdf8" stopOpacity={0.35} />
                              <stop offset="95%" stopColor="#38bdf8" stopOpacity={0} />
                            </linearGradient>
                          </defs>
                          <XAxis dataKey="symbol" tick={{ fill: '#94a3b8', fontSize: 11 }} />
                          <YAxis tick={{ fill: '#94a3b8', fontSize: 11 }} />
                          <Tooltip
                            contentStyle={{ background: '#0f172a', border: '1px solid #334155', borderRadius: '8px', fontSize: '12px' }}
                            labelStyle={{ color: '#94a3b8' }}
                            itemStyle={{ color: '#38bdf8' }}
                            formatter={(value: number) => [`$${value.toFixed(2)}`, 'Equity']}
                          />
                          <Area type="monotone" dataKey="cumulative_pnl" stroke="#38bdf8" fill="url(#copyEqGrad)" strokeWidth={2} />
                        </AreaChart>
                      </ResponsiveContainer>
                    </div>
                  </div>
                )}

                {copyStats.symbol_breakdown.length > 0 && (
                  <div className="bg-trading-bg border border-trading-border rounded-lg px-4 py-3">
                    <div className="text-xs font-bold text-trading-muted uppercase tracking-wider mb-3">Symbol Breakdown</div>
                    <div className="space-y-2">
                      {copyStats.symbol_breakdown.slice(0, 5).map((row) => (
                        <div key={row.symbol} className="grid grid-cols-[1.2fr_0.9fr_0.9fr_1fr] gap-2 text-xs items-center">
                          <div className="text-trading-text font-semibold">{row.symbol}</div>
                          <div className="text-trading-muted">{row.total_trades} trades</div>
                          <div className="text-trading-muted">{row.win_rate.toFixed(0)}% win</div>
                          <div className={`font-semibold text-right ${row.total_pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                            {row.total_pnl >= 0 ? '+' : ''}${row.total_pnl.toFixed(2)}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                <div className="grid lg:grid-cols-2 gap-3">
                  <div className="bg-trading-bg border border-trading-border rounded-lg px-4 py-3">
                    <div className="text-xs font-bold text-trading-muted uppercase tracking-wider mb-3">Recent Closed Trades</div>
                    {copyStats.recent_closed.length > 0 ? (
                      <div className="space-y-2">
                        {copyStats.recent_closed.slice(0, 5).map((trade) => (
                          <div key={trade.copy_trade_id} className="flex items-center gap-3 text-xs">
                            <div className="min-w-0 flex-1">
                              <div className="font-semibold text-trading-text">{trade.symbol}</div>
                              <div className="text-trading-muted">{trade.status.replace(/_/g, ' ')}</div>
                            </div>
                            <div className="text-trading-muted">{formatDuration(trade.holding_seconds)}</div>
                            <div className={`font-semibold ${trade.realized_pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                              {trade.realized_pnl >= 0 ? '+' : ''}${trade.realized_pnl.toFixed(2)}
                            </div>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <p className="text-xs text-trading-muted">No closed trades yet</p>
                    )}
                  </div>

                  <div className="bg-trading-bg border border-trading-border rounded-lg px-4 py-3">
                    <div className="text-xs font-bold text-trading-muted uppercase tracking-wider mb-3">Trade History</div>
                    <div className="flex flex-col sm:flex-row gap-2 mb-3">
                      <select
                        value={copyHistorySymbolFilter}
                        onChange={(event) => onCopyHistorySymbolFilterChange?.(event.target.value)}
                        className="bg-trading-card border border-trading-border rounded-md px-2 py-1.5 text-xs text-trading-text"
                      >
                        <option value="all">All Symbols</option>
                        {Array.from(new Set((copyHistory ?? []).map((trade) => trade.symbol))).map((symbol) => (
                          <option key={symbol} value={symbol}>{symbol}</option>
                        ))}
                      </select>
                      <select
                        value={copyHistoryDirectionFilter}
                        onChange={(event) => onCopyHistoryDirectionFilterChange?.(event.target.value as 'ALL' | 'BUY' | 'SELL')}
                        className="bg-trading-card border border-trading-border rounded-md px-2 py-1.5 text-xs text-trading-text"
                      >
                        <option value="ALL">All Directions</option>
                        <option value="BUY">BUY</option>
                        <option value="SELL">SELL</option>
                      </select>
                      <select
                        value={copyHistoryStatusFilter}
                        onChange={(event) => onCopyHistoryStatusFilterChange?.(event.target.value)}
                        className="bg-trading-card border border-trading-border rounded-md px-2 py-1.5 text-xs text-trading-text"
                      >
                        <option value="all">All Outcomes</option>
                        <option value="closed_tp3">TP3</option>
                        <option value="closed_sl">Stop Loss</option>
                        <option value="closed_manual">Manual Close</option>
                      </select>
                      <div className="inline-flex items-center gap-2 rounded-md border border-trading-border bg-trading-card px-2 py-1.5 text-xs text-trading-text">
                        <CalendarDays size={12} className="text-trading-muted" />
                        <select
                          value={copyHistoryRangeFilter}
                          onChange={(event) => onCopyHistoryRangeFilterChange?.(event.target.value as 'all' | '7d' | '30d' | '90d')}
                          className="bg-transparent text-xs text-trading-text outline-none"
                        >
                          <option value="all">All Time</option>
                          <option value="7d">Last 7d</option>
                          <option value="30d">Last 30d</option>
                          <option value="90d">Last 90d</option>
                        </select>
                      </div>
                      <a
                        href={exportHref}
                        className="inline-flex items-center justify-center rounded-md border border-trading-accent/30 px-3 py-1.5 text-xs font-semibold text-trading-accent hover:bg-trading-accent/10 transition-colors"
                      >
                        Export CSV
                      </a>
                    </div>
                    {closedHistory.length > 0 ? (
                      <div className="space-y-2 max-h-60 overflow-y-auto pr-1">
                        {closedHistory.slice(0, 12).map((trade) => (
                          <div key={trade.copy_trade_id} className="flex items-center gap-3 text-xs">
                            <span className={`px-1.5 py-0.5 rounded border font-semibold ${copyLifecycleTone(trade.status)}`}>
                              {trade.status.replace(/_/g, ' ')}
                            </span>
                            <div className="min-w-0 flex-1">
                              <div className="font-semibold text-trading-text">{trade.symbol}</div>
                              <div className="text-trading-muted">
                                {trade.direction} · {formatDuration(trade.holding_seconds)} · {trade.partial_exit_count ?? 0} partials
                              </div>
                              <div className="text-[10px] text-trading-muted/80">
                                Opened: {formatTradeTimestamp(trade.created_at)}
                              </div>
                              <div className="text-[10px] text-trading-muted/80">
                                Closed: {formatTradeTimestamp(trade.closed_at)}
                              </div>
                            </div>
                            <div className="text-trading-muted min-w-[52px] text-right">
                              {trade.realized_pnl !== 0 && trade.initial_stop_loss != null
                                ? `${(((trade.realized_pnl) / (Math.abs(trade.entry_price - trade.initial_stop_loss) * trade.quantity)) || 0).toFixed(2)}R`
                                : '—'}
                            </div>
                            <div className={`font-semibold ${trade.realized_pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                              {trade.realized_pnl >= 0 ? '+' : ''}${trade.realized_pnl.toFixed(2)}
                            </div>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <p className="text-xs text-trading-muted">History will appear once copy trades close.</p>
                    )}
                  </div>
                </div>
                </>
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
                onChange={(e) => onRiskPctChange(parseFloat(e.target.value))}
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
