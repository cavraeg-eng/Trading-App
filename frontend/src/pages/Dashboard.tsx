import { useState, useEffect, useCallback } from 'react'
import { TrendingUp, TrendingDown, Activity, Clock, Zap, Loader2 } from 'lucide-react'
import type { AccountMetrics, ForexPair, AIRecommendation, ChartSignalMarker, SignalStatus } from '../types'
import { PairSelector } from '../components/PairSelector'
import { ChartToolbar } from '../components/ChartToolbar'
import { TradingChart } from '../components/TradingChart'
import { AIRecommendations, fetchRecommendations } from '../components/AIRecommendations'
import { PairHeatmap } from '../components/PairHeatmap'
import { SentimentPanel } from '../components/SentimentPanel'
import { SentimentHeatmap } from '../components/SentimentHeatmap'
import { TradeExecutionPanel } from '../components/TradeExecutionPanel'
import WatchlistCard from '../components/WatchlistCard'
import EconomicCalendar from '../components/EconomicCalendar'

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
}

function Dashboard({ selectedPair, onPairChange, activePairs, recentPairs, defaultPairSymbol, onSetDefaultPair }: DashboardProps) {
  // Chart state
  const [timeframe, setTimeframe] = useState<string>('1h')
  
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
    indicators: []
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

  // Fetch real market analysis when pair or timeframe changes
  useEffect(() => {
    const fetchAnalysis = async () => {
      setIsLoading(true)
      try {
        const res = await fetch(`/api/market/analysis/${encodeURIComponent(selectedPair.symbol)}?timeframe=${timeframe}&trade_style=${tradeStyle}`)
        if (res.ok) {
          const data = await res.json()
          setCurrentPrice(data.currentPrice)
          setPriceChange(data.priceChange)
          setPriceChangePercent(data.priceChangePercent)
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
          })
          if (data.multiTimeframe) {
            setMultiTimeframe(data.multiTimeframe)
          }
        } else {
          console.warn('Failed to fetch analysis:', res.status)
        }
      } catch (err) {
        console.error('Failed to fetch analysis:', err)
        // Keep existing data on error
      } finally {
        setIsLoading(false)
      }
    }
    const fetchSignalBreakdown = async () => {
      try {
        const selectedTimeframe = timeframe || '1h'
        const res = await fetch(`/api/signals/breakdown/${encodeURIComponent(selectedPair.symbol)}?timeframe=${selectedTimeframe}`)
        if (res.ok) {
          const data = await res.json()
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
      } catch (err) {
        console.error('Failed to fetch signal breakdown:', err)
      }
    }

    fetchAnalysis()
    fetchSignalBreakdown()
    // Refresh every 30 seconds
    const interval = setInterval(() => {
      fetchAnalysis()
      fetchSignalBreakdown()
    }, 30000)
    return () => clearInterval(interval)
  }, [selectedPair, timeframe, tradeStyle])


  // Handle AI Suggest
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
          {/* Chart Toolbar */}
          <ChartToolbar
            timeframe={timeframe}
            onTimeframeChange={setTimeframe}
          />

          {/* Trading Chart - TradingView Widget */}
          <div className="bg-trading-card border border-trading-border rounded-lg p-4">
            <div className="h-[500px]">
              <TradingChart
                pair={selectedPair}
                timeframe={timeframe}
                signals={chartSignals}
              />
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
          <TradeExecutionPanel
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
          />

          {/* Technical Indicators Display */}
          <div className="bg-trading-card border border-trading-border rounded-lg p-4">
            <h3 className="text-sm font-semibold mb-3 flex items-center gap-2">
              <Activity size={16} />
              Technical Indicators
            </h3>
            <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
              {signalDetails.indicators.map((ind, i) => (
                <div key={i} className="p-2 bg-trading-bg rounded-lg text-center">
                  <span className="text-xs text-trading-muted block">{ind.name}</span>
                  <span className="text-sm font-medium block">{ind.value}</span>
                  <span className={`text-[10px] px-1.5 py-0.5 rounded ${
                    ind.signal === 'bullish' ? 'bg-emerald-500/20 text-emerald-400' :
                    ind.signal === 'bearish' ? 'bg-red-500/20 text-red-400' :
                    'bg-yellow-500/20 text-yellow-400'
                  }`}>
                    {ind.signal.toUpperCase()}
                  </span>
                </div>
              ))}
            </div>
          </div>

          {/* Multi-Timeframe Analysis */}
          <div className="bg-trading-card border border-trading-border rounded-lg p-4">
            <h3 className="text-sm font-semibold mb-3 flex items-center gap-2">
              <Clock size={16} />
              Multi-Timeframe Analysis
            </h3>
            <div className="grid grid-cols-5 gap-2">
              {(multiTimeframe.length > 0 ? multiTimeframe : [
                { tf: '1D', signal: 'HOLD' as const, alignment: 50 },
                { tf: '4H', signal: 'HOLD' as const, alignment: 50 },
                { tf: '1H', signal: 'HOLD' as const, alignment: 50 },
                { tf: '15M', signal: 'HOLD' as const, alignment: 50 },
                { tf: '5M', signal: 'HOLD' as const, alignment: 50 },
              ]).map((item, i) => (
                <div key={i} className="p-2 bg-trading-bg rounded-lg text-center">
                  <span className="text-xs font-medium block mb-1">{item.tf}</span>
                  <div className="h-1.5 bg-trading-card rounded-full overflow-hidden mb-1">
                    <div 
                      className={`h-full rounded-full ${
                        item.alignment > 60 ? 'bg-emerald-500' :
                        item.alignment > 40 ? 'bg-yellow-500' :
                        'bg-red-500'
                      }`}
                      style={{ width: `${item.alignment}%` }}
                    />
                  </div>
                  <span className={`text-[10px] px-1.5 py-0.5 rounded ${
                    item.signal === 'BUY' ? 'bg-emerald-500/20 text-emerald-400' :
                    item.signal === 'SELL' ? 'bg-red-500/20 text-red-400' :
                    'bg-yellow-500/20 text-yellow-400'
                  }`}>
                    {item.signal}
                  </span>
                </div>
              ))}
            </div>
          </div>


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

          {/* Signal Analysis */}
          <div className="bg-trading-card border border-trading-border rounded-lg p-4">
            <h3 className="text-sm font-semibold mb-3">Analysis</h3>
            <p className="text-xs text-trading-muted leading-relaxed mb-3">{signalDetails.reason}</p>
            {/* Indicator Consensus */}
            {signalDetails.indicators.length > 0 && (() => {
              const bullish = signalDetails.indicators.filter(i => i.signal === 'bullish').length
              const bearish = signalDetails.indicators.filter(i => i.signal === 'bearish').length
              const neutral = signalDetails.indicators.filter(i => i.signal === 'neutral').length
              const total = signalDetails.indicators.length
              return (
                <div>
                  <span className="text-[10px] text-trading-muted uppercase tracking-wide">Indicator Consensus</span>
                  <div className="h-2 bg-trading-bg rounded-full overflow-hidden flex mt-1 mb-1">
                    <div className="h-full bg-emerald-500 transition-all duration-500" style={{ width: `${(bullish / total) * 100}%` }} />
                    <div className="h-full bg-red-500 transition-all duration-500" style={{ width: `${(bearish / total) * 100}%` }} />
                    <div className="h-full bg-gray-500 transition-all duration-500" style={{ width: `${(neutral / total) * 100}%` }} />
                  </div>
                  <div className="flex justify-between text-[10px]">
                    <span className="text-emerald-400">{bullish} Bullish</span>
                    <span className="text-red-400">{bearish} Bearish</span>
                    <span className="text-gray-400">{neutral} Neutral</span>
                  </div>
                </div>
              )
            })()}
          </div>
        </div>
      </div>
    </div>
  )
}

export default Dashboard
