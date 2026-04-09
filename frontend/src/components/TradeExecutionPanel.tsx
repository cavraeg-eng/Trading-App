import { useState } from 'react'
import {
  TrendingUp,
  TrendingDown,
  Activity,
  Zap,
  Loader2,
  AlertTriangle,
} from 'lucide-react'
import type { ForexPair, SignalStatus } from '../types'

interface TradeExecutionPanelProps {
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
  }
  currentPrice: number
  priceChange: number
  priceChangePercent: number
  selectedPair: ForexPair
  accountBalance: number
  isLoading: boolean
  onBuy: () => void
  onSell: () => void
  tradeStyle?: 'scalp' | 'swing'
  onTradeStyleChange?: (style: 'scalp' | 'swing') => void
  signalStatus?: SignalStatus
}

// ---------- helpers ----------
const pipSize = (pair: ForexPair) => {
  const p = pair.basePriceApprox
  if (p < 10) return 0.0001
  if (p < 200) return 0.01
  if (p < 5000) return 0.10
  return 1.0
}
const toPips = (distance: number, pair: ForexPair) => Math.abs(distance) / pipSize(pair)
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

const badgeColors = (s: string) => {
  if (isBuyish(s)) return 'bg-emerald-500 text-white'
  if (isSellish(s)) return 'bg-red-500 text-white'
  return 'bg-amber-500 text-white'
}

// Signal status helpers
const statusBadgeStyle = (status: SignalStatus) => {
  switch (status) {
    case 'OPTIMAL_ENTRY': return 'bg-emerald-500/30 text-emerald-300 border-emerald-500/40';
    case 'VALID': return 'bg-blue-500/30 text-blue-300 border-blue-500/40';
    case 'ABOUT_TO_EXPIRE': return 'bg-amber-500/30 text-amber-300 border-amber-500/40';
    case 'EXPIRED': return 'bg-gray-500/30 text-gray-300 border-gray-500/40';
  }
}

const statusBadgeLabel = (status: SignalStatus) => {
  switch (status) {
    case 'OPTIMAL_ENTRY': return 'Optimal Entry';
    case 'VALID': return 'Valid';
    case 'ABOUT_TO_EXPIRE': return 'Expiring Soon';
    case 'EXPIRED': return 'Expired';
  }
}

const regimeLabel = (r: string) => {
  switch (r) {
    case 'trending_up': return 'Trending Up'
    case 'trending_down': return 'Trending Down'
    case 'volatile': return 'Volatile'
    default: return 'Ranging'
  }
}
const RegimeIcon = ({ regime }: { regime: string }) => {
  switch (regime) {
    case 'trending_up': return <TrendingUp size={16} className="text-emerald-400" />
    case 'trending_down': return <TrendingDown size={16} className="text-red-400" />
    case 'volatile': return <Zap size={16} className="text-yellow-400" />
    default: return <Activity size={16} className="text-blue-400" />
  }
}

// ---------- component ----------
export function TradeExecutionPanel({
  signalDetails, currentPrice, priceChange, priceChangePercent,
  selectedPair, accountBalance, isLoading, onBuy, onSell,
  tradeStyle, onTradeStyleChange, signalStatus,
}: TradeExecutionPanelProps) {
  const [riskPct, setRiskPct] = useState(2)

  const displayConf = signalDetails.confidence > 1
    ? Math.round(signalDetails.confidence)
    : Math.round(signalDetails.confidence * 100)

  const entryMid = (signalDetails.entryRange.min + signalDetails.entryRange.max) / 2

  // ---------- validity check ----------
  const hasValidData =
    signalDetails.stopLoss !== 0 &&
    signalDetails.stopLoss !== signalDetails.entryRange.min &&
    signalDetails.entryRange.min !== signalDetails.entryRange.max

  if (!hasValidData) {
    return (
      <article aria-label="Trade Execution Panel" className="bg-trading-card border border-trading-border rounded-lg p-8 text-center">
        <Loader2 className="animate-spin mx-auto mb-3 text-slate-400" size={28} />
        <p className="text-slate-300 text-base">Awaiting market data…</p>
      </article>
    )
  }

  // ---------- position sizing ----------
  const riskAmount = accountBalance * (riskPct / 100)
  const stopDistance = Math.abs(entryMid - signalDetails.stopLoss)
  const stopPips = toPips(stopDistance, selectedPair)
  const pipValuePerStandardLot = selectedPair.basePriceApprox < 10 ? 10 : 1
  const posSizeLots = stopPips > 0 ? riskAmount / (stopPips * pipValuePerStandardLot) : 0

  // ---------- pip distances ----------
  const slPips = toPips(entryMid - signalDetails.stopLoss, selectedPair)
  const tp1Pips = toPips(entryMid - signalDetails.takeProfit1, selectedPair)
  const tp2Pips = toPips(entryMid - signalDetails.takeProfit2, selectedPair)
  const tp3Pips = toPips(entryMid - signalDetails.takeProfit3, selectedPair)

  // ---------- risk/reward (3 levels) ----------
  const risk_distance = Math.abs(entryMid - signalDetails.stopLoss)
  const rr1 = risk_distance > 0 ? Math.abs(signalDetails.takeProfit1 - entryMid) / risk_distance : 1
  const rr2 = signalDetails.riskReward // from API
  const rr3 = risk_distance > 0 ? Math.abs(signalDetails.takeProfit3 - entryMid) / risk_distance : 3

  // Use TP2 R:R for quality assessment
  const rrQuality = rr2 >= 2
    ? { label: 'Good', cls: 'text-emerald-400', bg: 'bg-emerald-500', badgeBg: 'bg-emerald-500/30 text-emerald-300' }
    : rr2 >= 1
      ? { label: 'Moderate', cls: 'text-yellow-400', bg: 'bg-yellow-500', badgeBg: 'bg-yellow-500/30 text-yellow-300' }
      : { label: 'Poor', cls: 'text-red-400', bg: 'bg-red-500', badgeBg: 'bg-red-500/30 text-red-300' }

  // ---------- signal strength ----------
  const strengthNorm = displayConf / 100
  const strengthLabel = strengthNorm >= 0.8 ? 'Strong' : strengthNorm >= 0.6 ? 'Moderate' : strengthNorm >= 0.4 ? 'Weak' : 'Very Weak'

  // ---------- price ladder ----------
  const isBuy = isBuyish(signalDetails.signal)
  const allPrices = [signalDetails.stopLoss, entryMid, signalDetails.takeProfit1, signalDetails.takeProfit2, signalDetails.takeProfit3]
  const ladderMin = Math.min(...allPrices)
  const ladderMax = Math.max(...allPrices)
  const ladderRange = ladderMax - ladderMin || 1

  const slPct = ((signalDetails.stopLoss - ladderMin) / ladderRange) * 100
  const entryMinPct = ((signalDetails.entryRange.min - ladderMin) / ladderRange) * 100
  const entryMaxPct = ((signalDetails.entryRange.max - ladderMin) / ladderRange) * 100
  const tp1Pct = ((signalDetails.takeProfit1 - ladderMin) / ladderRange) * 100
  const tp2Pct = ((signalDetails.takeProfit2 - ladderMin) / ladderRange) * 100
  const tp3Pct = ((signalDetails.takeProfit3 - ladderMin) / ladderRange) * 100
  const currentPct = Math.max(0, Math.min(100, ((currentPrice - ladderMin) / ladderRange) * 100))

  // Determine left/right zones based on direction
  const leftZoneEnd = Math.min(entryMinPct, entryMaxPct)
  const rightZoneStart = Math.max(entryMinPct, entryMaxPct)

  const isExpired = signalStatus === 'EXPIRED'

  return (
    <article aria-label="Trade Execution Panel" className="bg-trading-card border border-trading-border rounded-lg overflow-hidden transition-all duration-300">

      {/* ── Section 1: Signal Header ── */}
      <section aria-label="Signal information" className="px-4 py-2">
        <div className="flex items-center gap-2 flex-wrap">
          {/* Signal Badge — inline pill */}
          <div
            className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg font-bold text-base leading-tight shadow-lg ${badgeColors(signalDetails.signal)}`}
            role="status"
            aria-label={`Signal: ${signalLabel(signalDetails.signal)}, confidence ${displayConf}%`}
          >
            <span className="font-extrabold tracking-wide">{signalLabel(signalDetails.signal)}</span>
            <span className="text-xs font-semibold opacity-90">{displayConf}%</span>
          </div>
          {/* Signal Status Badge */}
          {signalStatus && (
            <span
              aria-live="polite"
              className={`px-2 py-0.5 rounded-md border text-xs font-semibold ${statusBadgeStyle(signalStatus)}`}
            >
              {statusBadgeLabel(signalStatus)}
            </span>
          )}
          <span className="text-slate-400">·</span>
          <span className="text-lg font-bold text-trading-text">{selectedPair.symbol}</span>
          <span className="text-lg font-bold text-trading-text">{fmtPrice(currentPrice, selectedPair)}</span>
          <span className={`text-sm font-medium ${priceChange >= 0 ? 'text-trading-buy' : 'text-trading-sell'}`}>
            {priceChange >= 0 ? '+' : ''}{fmtPrice(priceChange, selectedPair)} ({priceChangePercent >= 0 ? '+' : ''}{priceChangePercent.toFixed(2)}%)
          </span>
          {isLoading && <Loader2 size={16} className="animate-spin text-trading-accent" />}
          <span className="text-slate-500">·</span>
          <span className="flex items-center gap-1 text-sm text-slate-300">
            <RegimeIcon regime={signalDetails.marketRegime} /> {regimeLabel(signalDetails.marketRegime)}
          </span>
          <span className="text-slate-500">·</span>
          <span className="text-sm text-slate-300">TF: <span className="text-trading-text font-semibold">{signalDetails.timeframe.toUpperCase()}</span></span>
          {tradeStyle && (
            <>
              <span className="text-slate-500">·</span>
              <span className="text-xs px-2 py-0.5 rounded-md bg-trading-bg text-slate-300 font-semibold uppercase">
                {tradeStyle === 'scalp' ? 'Scalp' : 'Swing'}
              </span>
            </>
          )}
        </div>

        {/* Strength bar */}
        <div className="mt-1 flex items-center gap-3">
          <span className="text-xs text-slate-300 uppercase tracking-wide font-semibold">Strength</span>
          <div className="flex-1 h-2 bg-trading-bg rounded-full overflow-hidden max-w-[200px]">
            <div
              className={`h-full rounded-full transition-all duration-500 ${isBuyish(signalDetails.signal) ? 'bg-emerald-500' : isSellish(signalDetails.signal) ? 'bg-red-500' : 'bg-yellow-500'}`}
              style={{ width: `${displayConf}%` }}
              role="progressbar"
              aria-valuenow={displayConf}
              aria-valuemin={0}
              aria-valuemax={100}
              aria-label={`Signal strength: ${displayConf}%`}
            />
          </div>
          <span className="text-xs text-trading-text font-semibold">{strengthLabel}</span>
        </div>
      </section>

      {/* ── Section 2: Price Ladder ── */}
      <section aria-label="Price levels and ladder" className="border-t border-trading-border px-4 py-2">
        <h3 className="text-sm font-bold text-slate-300 uppercase tracking-wide mb-1.5">Price Levels</h3>

        {/* Labels row */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-2">
          <div className="bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-1.5 text-center">
            <span className="text-xs font-bold uppercase tracking-wide text-red-400">Stop Loss</span>
            <div className="text-base font-bold text-trading-text">{fmtPrice(signalDetails.stopLoss, selectedPair)}</div>
            <div className="text-xs text-red-400">{slPips.toFixed(1)} pips</div>
          </div>
          <div className="bg-blue-500/10 border border-blue-500/20 rounded-lg px-3 py-1.5 text-center">
            <span className="text-xs font-bold uppercase tracking-wide text-blue-400">Entry Zone</span>
            <div className="text-base font-bold text-trading-text">
              {fmtPrice(signalDetails.entryRange.min, selectedPair)} — {fmtPrice(signalDetails.entryRange.max, selectedPair)}
            </div>
          </div>
          <div className="bg-emerald-500/10 border border-emerald-500/20 rounded-lg px-3 py-1.5 text-center">
            <span className="text-xs font-bold uppercase tracking-wide text-emerald-400">Take Profit</span>
            <div className="flex items-center justify-center gap-3 text-base font-bold">
              <span className="text-emerald-300">{fmtPrice(signalDetails.takeProfit1, selectedPair)}</span>
              <span className="text-emerald-400">{fmtPrice(signalDetails.takeProfit2, selectedPair)}</span>
              <span className="text-emerald-400">{fmtPrice(signalDetails.takeProfit3, selectedPair)}</span>
            </div>
          </div>
        </div>

        {/* Horizontal price ladder bar */}
        <div className="relative h-4 mt-1 mb-1 rounded-full overflow-hidden bg-trading-bg" role="img" aria-label="Visual price ladder showing stop loss, entry zone, and take profit levels">
          {/* Left zone */}
          <div
            className={`absolute top-0 bottom-0 ${isBuy ? 'bg-red-500/25' : 'bg-emerald-500/25'}`}
            style={{ left: 0, width: `${leftZoneEnd}%` }}
          />
          {/* Entry zone */}
          <div
            className="absolute top-0 bottom-0 bg-blue-500/25"
            style={{ left: `${leftZoneEnd}%`, width: `${rightZoneStart - leftZoneEnd}%` }}
          />
          {/* Right zone */}
          <div
            className={`absolute top-0 bottom-0 ${isBuy ? 'bg-emerald-500/25' : 'bg-red-500/25'}`}
            style={{ left: `${rightZoneStart}%`, width: `${100 - rightZoneStart}%` }}
          />
          {/* SL marker */}
          <div className="absolute top-0 bottom-0 w-1 bg-red-500 rounded" style={{ left: `${slPct}%` }}>
            <span className="absolute -top-5 left-1/2 -translate-x-1/2 text-xs font-bold text-red-400 whitespace-nowrap">SL</span>
          </div>
          {/* TP1 marker */}
          <div className="absolute top-0 bottom-0 w-1 bg-emerald-400 rounded" style={{ left: `${tp1Pct}%` }}>
            <span className="absolute -top-5 left-1/2 -translate-x-1/2 text-xs font-bold text-emerald-300 whitespace-nowrap">TP1</span>
          </div>
          {/* TP2 marker */}
          <div className="absolute top-0 bottom-0 w-1 bg-emerald-500 rounded" style={{ left: `${tp2Pct}%` }}>
            <span className="absolute -top-5 left-1/2 -translate-x-1/2 text-xs font-bold text-emerald-400 whitespace-nowrap">TP2</span>
          </div>
          {/* TP3 marker */}
          <div className="absolute top-0 bottom-0 w-1 bg-emerald-600 rounded" style={{ left: `${tp3Pct}%` }}>
            <span className="absolute -top-5 left-1/2 -translate-x-1/2 text-xs font-bold text-emerald-400 whitespace-nowrap">TP3</span>
          </div>
          {/* Current price marker */}
          <div className="absolute -top-1 -bottom-1 w-1 bg-white z-10 rounded" style={{ left: `${currentPct}%` }}>
            <div className="absolute -top-6 left-1/2 -translate-x-1/2 text-xs font-bold text-white bg-trading-accent px-2 py-0.5 rounded whitespace-nowrap shadow-md">
              ▲ Now
            </div>
          </div>
        </div>

        {/* Pip distances row */}
        {isBuy ? (
          <div className="flex justify-between text-sm text-slate-300 mt-2">
            <span className="text-red-400 font-medium">{slPips.toFixed(1)} pips</span>
            <span className="text-blue-400 font-medium">▲ Now</span>
            <span className="text-emerald-300 font-medium">{tp1Pips.toFixed(1)}</span>
            <span className="text-emerald-400 font-medium">{tp2Pips.toFixed(1)}</span>
            <span className="text-emerald-400 font-medium">{tp3Pips.toFixed(1)} pips</span>
          </div>
        ) : (
          <div className="flex justify-between text-sm text-slate-300 mt-2">
            <span className="text-emerald-400 font-medium">{tp3Pips.toFixed(1)} pips</span>
            <span className="text-emerald-400 font-medium">{tp2Pips.toFixed(1)}</span>
            <span className="text-emerald-300 font-medium">{tp1Pips.toFixed(1)}</span>
            <span className="text-blue-400 font-medium">▲ Now</span>
            <span className="text-red-400 font-medium">{slPips.toFixed(1)} pips</span>
          </div>
        )}

        {/* Risk/Reward cards */}
        <div className="mt-2">
          <div className="flex items-center justify-between mb-1">
            <h3 className="text-sm font-bold text-slate-300 uppercase tracking-wide">Risk / Reward</h3>
            <span className={`px-3 py-1 rounded-md text-xs font-bold ${rrQuality.badgeBg}`}>
              {rrQuality.label}
            </span>
          </div>
          <div className="grid grid-cols-3 gap-2">
            <div className="bg-trading-bg border border-trading-border rounded-lg px-3 py-1.5 text-center">
              <span className="text-xs text-slate-300 font-semibold">TP1</span>
              <div className="text-base font-bold text-emerald-300">1:{rr1.toFixed(1)}</div>
              <div className="text-xs text-slate-400">{tp1Pips.toFixed(1)} pips</div>
            </div>
            <div className="bg-trading-bg border border-trading-border rounded-lg px-3 py-1.5 text-center">
              <span className="text-xs text-slate-300 font-semibold">TP2</span>
              <div className="text-base font-bold text-emerald-400">1:{rr2.toFixed(1)}</div>
              <div className="text-xs text-slate-400">{tp2Pips.toFixed(1)} pips</div>
            </div>
            <div className="bg-trading-bg border border-trading-border rounded-lg px-3 py-1.5 text-center">
              <span className="text-xs text-slate-300 font-semibold">TP3</span>
              <div className="text-base font-bold text-emerald-400">1:{rr3.toFixed(1)}</div>
              <div className="text-xs text-slate-400">{tp3Pips.toFixed(1)} pips</div>
            </div>
          </div>
        </div>
      </section>

      {/* ── Section 3: Action Footer ── */}
      <section aria-label="Trade actions" className="border-t border-trading-border px-4 py-2">
        {/* Signal status warning/info text */}
        <div aria-live="polite">
          {signalStatus === 'EXPIRED' && (
            <div className="flex items-center gap-2 text-sm text-gray-300 mb-1.5 bg-gray-500/10 border border-gray-500/20 rounded-lg px-3 py-1.5">
              <AlertTriangle size={16} className="text-gray-400 shrink-0" />
              <span className="font-medium">Signal expired — wait for fresh signal</span>
            </div>
          )}
          {signalStatus === 'OPTIMAL_ENTRY' && (
            <div className="flex items-center gap-2 text-sm text-emerald-300 mb-1.5 bg-emerald-500/10 border border-emerald-500/20 rounded-lg px-3 py-1.5">
              <Zap size={16} className="text-emerald-400 shrink-0" />
              <span className="font-medium">Optimal entry window — act now</span>
            </div>
          )}
          {signalStatus === 'ABOUT_TO_EXPIRE' && (
            <div className="flex items-center gap-2 text-sm text-amber-300 mb-1.5 bg-amber-500/10 border border-amber-500/20 rounded-lg px-3 py-1.5">
              <AlertTriangle size={16} className="text-amber-400 shrink-0" />
              <span className="font-medium">Signal expiring soon</span>
            </div>
          )}
        </div>

        {/* Position summary */}
        <div className="flex items-center gap-1.5 text-sm text-slate-300 mb-1.5 flex-wrap">
          <AlertTriangle size={14} className="shrink-0 text-slate-400" />
          <span className="font-semibold text-trading-text">{posSizeLots.toFixed(2)} lots</span>
          <span className="text-slate-500">·</span>
          <span>Risk: <span className="text-trading-text font-semibold">${riskAmount.toFixed(0)} ({riskPct}%)</span></span>
          <span className="text-slate-500">·</span>
          <span>SL: <span className="text-trading-text font-medium">{fmtPrice(signalDetails.stopLoss, selectedPair)}</span></span>
          <span className="text-slate-500">·</span>
          <span>TP1: <span className="text-trading-text font-medium">{fmtPrice(signalDetails.takeProfit1, selectedPair)}</span></span>
          <span className="text-slate-500">·</span>
          <span>TP2: <span className="text-trading-text font-medium">{fmtPrice(signalDetails.takeProfit2, selectedPair)}</span></span>
          <span className="text-slate-500">·</span>
          <span>TP3: <span className="text-trading-text font-medium">{fmtPrice(signalDetails.takeProfit3, selectedPair)}</span></span>
        </div>

        {/* Controls row — stacks on mobile */}
        <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2">
          {/* Trade Style Toggle */}
          {onTradeStyleChange && (
            <div className="flex items-center gap-1 bg-trading-bg rounded-lg p-1 shrink-0" role="radiogroup" aria-label="Trade style">
              <button
                role="radio"
                aria-checked={tradeStyle === 'scalp'}
                onClick={() => onTradeStyleChange('scalp')}
                className={`px-3 py-1.5 rounded-md text-sm font-semibold transition-colors min-h-[36px] ${
                  tradeStyle === 'scalp'
                    ? 'bg-trading-accent text-white shadow-md'
                    : 'text-slate-300 hover:text-trading-text hover:bg-trading-border/50'
                }`}
              >
                Scalp
              </button>
              <button
                role="radio"
                aria-checked={tradeStyle === 'swing'}
                onClick={() => onTradeStyleChange('swing')}
                className={`px-3 py-1.5 rounded-md text-sm font-semibold transition-colors min-h-[36px] ${
                  tradeStyle === 'swing'
                    ? 'bg-trading-accent text-white shadow-md'
                    : 'text-slate-300 hover:text-trading-text hover:bg-trading-border/50'
                }`}
              >
                Swing
              </button>
            </div>
          )}

          {/* Risk slider */}
          <div className="flex items-center gap-2 flex-1 min-w-0">
            <label htmlFor="risk-slider" className="text-xs text-slate-300 whitespace-nowrap font-semibold">
              Risk: {riskPct}%
            </label>
            <input
              id="risk-slider"
              type="range"
              min="0.5"
              max="5"
              step="0.5"
              value={riskPct}
              onChange={(e) => setRiskPct(parseFloat(e.target.value))}
              className="flex-1 h-2 min-w-[80px] accent-trading-accent cursor-pointer"
              aria-label={`Risk percentage: ${riskPct}%`}
              aria-valuemin={0.5}
              aria-valuemax={5}
              aria-valuenow={riskPct}
            />
          </div>

          {/* Trade buttons — full width on mobile */}
          <div className="flex gap-2 shrink-0 w-full sm:w-auto">
            <button
              onClick={onBuy}
              disabled={isExpired}
              aria-label={isExpired ? 'Buy — Signal Expired' : `Buy ${selectedPair.symbol}`}
              className={`btn-buy flex-1 sm:flex-initial px-5 py-2 text-base font-bold rounded-lg flex items-center justify-center gap-2 transition-all min-h-[44px] ${
                isBuyish(signalDetails.signal) && !isExpired
                  ? 'ring-2 ring-emerald-400 shadow-lg shadow-emerald-500/20'
                  : ''
              } ${isExpired ? 'opacity-50 cursor-not-allowed' : 'hover:brightness-110 active:scale-[0.98]'}`}
            >
              <TrendingUp size={16} />
              {isExpired ? 'Signal Expired' : 'BUY'}
            </button>
            <button
              onClick={onSell}
              disabled={isExpired}
              aria-label={isExpired ? 'Sell — Signal Expired' : `Sell ${selectedPair.symbol}`}
              className={`btn-sell flex-1 sm:flex-initial px-5 py-2 text-base font-bold rounded-lg flex items-center justify-center gap-2 transition-all min-h-[44px] ${
                isSellish(signalDetails.signal) && !isExpired
                  ? 'ring-2 ring-red-400 shadow-lg shadow-red-500/20'
                  : ''
              } ${isExpired ? 'opacity-50 cursor-not-allowed' : 'hover:brightness-110 active:scale-[0.98]'}`}
            >
              <TrendingDown size={16} />
              {isExpired ? 'Signal Expired' : 'SELL'}
            </button>
          </div>
        </div>
      </section>
    </article>
  )
}
