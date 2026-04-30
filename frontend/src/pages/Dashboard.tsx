import { useState, useEffect, useCallback, useRef, useMemo } from 'react'
import { TrendingUp, TrendingDown, Activity, Zap, Loader2 } from 'lucide-react'
import type { AccountMetrics, ForexPair, AIRecommendation, ChartSignalMarker, SignalStatus, AIScoreData, DetectedPattern, CopyTradingSettings, CopyTradePosition, CopyTradeStats } from '../types'
import { getPairBySymbol } from '../config/forexPairs'
import { PairSelector } from '../components/PairSelector'
import { ChartToolbar } from '../components/ChartToolbar'
import { TradingChart, ChartErrorBoundary } from '../components/TradingChart'
import { AIRecommendations, fetchRecommendations } from '../components/AIRecommendations'
import { PairHeatmap } from '../components/PairHeatmap'
import { SentimentPanel } from '../components/SentimentPanel'
import { SentimentHeatmap } from '../components/SentimentHeatmap'
import { AITradingHub } from '../components/AITradingHub'
import { SignalBreakdown } from '../components/SignalBreakdown'
import { GoldContextPanel } from '../components/GoldContextPanel'
import { OpportunityBoard } from '../components/OpportunityBoard'
import { SpotProviderStatusCard } from '../components/SpotProviderStatusCard'
import { StrategyCatalog } from '../components/StrategyCatalog'
import { AutomationTemplateCard } from '../components/AutomationTemplateCard'
import { AutomationCenterCard } from '../components/AutomationCenterCard'
import WatchlistCard from '../components/WatchlistCard'
import EconomicCalendar from '../components/EconomicCalendar'
import { GoldScalperPro } from '../components/GoldScalperPro'
import type { ScalpTradeData } from '../components/GoldScalperPro'
import type { GoldContextData, SourceMetadata, DatasourceHealthResponse, OpportunityRow, StrategyDefinition, AutomationCenterState } from '../types'
import api from '../lib/api'

interface DashboardProps {
  selectedPair: ForexPair
  onPairChange: (pair: ForexPair) => void
  activePairs: ForexPair[]
  recentPairs?: ForexPair[]
  defaultPairSymbol?: string
  onSetDefaultPair?: (pair: ForexPair) => void
  apiConnected?: boolean
  backendBroker?: {
    id: string | null
    connected: boolean
    name: string | null
    environment?: string | null
  } | null
}

type Signal = 'buy' | 'sell' | 'hold' | 'strong_buy' | 'strong_sell'

type Timeframe = '1m' | '5m' | '15m' | '1h' | '4h' | '1d'
type MarketRegime = 'trending_up' | 'trending_down' | 'ranging' | 'volatile'

interface MultiTimeframeData {
  tf: string
  signal: 'BUY' | 'SELL' | 'HOLD'
  alignment: number
}

interface SignalDetails {
  signal: Signal
  confidence: number
  reason: string
  entryRange: { min: number; max: number }
  stopLoss: number
  takeProfit1: number
  takeProfit2: number
  takeProfit3: number
  riskReward: number
  timeframe: Timeframe
  marketRegime: MarketRegime
  indicators: { name: string; value: string; signal: 'bullish' | 'bearish' | 'neutral' }[]
  aiScore?: AIScoreData
  patterns?: DetectedPattern[]
  patternAccuracy?: number | null
}

interface ActiveSignalMeta {
  signalId: string
  direction: 'BUY' | 'SELL' | 'HOLD'
  expiresAt?: string
  confidence: number
}

interface ActiveBrokerInfo {
  id: string
  name: string
  connected: boolean
  type?: string
  environment?: string
}

function Dashboard({
  selectedPair,
  onPairChange,
  activePairs,
  recentPairs,
  defaultPairSymbol,
  onSetDefaultPair,
  apiConnected = false,
  backendBroker = null,
}: DashboardProps) {
  const autoExecutionLockRef = useRef<string | null>(null)
  // Chart state
  const [timeframe, setTimeframe] = useState<string>('1h')
  const goldPair = useMemo(() => getPairBySymbol('XAU/USD') ?? selectedPair, [selectedPair])
  
  // AI Recommendations state
  const [showAIRecommendations, setShowAIRecommendations] = useState(false)
  const [recommendations, setRecommendations] = useState<AIRecommendation[]>([])
  
  // Price and signal state
  const [currentPrice, setCurrentPrice] = useState(selectedPair.basePriceApprox)
  const [priceChange, setPriceChange] = useState(0)
  const [priceChangePercent, setPriceChangePercent] = useState(0)
  const [isLoading, setIsLoading] = useState(false)
  const [tradeStyle, setTradeStyle] = useState<'scalp' | 'swing'>('swing')
  const [tradeStatus, setTradeStatus] = useState<{type: 'success' | 'error', message: string} | null>(null)
  const [, setIsTrading] = useState(false)
  const [chartSignals, setChartSignals] = useState<ChartSignalMarker[]>([])
  const [signalStatus, setSignalStatus] = useState<SignalStatus | null>(null)
  const [multiTimeframe, setMultiTimeframe] = useState<MultiTimeframeData[]>([])
  const [lastSuccessfulFetch, setLastSuccessfulFetch] = useState<number>(Date.now())
  const [fetchError, setFetchError] = useState<string | null>(null)
  const [quoteSource, setQuoteSource] = useState<string>('unknown')
  const [sourceMetadata, setSourceMetadata] = useState<SourceMetadata | null>(null)
  const [goldContext, setGoldContext] = useState<GoldContextData | null>(null)
  const [datasourceHealth, setDatasourceHealth] = useState<DatasourceHealthResponse | null>(null)
  const [topOpportunities, setTopOpportunities] = useState<OpportunityRow[]>([])
  const [xauOpportunities, setXAUOpportunities] = useState<OpportunityRow[]>([])
  const [strategies, setStrategies] = useState<StrategyDefinition[]>([])
  const [selectedStrategy, setSelectedStrategy] = useState<StrategyDefinition | null>(null)
  const [automationCenter, setAutomationCenter] = useState<AutomationCenterState | null>(null)
  const [activeBroker, setActiveBroker] = useState<ActiveBrokerInfo | null>(null)

  const effectiveAnalysisTimeframe = useMemo(() => {
    if (tradeStyle === 'scalp') {
      if (timeframe === '1m' || timeframe === '5m') return timeframe
      return '1m'
    }
    return timeframe
  }, [timeframe, tradeStyle])

  const quoteTimeframe = useMemo(() => {
    if (tradeStyle === 'scalp') return timeframe === '5m' ? '5m' : '1m'
    if (selectedPair.symbol === 'XAU/USD') return '15m'
    if (timeframe === '1m' || timeframe === '5m' || timeframe === '15m') return timeframe
    return '1m'
  }, [selectedPair.symbol, timeframe, tradeStyle])

  const fetchIntervalMs = (() => {
    if (tradeStyle === 'scalp') return 10000
    if (timeframe === '1m' || timeframe === '5m') return 10000
    if (timeframe === '15m') return 15000
    return 30000
  })()

  const dataFreshness = useMemo<'live' | 'delayed' | 'stale'>(() => {
    const ageSeconds = Math.max(0, Math.round((Date.now() - lastSuccessfulFetch) / 1000))
    if (ageSeconds <= Math.max(6, Math.round(fetchIntervalMs / 1000) + 1)) return 'live'
    if (ageSeconds <= 20) return 'delayed'
    return 'stale'
  }, [lastSuccessfulFetch, fetchIntervalMs])

  // Ref to avoid stale closure for currentPrice in callbacks
  const currentPriceRef = useRef(currentPrice)
  useEffect(() => { currentPriceRef.current = currentPrice }, [currentPrice])

  // Copy trading state
  const [copyTradingEnabled, setCopyTradingEnabled] = useState(false)
  const [copySettings, setCopySettings] = useState<CopyTradingSettings | null>(null)
  const [copiedPositions, setCopiedPositions] = useState<CopyTradePosition[]>([])
  const [copyHistory, setCopyHistory] = useState<CopyTradePosition[]>([])
  const [copyStats, setCopyStats] = useState<CopyTradeStats | null>(null)
  const [copyHistorySymbolFilter, setCopyHistorySymbolFilter] = useState<string>('all')
  const [copyHistoryDirectionFilter, setCopyHistoryDirectionFilter] = useState<'ALL' | 'BUY' | 'SELL'>('ALL')
  const [copyHistoryStatusFilter, setCopyHistoryStatusFilter] = useState<string>('all')
  const [copyHistoryRangeFilter, setCopyHistoryRangeFilter] = useState<'all' | '7d' | '30d' | '90d'>('all')
  const [copyTradeLoading, setCopyTradeLoading] = useState(false)
  const [copyRiskPct, setCopyRiskPct] = useState(1)
  const [activeSignalMeta, setActiveSignalMeta] = useState<ActiveSignalMeta | null>(null)

  const [signalDetails, setSignalDetails] = useState<SignalDetails>({
    signal: 'hold',
    confidence: 50,
    reason: 'Loading market analysis...',
    entryRange: { min: 0, max: 0 },
    stopLoss: 0,
    takeProfit1: 0,
    takeProfit2: 0,
    takeProfit3: 0,
    riskReward: 2.0,
    timeframe: '1h',
    marketRegime: 'ranging',
    indicators: [],
    aiScore: undefined,
    patterns: [],
    patternAccuracy: null,
  })
  

  const [metrics] = useState<AccountMetrics>({
    balance: 10500.00,
    equity: 10509.90,
    openPnL: 9.90,
    dayPnL: 45.20,
    totalReturn: 5.1,
    maxDrawdown: -2.3,
    sharpeRatio: 1.45,
    winRate: 58.5,
    totalTrades: 127,
  })

  const refreshCopyData = useCallback(async () => {
    try {
      const symbolFilter = copyHistorySymbolFilter !== 'all' ? copyHistorySymbolFilter : undefined
      const directionFilter = copyHistoryDirectionFilter !== 'ALL' ? copyHistoryDirectionFilter : undefined
      const statusFilter = copyHistoryStatusFilter !== 'all' ? copyHistoryStatusFilter : undefined
      const nowSeconds = Math.floor(Date.now() / 1000)
      const fromTs = copyHistoryRangeFilter === '7d'
        ? nowSeconds - 7 * 24 * 60 * 60
        : copyHistoryRangeFilter === '30d'
          ? nowSeconds - 30 * 24 * 60 * 60
          : copyHistoryRangeFilter === '90d'
            ? nowSeconds - 90 * 24 * 60 * 60
            : undefined
      const [posData, statsData, historyData] = await Promise.all([
        api.fetchCopyPositions(),
        api.fetchCopyStats(),
        api.fetchCopyHistoryFiltered({
          limit: 50,
          symbol: symbolFilter,
          status: statusFilter,
          direction: directionFilter,
          fromTs,
        }),
      ])
      setCopiedPositions(posData.positions || [])
      setCopyStats(statsData)
      setCopyHistory(historyData.history || [])
    } catch (err) {
      console.error('Failed to fetch copy trading data:', err)
    }
  }, [copyHistoryDirectionFilter, copyHistoryRangeFilter, copyHistoryStatusFilter, copyHistorySymbolFilter])

  const loadCopySettings = useCallback(async () => {
    try {
      const settings = await api.fetchCopyTradingSettings()
      setCopySettings(settings)
      setCopyTradingEnabled(settings.enabled)
      if (!settings.enabled) {
        setCopiedPositions([])
        setCopyHistory([])
        setCopyStats(null)
      }
    } catch (err) {
      console.error('Failed to load copy trading settings:', err)
    }
  }, [])

  useEffect(() => {
    loadCopySettings()
  }, [loadCopySettings])

  // Fast quote polling keeps hero price reactive without duplicating full analysis cadence.
  useEffect(() => {
    let cancelled = false
    let inFlight = false
    const quoteIntervalMs = Math.max(fetchIntervalMs, 15000)

    const fetchQuote = async () => {
      if (inFlight) return
      inFlight = true
      try {
        const data = await api.fetchQuote(selectedPair.symbol, quoteTimeframe, tradeStyle)
        if (cancelled) return
        setCurrentPrice(data.currentPrice)
        setPriceChange(data.priceChange)
        setPriceChangePercent(data.priceChangePercent)
        setQuoteSource(data.priceSource ?? data.source ?? 'unknown')
        setSourceMetadata(data.sourceMetadata ?? null)
        setLastSuccessfulFetch(Date.now())
        setFetchError(null)
      } catch {
        if (!cancelled) setFetchError('Unable to refresh live quote')
      } finally {
        inFlight = false
      }
    }

    fetchQuote()
    const interval = setInterval(fetchQuote, quoteIntervalMs)
    return () => {
      cancelled = true
      clearInterval(interval)
    }
  }, [selectedPair.symbol, quoteTimeframe, fetchIntervalMs, tradeStyle])

  useEffect(() => {
    if (selectedPair.symbol !== 'XAU/USD') {
      setGoldContext(null)
      return
    }
    api.fetchGoldContext().then(setGoldContext).catch(() => setGoldContext(null))
  }, [selectedPair.symbol, tradeStyle])

  useEffect(() => {
    api.fetchTopOpportunities(effectiveAnalysisTimeframe, tradeStyle)
      .then((data) => setTopOpportunities(data.results || []))
      .catch(() => setTopOpportunities([]))
  }, [effectiveAnalysisTimeframe, tradeStyle])

  useEffect(() => {
    api.fetchStrategies().then((data) => setStrategies(data.results || [])).catch(() => setStrategies([]))
  }, [])

  useEffect(() => {
    api.fetchAutomationCenter().then(setAutomationCenter).catch(() => setAutomationCenter(null))
  }, [strategies])

  useEffect(() => {
    if (selectedPair.symbol !== 'XAU/USD') {
      setXAUOpportunities([])
      return
    }
    api.fetchXAUOpportunities()
      .then((data) => setXAUOpportunities(data.results || []))
      .catch(() => setXAUOpportunities([]))
  }, [selectedPair.symbol, tradeStyle])

  useEffect(() => {
    if (selectedPair.symbol !== 'XAU/USD') {
      setDatasourceHealth(null)
      return
    }
    const load = () => api.fetchDatasourceHealth().then(setDatasourceHealth).catch(() => setDatasourceHealth(null))
    load()
    const interval = setInterval(load, 15000)
    return () => clearInterval(interval)
  }, [selectedPair.symbol, tradeStyle])

  useEffect(() => {
    if (tradeStyle === 'scalp' && timeframe !== '1m' && timeframe !== '5m') {
      setTimeframe('1m')
    }
  }, [tradeStyle, timeframe])

  // Fetch full market analysis when pair or timeframe changes
  useEffect(() => {
    let cancelled = false
    let inFlight = false

    const fetchAllData = async () => {
      if (inFlight) return
      inFlight = true
      setIsLoading(true)
      try {
        const [analysisRes, signalRes] = await Promise.allSettled([
          fetch(`/api/market/analysis/${encodeURIComponent(selectedPair.symbol)}?timeframe=${effectiveAnalysisTimeframe}&trade_style=${tradeStyle}`),
          fetch(`/api/signals/breakdown/${encodeURIComponent(selectedPair.symbol)}?timeframe=${effectiveAnalysisTimeframe || '1h'}&trade_style=${tradeStyle}`)
        ])

        // Process analysis result
        if (analysisRes.status === 'fulfilled' && analysisRes.value.ok) {
          const data = await analysisRes.value.json()
          if (cancelled) return
          setSourceMetadata(data.sourceMetadata ?? null)
          setSignalDetails({
            signal: data.signal,
            confidence: data.confidence,
            reason: data.reason,
            entryRange: data.entryRange,
            stopLoss: data.stopLoss,
            takeProfit1: data.takeProfit1,
            takeProfit2: data.takeProfit2,
            takeProfit3: data.takeProfit3,
            riskReward: data.riskReward,
            timeframe: data.timeframe,
            marketRegime: data.marketRegime,
            indicators: data.indicators,
            aiScore: data.aiScore,
            patterns: data.patterns || [],
            patternAccuracy: data.patternAccuracy ?? null,
          })
          if (data.multiTimeframe) {
            setMultiTimeframe(data.multiTimeframe)
          }
        }

        // Process signal breakdown result
        if (signalRes.status === 'fulfilled' && signalRes.value.ok) {
          const data = await signalRes.value.json()
          if (cancelled) return
          const marker: ChartSignalMarker = {
            entry: (data.entry_min + data.entry_max) / 2,
            entryMin: data.entry_min,
            entryMax: data.entry_max,
            stopLoss: data.stop_loss,
            takeProfit1: data.take_profit1,
            takeProfit2: data.take_profit2,
            takeProfit3: data.take_profit3,
            signalId: data.signal_id,
            direction: data.direction,
            timestamp: data.timestamp,
            status: data.signal_status || 'VALID',
            confidence: data.confidence,
            symbol: data.symbol,
            expiresAt: data.expires_at,
          }
          setChartSignals([marker])
          setSignalStatus(data.signal_status || 'VALID')
          setActiveSignalMeta({
            signalId: data.signal_id,
            direction: data.direction,
            expiresAt: data.expires_at,
            confidence: data.confidence,
          })
        } else {
          if (cancelled) return
          setChartSignals([])
          setSignalStatus(null)
          setActiveSignalMeta(null)
        }

        setLastSuccessfulFetch(Date.now())
        setFetchError(null)
      } catch (err) {
        console.error('Failed to fetch data:', err)
        if (!cancelled) setFetchError('Unable to refresh market data')
      } finally {
        inFlight = false
        if (!cancelled) setIsLoading(false)
      }
    }

    fetchAllData()
    const interval = setInterval(fetchAllData, fetchIntervalMs)
    return () => {
      cancelled = true
      clearInterval(interval)
    }
  }, [selectedPair.symbol, effectiveAnalysisTimeframe, tradeStyle, fetchIntervalMs])

  useEffect(() => {
    let isMounted = true

    const refreshActiveBroker = async () => {
      try {
        const broker = await api.get<ActiveBrokerInfo | null>('/api/broker/active')
        if (isMounted) {
          setActiveBroker(broker)
        }
      } catch {
        if (isMounted) {
          setActiveBroker(null)
        }
      }
    }

    void refreshActiveBroker()
    const interval = setInterval(() => {
      void refreshActiveBroker()
    }, 10000)

    return () => {
      isMounted = false
      clearInterval(interval)
    }
  }, [])

  useEffect(() => {
    if (!backendBroker?.id) return
    setActiveBroker({
      id: backendBroker.id,
      name: backendBroker.name || backendBroker.id,
      connected: backendBroker.connected,
      environment: backendBroker.environment || undefined,
    })
  }, [backendBroker?.connected, backendBroker?.environment, backendBroker?.id, backendBroker?.name])

  // Fetch copy trading data when enabled
  useEffect(() => {
    if (!copyTradingEnabled) return

    refreshCopyData()
    const interval = setInterval(refreshCopyData, 10000)
    return () => clearInterval(interval)
  }, [copyTradingEnabled, refreshCopyData])

  const copyDisabledReason = useMemo(() => {
    if (!copyTradingEnabled) return 'Enable copy trading to copy this signal'
    if (copyTradeLoading) return 'Copy request already in progress'
    if (!copySettings) return 'Loading copy trading settings'
    if (!activeSignalMeta?.signalId) return 'Signal unavailable'
    if (activeSignalMeta.direction === 'HOLD' || signalDetails.signal === 'hold') return 'Hold signals cannot be copied'
    if (signalStatus === 'EXPIRED') return 'Signal expired — wait for a fresh setup'
    if (!copySettings.allowed_symbols.includes(selectedPair.symbol)) return `${selectedPair.symbol} is not enabled for copy trading`
    if (activeSignalMeta.confidence < copySettings.min_confidence) {
      return `Signal confidence is below the ${copySettings.min_confidence}% minimum`
    }
    if (sourceMetadata?.qualityFlags?.includes('mock_data') || sourceMetadata?.qualityFlags?.includes('stale_data')) {
      return 'Wait for fresh market data before copying this signal'
    }
    if (copiedPositions.some((position) => position.signal_id === activeSignalMeta.signalId && ['open', 'partial_tp1', 'partial_tp2'].includes(position.status))) {
      return 'This signal is already copied'
    }
    return null
  }, [activeSignalMeta, copiedPositions, copySettings, copyTradeLoading, copyTradingEnabled, selectedPair.symbol, signalDetails.signal, signalStatus, sourceMetadata])

  const handleAISuggest = useCallback(async () => {
    const recs = await fetchRecommendations(activePairs)
    setRecommendations(recs)
    setShowAIRecommendations(true)
  }, [activePairs])

  // Handle pair selection from AI recommendations or heatmap
  const handleSelectPairFromAI = useCallback((pair: ForexPair) => {
    onPairChange(pair)
  }, [onPairChange])

  const placeOrder = async (side: 'buy' | 'sell') => {
    setIsTrading(true)
    setTradeStatus(null)

    const template = automationCenter?.template
    const riskPct = template?.allocationPercent ?? 2
    const riskAmount = metrics.balance * (riskPct / 100)
    const entryMid = (signalDetails.entryRange.min + signalDetails.entryRange.max) / 2
    const stopDistance = Math.abs(entryMid - signalDetails.stopLoss)
    const pipSz = selectedPair.basePriceApprox < 10 ? 0.0001 : selectedPair.basePriceApprox < 200 ? 0.01 : selectedPair.basePriceApprox < 5000 ? 0.10 : 1.0
    const stopPips = stopDistance / pipSz
    const pipValue = selectedPair.basePriceApprox < 10 ? 10 : 1
    const calculatedQuantity = stopPips > 0 ? riskAmount / (stopPips * pipValue) : 1
    const paperQuantity = Math.max(0.01, Math.round(calculatedQuantity * 100) / 100)
    const brokerForExecution = activeBroker || (backendBroker?.id ? {
      id: backendBroker.id,
      name: backendBroker.name || backendBroker.id,
      connected: backendBroker.connected,
      environment: backendBroker.environment || undefined,
    } : null)
    const isForexPair = ['major', 'minor', 'exotic'].includes(selectedPair.category)
    const hasExecutionLevels =
      signalDetails.entryRange.min > 0 &&
      signalDetails.entryRange.max > 0 &&
      signalDetails.entryRange.min !== signalDetails.entryRange.max &&
      signalDetails.stopLoss > 0
    const liveQuantity = !hasExecutionLevels
      ? 1
      : brokerForExecution?.id === 'oanda' && isForexPair
        ? Math.max(1, Math.round(calculatedQuantity * 100000))
        : Math.max(1, Math.round(calculatedQuantity))

    try {
      if (brokerForExecution?.connected) {
        const data = await api.placeBrokerOrder({
          broker_id: brokerForExecution.id,
          symbol: selectedPair.symbol,
          side,
          quantity: liveQuantity,
          order_type: 'market',
          price: null,
          signal_id: activeSignalMeta?.signalId ?? null,
        })
        setTradeStatus({
          type: 'success',
          message: `${data.message}${selectedStrategy ? ` · strategy ${selectedStrategy.name}` : ''}`,
        })
      } else {
        const res = await fetch('/api/trading/paper-order', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            symbol: selectedPair.symbol,
            side,
            quantity: paperQuantity,
            order_type: 'market',
            price: currentPrice,
            stop_loss: signalDetails.stopLoss,
            take_profit_1: signalDetails.takeProfit1,
            take_profit_2: signalDetails.takeProfit2,
            take_profit_3: signalDetails.takeProfit3,
            risk_percent: riskPct,
            trade_style: tradeStyle,
            strategy_id: selectedStrategy?.id,
            confidence: signalDetails.confidence,
          })
        })

        const data = await res.json()
        if (res.ok && data.success) {
          setTradeStatus({ type: 'success', message: `${data.message}${selectedStrategy ? ` · strategy ${selectedStrategy.name}` : ''}` })
        } else {
          setTradeStatus({ type: 'error', message: data.detail || 'Order failed' })
        }
      }
    } catch (err: any) {
      setTradeStatus({ type: 'error', message: err?.detail || 'Network error placing order' })
    } finally {
      setIsTrading(false)
      // Auto-dismiss after 5 seconds
      setTimeout(() => setTradeStatus(null), 5000)
    }
  }

  const handleBuy = () => placeOrder('buy')

  const handleSell = () => placeOrder('sell')

  const handleToggleCopyTrading = useCallback(async (enabled: boolean) => {
    try {
      const res = await fetch('/api/copy-trading/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled }),
      })
      const data = await res.json()
      if (res.ok) {
        setCopySettings(data)
        setCopyTradingEnabled(Boolean(data.enabled))
        if (!data.enabled) {
          setCopiedPositions([])
          setCopyHistory([])
          setCopyStats(null)
        }
      } else {
        setTradeStatus({ type: 'error', message: data.detail || 'Failed to update copy trading settings' })
      }
    } catch (err) {
      console.error('Failed to update copy trading settings:', err)
      setTradeStatus({ type: 'error', message: 'Failed to update copy trading settings' })
    }
  }, [])

  const handleCopySignal = useCallback(async () => {
    if (copyDisabledReason) {
      setTradeStatus({ type: 'error', message: copyDisabledReason })
      setTimeout(() => setTradeStatus(null), 5000)
      return
    }
    if (!activeSignalMeta?.signalId) {
      setTradeStatus({ type: 'error', message: 'Signal unavailable' })
      setTimeout(() => setTradeStatus(null), 5000)
      return
    }
    setCopyTradeLoading(true)
    try {
      const entryMid = (signalDetails.entryRange.min + signalDetails.entryRange.max) / 2
      const pipSz = selectedPair.basePriceApprox < 10 ? 0.0001 : selectedPair.basePriceApprox < 200 ? 0.01 : selectedPair.basePriceApprox < 5000 ? 0.10 : 1.0
      const stopDist = Math.abs(entryMid - signalDetails.stopLoss)
      const stopPips = stopDist / pipSz
      const pipValue = selectedPair.basePriceApprox < 10 ? 10 : 1
      const riskAmount = metrics.balance * (copyRiskPct / 100)
      const quantity = stopPips > 0 ? riskAmount / (stopPips * pipValue) : 0.01
      const requestedQuantity = Math.round(quantity * 100) / 100

      const res = await fetch('/api/copy-trading/copy-signal', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          signal_id: activeSignalMeta.signalId,
          quantity: requestedQuantity,
          entry_price: currentPriceRef.current,
          risk_percent: copyRiskPct,
        }),
      })
      const data = await res.json()
      if (res.ok && data.success) {
        const adjustments: string[] = []
        if (typeof data.effective_risk_percent === 'number' && Math.abs(data.effective_risk_percent - copyRiskPct) > 0.001) {
          adjustments.push(`risk capped to ${data.effective_risk_percent}%`)
        }
        if (typeof data.effective_quantity === 'number' && Math.abs(data.effective_quantity - requestedQuantity) > 0.001) {
          adjustments.push(`size capped to ${Number(data.effective_quantity).toFixed(2)} lots`)
        }
        setTradeStatus({
          type: 'success',
          message: adjustments.length > 0 ? `${data.message} · ${adjustments.join(' · ')}` : data.message,
        })
        await refreshCopyData()
      } else {
        setTradeStatus({ type: 'error', message: data.detail || 'Copy trade failed' })
      }
    } catch (err) {
      setTradeStatus({ type: 'error', message: 'Failed to copy signal' })
    } finally {
      setCopyTradeLoading(false)
      setTimeout(() => setTradeStatus(null), 5000)
    }
  }, [activeSignalMeta, copyDisabledReason, copyRiskPct, metrics.balance, refreshCopyData, selectedPair.basePriceApprox, signalDetails.entryRange.max, signalDetails.entryRange.min, signalDetails.stopLoss])

  const handleCloseCopyTrade = useCallback(async (copyTradeId: string) => {
    try {
      const res = await fetch(`/api/copy-trading/close/${copyTradeId}`, { method: 'POST' })
      const data = await res.json()
      if (res.ok && data.success) {
        setTradeStatus({ type: 'success', message: `Closed copy trade: ${data.realized_pnl >= 0 ? '+' : ''}$${data.realized_pnl.toFixed(2)}` })
        await refreshCopyData()
      } else {
        setTradeStatus({ type: 'error', message: data.detail || 'Failed to close copy trade' })
      }
    } catch (err) {
      setTradeStatus({ type: 'error', message: 'Failed to close copy trade' })
    }
    setTimeout(() => setTradeStatus(null), 5000)
  }, [refreshCopyData])

  const handleScalpTrade = useCallback(async (side: 'buy' | 'sell', data: ScalpTradeData) => {
    setTradeStatus(null)
    try {
      const res = await fetch('/api/trading/paper-order', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          symbol: data.symbol,
          side,
          quantity: Math.round(data.quantity * 100) / 100,
          order_type: 'market',
          price: data.price,
          stop_loss: data.stopLoss,
          take_profit_1: data.takeProfit1,
          take_profit_2: data.takeProfit2,
          risk_percent: data.riskPercent,
          trade_style: 'scalp',
          strategy_id: selectedStrategy?.id,
          confidence: data.confidence,
          timeframe: data.timeframe,
        })
      })
      const result = await res.json()
      if (res.ok && result.success) {
        setTradeStatus({ type: 'success', message: `Scalp ${side.toUpperCase()} executed: ${data.symbol}` })
      } else {
        setTradeStatus({ type: 'error', message: result.detail || 'Scalp order failed' })
      }
    } catch {
      setTradeStatus({ type: 'error', message: 'Network error placing scalp order' })
    }
    setTimeout(() => setTradeStatus(null), 5000)
  }, [selectedStrategy])

  useEffect(() => {
    const template = automationCenter?.template
    const activeStrategy = automationCenter?.activeStrategy
    if (!template?.enabled || automationCenter?.activeMode !== 'paper' || !activeStrategy) return
    if (activeStrategy.symbol !== selectedPair.symbol) return
    if (signalDetails.signal === 'hold') return
    if (signalDetails.confidence < 70) return
    if (sourceMetadata?.qualityFlags?.includes('stale_data')) return

    const side = signalDetails.signal.includes('buy') ? 'buy' : signalDetails.signal.includes('sell') ? 'sell' : null
    if (!side) return

    const signalKey = [
      activeStrategy.id,
      selectedPair.symbol,
      tradeStyle,
      signalDetails.signal,
      Math.round(currentPriceRef.current * 100) / 100,
    ].join(':')

    if (autoExecutionLockRef.current === signalKey) return
    autoExecutionLockRef.current = signalKey

    const timer = setTimeout(async () => {
      try {
        const riskPct = template.allocationPercent ?? 2
        const riskAmount = metrics.balance * (riskPct / 100)
        const entryMid = (signalDetails.entryRange.min + signalDetails.entryRange.max) / 2
        const stopDistance = Math.abs(entryMid - signalDetails.stopLoss)
        const pipSz = selectedPair.basePriceApprox < 10 ? 0.0001 : selectedPair.basePriceApprox < 200 ? 0.01 : selectedPair.basePriceApprox < 5000 ? 0.10 : 1.0
        const stopPips = stopDistance / pipSz
        const pipValue = selectedPair.basePriceApprox < 10 ? 10 : 1
        const quantity = stopPips > 0 ? riskAmount / (stopPips * pipValue) : 0.01

        const res = await fetch('/api/trading/paper-order', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            symbol: selectedPair.symbol,
            side,
            quantity: Math.round(quantity * 100) / 100,
            order_type: 'market',
            price: currentPriceRef.current,
            stop_loss: signalDetails.stopLoss,
            take_profit_1: signalDetails.takeProfit1,
            take_profit_2: signalDetails.takeProfit2,
            take_profit_3: signalDetails.takeProfit3,
            risk_percent: riskPct,
            trade_style: tradeStyle,
            strategy_id: activeStrategy.id,
            confidence: signalDetails.confidence,
          }),
        })
        const data = await res.json()
        if (res.ok && data.success) {
          setTradeStatus({ type: 'success', message: `Auto paper ${side.toUpperCase()} executed via ${activeStrategy.name}` })
        }
      } catch {
        setTradeStatus({ type: 'error', message: 'Auto paper execution failed' })
      }
      setTimeout(() => setTradeStatus(null), 5000)
    }, 800)

    return () => clearTimeout(timer)
  }, [automationCenter, metrics.balance, selectedPair, signalDetails, sourceMetadata, tradeStyle])

  const handleActivateGoldMode = useCallback((nextTimeframe: '1m' | '5m') => {
    if (goldPair.symbol === 'XAU/USD' && selectedPair.symbol !== 'XAU/USD') {
      onPairChange(goldPair)
    }
    setTradeStyle('scalp')
    setTimeframe(nextTimeframe)
  }, [goldPair, onPairChange, selectedPair.symbol])

  const canRenderTradeControls = useMemo(() => {
    return (
      signalDetails.entryRange.min > 0 &&
      signalDetails.entryRange.max > 0 &&
      signalDetails.entryRange.min !== signalDetails.entryRange.max &&
      signalDetails.stopLoss > 0
    )
  }, [
    signalDetails.entryRange.max,
    signalDetails.entryRange.min,
    signalDetails.stopLoss,
  ])
  const liveExecutionReady = Boolean(apiConnected && (activeBroker?.connected || backendBroker?.connected))

  const getRegimeIcon = (regime: MarketRegime) => {
    switch (regime) {
      case 'trending_up': return <TrendingUp size={16} className="text-emerald-400" />
      case 'trending_down': return <TrendingDown size={16} className="text-red-400" />
      case 'volatile': return <Zap size={16} className="text-yellow-400" />
      default: return <Activity size={16} className="text-blue-400" />
    }
  }

  const getRegimeText = (regime: MarketRegime) => {
    switch (regime) {
      case 'trending_up': return 'Trending Up'
      case 'trending_down': return 'Trending Down'
      case 'volatile': return 'Volatile'
      default: return 'Ranging'
    }
  }

  const formatPrice = (price: number) => {
    return price.toFixed(selectedPair.basePriceApprox < 10 ? 4 : 2)
  }

  return (
    <div className="p-6">
      {/* Header with PairSelector and Live Price Ticker */}
      <header className="mb-6 flex items-center justify-between flex-wrap gap-4">
        <div className="flex items-center gap-4">
          <PairSelector
            selectedPair={selectedPair}
            onPairChange={onPairChange}
            onAISuggest={handleAISuggest}
            recentPairs={recentPairs}
            defaultPairSymbol={defaultPairSymbol}
            onSetDefaultPair={onSetDefaultPair}
          />
        </div>
        
        {/* Live Price Ticker */}
        <div className="flex items-center gap-4">
          <div className="text-right">
            <div className="flex items-center gap-2 justify-end">
              <span className="text-sm text-trading-muted">{selectedPair.name}</span>
              {isLoading && (
                <span className="flex items-center gap-1 px-2 py-0.5 bg-trading-bg rounded text-xs text-trading-accent">
                  <Loader2 size={12} className="animate-spin" />
                  Updating...
                </span>
              )}
              <span className={`flex items-center gap-1 px-2 py-0.5 bg-trading-bg rounded text-xs`}>
                {getRegimeIcon(signalDetails.marketRegime)}
                {getRegimeText(signalDetails.marketRegime)}
              </span>
            </div>
            <div className="flex items-baseline gap-3 mt-1 justify-end">
              <span className="text-3xl font-bold text-trading-text">{formatPrice(currentPrice)}</span>
              <span className={`text-sm ${priceChange >= 0 ? 'text-trading-buy' : 'text-trading-sell'}`}>
                {priceChange >= 0 ? '+' : ''}{formatPrice(priceChange)} ({priceChangePercent >= 0 ? '+' : ''}{priceChangePercent.toFixed(2)}%)
              </span>
            </div>
          </div>
        </div>
      </header>

      {/* Main Grid Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-4 gap-4">
        {/* Left Main Content - Chart Area (~70-75% on large screens) */}
        <div className="lg:col-span-3 space-y-4">
          {/* TradingView Data Status */}
          <div className="flex items-center gap-2 px-3 py-1.5 bg-trading-card border border-trading-border rounded-md text-xs text-slate-300">
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
            <span className="font-medium">Chart feed: TradingView</span>
            <span className="text-slate-500">· Signal feed: backend {selectedPair.symbol} {effectiveAnalysisTimeframe.toUpperCase()} {tradeStyle}</span>
          </div>

          {fetchError && (
            <div className="flex items-center gap-2 px-3 py-1.5 bg-yellow-500/10 border border-yellow-500/30 rounded-md text-xs text-yellow-400">
              <span className="w-2 h-2 rounded-full bg-yellow-400" />
              <span>{fetchError} — last updated {Math.round((Date.now() - lastSuccessfulFetch) / 1000)}s ago</span>
            </div>
          )}

          {/* Chart Toolbar */}
          <ChartToolbar
            timeframe={timeframe}
            onTimeframeChange={setTimeframe}
          />

          {/* Trading Chart - TradingView Widget */}
          <div className="bg-trading-card border border-trading-border rounded-lg p-4">
            <div className="h-[500px]">
              <ChartErrorBoundary>
                <TradingChart
                  pair={selectedPair}
                  timeframe={timeframe}
                  signals={chartSignals}
                  tradeStyle={tradeStyle}
                  signalTimeframe={effectiveAnalysisTimeframe}
                  signalTradeStyle={tradeStyle}
                  signalMode="strict"
                />
              </ChartErrorBoundary>
            </div>
          </div>

          {/* Trade Status Notification */}
          {tradeStatus && (
            <div className={`rounded-lg px-4 py-3 flex items-center justify-between text-sm font-medium ${
              tradeStatus.type === 'success' 
                ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30' 
                : 'bg-red-500/20 text-red-400 border border-red-500/30'
            }`}>
              <span>{tradeStatus.message}</span>
              <button onClick={() => setTradeStatus(null)} className="text-xs opacity-60 hover:opacity-100">✕</button>
            </div>
          )}

          {/* Unified Trading Signal Card - Full Width */}
          {selectedPair.symbol === 'XAU/USD' && <GoldContextPanel context={goldContext} />}
          <AITradingHub
            signalDetails={signalDetails}
            currentPrice={currentPrice}
            priceChange={priceChange}
            priceChangePercent={priceChangePercent}
            selectedPair={selectedPair}
            accountBalance={metrics.balance}
            isLoading={isLoading && !canRenderTradeControls}
            onBuy={handleBuy}
            onSell={handleSell}
            tradeStyle={tradeStyle}
            onTradeStyleChange={setTradeStyle}
            signalStatus={signalStatus ?? undefined}
            multiTimeframe={multiTimeframe}
            forceShowTradeControls={liveExecutionReady}
            copyTradingEnabled={copyTradingEnabled}
            onToggleCopyTrading={handleToggleCopyTrading}
            copiedPositions={copiedPositions}
            copyHistory={copyHistory}
            copyStats={copyStats}
            copyHistorySymbolFilter={copyHistorySymbolFilter}
            onCopyHistorySymbolFilterChange={setCopyHistorySymbolFilter}
            copyHistoryDirectionFilter={copyHistoryDirectionFilter}
            onCopyHistoryDirectionFilterChange={setCopyHistoryDirectionFilter}
            copyHistoryStatusFilter={copyHistoryStatusFilter}
            onCopyHistoryStatusFilterChange={setCopyHistoryStatusFilter}
            copyHistoryRangeFilter={copyHistoryRangeFilter}
            onCopyHistoryRangeFilterChange={setCopyHistoryRangeFilter}
            onCopySignal={handleCopySignal}
            onCloseCopyTrade={handleCloseCopyTrade}
            copyTradeLoading={copyTradeLoading}
            riskPct={copyRiskPct}
            onRiskPctChange={setCopyRiskPct}
            copyDisabledReason={copyDisabledReason}
            dataFreshness={dataFreshness}
            lastUpdatedMs={lastSuccessfulFetch}
            quoteSource={quoteSource}
            activeTimeframe={quoteTimeframe}
            sourceMetadata={sourceMetadata}
          />

          <SignalBreakdown
            symbol={selectedPair.symbol}
            pair={selectedPair}
            signalData={{
              signal: signalDetails.signal,
              confidence: signalDetails.confidence,
              indicators: signalDetails.indicators,
            }}
            signalStatus={signalStatus ?? undefined}
            sourceMetadata={sourceMetadata}
          />



          {/* Watchlist & Economic Calendar */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <WatchlistCard
              pairs={recentPairs || []}
              selectedPair={selectedPair}
              onPairChange={onPairChange}
            />
            <EconomicCalendar selectedPair={selectedPair} />
          </div>
        </div>

        {/* Right Sidebar (~25-30% on large screens) */}
        <div className="lg:col-span-1 space-y-4">
          {/* AI Recommendations */}
          <AIRecommendations
            recommendations={recommendations}
            onSelectPair={handleSelectPairFromAI}
            isVisible={showAIRecommendations}
          />

          <StrategyCatalog
            strategies={strategies}
            onSelectStrategy={setSelectedStrategy}
            onActivate={async (strategy, mode) => {
              await api.activateStrategy(strategy.id, mode, true)
              const data = await api.fetchStrategies()
              setStrategies(data.results || [])
              setSelectedStrategy(strategy)
              setTradeStatus({ type: 'success', message: `Activated ${strategy.name} in ${mode} mode` })
              const center = await api.fetchAutomationCenter()
              setAutomationCenter(center)
            }}
          />
          <AutomationTemplateCard
            strategy={selectedStrategy}
            onSaved={async () => {
              setTradeStatus({ type: 'success', message: `Saved automation template for ${selectedStrategy?.name}` })
              const center = await api.fetchAutomationCenter()
              setAutomationCenter(center)
            }}
          />
          <AutomationCenterCard automationCenter={automationCenter} />

          <OpportunityBoard
            title="Top Opportunities"
            rows={topOpportunities}
            onSelectSymbol={(symbol) => {
              const pair = getPairBySymbol(symbol)
              if (pair) onPairChange(pair)
            }}
          />

          {selectedPair.symbol === 'XAU/USD' && (
            <OpportunityBoard
              title="XAU Setups"
              rows={xauOpportunities}
              onSelectSymbol={(symbol) => {
                const pair = getPairBySymbol(symbol)
                if (pair) onPairChange(pair)
              }}
            />
          )}

          {/* Pair Heatmap */}
          <PairHeatmap
            pairs={activePairs}
            selectedPair={selectedPair}
            onSelectPair={onPairChange}
          />

          {/* Sentiment Heatmap */}
          <SentimentHeatmap onSelectPair={handleSelectPairFromAI} />

          {/* Sentiment Panel */}
          <SentimentPanel symbol={selectedPair.symbol} />

          {/* Market Stats */}
          <div className="bg-trading-card border border-trading-border rounded-lg p-4">
            <h3 className="text-sm font-semibold mb-3">Market Stats</h3>
            <div className="space-y-2">
              <div className="flex justify-between text-sm">
                <span className="text-trading-muted">24h High</span>
                <span className="font-medium">{formatPrice(currentPrice * 1.006)}</span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-trading-muted">24h Low</span>
                <span className="font-medium">{formatPrice(currentPrice * 0.994)}</span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-trading-muted">Spread</span>
                <span className="font-medium">{selectedPair.baseSpread} pips</span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-trading-muted">Volume</span>
                <span className="font-medium">{(Math.random() * 10 + 5).toFixed(1)}K</span>
              </div>
            </div>
          </div>

          {selectedPair.symbol === 'XAU/USD' && (
            <SpotProviderStatusCard health={datasourceHealth} />
          )}

        </div>
      </div>

      {/* MIDAS Gold Scalper Pro — floating widget */}
      <GoldScalperPro
        accountBalance={metrics.balance}
        onExecuteTrade={handleScalpTrade}
        onActivateGoldMode={handleActivateGoldMode}
      />
    </div>
  )
}

export default Dashboard
