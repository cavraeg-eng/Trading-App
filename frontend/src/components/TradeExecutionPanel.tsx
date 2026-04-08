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
    case 'OPTIMAL_ENTRY': return 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30';
    case 'VALID': return 'bg-blue-500/20 text-blue-400 border-blue-500/30';
    case 'ABOUT_TO_EXPIRE': return 'bg-amber-500/20 text-amber-400 border-amber-500/30';
    case 'EXPIRED': return 'bg-gray-500/20 text-gray-400 border-gray-500/30';
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
    case 'trending_up': return <TrendingUp size={14} className="text-emerald-400" />
    case 'trending_down': return <TrendingDown size={14} className="text-red-400" />
    case 'volatile': return <Zap size={14} className="text-yellow-400" />
    default: return <Activity size={14} className="text-blue-400" />
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
      <div className="bg-trading-card border border-trading-border rounded-lg p-6 text-center">
        <Loader2 className="animate-spin mx-auto mb-2 text-trading-muted" size={24} />
        <p className="text-trading-muted text-sm">Awaiting market data…</p>
      </div>
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
    ? { label: 'Good', cls: 'text-emerald-400', bg: 'bg-emerald-500' }
    : rr2 >= 1
      ? { label: 'Moderate', cls: 'text-yellow-400', bg: 'bg-yellow-500' }
      : { label: 'Poor', cls: 'text-red-400', bg: 'bg-red-500' }

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

  return (
    <div className="bg-trading-card border border-trading-border rounded-lg overflow-hidden transition-all duration-300">
      {/* ── Section 1: Signal Header ── */}
      <div className="px-5 py-4 flex items-center gap-4">
        {/* Badge */}
        <div className="flex items-center gap-2">
          <div className={`flex flex-col items-center justify-center px-5 py-3 rounded-lg font-bold text-lg leading-tight ${badgeColors(signalDetails.signal)}`}>
            <span>{signalLabel(signalDetails.signal).split(' ').slice(-1)[0]}</span>
            <span className="text-sm opacity-90">{displayConf}%</span>
          </div>
          {/* Signal Status Badge */}
          {signalStatus && (
            <span className={`px-2 py-1 rounded border text-[10px] font-medium ${statusBadgeStyle(signalStatus)}`}>
              {statusBadgeLabel(signalStatus)}
            </span>
          )}
        </div>

        {/* Info */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-base font-semibold text-trading-text">{selectedPair.symbol}</span>
            <span className="text-trading-muted">·</span>
            <span className="text-base font-bold text-trading-text">{fmtPrice(currentPrice, selectedPair)}</span>
            <span className={`text-sm ${priceChange >= 0 ? 'text-trading-buy' : 'text-trading-sell'}`}>
              {priceChange >= 0 ? '+' : ''}{fmtPrice(priceChange, selectedPair)} ({priceChangePercent >= 0 ? '+' : ''}{priceChangePercent.toFixed(2)}%)
            </span>
            {isLoading && <Loader2 size={14} className="animate-spin text-trading-accent" />}
          </div>
          <div className="flex items-center gap-3 mt-1 text-xs text-trading-muted">
            <span className="flex items-center gap-1"><RegimeIcon regime={signalDetails.marketRegime} /> {regimeLabel(signalDetails.marketRegime)}</span>
            <span>·</span>
            <span>Timeframe: <span className="text-trading-text font-medium">{signalDetails.timeframe.toUpperCase()}</span></span>
            {tradeStyle && (
              <>
                <span>·</span>
                <span className="text-[10px] px-1.5 py-0.5 rounded bg-trading-bg text-trading-muted font-medium uppercase">
                  {tradeStyle === 'scalp' ? 'Scalp' : 'Swing'}
                </span>
              </>
            )}
          </div>
          {/* Strength bar */}
          <div className="mt-2 flex items-center gap-2">
            <span className="text-[10px] text-trading-muted uppercase tracking-wide">Strength</span>
            <div className="flex-1 h-2 bg-trading-bg rounded-full overflow-hidden max-w-[180px]">
              <div
                className={`h-full rounded-full transition-all duration-500 ${isBuyish(signalDetails.signal) ? 'bg-emerald-500' : isSellish(signalDetails.signal) ? 'bg-red-500' : 'bg-yellow-500'}`}
                style={{ width: `${displayConf}%` }}
              />
            </div>
            <span className="text-[10px] text-trading-text font-medium">{strengthLabel}</span>
          </div>
        </div>
      </div>

      {/* ── Section 2: Price Ladder ── */}
      <div className="border-t border-trading-border px-5 py-4">
        {/* Labels row */}
        <div className="flex justify-between items-start mb-1">
          <div className="text-center">
            <span className="text-[10px] font-semibold uppercase tracking-wide text-red-400">Stop Loss</span>
            <div className="text-sm font-bold text-trading-text">{fmtPrice(signalDetails.stopLoss, selectedPair)}</div>
          </div>
          <div className="text-center">
            <span className="text-[10px] font-semibold uppercase tracking-wide text-blue-400">Entry Zone</span>
            <div className="text-sm font-bold text-trading-text">
              {fmtPrice(signalDetails.entryRange.min, selectedPair)} — {fmtPrice(signalDetails.entryRange.max, selectedPair)}
            </div>
          </div>
          <div className="text-center">
            <span className="text-[10px] font-semibold uppercase tracking-wide text-emerald-400">Take Profit</span>
            <div className="flex items-center gap-2 text-sm font-bold text-trading-text">
              <span className="text-emerald-400/60">{fmtPrice(signalDetails.takeProfit1, selectedPair)}</span>
              <span className="text-emerald-400/80">{fmtPrice(signalDetails.takeProfit2, selectedPair)}</span>
              <span className="text-emerald-400">{fmtPrice(signalDetails.takeProfit3, selectedPair)}</span>
            </div>
          </div>
        </div>

        {/* Horizontal bar */}
        <div className="relative h-3 mt-2 mb-1 rounded-full overflow-hidden bg-trading-bg">
          {/* Left zone */}
          <div
            className={`absolute top-0 bottom-0 ${isBuy ? 'bg-red-500/30' : 'bg-emerald-500/30'}`}
            style={{ left: 0, width: `${leftZoneEnd}%` }}
          />
          {/* Entry zone */}
          <div
            className="absolute top-0 bottom-0 bg-blue-500/30"
            style={{ left: `${leftZoneEnd}%`, width: `${rightZoneStart - leftZoneEnd}%` }}
          />
          {/* Right zone */}
          <div
            className={`absolute top-0 bottom-0 ${isBuy ? 'bg-emerald-500/30' : 'bg-red-500/30'}`}
            style={{ left: `${rightZoneStart}%`, width: `${100 - rightZoneStart}%` }}
          />
          {/* SL marker */}
          <div className="absolute top-0 bottom-0 w-0.5 bg-red-500" style={{ left: `${slPct}%` }} />
          {/* TP1 marker */}
          <div className="absolute top-0 bottom-0 w-0.5 bg-emerald-400" style={{ left: `${tp1Pct}%` }} />
          {/* TP2 marker */}
          <div className="absolute top-0 bottom-0 w-0.5 bg-emerald-500" style={{ left: `${tp2Pct}%` }} />
          {/* TP3 marker */}
          <div className="absolute top-0 bottom-0 w-0.5 bg-emerald-600" style={{ left: `${tp3Pct}%` }} />
          {/* Current price marker */}
          <div className="absolute -top-1 -bottom-1 w-0.5 bg-white z-10" style={{ left: `${currentPct}%` }}>
            <div className="absolute -top-4 left-1/2 -translate-x-1/2 text-[9px] font-bold text-white bg-trading-accent/80 px-1 rounded whitespace-nowrap">
              ▲ Now
            </div>
          </div>
        </div>

        {/* Pip distances row */}
        {isBuy ? (
          <div className="flex justify-between text-[10px] text-trading-muted">
            <span className="text-red-400">{slPips.toFixed(1)} pips</span>
            <span className="text-blue-400">▲ Now</span>
            <span className="text-emerald-400/60">{tp1Pips.toFixed(1)}</span>
            <span className="text-emerald-400/80">{tp2Pips.toFixed(1)}</span>
            <span className="text-emerald-400">{tp3Pips.toFixed(1)} pips</span>
          </div>
        ) : (
          <div className="flex justify-between text-[10px] text-trading-muted">
            <span className="text-emerald-400">{tp3Pips.toFixed(1)} pips</span>
            <span className="text-emerald-400/80">{tp2Pips.toFixed(1)}</span>
            <span className="text-emerald-400/60">{tp1Pips.toFixed(1)}</span>
            <span className="text-blue-400">▲ Now</span>
            <span className="text-red-400">{slPips.toFixed(1)} pips</span>
          </div>
        )}

        {/* Risk/Reward compact line */}
        <div className="flex items-center gap-3 mt-3">
          <span className="text-xs text-trading-muted">Risk/Reward:</span>
          <span className={`text-xs font-bold ${rrQuality.cls}`}>
            1:{rr1.toFixed(1)} / 1:{rr2.toFixed(1)} / 1:{rr3.toFixed(1)} {rrQuality.label}
          </span>
          <div className="flex-1 h-1.5 bg-trading-bg rounded-full overflow-hidden max-w-[120px]">
            <div className={`h-full rounded-full ${rrQuality.bg} transition-all duration-500`}
              style={{ width: `${Math.min((rr2 / 3) * 100, 100)}%` }} />
          </div>
        </div>
      </div>

      {/* ── Section 3: Action Footer ── */}
      <div className="border-t border-trading-border px-5 py-3">
        {/* Signal status warning/info text */}
        {signalStatus === 'EXPIRED' && (
          <div className="flex items-center gap-1.5 text-[11px] text-gray-400 mb-2">
            <AlertTriangle size={12} className="text-gray-400" />
            <span>Signal expired — wait for fresh signal</span>
          </div>
        )}
        {signalStatus === 'OPTIMAL_ENTRY' && (
          <div className="flex items-center gap-1.5 text-[11px] text-emerald-400 mb-2">
            <Zap size={12} className="text-emerald-400" />
            <span>Optimal entry window</span>
          </div>
        )}
        {signalStatus === 'ABOUT_TO_EXPIRE' && (
          <div className="flex items-center gap-1.5 text-[11px] text-amber-400 mb-2">
            <AlertTriangle size={12} className="text-amber-400" />
            <span>Signal expiring soon</span>
          </div>
        )}

        {/* Summary line */}
        <div className="flex items-center gap-1 text-[11px] text-trading-muted mb-2 flex-wrap">
          <AlertTriangle size={10} className="shrink-0" />
          <span className="font-medium text-trading-text">{posSizeLots.toFixed(2)} lots</span>
          <span>·</span>
          <span>Risk: <span className="text-trading-text font-medium">${riskAmount.toFixed(0)} ({riskPct}%)</span></span>
          <span>·</span>
          <span>SL: <span className="text-trading-text">{fmtPrice(signalDetails.stopLoss, selectedPair)}</span></span>
          <span>·</span>
          <span>TP1: <span className="text-trading-text">{fmtPrice(signalDetails.takeProfit1, selectedPair)}</span></span>
          <span>·</span>
          <span>TP2: <span className="text-trading-text">{fmtPrice(signalDetails.takeProfit2, selectedPair)}</span></span>
          <span>·</span>
          <span>TP3: <span className="text-trading-text">{fmtPrice(signalDetails.takeProfit3, selectedPair)}</span></span>
        </div>

        {/* Controls row */}
        <div className="flex items-center gap-3">
          {/* Trade Style Toggle */}
          {onTradeStyleChange && (
            <div className="flex items-center gap-1 bg-trading-bg rounded-lg p-0.5">
              <button
                onClick={() => onTradeStyleChange('scalp')}
                className={`px-2.5 py-1 rounded-md text-xs font-medium transition-colors ${
                  tradeStyle === 'scalp'
                    ? 'bg-trading-accent text-white'
                    : 'text-trading-muted hover:text-trading-text'
                }`}
              >
                Scalp
              </button>
              <button
                onClick={() => onTradeStyleChange('swing')}
                className={`px-2.5 py-1 rounded-md text-xs font-medium transition-colors ${
                  tradeStyle === 'swing'
                    ? 'bg-trading-accent text-white'
                    : 'text-trading-muted hover:text-trading-text'
                }`}
              >
                Swing
              </button>
            </div>
          )}

          {/* Risk slider */}
          <div className="flex items-center gap-2 flex-1 min-w-0">
            <span className="text-[10px] text-trading-muted whitespace-nowrap">Risk: {riskPct}%</span>
            <input type="range" min="0.5" max="5" step="0.5" value={riskPct}
              onChange={(e) => setRiskPct(parseFloat(e.target.value))}
              className="flex-1 h-1 min-w-[60px]" />
          </div>

          {/* Trade buttons */}
          <div className="flex gap-2 shrink-0">
            <button onClick={onBuy}
              disabled={signalStatus === 'EXPIRED'}
              className={`btn-buy px-4 py-2 text-sm font-semibold rounded-lg flex items-center gap-1 transition-all ${isBuyish(signalDetails.signal) ? 'ring-2 ring-emerald-500 scale-[1.02]' : 'opacity-70'} ${signalStatus === 'EXPIRED' ? 'opacity-50 cursor-not-allowed' : ''} ${signalStatus === 'OPTIMAL_ENTRY' ? 'animate-pulse shadow-lg shadow-emerald-500/25' : ''}`}>
              <TrendingUp size={14} /> BUY
            </button>
            <button onClick={onSell}
              disabled={signalStatus === 'EXPIRED'}
              className={`btn-sell px-4 py-2 text-sm font-semibold rounded-lg flex items-center gap-1 transition-all ${isSellish(signalDetails.signal) ? 'ring-2 ring-red-500 scale-[1.02]' : 'opacity-70'} ${signalStatus === 'EXPIRED' ? 'opacity-50 cursor-not-allowed' : ''} ${signalStatus === 'OPTIMAL_ENTRY' ? 'animate-pulse shadow-lg shadow-red-500/25' : ''}`}>
              <TrendingDown size={14} /> SELL
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
