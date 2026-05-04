import type { AIPrediction, AIPredictionRecommendation, ChartSignalMarker, ScanResult, SourceMetadata } from '../types'

function readString(...values: unknown[]) {
  for (const value of values) {
    if (typeof value === 'string' && value.trim().length > 0) return value
  }
  return undefined
}

function readNumber(...values: unknown[]) {
  for (const value of values) {
    if (typeof value === 'number' && Number.isFinite(value)) return value
    if (typeof value === 'string' && value.trim().length > 0) {
      const parsed = Number(value)
      if (Number.isFinite(parsed)) return parsed
    }
  }
  return null
}

function readRecord(value: unknown): Record<string, unknown> | null {
  return typeof value === 'object' && value !== null ? value as Record<string, unknown> : null
}

function readWarnings(...values: unknown[]) {
  const warnings: string[] = []
  values.forEach((value) => {
    if (Array.isArray(value)) {
      value.forEach((item) => {
        if (typeof item === 'string' && item.trim()) warnings.push(item.trim())
      })
    }
  })
  return Array.from(new Set(warnings))
}

export function normalizeRecommendation(value: unknown): AIPredictionRecommendation {
  const normalized = String(value ?? 'HOLD').trim().toUpperCase().replace(/\s+/g, '_')
  if (normalized === 'BUY' || normalized === 'LONG' || normalized === 'STRONG_BUY') return 'BUY'
  if (normalized === 'SELL' || normalized === 'SHORT' || normalized === 'STRONG_SELL') return 'SELL'
  if (normalized === 'NO_TRADE' || normalized === 'NO TRADE') return 'NO_TRADE'
  if (normalized === 'NEUTRAL') return 'NEUTRAL'
  return 'HOLD'
}

export function normalizePredictionPayload(payload: Record<string, unknown>, fallbackSymbol: string): AIPrediction {
  const entryRange = readRecord(payload.entryRange) ?? readRecord(payload.entry_range)
  const sourceMetadata = (readRecord(payload.sourceMetadata) ?? readRecord(payload.source_metadata)) as SourceMetadata | null
  const recommendation = normalizeRecommendation(payload.recommendation ?? payload.signal ?? payload.direction)
  const generatedAt = readString(payload.generatedAt, payload.generated_at, payload.timestamp)
  const dataFetchedAt = readNumber(payload.data_fetched_at, payload.dataFetchedAt)
  const qualityFlags = sourceMetadata?.qualityFlags ?? []

  return {
    symbol: readString(payload.symbol) ?? fallbackSymbol,
    recommendation,
    confidence: readNumber(payload.confidence) ?? 0,
    timeframe: readString(payload.timeframe),
    tradeStyle: readString(payload.tradeStyle, payload.trade_style),
    marketRegime: readString(payload.marketRegime, payload.market_regime),
    rationale: readString(payload.rationale, payload.reason, payload.explanation),
    warnings: readWarnings(payload.warnings, qualityFlags),
    generatedAt: generatedAt ?? (dataFetchedAt ? new Date(dataFetchedAt * 1000).toISOString() : undefined),
    dataFetchedAt,
    source: readString(payload.source),
    sourceMetadata,
    currentPrice: readNumber(payload.currentPrice, payload.current_price),
    setup: {
      entry: readNumber(payload.entry),
      entryMin: readNumber(entryRange?.min, payload.entryMin, payload.entry_min),
      entryMax: readNumber(entryRange?.max, payload.entryMax, payload.entry_max),
      stopLoss: readNumber(payload.stopLoss, payload.stop_loss),
      takeProfit1: readNumber(payload.takeProfit1, payload.take_profit1),
      takeProfit2: readNumber(payload.takeProfit2, payload.take_profit2),
      takeProfit3: readNumber(payload.takeProfit3, payload.take_profit3),
      riskReward: readNumber(payload.riskReward, payload.risk_reward),
    },
    predictionSource: readString(payload.predictionSource, payload.prediction_source),
  }
}

export function normalizePredictionFromScanResult(result: ScanResult): AIPrediction {
  return normalizePredictionPayload({
    symbol: result.symbol,
    signal: result.recommendation ?? result.signal,
    confidence: result.confidence,
    timeframe: result.timeframe,
    trade_style: result.trade_style,
    market_regime: result.market_regime,
    reason: result.reason,
    source_metadata: result.source_metadata,
    entry_range: result.entry_range,
    stop_loss: result.stop_loss,
    take_profit1: result.take_profit1,
    take_profit2: result.take_profit2,
    take_profit3: result.take_profit3,
    risk_reward: result.risk_reward,
    data_fetched_at: result.data_fetched_at,
    warnings: result.warnings,
  }, result.symbol)
}

export function isNoTradePrediction(prediction?: AIPrediction | null) {
  if (!prediction) return true
  const recommendation = normalizeRecommendation(prediction.recommendation)
  return recommendation === 'HOLD' || recommendation === 'NO_TRADE' || recommendation === 'NEUTRAL'
}

export function isPredictionStale(prediction?: AIPrediction | null) {
  if (!prediction) return false
  const status = prediction.sourceMetadata?.marketStatus?.toLowerCase()
  if (status === 'stale') return true
  if (prediction.sourceMetadata?.qualityFlags?.some((flag) => flag.toLowerCase().includes('stale'))) return true
  const freshnessSeconds = prediction.sourceMetadata?.freshnessSeconds
  if (typeof freshnessSeconds === 'number' && freshnessSeconds > 900) return true
  if (prediction.dataFetchedAt && Date.now() / 1000 - prediction.dataFetchedAt > 900) return true
  return false
}

export function hasPredictionSetupLevels(prediction?: AIPrediction | null) {
  if (!prediction) return false
  return [
    prediction.setup.entry ?? prediction.setup.entryMin,
    prediction.setup.stopLoss,
    prediction.setup.takeProfit1,
  ].every((value) => typeof value === 'number' && Number.isFinite(value) && value > 0)
}

export function isActionablePrediction(prediction?: AIPrediction | null) {
  if (!prediction) return false
  return !isNoTradePrediction(prediction) && !isPredictionStale(prediction) && prediction.confidence >= 55 && hasPredictionSetupLevels(prediction)
}

export function predictionToneClass(prediction?: AIPrediction | null) {
  const recommendation = normalizeRecommendation(prediction?.recommendation)
  if (recommendation === 'BUY') return 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300'
  if (recommendation === 'SELL') return 'border-red-500/30 bg-red-500/10 text-red-300'
  if (recommendation === 'NO_TRADE') return 'border-amber-500/30 bg-amber-500/10 text-amber-200'
  return 'border-slate-500/30 bg-slate-500/10 text-slate-300'
}

export function confidenceToneClass(confidence: number) {
  if (confidence >= 75) return 'text-emerald-300'
  if (confidence >= 55) return 'text-amber-200'
  return 'text-slate-300'
}

export function formatPredictionTimestamp(prediction?: AIPrediction | null) {
  if (!prediction) return 'No update'
  const value = prediction.generatedAt ?? (prediction.dataFetchedAt ? new Date(prediction.dataFetchedAt * 1000).toISOString() : null)
  if (!value) return 'No timestamp'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return 'No timestamp'
  return date.toLocaleTimeString()
}

export function predictionToChartSignal(prediction?: AIPrediction | null): ChartSignalMarker | null {
  if (!isActionablePrediction(prediction) || !prediction) return null
  const direction = normalizeRecommendation(prediction.recommendation)
  if (direction !== 'BUY' && direction !== 'SELL') return null
  const entryMin = prediction.setup.entryMin ?? prediction.setup.entry ?? 0
  const entryMax = prediction.setup.entryMax ?? prediction.setup.entry ?? 0
  return {
    entry: prediction.setup.entry ?? (entryMin + entryMax) / 2,
    entryMin,
    entryMax,
    stopLoss: prediction.setup.stopLoss,
    takeProfit1: prediction.setup.takeProfit1,
    takeProfit2: prediction.setup.takeProfit2,
    takeProfit3: prediction.setup.takeProfit3,
    signalId: `${prediction.symbol}:${prediction.timeframe ?? 'tf'}:${prediction.generatedAt ?? prediction.dataFetchedAt ?? 'prediction'}`,
    direction,
    timestamp: prediction.generatedAt ?? new Date().toISOString(),
    status: 'VALID',
    setupStatus: 'pending',
    confidence: prediction.confidence,
    symbol: prediction.symbol,
  }
}