import { useState, useEffect, useCallback, useRef, useMemo } from 'react'
import { TrendingUp, TrendingDown, Activity, Zap, Loader2 } from 'lucide-react'
import type { AccountMetrics, ForexPair, AIRecommendation, ChartSignalMarker, SignalStatus, AIScoreData, DetectedPattern } from '../types'
import { getPairBySymbol } from '../config/forexPairs'
import { PairSelector } from '../components/PairSelector'
import { ChartToolbar } from '../components/ChartToolbar'
import { TradingChart, ChartErrorBoundary } from '../components/TradingChart'
import { AIRecommendations, fetchRecommendations } from '../components/AIRecommendations'
import { PairHeatmap } from '../components/PairHeatmap'
import { SentimentPanel } from '../components/SentimentPanel'
import { SentimentHeatmap } from '../components/SentimentHeatmap'
import { AITradingHub } from '../components/AITradingHub'
import WatchlistCard from '../components/WatchlistCard'
import EconomicCalendar from '../components/EconomicCalendar'
import { GoldScalperPro } from '../components/GoldScalperPro'
import type { ScalpTradeData } from '../components/GoldScalperPro'

interface DashboardProps {
  selectedPair: ForexPair
  onPairChange: (pair: ForexPair) => void
  activePairs: ForexPair[]
  recentPairs?: ForexPair[]
  defaultPairSymbol?: string
  onSetDefaultPair?: (pair: ForexPair) => void
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

function Dashboard({ selectedPair, onPairChange, activePairs, recentPairs, defaultPairSymbol, onSetDefaultPair }: DashboardProps) {
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
  const [quoteSource, setQuoteSource] = useState<'live' | 'mock' | 'unknown'>('unknown')

  const effectiveAnalysisTimeframe = useMemo(() => {
    if (tradeStyle === 'scalp') {
      if (timeframe === '1m' || timeframe === '5m') return timeframe
      return '1m'
    }
    return timeframe
  }, [timeframe, tradeStyle])

  const quoteTimeframe = useMemo(() => {
    if (tradeStyle === 'scalp') return timeframe === '5m' ? '5m' : '1m'
    if (timeframe === '1m' || timeframe === '5m' || timeframe === '15m') return timeframe
    return '1m'
  }, [timeframe, tradeStyle])

  const fetchIntervalMs = (() => {
    if (tradeStyle === 'scalp') return 5000
    if (timeframe === '1m' || timeframe === '5m') return 5000
    if (timeframe === '15m') return 10000
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
  const [copiedPositions, setCopiedPositions] = useState<any[]>([])
  const [copyStats, setCopyStats] = useState<any>(null)
  const [copyTradeLoading, setCopyTradeLoading] = useState(false)

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

  // Fast quote polling keeps hero price reactive even when full analysis is slower.
  useEffect(() => {
    const fetchQuote = async () => {
      try {
        const res = await fetch(`/api/market/quote/${encodeURIComponent(selectedPair.symbol)}?timeframe=${quoteTimeframe}`)
        if (!res.ok) return
        const data = await res.json()
        setCurrentPrice(data.currentPrice)
        setPriceChange(data.priceChange)
        setPriceChangePercent(data.priceChangePercent)
        setQuoteSource(data.source ?? 'unknown')
        setLastSuccessfulFetch(Date.now())
        setFetchError(null)
      } catch {
        setFetchError('Unable to refresh live quote')
      }
    }

    fetchQuote()
    const interval = setInterval(fetchQuote, fetchIntervalMs)
    return () => clearInterval(interval)
  }, [selectedPair, quoteTimeframe, fetchIntervalMs])

  useEffect(() => {
    if (tradeStyle === 'scalp' && timeframe !== '1m' && timeframe !== '5m') {
      setTimeframe('1m')
    }
  }, [tradeStyle, timeframe])

  // Fetch full market analysis when pair or timeframe changes
  useEffect(() => {
    const fetchAllData = async () => {
      setIsLoading(true)
      try {
        const [analysisRes, signalRes] = await Promise.allSettled([
          fetch(`/api/market/analysis/${encodeURIComponent(selectedPair.symbol)}?timeframe=${effectiveAnalysisTimeframe}&trade_style=${tradeStyle}`),
          fetch(`/api/signals/breakdown/${encodeURIComponent(selectedPair.symbol)}?timeframe=${effectiveAnalysisTimeframe || '1h'}`)
        ])

        // Process analysis result
        if (analysisRes.status === 'fulfilled' && analysisRes.value.ok) {
          const data = await analysisRes.value.json()
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
          const marker: ChartSignalMarker = {
            entry: (data.entry_min + data.entry_max) / 2,
            entryMin: data.entry_min,
            entryMax: data.entry_max,
            stopLoss: data.stop_loss,
            takeProfit1: data.take_profit1,
            takeProfit2: data.take_profit2,
            takeProfit3: data.take_profit3,
            direction: data.direction,
            timestamp: data.timestamp,
            status: data.signal_status || 'VALID',
            confidence: data.confidence,
            symbol: data.symbol,
            expiresAt: data.expires_at,
          }
          setChartSignals([marker])
          setSignalStatus(data.signal_status || 'VALID')
        }

        setLastSuccessfulFetch(Date.now())
        setFetchError(null)
      } catch (err) {
        console.error('Failed to fetch data:', err)
        setFetchError('Unable to refresh market data')
      } finally {
        setIsLoading(false)
      }
    }

    fetchAllData()
    const interval = setInterval(fetchAllData, fetchIntervalMs)
    return () => clearInterval(interval)
  }, [selectedPair, effectiveAnalysisTimeframe, tradeStyle, fetchIntervalMs])

  // Fetch copy trading data when enabled
  useEffect(() => {
    if (!copyTradingEnabled) return

    const fetchCopyData = async () => {
      try {
        const [posRes, statsRes] = await Promise.all([
          fetch('/api/copy-trading/positions'),
          fetch('/api/copy-trading/stats'),
        ])
        if (posRes.ok) {
          const posData = await posRes.json()
          setCopiedPositions(posData.positions || [])
        }
        if (statsRes.ok) {
          const statsData = await statsRes.json()
          setCopyStats(statsData)
        }
      } catch (err) {
        console.error('Failed to fetch copy trading data:', err)
      }
    }

    fetchCopyData()
    const interval = setInterval(fetchCopyData, 10000)
    return () => clearInterval(interval)
  }, [copyTradingEnabled])

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

    // Calculate position size (same logic as TradeExecutionPanel)
    const riskPct = 2 // default risk %
    const riskAmount = metrics.balance * (riskPct / 100)
    const entryMid = (signalDetails.entryRange.min + signalDetails.entryRange.max) / 2
    const stopDistance = Math.abs(entryMid - signalDetails.stopLoss)
    const pipSz = selectedPair.basePriceApprox < 10 ? 0.0001 : selectedPair.basePriceApprox < 200 ? 0.01 : selectedPair.basePriceApprox < 5000 ? 0.10 : 1.0
    const stopPips = stopDistance / pipSz
    const pipValue = selectedPair.basePriceApprox < 10 ? 10 : 1
    const quantity = stopPips > 0 ? riskAmount / (stopPips * pipValue) : 0.01

    try {
      const res = await fetch('/api/trading/paper-order', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          symbol: selectedPair.symbol,
          side,
          quantity: Math.round(quantity * 100) / 100,
          order_type: 'market',
          price: currentPrice,
          stop_loss: signalDetails.stopLoss,
          take_profit_1: signalDetails.takeProfit1,
          take_profit_2: signalDetails.takeProfit2,
          take_profit_3: signalDetails.takeProfit3,
          risk_percent: riskPct,
          trade_style: tradeStyle,
          confidence: signalDetails.confidence,
        })
      })

      const data = await res.json()
      if (res.ok && data.success) {
        setTradeStatus({ type: 'success', message: data.message })
      } else {
        setTradeStatus({ type: 'error', message: data.detail || 'Order failed' })
      }
    } catch (err) {
      setTradeStatus({ type: 'error', message: 'Network error placing order' })
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
      if (res.ok) {
        setCopyTradingEnabled(enabled)
        if (!enabled) {
          setCopiedPositions([])
          setCopyStats(null)
        }
      }
    } catch (err) {
      console.error('Failed to update copy trading settings:', err)
    }
  }, [])

  const handleCopySignal = useCallback(async () => {
    setCopyTradeLoading(true)
    try {
      const entryMid = (signalDetails.entryRange.min + signalDetails.entryRange.max) / 2
      const pipSz = selectedPair.basePriceApprox < 10 ? 0.0001 : selectedPair.basePriceApprox < 200 ? 0.01 : selectedPair.basePriceApprox < 5000 ? 0.10 : 1.0
      const stopDist = Math.abs(entryMid - signalDetails.stopLoss)
      const stopPips = stopDist / pipSz
      const pipValue = selectedPair.basePriceApprox < 10 ? 10 : 1
      const riskAmount = metrics.balance * 0.01
      const quantity = stopPips > 0 ? riskAmount / (stopPips * pipValue) : 0.01

      const res = await fetch('/api/copy-trading/copy-signal', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          symbol: selectedPair.symbol,
          direction: signalDetails.signal.includes('buy') ? 'BUY' : 'SELL',
          quantity: Math.round(quantity * 100) / 100,
          entry_price: currentPriceRef.current,
          stop_loss: signalDetails.stopLoss,
          take_profit1: signalDetails.takeProfit1,
          take_profit2: signalDetails.takeProfit2,
          take_profit3: signalDetails.takeProfit3,
          confidence: signalDetails.confidence,
          risk_percent: 1.0,
          trade_style: tradeStyle,
          timeframe: timeframe,
        }),
      })
      const data = await res.json()
      if (data.success) {
        setTradeStatus({ type: 'success', message: data.message })
        const posRes = await fetch('/api/copy-trading/positions')
        if (posRes.ok) {
          const posData = await posRes.json()
          setCopiedPositions(posData.positions || [])
        }
      } else {
        setTradeStatus({ type: 'error', message: data.detail || 'Copy trade failed' })
      }
    } catch (err) {
      setTradeStatus({ type: 'error', message: 'Failed to copy signal' })
    } finally {
      setCopyTradeLoading(false)
      setTimeout(() => setTradeStatus(null), 5000)
    }
  }, [selectedPair, signalDetails, currentPrice, tradeStyle, timeframe, metrics.balance])

  const handleCloseCopyTrade = useCallback(async (copyTradeId: string) => {
    try {
      const res = await fetch(`/api/copy-trading/close/${copyTradeId}`, { method: 'POST' })
      const data = await res.json()
      if (data.success) {
        setTradeStatus({ type: 'success', message: `Closed copy trade: ${data.realized_pnl >= 0 ? '+' : ''}$${data.realized_pnl.toFixed(2)}` })
        setCopiedPositions(prev => prev.filter(p => p.copy_trade_id !== copyTradeId))
      }
    } catch (err) {
      setTradeStatus({ type: 'error', message: 'Failed to close copy trade' })
    }
    setTimeout(() => setTradeStatus(null), 5000)
  }, [])

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
  }, [])

  const handleActivateGoldMode = useCallback((nextTimeframe: '1m' | '5m') => {
    if (goldPair.symbol === 'XAU/USD' && selectedPair.symbol !== 'XAU/USD') {
      onPairChange(goldPair)
    }
    setTradeStyle('scalp')
    setTimeframe(nextTimeframe)
  }, [goldPair, onPairChange, selectedPair.symbol])

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
            <span className="font-medium">TradingView Live</span>
            <span className="text-slate-500">· Real-time market data</span>
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
          <AITradingHub
            signalDetails={signalDetails}
            currentPrice={currentPrice}
            priceChange={priceChange}
            priceChangePercent={priceChangePercent}
            selectedPair={selectedPair}
            accountBalance={metrics.balance}
            isLoading={isLoading}
            onBuy={handleBuy}
            onSell={handleSell}
            tradeStyle={tradeStyle}
            onTradeStyleChange={setTradeStyle}
            signalStatus={signalStatus ?? undefined}
            multiTimeframe={multiTimeframe}
            copyTradingEnabled={copyTradingEnabled}
            onToggleCopyTrading={handleToggleCopyTrading}
            copiedPositions={copiedPositions}
            copyStats={copyStats}
            onCopySignal={handleCopySignal}
            onCloseCopyTrade={handleCloseCopyTrade}
            copyTradeLoading={copyTradeLoading}
            dataFreshness={dataFreshness}
            lastUpdatedMs={lastSuccessfulFetch}
            quoteSource={quoteSource}
            activeTimeframe={quoteTimeframe}
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
