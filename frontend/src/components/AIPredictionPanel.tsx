import { AlertTriangle, Brain, Clock, Minus, RefreshCw, ShieldAlert, Target, TrendingDown, TrendingUp } from 'lucide-react'
import type { AIPrediction, ForexPair } from '../types'
import { DataSourceBadge } from './DataSourceBadge'
import { FreshnessPill } from './FreshnessPill'
import {
  confidenceToneClass,
  formatPredictionTimestamp,
  hasPredictionSetupLevels,
  isActionablePrediction,
  isNoTradePrediction,
  isPredictionStale,
  normalizeRecommendation,
  predictionToneClass,
} from '../lib/predictionPresentation'

interface AIPredictionPanelProps {
  pair: ForexPair
  prediction: AIPrediction | null
  loading?: boolean
  error?: string | null
  compact?: boolean
  onRefresh?: () => void
}

function formatPrice(pair: ForexPair, value?: number | null) {
  if (typeof value !== 'number' || !Number.isFinite(value) || value <= 0) return '—'
  if (pair.basePriceApprox < 10) return value.toFixed(5)
  if (pair.basePriceApprox < 200) return value.toFixed(3)
  return value.toFixed(2)
}

function RecommendationIcon({ recommendation }: { recommendation: string }) {
  const normalized = normalizeRecommendation(recommendation)
  if (normalized === 'BUY') return <TrendingUp size={14} />
  if (normalized === 'SELL') return <TrendingDown size={14} />
  return <Minus size={14} />
}

export function AIPredictionPanel({ pair, prediction, loading = false, error = null, compact = false, onRefresh }: AIPredictionPanelProps) {
  const recommendation = normalizeRecommendation(prediction?.recommendation)
  const stale = isPredictionStale(prediction)
  const noTrade = isNoTradePrediction(prediction)
  const actionable = isActionablePrediction(prediction)
  const warnings = [
    ...(prediction?.warnings ?? []),
    ...(stale ? ['Market data appears stale. Wait for a fresh update before acting.'] : []),
    ...(noTrade ? ['No actionable trade: confidence, setup quality, or safety gates are not sufficient.'] : []),
    ...(prediction && prediction.confidence < 55 ? ['Confidence is below the action threshold.'] : []),
  ]
  const uniqueWarnings = Array.from(new Set(warnings))
  const setup = prediction?.setup

  return (
    <section className={`border border-[#1c2333] bg-[#0d1117] ${compact ? 'p-3' : 'rounded-lg p-4'}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2 text-[10px] font-semibold uppercase tracking-[0.2em] text-blue-300">
            <Brain size={13} />
            AI prediction
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-2">
            <span className="text-sm font-bold text-trading-text">{pair.symbol}</span>
            {prediction?.timeframe ? <span className="rounded bg-[#1c2333] px-1.5 py-0.5 text-[10px] uppercase text-trading-muted">{prediction.timeframe}</span> : null}
            {prediction?.tradeStyle ? <span className="rounded bg-[#1c2333] px-1.5 py-0.5 text-[10px] capitalize text-trading-muted">{prediction.tradeStyle}</span> : null}
          </div>
        </div>
        <button
          type="button"
          onClick={onRefresh}
          disabled={loading || !onRefresh}
          className="rounded border border-[#1c2333] p-1.5 text-trading-muted transition-colors hover:text-trading-text disabled:cursor-not-allowed disabled:opacity-40"
          title="Refresh AI prediction"
        >
          <RefreshCw size={13} className={loading ? 'animate-spin' : ''} />
        </button>
      </div>

      {loading && !prediction ? (
        <div className="mt-3 space-y-2">
          <div className="h-9 animate-pulse rounded bg-[#161b26]" />
          <div className="h-16 animate-pulse rounded bg-[#161b26]" />
        </div>
      ) : error && !prediction ? (
        <div className="mt-3 rounded border border-red-500/25 bg-red-500/10 p-3 text-[11px] text-red-200">
          {error}
        </div>
      ) : prediction ? (
        <>
          <div className="mt-3 grid grid-cols-2 gap-2">
            <div className={`rounded-lg border p-3 ${predictionToneClass(prediction)}`}>
              <div className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-wide">
                <RecommendationIcon recommendation={prediction.recommendation} />
                {recommendation === 'NO_TRADE' ? 'No trade' : recommendation}
              </div>
              <div className={`mt-1 text-2xl font-black tabular-nums ${confidenceToneClass(prediction.confidence)}`}>
                {Math.round(prediction.confidence)}%
              </div>
              <div className="text-[10px] text-current/70">confidence</div>
            </div>
            <div className="rounded-lg border border-[#1c2333] bg-[#0b0e14] p-3">
              <div className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-wide text-trading-muted">
                <Clock size={12} />
                Freshness
              </div>
              <div className={`mt-1 text-sm font-bold ${stale ? 'text-red-300' : 'text-trading-text'}`}>
                {formatPredictionTimestamp(prediction)}
              </div>
              <div className="mt-1 text-[10px] text-trading-muted">{prediction.marketRegime ?? 'regime unknown'}</div>
            </div>
          </div>

          <div className="mt-3 flex flex-wrap gap-1.5">
            {prediction.sourceMetadata ? (
              <>
                <DataSourceBadge sourceType={prediction.sourceMetadata.sourceType} sourceName={prediction.sourceMetadata.sourceName} />
                <FreshnessPill freshnessSeconds={prediction.sourceMetadata.freshnessSeconds} marketStatus={prediction.sourceMetadata.marketStatus} />
              </>
            ) : null}
            <span className={`inline-flex items-center rounded-full px-2 py-1 text-[11px] font-medium ${
              actionable ? 'border border-emerald-500/30 bg-emerald-500/10 text-emerald-300' : 'border border-amber-500/30 bg-amber-500/10 text-amber-200'
            }`}>
              {actionable ? 'Setup levels available' : 'Observation only'}
            </span>
          </div>

          <p className="mt-3 text-[11px] leading-5 text-trading-muted">
            {prediction.rationale ?? 'No rationale was returned for this prediction.'}
          </p>

          {hasPredictionSetupLevels(prediction) ? (
            <div className="mt-3 rounded-lg border border-[#1c2333] bg-[#0b0e14] p-3">
              <div className="mb-2 flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-wide text-trading-muted">
                <Target size={12} />
                Suggested levels
              </div>
              <div className="grid grid-cols-2 gap-2 text-[11px] tabular-nums">
                <div>
                  <div className="text-trading-muted">Entry</div>
                  <div className="font-semibold text-blue-300">
                    {setup?.entryMin && setup?.entryMax
                      ? `${formatPrice(pair, setup.entryMin)}–${formatPrice(pair, setup.entryMax)}`
                      : formatPrice(pair, setup?.entry)}
                  </div>
                </div>
                <div>
                  <div className="text-trading-muted">Stop</div>
                  <div className="font-semibold text-red-300">{formatPrice(pair, setup?.stopLoss)}</div>
                </div>
                <div>
                  <div className="text-trading-muted">Take profit</div>
                  <div className="font-semibold text-emerald-300">{formatPrice(pair, setup?.takeProfit1)}</div>
                </div>
                <div>
                  <div className="text-trading-muted">Risk/reward</div>
                  <div className="font-semibold text-trading-text">{setup?.riskReward ? `${setup.riskReward.toFixed(2)}R` : '—'}</div>
                </div>
              </div>
            </div>
          ) : null}

          {uniqueWarnings.length > 0 ? (
            <div className="mt-3 rounded-lg border border-amber-500/25 bg-amber-500/10 p-3">
              <div className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-wide text-amber-200">
                <ShieldAlert size={12} />
                Safety notes
              </div>
              <ul className="mt-1 space-y-1 text-[11px] leading-4 text-amber-100/80">
                {uniqueWarnings.slice(0, 4).map((warning) => (
                  <li key={warning} className="flex gap-1.5">
                    <AlertTriangle size={11} className="mt-0.5 shrink-0" />
                    <span>{warning}</span>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </>
      ) : (
        <div className="mt-3 rounded border border-[#1c2333] bg-[#0b0e14] p-3 text-[11px] text-trading-muted">
          No prediction has been loaded for this symbol yet.
        </div>
      )}
    </section>
  )
}