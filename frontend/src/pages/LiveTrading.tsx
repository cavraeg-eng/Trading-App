import { useState, useEffect, useMemo, useCallback, useRef } from 'react'
import { Power, ChevronDown, AlertCircle, Check, X, XCircle, RefreshCw, Brain, TrendingUp, TrendingDown, Plus, ArrowRight, Calendar, Filter, BarChart2, Edit3 } from 'lucide-react'
import type { ForexPair, StrategyDefinition, ChartSignalMarker, ActivePositionOverlay, GhostTradeOverlay } from '../types'
import { api } from '../lib/api'
import { ALL_FOREX_PAIRS, getPairBySymbol } from '../config/forexPairs'
import { formatDateTimeWithZone } from '../lib/time'
import TradingChart, { ChartErrorBoundary } from '../components/TradingChart'
import { ChartToolbar } from '../components/ChartToolbar'

interface LiveTradingProps {
  selectedPair: ForexPair
  onPairChange: (pair: ForexPair) => void
  activePairs: ForexPair[]
  recentPairs?: ForexPair[]
  backendBroker?: {
    id: string | null
    connected: boolean
    name: string | null
    environment?: string | null
  } | null
}

interface Broker {
  id: string
  name: string
  type: string
  connected: boolean
  supported_markets: string[]
  environment?: string
}

interface Position {
  position_id?: string | null
  symbol: string
  broker_id: string
  quantity: number
  side: string
  avg_entry: number
  current_price: number
  unrealized_pnl: number
  unrealized_pnl_pct: number
  opened_at?: string | null
  last_updated?: string
}

interface OrderConfirmation {
  show: boolean
  side: 'buy' | 'sell'
  quantity: number
  price: number
}

interface TradeHistoryItem {
  trade_id: string
  symbol: string
  side: string
  quantity: number
  entry_price: number
  exit_price: number
  realized_pnl: number
  opened_at: string
  closed_at: string
  state: string
  stop_loss?: number | null
  take_profit_1?: number | null
  take_profit_2?: number | null
  take_profit_3?: number | null
}

interface BrokerBalance {
  total_equity?: number
  available_margin?: number
  used_margin?: number
  currency?: string
}

interface BrokerOrderItem {
  order_id: string
  symbol: string
  side: string
  order_type: string
  quantity: number
  price: number | null
  status: string
  filled_quantity: number
  avg_fill_price: number
  stop_loss?: number | null
  take_profit_1?: number | null
  take_profit_2?: number | null
  take_profit_3?: number | null
  broker_id: string
  created_at: string | null
  updated_at: string | null
}

interface AutomationStatusData {
  worker: { running: boolean; lastRun: number | null; lastExecution: number | null; lastError: string | null } | undefined
  mode: string
  brokerId: string | null
  activeStrategy: StrategyDefinition | null
  activeMode: string
  lastAnalysis: {
    signal: string; confidence: number; reason: string; marketRegime: string
    entryRange: { min: number; max: number } | null
    stopLoss: number; takeProfit1: number; takeProfit2: number; takeProfit3: number
    currentPrice: number; symbol: string; timeframe: string; tradeStyle: string; timestamp: number
  } | null
  executions: Array<{ id: number; strategy_id: string; symbol: string; action: string; status: string; detail: Record<string, unknown>; created_at: string }>
}

type FeedKey = 'broker' | 'positions' | 'balance' | 'history' | 'orders' | 'quote' | 'automation' | 'signal'
type FeedStatus = 'idle' | 'loading' | 'ready' | 'error'

type FeedState = Record<FeedKey, {
  status: FeedStatus
  error: string | null
  updatedAt: string | null
}>

type TradeLedgerEntry = Awaited<ReturnType<typeof api.fetchTradeLedger>>['entries'][number]
type LedgerMetrics = Awaited<ReturnType<typeof api.fetchLedgerMetrics>>

function getPriceDecimals(pair: ForexPair) {
  if (pair.basePriceApprox < 10) return 5
  if (pair.basePriceApprox < 200) return 3
  return 2
}

function formatPairPrice(value: number, pair: ForexPair) {
  return value.toFixed(getPriceDecimals(pair))
}

function formatAccountAmount(value: number) {
  const normalized = Math.abs(value) < 1e-9 ? 0 : value
  const maximumFractionDigits = Math.abs(normalized) >= 1 ? 4 : 5
  return normalized.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits })
}

function formatSignedCurrency(value: number) {
  const normalized = Math.abs(value) < 1e-9 ? 0 : value
  const magnitude = Math.abs(normalized)
  const maximumFractionDigits = magnitude >= 1 ? 2 : magnitude >= 0.01 ? 4 : 5
  return `${normalized >= 0 ? '+' : '-'}$${magnitude.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits })}`
}

function formatTradeTimestamp(value: string | null | undefined) {
  return formatDateTimeWithZone(value)
}

function formatMovementAmount(value: number) {
  const normalized = Math.abs(value) < 1e-9 ? 0 : value
  const magnitude = Math.abs(normalized)
  const maximumFractionDigits = magnitude >= 1 ? 2 : magnitude >= 0.01 ? 4 : 5
  return `${normalized >= 0 ? '+' : '-'}${magnitude.toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits,
  })}`
}

function getPipMovement(pair: ForexPair, entry: number, current: number) {
  const pipSize = pair.symbol.includes('JPY')
    ? 0.01
    : pair.basePriceApprox < 10
      ? 0.0001
      : pair.basePriceApprox < 200
        ? 0.01
        : 0.1
  if (!pipSize) return 0
  return (current - entry) / pipSize
}

function getPositionRowId(position: Position) {
  return position.position_id ?? `${position.broker_id}:${position.symbol}:${position.side}:${position.avg_entry}:${position.quantity}`
}

function getOrderStatusClasses(status: string) {
  switch (status.toLowerCase()) {
    case 'filled': return 'bg-emerald-500/20 text-emerald-400'
    case 'partially_filled': return 'bg-blue-500/20 text-blue-400'
    case 'open': case 'pending': return 'bg-amber-500/20 text-amber-400'
    case 'cancelled': case 'rejected': return 'bg-red-500/20 text-red-400'
    default: return 'bg-trading-border text-trading-muted'
  }
}

function getTimestampValue(value: string | null | undefined) {
  if (!value) return 0
  const parsed = Date.parse(value)
  return Number.isFinite(parsed) ? parsed : 0
}

function toFiniteNumber(value: unknown) {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string' && value.trim().length > 0) {
    const parsed = Number(value)
    if (Number.isFinite(parsed)) return parsed
  }
  return null
}

function hasTradeTargets(order: BrokerOrderItem) {
  return [
    order.stop_loss,
    order.take_profit_1,
    order.take_profit_2,
    order.take_profit_3,
  ].some((value) => typeof value === 'number' && Number.isFinite(value) && value > 0)
}

function ledgerEntryHasTargets(entry: TradeLedgerEntry) {
  return [
    entry.stop_loss,
    entry.take_profit_1,
    entry.take_profit_2,
    entry.take_profit_3,
  ].some((value) => typeof value === 'number' && Number.isFinite(value) && value > 0)
}

function ledgerEntryToOrder(entry: TradeLedgerEntry): BrokerOrderItem {
  const metadata = entry.metadata ?? {}
  const metadataOrderId = typeof metadata.order_id === 'string' ? metadata.order_id : undefined
  const metadataOrderType = typeof metadata.order_type === 'string' ? metadata.order_type : undefined
  return {
    order_id: metadataOrderId || (entry.source_type === 'trade' ? `trade:${entry.source_id}` : entry.source_id),
    symbol: entry.symbol,
    side: entry.side === 'long' ? 'buy' : entry.side === 'short' ? 'sell' : entry.side,
    order_type: metadataOrderType || entry.source_type,
    quantity: entry.quantity,
    price: entry.entry_price ?? null,
    status: entry.status,
    filled_quantity: entry.remaining_quantity != null ? Math.max(entry.quantity - entry.remaining_quantity, 0) : entry.quantity,
    avg_fill_price: entry.entry_price ?? 0,
    stop_loss: entry.stop_loss,
    take_profit_1: entry.take_profit_1,
    take_profit_2: entry.take_profit_2,
    take_profit_3: entry.take_profit_3,
    broker_id: entry.broker_id,
    created_at: entry.opened_at ?? entry.updated_at,
    updated_at: entry.updated_at,
  }
}

function ledgerEntryToHistory(entry: TradeLedgerEntry): TradeHistoryItem {
  return {
    trade_id: entry.source_id,
    symbol: entry.symbol,
    side: entry.side,
    quantity: entry.quantity,
    entry_price: entry.entry_price ?? 0,
    exit_price: entry.exit_price ?? entry.current_price ?? entry.entry_price ?? 0,
    realized_pnl: entry.realized_pnl,
    opened_at: entry.opened_at ?? entry.updated_at,
    closed_at: entry.closed_at ?? entry.updated_at,
    state: entry.status,
    stop_loss: entry.stop_loss,
    take_profit_1: entry.take_profit_1,
    take_profit_2: entry.take_profit_2,
    take_profit_3: entry.take_profit_3,
  }
}

function createInitialFeedState(): FeedState {
  return {
    broker: { status: 'idle', error: null, updatedAt: null },
    positions: { status: 'idle', error: null, updatedAt: null },
    balance: { status: 'idle', error: null, updatedAt: null },
    history: { status: 'idle', error: null, updatedAt: null },
    orders: { status: 'idle', error: null, updatedAt: null },
    quote: { status: 'idle', error: null, updatedAt: null },
    automation: { status: 'idle', error: null, updatedAt: null },
    signal: { status: 'idle', error: null, updatedAt: null },
  }
}

function getErrorDetail(error: unknown, fallback: string) {
  if (typeof error === 'object' && error && 'detail' in error && typeof (error as { detail?: unknown }).detail === 'string') {
    return (error as { detail: string }).detail
  }
  if (error instanceof Error && error.message) return error.message
  return fallback
}

function LiveTrading({
  selectedPair,
  onPairChange,
  activePairs: _activePairs,
  recentPairs: _recentPairs,
  backendBroker = null,
}: LiveTradingProps) {
  const [isTrading, setIsTrading] = useState(false)
  const [_isConnected, setIsConnected] = useState(false)
  const [currentPnL, setCurrentPnL] = useState(0)
  const [_dailyPnL, setDailyPnL] = useState(0)
  const [_tradesToday, setTradesToday] = useState(0)

  // Broker State
  const [activeBroker, setActiveBroker] = useState<Broker | null>(null)
  const [positions, setPositions] = useState<Position[]>([])
  const [_isLoadingPositions, setIsLoadingPositions] = useState(false)

  // Order State
  const [orderConfirmation, setOrderConfirmation] = useState<OrderConfirmation>({ show: false, side: 'buy', quantity: 1.0, price: 0 })
  const [isPlacingOrder, setIsPlacingOrder] = useState(false)
  const [orderMessage, setOrderMessage] = useState<{ type: 'success' | 'error', message: string } | null>(null)
  const [brokerError, setBrokerError] = useState<string | null>(null)
  const [isClosingPosition, setIsClosingPosition] = useState<string | null>(null)

  // Balance & History
  const [balance, setBalance] = useState<BrokerBalance>({})
  const [tradeHistory, setTradeHistory] = useState<TradeHistoryItem[]>([])
  const [orders, setOrders] = useState<BrokerOrderItem[]>([])
  const [ledgerEntries, setLedgerEntries] = useState<TradeLedgerEntry[]>([])
  const [ledgerMetrics, setLedgerMetrics] = useState<LedgerMetrics | null>(null)
  const [_isLoadingOrders, setIsLoadingOrders] = useState(false)
  const [latestQuote, setLatestQuote] = useState<{ currentPrice: number; source?: string; priceSource?: string } | null>(null)
  const [feedState, setFeedState] = useState<FeedState>(() => createInitialFeedState())
  const activeBrokerRef = useRef<Broker | null>(null)
  const fetchVersionRef = useRef(0)
  const refreshInFlightRef = useRef(false)

  // Strategy & Automation State
  const [strategies, setStrategies] = useState<StrategyDefinition[]>([])
  const [selectedStrategyId, setSelectedStrategyId] = useState<string>('')
  const [automationStatus, setAutomationStatus] = useState<AutomationStatusData | null>(null)
  const [isStartingTrading, setIsStartingTrading] = useState(false)

  // Chart State
  const [chartTimeframe, setChartTimeframe] = useState('5m')
  const [signalMode, setSignalMode] = useState<'strict' | 'actionable'>('actionable')
  const [chartSignals, setChartSignals] = useState<ChartSignalMarker[]>([])
  const [chartSignalMeta, setChartSignalMeta] = useState<{
    source: string
    timeframe?: string
    tradeStyle?: string
    fallbackReason?: string
  } | null>(null)

  // MT5-style tab state
  const [activeTab, setActiveTab] = useState<'positions' | 'orders' | 'history'>('positions')
  const [showAIPanel, setShowAIPanel] = useState(false)

  // Position/Order/History selection for chart sync
  const [selectedPositionId, setSelectedPositionId] = useState<string | null>(null)
  const [selectedOrderId, setSelectedOrderId] = useState<string | null>(null)
  const [ghostTrade, setGhostTrade] = useState<GhostTradeOverlay | null>(null)

  // SL/TP Modify Modal State
  const [modifyModal, setModifyModal] = useState<{
    show: boolean
    positionId: string | null
    symbol: string
    side: string
    currentSL: number | null
    currentTP1: number | null
    currentTP2: number | null
    currentTP3: number | null
    newSL: string
    newTP1: string
    newTP2: string
    newTP3: string
  }>({
    show: false, positionId: null, symbol: '', side: '',
    currentSL: null, currentTP1: null, currentTP2: null, currentTP3: null,
    newSL: '', newTP1: '', newTP2: '', newTP3: '',
  })
  const [isModifying, setIsModifying] = useState(false)

  // History filter state
  type HistoryDateRange = 'today' | 'last_week' | 'last_month' | 'last_3_months' | 'last_6_months' | 'last_year' | 'custom' | 'all'
  const [historyDateRange, setHistoryDateRange] = useState<HistoryDateRange>('all')
  const [historySymbolFilter, setHistorySymbolFilter] = useState<string>('all')
  const [historyCustomFrom, setHistoryCustomFrom] = useState('')
  const [historyCustomTo, setHistoryCustomTo] = useState('')
  const [showHistoryDatePicker, setShowHistoryDatePicker] = useState(false)

  useEffect(() => {
    activeBrokerRef.current = activeBroker
  }, [activeBroker])

  const markFeed = useCallback((key: FeedKey, status: FeedStatus, error: string | null = null) => {
    setFeedState((prev) => ({
      ...prev,
      [key]: {
        status,
        error,
        updatedAt: status === 'ready' || status === 'error' ? new Date().toISOString() : prev[key].updatedAt,
      },
    }))
  }, [])

  // Fetch strategies on mount + retry every 10s if empty
  const fetchStrategiesRef = useRef(false)
  useEffect(() => {
    const loadStrategies = () => {
      api.fetchStrategies().then(data => {
        const results = data.results || []
        setStrategies(results)
        if (results.length > 0) fetchStrategiesRef.current = true
        // Auto-select the first strategy or the currently active one
        const active = results.find((s: StrategyDefinition) => s.isActive)
        if (active) setSelectedStrategyId(prev => prev || active.id)
        else if (results.length && !selectedStrategyId) setSelectedStrategyId(results[0].id)
      }).catch(() => {})
    }
    loadStrategies()
    // Retry periodically until strategies are loaded
    const interval = setInterval(() => {
      if (!fetchStrategiesRef.current) loadStrategies()
    }, 10000)
    return () => clearInterval(interval)
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const fetchActiveBroker = useCallback(async (): Promise<Broker | null> => {
    markFeed('broker', 'loading')
    try {
      const data = await api.get<Broker | null>('/api/broker/active')
      if (data) {
        setActiveBroker(data)
        setIsConnected(data.connected)
        setBrokerError(null)
        markFeed('broker', 'ready')
        return data
      }

      setActiveBroker(null)
      setIsConnected(false)
      setPositions([])
      setTradeHistory([])
      setOrders([])
      setBalance({})
      markFeed('broker', 'ready')
      return null
    } catch (error) {
      const detail = getErrorDetail(error, 'Unable to connect to broker. Please check your connection settings.')
      console.error('Failed to fetch active broker:', error)
      setBrokerError(detail)
      markFeed('broker', 'error', detail)
      return null
    }
  }, [markFeed])

  const fetchPositions = useCallback(async (brokerId: string, fetchVersion?: number) => {
    setIsLoadingPositions(true)
    markFeed('positions', 'loading')
    try {
      const data = await api.fetchBrokerPositions(brokerId)
      if (fetchVersion != null && fetchVersion !== fetchVersionRef.current) return
      setPositions(data)
      markFeed('positions', 'ready')
    } catch (error) {
      const detail = getErrorDetail(error, 'Failed to fetch positions')
      console.error('Failed to fetch positions:', error)
      if (fetchVersion != null && fetchVersion !== fetchVersionRef.current) return
      setPositions([])
      markFeed('positions', 'error', detail)
    } finally {
      if (fetchVersion == null || fetchVersion === fetchVersionRef.current) {
        setIsLoadingPositions(false)
      }
    }
  }, [markFeed])

  const fetchBalance = useCallback(async (brokerId: string, fetchVersion?: number) => {
    markFeed('balance', 'loading')
    try {
      const data = await api.fetchBrokerBalance(brokerId)
      if (fetchVersion != null && fetchVersion !== fetchVersionRef.current) return
      setBalance({
        total_equity: data.total_equity,
        available_margin: data.available_margin,
        used_margin: data.used_margin,
        currency: data.currency,
      })
      markFeed('balance', 'ready')
    } catch (error) {
      const detail = getErrorDetail(error, 'Failed to fetch balance')
      if (fetchVersion != null && fetchVersion !== fetchVersionRef.current) return
      markFeed('balance', 'error', detail)
    }
  }, [markFeed])

  const fetchTradeHistory = useCallback(async (brokerId: string, fetchVersion?: number) => {
    markFeed('history', 'loading')
    try {
      const trades = await api.fetchTradeHistory(brokerId, 20)
      if (fetchVersion != null && fetchVersion !== fetchVersionRef.current) return
      setTradeHistory(trades)
      const todayStart = new Date()
      todayStart.setHours(0, 0, 0, 0)
      const todayTrades = trades.filter(t => t.closed_at && new Date(t.closed_at) >= todayStart)
      setDailyPnL(todayTrades.reduce((s, t) => s + t.realized_pnl, 0))
      setTradesToday(todayTrades.length)
      markFeed('history', 'ready')
    } catch (error) {
      const detail = getErrorDetail(error, 'Failed to fetch trade history')
      if (fetchVersion != null && fetchVersion !== fetchVersionRef.current) return
      setTradeHistory([])
      setDailyPnL(0)
      setTradesToday(0)
      markFeed('history', 'error', detail)
    }
  }, [markFeed])

  const fetchOrders = useCallback(async (brokerId: string, fetchVersion?: number) => {
    setIsLoadingOrders(true)
    markFeed('orders', 'loading')
    try {
      const recentOrders = await api.fetchBrokerOrders(brokerId, 10)
      if (fetchVersion != null && fetchVersion !== fetchVersionRef.current) return
      setOrders(recentOrders)
      markFeed('orders', 'ready')
    } catch (error) {
      const detail = getErrorDetail(error, 'Failed to fetch orders')
      if (fetchVersion != null && fetchVersion !== fetchVersionRef.current) return
      setOrders([])
      markFeed('orders', 'error', detail)
    } finally {
      if (fetchVersion == null || fetchVersion === fetchVersionRef.current) {
        setIsLoadingOrders(false)
      }
    }
  }, [markFeed])

  const fetchLedger = useCallback(async (brokerId: string, fetchVersion?: number) => {
    try {
      const [ledger, metrics] = await Promise.all([
        api.fetchTradeLedger(brokerId, 100),
        api.fetchLedgerMetrics(brokerId),
      ])
      if (fetchVersion != null && fetchVersion !== fetchVersionRef.current) return
      setLedgerEntries(ledger.entries)
      setLedgerMetrics(metrics)

      const ledgerOrders = ledger.entries
        .filter((entry) => ['order', 'trade'].includes(entry.source_type))
        .map(ledgerEntryToOrder)
      if (ledgerOrders.length > 0) {
        setOrders(ledgerOrders)
      }

      const ledgerHistory = ledger.entries
        .filter((entry) => entry.closed_at || ['closed', 'filled', 'cancelled', 'rejected'].includes(entry.status.toLowerCase()))
        .map(ledgerEntryToHistory)
      if (ledgerHistory.length > 0) {
        setTradeHistory(ledgerHistory)
        const todayStart = new Date()
        todayStart.setHours(0, 0, 0, 0)
        const todayTrades = ledgerHistory.filter(t => t.closed_at && new Date(t.closed_at) >= todayStart)
        setDailyPnL(todayTrades.reduce((sum, trade) => sum + trade.realized_pnl, 0))
        setTradesToday(todayTrades.length)
      }
    } catch (error) {
      console.warn('Failed to fetch trade ledger:', error)
    }
  }, [])

  const refreshBrokerData = useCallback(async (reason: string) => {
    // Prevent overlapping refreshes - if one is in progress, skip
    if (refreshInFlightRef.current && reason === 'poll') {
      console.info('[LiveTrading] skipping refresh, already in-flight', { reason })
      return
    }
    refreshInFlightRef.current = true
    const fetchVersion = fetchVersionRef.current + 1
    fetchVersionRef.current = fetchVersion

    console.info('[LiveTrading] refreshBrokerData', { reason, fetchVersion })

    const canUseSeededBroker = reason === 'mount' || !activeBrokerRef.current
    const seededBroker = canUseSeededBroker && backendBroker?.id
      ? {
          id: backendBroker.id,
          name: backendBroker.name || backendBroker.id,
          type: activeBrokerRef.current?.type || backendBroker.id,
          connected: backendBroker.connected,
          supported_markets: activeBrokerRef.current?.supported_markets || [],
          environment: backendBroker.environment || activeBrokerRef.current?.environment,
        }
      : null

    if (seededBroker) {
      setActiveBroker(seededBroker)
      setIsConnected(seededBroker.connected)
      markFeed('broker', 'ready')
    }

    const broker = seededBroker || await fetchActiveBroker()
    if (fetchVersion !== fetchVersionRef.current) {
      refreshInFlightRef.current = false
      return
    }

    if (!broker?.id || !broker.connected) {
      setPositions([])
      setTradeHistory([])
      setOrders([])
      setBalance({})
      refreshInFlightRef.current = false
      return
    }

    // Fetch broker data sequentially to avoid exhausting browser connections.
    await fetchPositions(broker.id, fetchVersion)
    if (fetchVersion !== fetchVersionRef.current) { refreshInFlightRef.current = false; return }
    await fetchOrders(broker.id, fetchVersion)
    if (fetchVersion !== fetchVersionRef.current) { refreshInFlightRef.current = false; return }
    await fetchLedger(broker.id, fetchVersion)
    if (fetchVersion !== fetchVersionRef.current) { refreshInFlightRef.current = false; return }
    await fetchBalance(broker.id, fetchVersion)
    if (fetchVersion !== fetchVersionRef.current) { refreshInFlightRef.current = false; return }
    if (reason !== 'poll') {
      await fetchTradeHistory(broker.id, fetchVersion)
    }
    refreshInFlightRef.current = false
  }, [backendBroker?.connected, backendBroker?.environment, backendBroker?.id, backendBroker?.name, fetchActiveBroker, fetchBalance, fetchLedger, fetchOrders, fetchPositions, fetchTradeHistory, markFeed])

  // Broker data polling
  useEffect(() => {
    void refreshBrokerData('mount')
    const interval = setInterval(() => void refreshBrokerData('poll'), 15000)
    return () => clearInterval(interval)
  }, [refreshBrokerData])

  // Automation status polling
  useEffect(() => {
    const poll = async () => {
      markFeed('automation', 'loading')
      try {
        const status = await api.fetchAutomationStatus()
        setAutomationStatus(status)
        setIsTrading(!!status.worker?.running)
        markFeed('automation', 'ready')
      } catch (error) {
        markFeed('automation', 'error', getErrorDetail(error, 'Failed to fetch automation status'))
      }
    }
    void poll()
    const interval = setInterval(() => void poll(), 15000)
    return () => clearInterval(interval)
  }, [markFeed])

  // Signal breakdown polling for chart overlay
  useEffect(() => {
    const fetchSignal = async () => {
      markFeed('signal', 'loading')
      try {
        const data = await api.fetchSignalBreakdown(selectedPair.symbol, chartTimeframe, 'scalp', signalMode === 'actionable')
        if (data && data.direction && data.direction !== 'HOLD') {
          const marker: ChartSignalMarker = {
            entry: (data.entryMin + data.entryMax) / 2,
            entryMin: data.entryMin,
            entryMax: data.entryMax,
            stopLoss: data.stopLoss,
            takeProfit1: data.takeProfit1,
            takeProfit2: data.takeProfit2,
            takeProfit3: data.takeProfit3,
            signalId: data.signalId,
            direction: data.direction as 'BUY' | 'SELL' | 'HOLD',
            timestamp: data.createdAt || new Date().toISOString(),
            status: (data.status as ChartSignalMarker['status']) || 'VALID',
            confidence: data.confidence,
            symbol: data.symbol || selectedPair.symbol,
            expiresAt: data.expiresAt,
          }
          setChartSignals([marker])
          setChartSignalMeta({
            source: data.displaySource || 'primary',
            timeframe: data.sourceTimeframe || chartTimeframe,
            tradeStyle: data.sourceTradeStyle || 'scalp',
            fallbackReason: data.fallbackReason,
          })
        } else {
          setChartSignals([])
          setChartSignalMeta(null)
        }
        markFeed('signal', 'ready')
      } catch (error) {
        setChartSignals([])
        setChartSignalMeta(null)
        markFeed('signal', 'error', getErrorDetail(error, 'Failed to fetch signal breakdown'))
      }
    }
    void fetchSignal()
    const interval = setInterval(() => void fetchSignal(), 15000)
    return () => clearInterval(interval)
  }, [chartTimeframe, markFeed, selectedPair.symbol, signalMode])

  useEffect(() => {
    const fetchQuote = async () => {
      markFeed('quote', 'loading')
      try {
        const quote = await api.fetchQuote(selectedPair.symbol, '1m', 'scalp')
        setLatestQuote({
          currentPrice: quote.currentPrice,
          source: quote.source,
          priceSource: quote.priceSource,
        })
        markFeed('quote', 'ready')
      } catch (error) {
        setLatestQuote(null)
        markFeed('quote', 'error', getErrorDetail(error, 'Failed to fetch live quote'))
      }
    }

    void fetchQuote()
    const interval = setInterval(() => void fetchQuote(), 15000)
    return () => clearInterval(interval)
  }, [selectedPair.symbol])

  // Clear selection when positions disappear
  useEffect(() => {
    if (selectedPositionId && !positions.find(p => getPositionRowId(p) === selectedPositionId)) {
      setSelectedPositionId(null)
    }
  }, [positions, selectedPositionId])

  // Compute P&L from positions
  useEffect(() => {
    const total = positions.reduce((sum, p) => sum + p.unrealized_pnl, 0)
    setCurrentPnL(total)
  }, [positions])

  const handleToggleTrading = useCallback(async () => {
    if (isStartingTrading) return

    if (!isTrading) {
      // === START TRADING ===
      if (!activeBroker?.connected) {
        setOrderMessage({ type: 'error', message: 'Please connect a broker in Settings first' })
        return
      }
      if (!selectedStrategyId) {
        setOrderMessage({ type: 'error', message: 'Please select a strategy before starting' })
        return
      }

      setIsStartingTrading(true)
      try {
        // 1. Activate strategy in live mode
        await api.activateStrategy(selectedStrategyId, 'live', true)
        // 2. Start automation worker in live mode with broker
        await api.startAutomationWorker({ mode: 'live', broker_id: activeBroker.id })
        setIsTrading(true)
        setOrderMessage({ type: 'success', message: `AI trading started with ${strategies.find(s => s.id === selectedStrategyId)?.name || selectedStrategyId}` })
      } catch (err: any) {
        setOrderMessage({ type: 'error', message: err?.detail || 'Failed to start trading' })
      } finally {
        setIsStartingTrading(false)
      }
    } else {
      // === STOP TRADING ===
      setIsStartingTrading(true)
      try {
        await api.stopAutomationWorker()
        setIsTrading(false)
        setOrderMessage({ type: 'success', message: 'AI trading stopped' })
      } catch (err: any) {
        setOrderMessage({ type: 'error', message: err?.detail || 'Failed to stop trading' })
      } finally {
        setIsStartingTrading(false)
      }
    }
  }, [isTrading, isStartingTrading, activeBroker, selectedStrategyId, strategies])

  // Handle position row click - select for chart sync
  const handlePositionClick = useCallback((pos: Position) => {
    const posId = getPositionRowId(pos)
    if (selectedPositionId === posId) {
      // Deselect
      setSelectedPositionId(null)
    } else {
      setSelectedPositionId(posId)
      setSelectedOrderId(null)
      setGhostTrade(null)
      // Auto-switch pair if different
      const pair = getPairBySymbol(pos.symbol)
      if (pair && pair.symbol !== selectedPair.symbol) {
        onPairChange(pair)
      }
    }
  }, [selectedPositionId, selectedPair.symbol, onPairChange])

  // Handle order row click - select for chart sync
  const handleOrderClick = useCallback((order: BrokerOrderItem) => {
    if (selectedOrderId === order.order_id) {
      setSelectedOrderId(null)
    } else {
      setSelectedOrderId(order.order_id)
      setSelectedPositionId(null)
      setGhostTrade(null)
      const pair = getPairBySymbol(order.symbol)
      if (pair && pair.symbol !== selectedPair.symbol) {
        onPairChange(pair)
      }
    }
  }, [selectedOrderId, selectedPair.symbol, onPairChange])

  // Handle history trade click - show ghost overlay on chart
  const handleHistoryClick = useCallback((trade: TradeHistoryItem) => {
    if (ghostTrade && ghostTrade.entryPrice === trade.entry_price && ghostTrade.exitPrice === trade.exit_price) {
      setGhostTrade(null)
    } else {
      setGhostTrade({
        entryPrice: trade.entry_price,
        exitPrice: trade.exit_price,
        side: trade.side as 'buy' | 'sell',
        realizedPnl: trade.realized_pnl,
        symbol: trade.symbol,
        stopLoss: trade.stop_loss != null && trade.stop_loss > 0 ? trade.stop_loss : undefined,
        takeProfit1: trade.take_profit_1 != null && trade.take_profit_1 > 0 ? trade.take_profit_1 : undefined,
        takeProfit2: trade.take_profit_2 != null && trade.take_profit_2 > 0 ? trade.take_profit_2 : undefined,
        takeProfit3: trade.take_profit_3 != null && trade.take_profit_3 > 0 ? trade.take_profit_3 : undefined,
      })
      setSelectedPositionId(null)
      setSelectedOrderId(null)
      const pair = getPairBySymbol(trade.symbol)
      if (pair && pair.symbol !== selectedPair.symbol) {
        onPairChange(pair)
      }
    }
  }, [ghostTrade, selectedPair.symbol, onPairChange])

  // Handle opening modify SL/TP modal
  const handleOpenModify = useCallback((pos: Position) => {
    const ledgerTrade = ledgerEntries.find(entry => (
      entry.symbol === pos.symbol
      && ['trade', 'order'].includes(entry.source_type)
      && ['open', 'filled'].includes(entry.status.toLowerCase())
      && ledgerEntryHasTargets(entry)
    ))
    const matchingOrder = ledgerTrade ? ledgerEntryToOrder(ledgerTrade) : orders.find(o => o.symbol === pos.symbol && hasTradeTargets(o) && ['filled', 'open'].includes(o.status.toLowerCase()))
    setModifyModal({
      show: true,
      positionId: ledgerTrade?.source_type === 'trade' ? ledgerTrade.source_id : pos.position_id ?? null,
      symbol: pos.symbol,
      side: pos.side,
      currentSL: matchingOrder?.stop_loss ?? null,
      currentTP1: matchingOrder?.take_profit_1 ?? null,
      currentTP2: matchingOrder?.take_profit_2 ?? null,
      currentTP3: matchingOrder?.take_profit_3 ?? null,
      newSL: matchingOrder?.stop_loss != null && matchingOrder.stop_loss > 0 ? String(matchingOrder.stop_loss) : '',
      newTP1: matchingOrder?.take_profit_1 != null && matchingOrder.take_profit_1 > 0 ? String(matchingOrder.take_profit_1) : '',
      newTP2: matchingOrder?.take_profit_2 != null && matchingOrder.take_profit_2 > 0 ? String(matchingOrder.take_profit_2) : '',
      newTP3: matchingOrder?.take_profit_3 != null && matchingOrder.take_profit_3 > 0 ? String(matchingOrder.take_profit_3) : '',
    })
  }, [ledgerEntries, orders])

  const handleConfirmModify = async () => {
    if (!activeBroker?.id || !modifyModal.positionId) return
    setIsModifying(true)
    try {
      await api.modifyTrade(activeBroker.id, modifyModal.positionId, {
        stop_loss: modifyModal.newSL ? parseFloat(modifyModal.newSL) : undefined,
        take_profit: modifyModal.newTP1 ? parseFloat(modifyModal.newTP1) : undefined,
      })
      setOrderMessage({ type: 'success', message: `Trade ${modifyModal.positionId} modified for ${modifyModal.symbol}` })
      setModifyModal(prev => ({ ...prev, show: false }))
      setTimeout(() => void refreshBrokerData('modify-trade'), 2000)
    } catch (err: any) {
      setOrderMessage({ type: 'error', message: err?.detail || 'Failed to modify trade' })
    } finally {
      setIsModifying(false)
    }
  }

  const handlePlaceOrderClick = (side: 'buy' | 'sell') => {
    if (!activeBroker?.connected) {
      setOrderMessage({ type: 'error', message: 'Please connect a broker in Settings first' })
      return
    }
    const currentPrice = latestQuote?.currentPrice ?? selectedPair.basePriceApprox
    setOrderConfirmation({ show: true, side, quantity: 1.0, price: currentPrice })
  }

  const handleConfirmOrder = async () => {
    if (!activeBroker) return
    setIsPlacingOrder(true)
    setOrderMessage(null)
    try {
      const data = await api.placeBrokerOrder({
          broker_id: activeBroker.id,
          symbol: selectedPair.symbol,
          side: orderConfirmation.side,
          quantity: orderConfirmation.quantity,
          order_type: 'market',
          price: null,
          signal_id: chartSignals.find((signal) => signal.symbol === selectedPair.symbol)?.signalId ?? null,
          stop_loss: lastAnalysis?.symbol === selectedPair.symbol ? lastAnalysis.stopLoss : undefined,
          take_profit_1: lastAnalysis?.symbol === selectedPair.symbol ? lastAnalysis.takeProfit1 : undefined,
          take_profit_2: lastAnalysis?.symbol === selectedPair.symbol ? lastAnalysis.takeProfit2 : undefined,
          take_profit_3: lastAnalysis?.symbol === selectedPair.symbol ? lastAnalysis.takeProfit3 : undefined,
      })
      // Close modal immediately after order is placed - don't wait for data refresh
      setIsPlacingOrder(false)
      setOrderConfirmation(prev => ({ ...prev, show: false }))
      setOrderMessage({ type: 'success', message: `Order placed: ${data.message}` })
      // Refresh broker data in background after short delay for OANDA to settle
      setTimeout(() => void refreshBrokerData('manual-order'), 2000)
    } catch (err: any) {
      setOrderMessage({ type: 'error', message: err?.detail || 'Network error. Please try again.' })
      setIsPlacingOrder(false)
      setOrderConfirmation(prev => ({ ...prev, show: false }))
    }
  }

  const handleCancelOrder = () => setOrderConfirmation(prev => ({ ...prev, show: false }))

  const handleClosePosition = async (pos: Position) => {
    if (!activeBroker?.id) return
    const positionRowId = getPositionRowId(pos)
    setIsClosingPosition(positionRowId)
    try {
      await api.closePosition(activeBroker.id, pos.symbol, pos.position_id ?? undefined)
      setOrderMessage({
        type: 'success',
        message: pos.position_id
          ? `Position ${pos.position_id} closed for ${pos.symbol}`
          : `Position closed for ${pos.symbol}`,
      })
      // Clear selection & overlay state immediately so stale SL/TP lines disappear
      setSelectedPositionId(null)
      setSelectedOrderId(null)
      setGhostTrade(null)
      // Remove closed position from local state immediately for instant UI feedback
      setPositions(prev => prev.filter(p => getPositionRowId(p) !== positionRowId))
      // Then refresh from broker to get authoritative data + updated history
      await refreshBrokerData('close-position')
      // OANDA may take a moment to settle the closed trade into history;
      // schedule a second refresh so trade history picks it up.
      setTimeout(() => void refreshBrokerData('close-position-settle'), 3000)
    } catch (err: any) {
      setOrderMessage({ type: 'error', message: err?.detail || 'Failed to close position' })
    } finally {
      setIsClosingPosition(null)
    }
  }

  const lastAnalysis = automationStatus?.lastAnalysis
  const workerRunning = automationStatus?.worker?.running ?? false
  const recentExecs = automationStatus?.executions ?? []

  // Build active position overlay for chart
  const activePositionOverlay = useMemo<ActivePositionOverlay | null>(() => {
    if (!selectedPositionId) return null
    const pos = positions.find(p => getPositionRowId(p) === selectedPositionId)
    if (!pos) return null
    const matchingOrder = orders.find(o => o.symbol === pos.symbol && hasTradeTargets(o) && ['filled', 'open'].includes(o.status.toLowerCase()))
    return {
      entryPrice: pos.avg_entry,
      currentPrice: pos.current_price,
      side: pos.side === 'long' ? 'long' : 'short',
      unrealizedPnl: pos.unrealized_pnl,
      quantity: pos.quantity,
      positionId: pos.position_id ?? undefined,
      status: 'active',
      stopLoss: matchingOrder?.stop_loss != null && matchingOrder.stop_loss > 0 ? matchingOrder.stop_loss : undefined,
      takeProfit1: matchingOrder?.take_profit_1 != null && matchingOrder.take_profit_1 > 0 ? matchingOrder.take_profit_1 : undefined,
      takeProfit2: matchingOrder?.take_profit_2 != null && matchingOrder.take_profit_2 > 0 ? matchingOrder.take_profit_2 : undefined,
      takeProfit3: matchingOrder?.take_profit_3 != null && matchingOrder.take_profit_3 > 0 ? matchingOrder.take_profit_3 : undefined,
    }
  }, [selectedPositionId, positions, orders])

  // Build order overlay for chart when an order is selected
  const selectedOrderOverlay = useMemo<ActivePositionOverlay | null>(() => {
    if (!selectedOrderId) return null
    const order = orders.find(o => o.order_id === selectedOrderId)
    if (!order) return null
    const price = order.avg_fill_price || order.price || 0
    const orderStatus = order.status.toLowerCase()
    return {
      entryPrice: price,
      currentPrice: price,
      side: order.side === 'buy' ? 'long' : 'short',
      unrealizedPnl: 0,
      quantity: order.quantity,
      status: ['filled', 'partially_filled'].includes(orderStatus) ? 'active' : 'pending',
      stopLoss: order.stop_loss != null && order.stop_loss > 0 ? order.stop_loss : undefined,
      takeProfit1: order.take_profit_1 != null && order.take_profit_1 > 0 ? order.take_profit_1 : undefined,
      takeProfit2: order.take_profit_2 != null && order.take_profit_2 > 0 ? order.take_profit_2 : undefined,
      takeProfit3: order.take_profit_3 != null && order.take_profit_3 > 0 ? order.take_profit_3 : undefined,
    }
  }, [selectedOrderId, orders])

  // Effective active position overlay (position selection takes priority)
  const effectiveActivePosition = activePositionOverlay || selectedOrderOverlay || null

  const chartOverlay = useMemo(() => {
    const fallbackSignal = chartSignals.find((signal) => signal.symbol === selectedPair.symbol) ?? chartSignals[0] ?? null

    const activePosition = positions.find((position) => position.symbol === selectedPair.symbol) ?? null
    const hasOpenPosition = Boolean(activePosition)
    const activeLedgerEntry = [...ledgerEntries]
      .filter((entry) => (
        entry.symbol === selectedPair.symbol
        && ['trade', 'order', 'position'].includes(entry.source_type)
        && ['open', 'pending', 'partially_filled'].includes(entry.status.toLowerCase())
        && (entry.source_type === 'position' || ledgerEntryHasTargets(entry))
      ))
      .sort((left, right) => getTimestampValue(right.updated_at) - getTimestampValue(left.updated_at))[0] ?? null

    // Find matching order that has trade-level SL/TP configured on the broker
    const activeOrder = activeLedgerEntry && activeLedgerEntry.source_type !== 'position'
      ? ledgerEntryToOrder(activeLedgerEntry)
      : [...orders]
      .filter((order) => (
        order.symbol === selectedPair.symbol
        && hasTradeTargets(order)
        && (
          ['open', 'pending', 'partially_filled'].includes(order.status.toLowerCase())
          || (order.status.toLowerCase() === 'filled' && hasOpenPosition)
        )
      ))
      .sort((left, right) => (
        getTimestampValue(right.updated_at || right.created_at)
        - getTimestampValue(left.updated_at || left.created_at)
      ))[0] ?? null

    // ── ACTIVE TRADE MODE ──
    // When there's an open position, ONLY show levels that are actually
    // configured on the broker (order SL/TP). Do NOT fall through to
    // AI-suggested levels — those are recommendations, not real orders.
    if ((hasOpenPosition && activePosition) || activeLedgerEntry) {
      const positionEntry = toFiniteNumber(activePosition?.avg_entry)
      const ledgerEntry = toFiniteNumber(activeLedgerEntry?.entry_price)
      const orderEntry = toFiniteNumber(activeOrder?.avg_fill_price) ?? toFiniteNumber(activeOrder?.price)
      const entry = orderEntry ?? ledgerEntry ?? positionEntry ?? 0

      // Only use SL/TP that are actually set on the broker order
      const stopLoss = toFiniteNumber(activeOrder?.stop_loss) ?? toFiniteNumber(activeLedgerEntry?.stop_loss) ?? 0
      const takeProfit1 = toFiniteNumber(activeOrder?.take_profit_1) ?? toFiniteNumber(activeLedgerEntry?.take_profit_1) ?? 0
      const takeProfit2 = toFiniteNumber(activeOrder?.take_profit_2) ?? toFiniteNumber(activeLedgerEntry?.take_profit_2) ?? 0
      const takeProfit3 = toFiniteNumber(activeOrder?.take_profit_3) ?? toFiniteNumber(activeLedgerEntry?.take_profit_3) ?? 0

      const direction: 'BUY' | 'SELL' | 'HOLD' = (
        activeOrder?.side === 'buy' ? 'BUY'
        : activeOrder?.side === 'sell' ? 'SELL'
        : activeLedgerEntry?.side === 'buy' || activeLedgerEntry?.side === 'long' ? 'BUY'
        : activeLedgerEntry?.side === 'sell' || activeLedgerEntry?.side === 'short' ? 'SELL'
        : activePosition?.side === 'long' ? 'BUY'
        : activePosition?.side === 'short' ? 'SELL'
        : 'HOLD'
      )

      const hasAnyLevel = entry > 0 || stopLoss > 0 || takeProfit1 > 0
      if (hasAnyLevel) {
        const setupStatus = hasOpenPosition || ['filled', 'partially_filled', 'open'].includes(activeOrder?.status.toLowerCase() ?? activeLedgerEntry?.status.toLowerCase() ?? '')
          ? 'active' as const
          : 'pending' as const
        return {
          source: 'active' as const,
          signals: [{
            entry,
            entryMin: entry,
            entryMax: entry,
            stopLoss,
            takeProfit1,
            takeProfit2,
            takeProfit3,
            signalId: activeOrder?.order_id ?? activeLedgerEntry?.ledger_id ?? undefined,
            direction,
            timestamp: activeOrder?.updated_at || activeOrder?.created_at || activeLedgerEntry?.updated_at || new Date().toISOString(),
            status: 'VALID' as const,
            setupStatus,
            confidence: 100,
            symbol: selectedPair.symbol,
            expiresAt: undefined,
          }],
        }
      }
    }

    // ── SIGNAL MODE ──
    // No open position — show AI-suggested signal levels if available
    if (fallbackSignal) {
      const analysisForPair = lastAnalysis?.symbol === selectedPair.symbol ? lastAnalysis : null

      // Enrich fallback signal with latest AI analysis if available
      if (analysisForPair) {
        return {
          source: 'signal' as const,
          signals: [{
            ...fallbackSignal,
            entry: toFiniteNumber(fallbackSignal.entry) ?? 0,
            entryMin: analysisForPair.entryRange?.min ?? fallbackSignal.entryMin ?? 0,
            entryMax: analysisForPair.entryRange?.max ?? fallbackSignal.entryMax ?? 0,
            stopLoss: analysisForPair.stopLoss ?? fallbackSignal.stopLoss ?? 0,
            takeProfit1: analysisForPair.takeProfit1 ?? fallbackSignal.takeProfit1 ?? 0,
            takeProfit2: analysisForPair.takeProfit2 ?? fallbackSignal.takeProfit2 ?? 0,
            takeProfit3: analysisForPair.takeProfit3 ?? fallbackSignal.takeProfit3 ?? 0,
            direction: (
              analysisForPair.signal === 'buy' ? 'BUY'
              : analysisForPair.signal === 'sell' ? 'SELL'
              : fallbackSignal.direction
            ) ?? 'HOLD',
            confidence: analysisForPair.confidence ?? fallbackSignal.confidence ?? 0,
          }],
        }
      }

      return {
        source: 'signal' as const,
        signals: [fallbackSignal],
      }
    }

    return {
      source: 'none' as const,
      signals: [] as ChartSignalMarker[],
    }
  }, [chartSignals, lastAnalysis, ledgerEntries, orders, positions, selectedPair.symbol])

  return (
    <div className="flex flex-col h-[calc(100vh-48px)] bg-[#0b0e14]">
      {/* MT5-style Header Bar */}
      <header className="flex items-center justify-between px-3 py-2 border-b border-[#1c2333] bg-[#0d1117] shrink-0">
        <div className="flex items-center gap-3">
          {/* Pair selector */}
          <div className="relative">
            <select
              value={selectedPair.symbol}
              onChange={(e) => { const pair = getPairBySymbol(e.target.value); if (pair) onPairChange(pair) }}
              className="bg-[#161b26] border border-[#1c2333] text-trading-text text-sm font-semibold rounded px-2 py-1.5 pr-7 appearance-none cursor-pointer focus:outline-none focus:border-trading-accent"
            >
              {ALL_FOREX_PAIRS.map((pair) => (
                <option key={pair.symbol} value={pair.symbol}>{pair.symbol}</option>
              ))}
            </select>
            <ChevronDown className="absolute right-1.5 top-1/2 -translate-y-1/2 text-trading-muted pointer-events-none" size={14} />
          </div>
          {/* Live price */}
          {latestQuote && (
            <span className="text-sm font-bold tabular-nums text-trading-text">
              {formatPairPrice(latestQuote.currentPrice, selectedPair)}
            </span>
          )}
          {/* Broker status pill */}
          {activeBroker && (
            <div className={`flex items-center gap-1.5 px-2 py-1 rounded text-[11px] font-medium ${activeBroker.connected ? 'bg-emerald-500/10 text-emerald-400' : 'bg-red-500/10 text-red-400'}`}>
              <span className={`w-1.5 h-1.5 rounded-full ${activeBroker.connected ? 'bg-emerald-400' : 'bg-red-400'}`} />
              <span>{activeBroker.name}</span>
              {activeBroker.environment && <span className="uppercase opacity-60 text-[10px]">{activeBroker.environment}</span>}
            </div>
          )}
        </div>
        <div className="flex items-center gap-2">
          {/* Strategy compact dropdown */}
          <select
            value={selectedStrategyId}
            onChange={(e) => setSelectedStrategyId(e.target.value)}
            disabled={isTrading}
            className="bg-[#161b26] border border-[#1c2333] text-trading-muted text-[11px] rounded px-2 py-1.5 appearance-none cursor-pointer focus:outline-none focus:border-trading-accent disabled:opacity-50 max-w-[140px]"
          >
            <option value="">Strategy...</option>
            {strategies.map((s) => (
              <option key={s.id} value={s.id}>{s.name}</option>
            ))}
          </select>
          {/* AI Activity toggle */}
          <button
            onClick={() => setShowAIPanel(!showAIPanel)}
            className={`flex items-center gap-1 px-2 py-1.5 rounded text-[11px] font-medium transition-colors ${
              workerRunning ? 'bg-blue-500/15 text-blue-400 hover:bg-blue-500/25' : 'bg-[#161b26] text-trading-muted hover:bg-[#1c2333]'
            }`}
          >
            <Brain size={12} />
            <span className="hidden sm:inline">AI</span>
          </button>
          {/* Start/Stop trading */}
          <button
            onClick={handleToggleTrading}
            disabled={isStartingTrading || (!isTrading && !activeBroker?.connected)}
            className={`flex items-center gap-1 px-3 py-1.5 rounded text-[11px] font-semibold transition-colors disabled:opacity-40 disabled:cursor-not-allowed ${
              isTrading
                ? 'bg-red-500/20 text-red-400 hover:bg-red-500/30'
                : 'bg-emerald-500/20 text-emerald-400 hover:bg-emerald-500/30'
            }`}
          >
            <Power size={12} />
            {isStartingTrading ? '...' : isTrading ? 'Stop' : 'Start'}
          </button>
          {/* New Order button */}
          <button
            onClick={() => handlePlaceOrderClick('buy')}
            disabled={isPlacingOrder || !activeBroker?.connected}
            className="flex items-center gap-1 px-3 py-1.5 rounded bg-trading-accent/20 text-trading-accent text-[11px] font-semibold hover:bg-trading-accent/30 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <Plus size={12} />
            <span className="hidden sm:inline">New Order</span>
          </button>
        </div>
      </header>

      {/* Compact Banners */}
      {brokerError && (
        <div className="flex items-center justify-between px-3 py-1.5 bg-red-500/8 border-b border-red-500/20 text-[11px] shrink-0">
          <span className="text-red-400">{brokerError}</span>
          <button onClick={() => { setBrokerError(null); fetchActiveBroker() }} className="text-red-400 hover:text-red-300 font-medium">Retry</button>
        </div>
      )}
      {orderMessage && (
        <div className={`flex items-center gap-2 px-3 py-1.5 text-[11px] border-b shrink-0 ${orderMessage.type === 'success' ? 'bg-emerald-500/8 border-emerald-500/20 text-emerald-400' : 'bg-red-500/8 border-red-500/20 text-red-400'}`}>
          {orderMessage.type === 'success' ? <Check size={12} /> : <AlertCircle size={12} />}
          <span>{orderMessage.message}</span>
          <button onClick={() => setOrderMessage(null)} className="ml-auto hover:opacity-70"><X size={12} /></button>
        </div>
      )}

      {/* AI Activity Collapsible Panel */}
      {showAIPanel && (
        <div className="border-b border-[#1c2333] bg-[#0d1117] px-3 py-2 shrink-0">
          <div className="flex items-center justify-between mb-1.5">
            <div className="flex items-center gap-2">
              <Brain size={12} className="text-blue-400" />
              <span className="text-[11px] font-semibold text-trading-muted uppercase tracking-wide">AI Activity</span>
              <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${workerRunning ? 'bg-emerald-500/15 text-emerald-400' : 'bg-[#1c2333] text-trading-muted'}`}>
                {workerRunning ? 'Running' : 'Stopped'}
              </span>
            </div>
            <button onClick={() => setShowAIPanel(false)} className="text-trading-muted hover:text-trading-text"><X size={12} /></button>
          </div>
          {lastAnalysis ? (
            <div className="flex items-start gap-4 text-[11px]">
              <div className="flex items-center gap-1.5">
                <span className={`inline-flex items-center rounded px-1.5 py-0.5 font-bold text-[10px] ${lastAnalysis.signal === 'buy' ? 'bg-emerald-500/20 text-emerald-400' : lastAnalysis.signal === 'sell' ? 'bg-red-500/20 text-red-400' : 'bg-slate-500/20 text-slate-400'}`}>
                  {lastAnalysis.signal === 'buy' ? <TrendingUp size={10} className="mr-0.5" /> : lastAnalysis.signal === 'sell' ? <TrendingDown size={10} className="mr-0.5" /> : null}
                  {lastAnalysis.signal.toUpperCase()}
                </span>
                <span className="text-trading-muted">{lastAnalysis.confidence}%</span>
                <span className="px-1 py-0.5 rounded bg-blue-500/10 text-blue-400 text-[10px]">{lastAnalysis.marketRegime}</span>
              </div>
              {lastAnalysis.entryRange && (
                <div className="flex items-center gap-3 text-trading-muted tabular-nums">
                  <span>Entry: <span className="text-trading-text">{lastAnalysis.entryRange.min.toFixed(2)}-{lastAnalysis.entryRange.max.toFixed(2)}</span></span>
                  <span>SL: <span className="text-red-400">{lastAnalysis.stopLoss.toFixed(2)}</span></span>
                  <span>TP: <span className="text-emerald-400">{lastAnalysis.takeProfit1.toFixed(2)}</span> / <span className="text-emerald-400">{lastAnalysis.takeProfit2.toFixed(2)}</span> / <span className="text-emerald-400">{lastAnalysis.takeProfit3.toFixed(2)}</span></span>
                </div>
              )}
              <span className="text-trading-muted/50 text-[10px] ml-auto shrink-0">
                {new Date(lastAnalysis.timestamp * 1000).toLocaleTimeString()}
              </span>
            </div>
          ) : (
            <p className="text-[11px] text-trading-muted">{workerRunning ? 'Analyzing market...' : 'Start trading to see AI analysis'}</p>
          )}
          {recentExecs.length > 0 && (
            <div className="flex items-center gap-3 mt-1.5 text-[10px]">
              {recentExecs.slice(0, 4).map((exec) => (
                <div key={exec.id} className="flex items-center gap-1">
                  <span className={`w-1 h-1 rounded-full ${exec.status === 'success' ? 'bg-emerald-400' : exec.status === 'skipped' ? 'bg-amber-400' : 'bg-red-400'}`} />
                  <span className="text-trading-muted">{exec.action}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {ledgerMetrics && (
        <div className="grid grid-cols-2 gap-px border-b border-[#1c2333] bg-[#1c2333] text-[10px] md:grid-cols-7 shrink-0">
          <div className="bg-[#0d1117] px-3 py-1.5">
            <div className="text-trading-muted uppercase tracking-wide">Ledger P&L</div>
            <div className={`font-bold tabular-nums ${ledgerMetrics.realized_pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
              {formatSignedCurrency(ledgerMetrics.realized_pnl)}
            </div>
          </div>
          <div className="bg-[#0d1117] px-3 py-1.5">
            <div className="text-trading-muted uppercase tracking-wide">Open P&L</div>
            <div className={`font-bold tabular-nums ${ledgerMetrics.unrealized_pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
              {formatSignedCurrency(ledgerMetrics.unrealized_pnl)}
            </div>
          </div>
          <div className="bg-[#0d1117] px-3 py-1.5">
            <div className="text-trading-muted uppercase tracking-wide">Win Rate</div>
            <div className="font-bold text-trading-text tabular-nums">{ledgerMetrics.win_rate.toFixed(1)}%</div>
          </div>
          <div className="bg-[#0d1117] px-3 py-1.5">
            <div className="text-trading-muted uppercase tracking-wide">Avg R</div>
            <div className="font-bold text-trading-text tabular-nums">{ledgerMetrics.avg_r_multiple != null ? `${ledgerMetrics.avg_r_multiple.toFixed(2)}R` : '—'}</div>
          </div>
          <div className="bg-[#0d1117] px-3 py-1.5">
            <div className="text-trading-muted uppercase tracking-wide">MFE / MAE</div>
            <div className="font-bold text-trading-text tabular-nums">
              {ledgerMetrics.avg_mfe != null ? ledgerMetrics.avg_mfe.toFixed(2) : '—'} / {ledgerMetrics.avg_mae != null ? ledgerMetrics.avg_mae.toFixed(2) : '—'}
            </div>
          </div>
          <div className="bg-[#0d1117] px-3 py-1.5">
            <div className="text-trading-muted uppercase tracking-wide">Profit Factor</div>
            <div className="font-bold text-trading-text tabular-nums">{ledgerMetrics.profit_factor != null ? ledgerMetrics.profit_factor.toFixed(2) : '∞'}</div>
          </div>
          <div className="bg-[#0d1117] px-3 py-1.5">
            <div className="text-trading-muted uppercase tracking-wide">Ledger</div>
            <div className="font-bold text-trading-text tabular-nums">{ledgerMetrics.open_entries} open · {ledgerMetrics.closed_entries} closed</div>
          </div>
        </div>
      )}

      {/* Main Content: Chart + Positions Side-by-Side on larger screens */}
      <div className="flex-1 flex flex-col lg:flex-row min-h-0 overflow-hidden">
        {/* Chart Section */}
        <div className="flex flex-col lg:flex-1 min-h-0">
          <div className="flex items-center justify-between px-3 py-1 border-b border-[#1c2333] bg-[#0d1117] shrink-0">
            <ChartToolbar timeframe={chartTimeframe} onTimeframeChange={setChartTimeframe} />
            <div className="flex items-center gap-1 rounded border border-[#1c2333] bg-[#0b0f17] p-0.5 text-[10px]">
              {(['strict', 'actionable'] as const).map((mode) => (
                <button
                  key={mode}
                  type="button"
                  onClick={() => setSignalMode(mode)}
                  className={`rounded px-2 py-1 font-semibold uppercase tracking-wide transition ${
                    signalMode === mode
                      ? mode === 'actionable'
                        ? 'bg-amber-500/20 text-amber-200'
                        : 'bg-blue-500/20 text-blue-200'
                      : 'text-slate-500 hover:text-slate-300'
                  }`}
                  title={mode === 'strict' ? 'Show only the selected chart timeframe signal' : 'Show nearest quality setup if selected timeframe is HOLD'}
                >
                  {mode}
                </button>
              ))}
            </div>
            {chartOverlay.source !== 'none' && (
              <div className="flex items-center gap-2">
                {chartSignalMeta?.fallbackReason && chartOverlay.source === 'signal' && (
                  <span className="text-[10px] text-amber-300 truncate max-w-[380px]" title={chartSignalMeta.fallbackReason}>
                    {chartSignalMeta.fallbackReason}
                  </span>
                )}
                <span className={`rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${
                  chartOverlay.source === 'active' ? 'bg-emerald-500/15 text-emerald-300' : 'bg-blue-500/15 text-blue-300'
                }`}>
                  {chartOverlay.source === 'active'
                    ? 'Active Trade'
                    : chartSignalMeta?.source === 'fallback'
                      ? `Signal · ${chartSignalMeta.timeframe ?? chartTimeframe} ${chartSignalMeta.tradeStyle ?? 'swing'}`
                      : 'Signal'}
                </span>
              </div>
            )}
          </div>
          <div className="flex-1 min-h-[300px] overflow-hidden">
            <ChartErrorBoundary>
              <TradingChart
                pair={selectedPair}
                timeframe={chartTimeframe}
                signals={chartOverlay.signals}
                tradeStyle="scalp"
                signalTimeframe={chartSignalMeta?.timeframe || chartTimeframe}
                signalTradeStyle={chartSignalMeta?.tradeStyle || 'scalp'}
                signalMode={signalMode}
                activePosition={effectiveActivePosition}
                ghostTrade={ghostTrade}
              />
            </ChartErrorBoundary>
          </div>
          {/* MT5-style Account Summary Strip */}
          <div className="flex items-center justify-between px-3 py-1.5 border-y border-[#1c2333] bg-[#0d1117] shrink-0 text-[11px] tabular-nums">
        <div className="flex items-center gap-4 overflow-x-auto">
          {balance.total_equity != null ? (
            <>
              <div className="flex items-center gap-1">
                <span className="text-trading-muted">Balance</span>
                <span className="text-trading-text font-medium">${formatAccountAmount(balance.total_equity)}</span>
              </div>
              <div className="flex items-center gap-1">
                <span className="text-trading-muted">Equity</span>
                <span className="text-trading-text font-medium">${formatAccountAmount((balance.total_equity ?? 0) + currentPnL)}</span>
              </div>
              {balance.used_margin != null && (
                <div className="flex items-center gap-1">
                  <span className="text-trading-muted">Margin</span>
                  <span className="text-trading-text font-medium">${formatAccountAmount(balance.used_margin)}</span>
                </div>
              )}
              {balance.available_margin != null && (
                <div className="flex items-center gap-1">
                  <span className="text-trading-muted">Free</span>
                  <span className="text-trading-text font-medium">${formatAccountAmount(balance.available_margin)}</span>
                </div>
              )}
            </>
          ) : (
            <span className="text-trading-muted">No account data</span>
          )}
          </div>
          <div className="flex items-center gap-1 shrink-0">
            <span className="text-trading-muted">Profit</span>
            <span className={`font-semibold ${currentPnL >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
              {formatSignedCurrency(currentPnL)}
            </span>
          </div>
          </div>
        </div>

        {/* Positions/Orders/History Panel - Side panel on lg+, below on mobile */}
        <div className="flex flex-col lg:w-[380px] xl:w-[420px] lg:border-l border-[#1c2333] min-h-[200px] lg:min-h-0">
          {/* MT5-style Tab Navigation */}
          <div className="flex border-b border-[#1c2333] bg-[#0d1117] shrink-0">
            {(['positions', 'orders', 'history'] as const).map((tab) => {
              const count = tab === 'positions' ? positions.length : tab === 'orders' ? orders.length : tradeHistory.length
              return (
                <button
                  key={tab}
                  onClick={() => setActiveTab(tab)}
                  className={`flex-1 py-2 text-[11px] font-semibold uppercase tracking-wide transition-colors relative ${
                    activeTab === tab
                      ? 'text-trading-text'
                      : 'text-trading-muted hover:text-trading-text/70'
                  }`}
                >
                  {tab === 'positions' ? 'Positions' : tab === 'orders' ? 'Orders' : 'History'}
                  {count > 0 && <span className="ml-1 text-[10px] opacity-60">({count})</span>}
                  {activeTab === tab && (
                    <div className="absolute bottom-0 left-0 right-0 h-[2px] bg-trading-accent" />
                  )}
                </button>
              )
            })}
            <button
              onClick={() => void refreshBrokerData('manual-tab-refresh')}
              className="px-3 py-2 text-trading-muted hover:text-trading-text transition-colors"
              title="Refresh"
            >
              <RefreshCw size={12} />
            </button>
          </div>

          {/* Tab Content - Scrollable */}
          <div className="flex-1 overflow-y-auto bg-[#0b0e14]">
        {/* Positions Tab */}
        {activeTab === 'positions' && (
          <div className="divide-y divide-[#1c2333]/70">
            {feedState.positions.status === 'error' ? (
              <div className="px-3 py-6 text-center text-[11px] text-amber-300">{feedState.positions.error}</div>
            ) : positions.length === 0 ? (
              <div className="px-3 py-8 text-center">
                <p className="text-[11px] text-trading-muted">No open positions</p>
                {!activeBroker?.connected && (
                  <p className="text-[10px] text-trading-muted/60 mt-1">Connect a broker in Settings to start trading</p>
                )}
              </div>
            ) : (
              positions.map((pos) => {
                const positionRowId = getPositionRowId(pos)
                const pair = getPairBySymbol(pos.symbol) || selectedPair
                const pipDelta = pos.side === 'long'
                  ? getPipMovement(pair, pos.avg_entry, pos.current_price)
                  : getPipMovement(pair, pos.current_price, pos.avg_entry)
                const isSelected = selectedPositionId === positionRowId
                const pnlStatus = Math.abs(pos.unrealized_pnl) < 0.01 ? 'breakeven' : pos.unrealized_pnl >= 0 ? 'profit' : 'loss'
                // Find matching order for SL/TP display
                const matchingOrder = orders.find(o => o.symbol === pos.symbol && hasTradeTargets(o) && ['filled', 'open'].includes(o.status.toLowerCase()))
                return (
                  <div
                    key={positionRowId}
                    className={`px-3 py-2 cursor-pointer transition-colors border-l-2 ${
                      isSelected
                        ? `${pos.side === 'long' ? 'border-l-blue-400 bg-blue-500/8' : 'border-l-red-400 bg-red-500/8'}`
                        : 'border-l-transparent hover:bg-[#161b26]/60'
                    }`}
                    onClick={() => handlePositionClick(pos)}
                  >
                    {/* Row 1: Side, Symbol, Volume ... P&L */}
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        {/* P&L status pulse */}
                        <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${
                          pnlStatus === 'profit' ? 'bg-emerald-400 animate-pulse' : pnlStatus === 'loss' ? 'bg-red-400 animate-pulse' : 'bg-amber-400'
                        }`} />
                        <span className={`text-[11px] font-bold ${pos.side === 'long' ? 'text-blue-400' : 'text-red-400'}`}>
                          {pos.side === 'long' ? 'buy' : 'sell'}
                        </span>
                        <span className="text-[12px] font-semibold text-trading-text">{pos.symbol}</span>
                        <span className="text-[11px] text-trading-muted tabular-nums">{pos.quantity}</span>
                        {pos.position_id && <span className="text-[10px] text-trading-muted/50">#{pos.position_id}</span>}
                        {isSelected && <BarChart2 size={10} className="text-trading-accent opacity-60" />}
                      </div>
                      <span className={`text-[12px] font-bold tabular-nums ${pos.unrealized_pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                        {formatSignedCurrency(pos.unrealized_pnl)}
                      </span>
                    </div>
                    {/* Row 2: Entry -> Current ... Pips */}
                    <div className="flex items-center justify-between mt-0.5">
                      <div className="flex items-center gap-1 text-[11px] tabular-nums">
                        <span className="text-trading-muted">{formatPairPrice(pos.avg_entry, pair)}</span>
                        <ArrowRight size={10} className="text-trading-muted/50" />
                        <span className="text-trading-text">{formatPairPrice(pos.current_price, pair)}</span>
                      </div>
                      <span className={`text-[10px] tabular-nums ${pipDelta >= 0 ? 'text-emerald-400/70' : 'text-red-400/70'}`}>
                        {formatMovementAmount(pipDelta)} pips
                      </span>
                    </div>
                    {/* Row 3: SL/TP if available */}
                    {matchingOrder && (
                      <div className="flex items-center gap-3 mt-0.5 text-[10px] tabular-nums">
                        {matchingOrder.stop_loss != null && matchingOrder.stop_loss > 0 && (
                          <span className="text-trading-muted">SL: <span className="text-red-400/80">{formatPairPrice(matchingOrder.stop_loss, pair)}</span></span>
                        )}
                        {matchingOrder.take_profit_1 != null && matchingOrder.take_profit_1 > 0 && (
                          <span className="text-trading-muted">TP1: <span className="text-emerald-400/80">{formatPairPrice(matchingOrder.take_profit_1, pair)}</span></span>
                        )}
                        {matchingOrder.take_profit_2 != null && matchingOrder.take_profit_2 > 0 && (
                          <span className="text-trading-muted">TP2: <span className="text-emerald-400/80">{formatPairPrice(matchingOrder.take_profit_2, pair)}</span></span>
                        )}
                        {matchingOrder.take_profit_3 != null && matchingOrder.take_profit_3 > 0 && (
                          <span className="text-trading-muted">TP3: <span className="text-emerald-400/80">{formatPairPrice(matchingOrder.take_profit_3, pair)}</span></span>
                        )}
                      </div>
                    )}
                    {/* Action bar: always visible when selected */}
                    {isSelected && (
                      <div className="flex items-center justify-between mt-2 pt-1.5 border-t border-[#1c2333]/50">
                        <div className="flex items-center gap-3 text-[10px] text-trading-muted/70">
                          <span>P&L: {formatMovementAmount(pos.unrealized_pnl_pct)}%</span>
                          <span>{pos.opened_at ? 'Opened' : 'Updated'}: {formatTradeTimestamp(pos.opened_at ?? pos.last_updated ?? null)}</span>
                        </div>
                        <div className="flex items-center gap-1.5">
                          {pos.position_id && (
                            <button
                              onClick={(e) => { e.stopPropagation(); handleOpenModify(pos) }}
                              className="flex items-center gap-1 px-2 py-1 rounded text-[10px] font-semibold bg-blue-500/15 text-blue-400 hover:bg-blue-500/25 transition-colors"
                            >
                              <Edit3 size={10} />Modify
                            </button>
                          )}
                          <button
                            onClick={(e) => { e.stopPropagation(); handleClosePosition(pos) }}
                            disabled={isClosingPosition === positionRowId}
                            className="flex items-center gap-1 px-2 py-1 rounded text-[10px] font-semibold bg-orange-500/15 text-orange-400 hover:bg-orange-500/25 transition-colors disabled:opacity-50"
                          >
                            {isClosingPosition === positionRowId ? <RefreshCw size={10} className="animate-spin" /> : <><XCircle size={10} />Close</>}
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                )
              })
            )}
          </div>
        )}

        {/* Orders Tab */}
        {activeTab === 'orders' && (
          <div className="divide-y divide-[#1c2333]/70">
            {feedState.orders.status === 'error' ? (
              <div className="px-3 py-6 text-center text-[11px] text-amber-300">{feedState.orders.error}</div>
            ) : orders.length === 0 ? (
              <div className="px-3 py-8 text-center text-[11px] text-trading-muted">No recent orders</div>
            ) : (
              orders.map((order) => {
                const orderPair = getPairBySymbol(order.symbol) || selectedPair
                const executionPrice = order.avg_fill_price || order.price
                const isOrderSelected = selectedOrderId === order.order_id
                return (
                  <div
                    key={order.order_id}
                    className={`px-3 py-2 cursor-pointer transition-colors border-l-2 ${
                      isOrderSelected
                        ? `${order.side === 'buy' ? 'border-l-blue-400 bg-blue-500/8' : 'border-l-red-400 bg-red-500/8'}`
                        : 'border-l-transparent hover:bg-[#161b26]/60'
                    }`}
                    onClick={() => handleOrderClick(order)}
                  >
                    {/* Row 1: Side, Symbol, Type, Status */}
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span className={`text-[11px] font-bold ${order.side === 'buy' ? 'text-blue-400' : 'text-red-400'}`}>
                          {order.side}
                        </span>
                        <span className="text-[12px] font-semibold text-trading-text">{order.symbol}</span>
                        <span className="text-[10px] text-trading-muted uppercase">{order.order_type}</span>
                      </div>
                      <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${getOrderStatusClasses(order.status)}`}>
                        {order.status.replace(/_/g, ' ')}
                      </span>
                    </div>
                    {/* Row 2: Volume, Price */}
                    <div className="flex items-center justify-between mt-0.5 text-[11px] tabular-nums">
                      <span className="text-trading-muted">{order.quantity} units</span>
                      {executionPrice != null && (
                        <span className="text-trading-text">{formatPairPrice(executionPrice, orderPair)}</span>
                      )}
                    </div>
                    {/* Row 3: SL/TP if set */}
                    {hasTradeTargets(order) && (
                      <div className="flex items-center gap-3 mt-0.5 text-[10px] tabular-nums">
                        {order.stop_loss != null && order.stop_loss > 0 && (
                          <span className="text-trading-muted">SL: <span className="text-red-400/80">{formatPairPrice(order.stop_loss, orderPair)}</span></span>
                        )}
                        {order.take_profit_1 != null && order.take_profit_1 > 0 && (
                          <span className="text-trading-muted">TP1: <span className="text-emerald-400/80">{formatPairPrice(order.take_profit_1, orderPair)}</span></span>
                        )}
                      </div>
                    )}
                    <div className="text-[10px] text-trading-muted/50 mt-0.5">
                      {formatTradeTimestamp(order.updated_at || order.created_at)}
                    </div>
                  </div>
                )
              })
            )}
          </div>
        )}

          {/* History Tab */}
          {activeTab === 'history' && (() => {
            // Compute date cutoff
            const getDateCutoff = (): Date | null => {
              const now = new Date()
              switch (historyDateRange) {
                case 'today': { const d = new Date(now); d.setHours(0,0,0,0); return d }
                case 'last_week': return new Date(now.getTime() - 7 * 86400000)
                case 'last_month': return new Date(now.getTime() - 30 * 86400000)
                case 'last_3_months': return new Date(now.getTime() - 90 * 86400000)
                case 'last_6_months': return new Date(now.getTime() - 180 * 86400000)
                case 'last_year': return new Date(now.getTime() - 365 * 86400000)
                case 'custom': return historyCustomFrom ? new Date(historyCustomFrom) : null
                default: return null
              }
            }
            const cutoff = getDateCutoff()
            const customEnd = historyDateRange === 'custom' && historyCustomTo ? new Date(historyCustomTo + 'T23:59:59') : null
            const filteredHistory = tradeHistory.filter((t) => {
              if (historySymbolFilter !== 'all' && t.symbol !== historySymbolFilter) return false
              const closed = t.closed_at ? new Date(t.closed_at) : null
              if (cutoff && closed && closed < cutoff) return false
              if (customEnd && closed && closed > customEnd) return false
              return true
            })
            const historySymbols = [...new Set(tradeHistory.map(t => t.symbol))].sort()
            const dateRangeLabels: Record<HistoryDateRange, string> = {
              all: 'All time', today: 'Today', last_week: 'Last week', last_month: 'Last month',
              last_3_months: 'Last 3 months', last_6_months: 'Last 6 months', last_year: 'Last year', custom: 'Custom',
            }

            return (
            <div>
              {/* Filter Bar */}
              <div className="px-2 py-1.5 border-b border-[#1c2333] bg-[#0d1117] space-y-1.5">
                {/* Symbol filter */}
                <div className="flex items-center gap-2">
                  <Filter size={10} className="text-trading-muted shrink-0" />
                  <select
                    value={historySymbolFilter}
                    onChange={(e) => setHistorySymbolFilter(e.target.value)}
                    className="flex-1 bg-[#161b26] border border-[#1c2333] text-trading-text text-[11px] rounded px-1.5 py-1 appearance-none cursor-pointer focus:outline-none focus:border-trading-accent"
                  >
                    <option value="all">All symbols</option>
                    {historySymbols.map(s => <option key={s} value={s}>{s}</option>)}
                  </select>
                </div>
                {/* Date range selector */}
                <div className="relative">
                  <button
                    onClick={() => setShowHistoryDatePicker(p => !p)}
                    className="w-full flex items-center justify-between bg-[#161b26] border border-[#1c2333] text-[11px] rounded px-2 py-1 text-trading-text hover:border-trading-accent/50 transition-colors"
                  >
                    <div className="flex items-center gap-1.5">
                      <Calendar size={10} className="text-trading-muted" />
                      <span>{dateRangeLabels[historyDateRange]}</span>
                    </div>
                    <ChevronDown size={10} className={`text-trading-muted transition-transform ${showHistoryDatePicker ? 'rotate-180' : ''}`} />
                  </button>
                  {showHistoryDatePicker && (
                    <div className="absolute z-20 top-full left-0 right-0 mt-0.5 bg-[#161b26] border border-[#1c2333] rounded shadow-xl overflow-hidden">
                      {(['all','today','last_week','last_month','last_3_months','last_6_months','last_year','custom'] as HistoryDateRange[]).map(range => (
                        <button
                          key={range}
                          onClick={() => { setHistoryDateRange(range); if (range !== 'custom') setShowHistoryDatePicker(false) }}
                          className={`w-full text-left px-3 py-1.5 text-[11px] transition-colors flex items-center justify-between ${
                            historyDateRange === range
                              ? 'bg-trading-accent/10 text-trading-accent'
                              : 'text-trading-text hover:bg-[#1c2333]'
                          }`}
                        >
                          {dateRangeLabels[range]}
                          {historyDateRange === range && <Check size={10} className="text-trading-accent" />}
                        </button>
                      ))}
                      {historyDateRange === 'custom' && (
                        <div className="px-3 py-2 border-t border-[#1c2333] space-y-1.5">
                          <div className="flex items-center gap-1.5">
                            <label className="text-[10px] text-trading-muted w-10">From</label>
                            <input type="date" value={historyCustomFrom} onChange={e => setHistoryCustomFrom(e.target.value)}
                              className="flex-1 bg-[#0d1117] border border-[#1c2333] text-trading-text text-[10px] rounded px-1.5 py-0.5 focus:outline-none focus:border-trading-accent" />
                          </div>
                          <div className="flex items-center gap-1.5">
                            <label className="text-[10px] text-trading-muted w-10">To</label>
                            <input type="date" value={historyCustomTo} onChange={e => setHistoryCustomTo(e.target.value)}
                              className="flex-1 bg-[#0d1117] border border-[#1c2333] text-trading-text text-[10px] rounded px-1.5 py-0.5 focus:outline-none focus:border-trading-accent" />
                          </div>
                          <button onClick={() => setShowHistoryDatePicker(false)}
                            className="w-full text-center text-[10px] font-semibold text-trading-accent hover:text-trading-accent/80 py-1">Apply</button>
                        </div>
                      )}
                    </div>
                  )}
                </div>
                {/* Summary */}
                <div className="flex items-center justify-between text-[10px] text-trading-muted">
                  <span>{filteredHistory.length} trade{filteredHistory.length !== 1 ? 's' : ''}</span>
                  {filteredHistory.length > 0 && (
                    <span className={`font-medium ${
                      filteredHistory.reduce((s, t) => s + t.realized_pnl, 0) >= 0 ? 'text-emerald-400' : 'text-red-400'
                    }`}>
                      Total: {formatSignedCurrency(filteredHistory.reduce((s, t) => s + t.realized_pnl, 0))}
                    </span>
                  )}
                </div>
              </div>

              {/* Trade list */}
              <div className="divide-y divide-[#1c2333]/70">
              {feedState.history.status === 'error' ? (
                <div className="px-3 py-6 text-center text-[11px] text-amber-300">{feedState.history.error}</div>
              ) : filteredHistory.length === 0 ? (
                <div className="px-3 py-8 text-center text-[11px] text-trading-muted">
                  {tradeHistory.length === 0 ? 'No closed trades yet' : 'No trades match the selected filters'}
                </div>
              ) : (
                filteredHistory.map((trade) => {
                  const tradePair = getPairBySymbol(trade.symbol) || selectedPair
                  const isGhostSelected = ghostTrade && ghostTrade.entryPrice === trade.entry_price && ghostTrade.exitPrice === trade.exit_price && ghostTrade.symbol === trade.symbol
                  return (
                    <div
                      key={trade.trade_id}
                      className={`px-3 py-2 cursor-pointer transition-colors border-l-2 ${
                        isGhostSelected
                          ? 'border-l-orange-400 bg-orange-500/8'
                          : 'border-l-transparent hover:bg-[#161b26]/60'
                      }`}
                      onClick={() => handleHistoryClick(trade)}
                    >
                      {/* Row 1: Side, Symbol ... P&L */}
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <span className={`text-[11px] font-bold ${trade.side === 'buy' ? 'text-blue-400' : 'text-red-400'}`}>
                            {trade.side}
                          </span>
                          <span className="text-[12px] font-semibold text-trading-text">{trade.symbol}</span>
                          <span className="text-[11px] text-trading-muted tabular-nums">{trade.quantity}</span>
                        </div>
                        <span className={`text-[12px] font-bold tabular-nums ${trade.realized_pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                          {formatSignedCurrency(trade.realized_pnl)}
                        </span>
                      </div>
                      {/* Row 2: Entry -> Exit */}
                      <div className="flex items-center gap-1 mt-0.5 text-[11px] tabular-nums">
                        <span className="text-trading-muted">{formatPairPrice(trade.entry_price, tradePair)}</span>
                        <ArrowRight size={10} className="text-trading-muted/50" />
                        <span className="text-trading-text">{formatPairPrice(trade.exit_price, tradePair)}</span>
                      </div>
                      {/* Row 3: Timestamps */}
                      <div className="flex items-center gap-3 mt-0.5 text-[10px] text-trading-muted/50">
                        <span>{formatTradeTimestamp(trade.opened_at)}</span>
                        <span>&rarr;</span>
                        <span>{formatTradeTimestamp(trade.closed_at)}</span>
                      </div>
                    </div>
                  )
                })
              )}
              </div>
            </div>
            )
          })()}
          </div>
        </div>
      </div>

      {/* MT5-style Quick Buy/Sell Buttons - Fixed Bottom */}
      {activeBroker?.connected && (
        <div className="flex items-stretch border-t border-[#1c2333] bg-[#0d1117] shrink-0">
          <button
            onClick={() => handlePlaceOrderClick('sell')}
            disabled={isPlacingOrder}
            className="flex-1 py-2.5 text-[12px] font-bold text-red-400 bg-red-500/8 hover:bg-red-500/15 transition-colors disabled:opacity-40 border-r border-[#1c2333]"
          >
            Sell
            {latestQuote && <span className="ml-1.5 tabular-nums text-[11px] font-normal opacity-70">{formatPairPrice(latestQuote.currentPrice, selectedPair)}</span>}
          </button>
          <button
            onClick={() => handlePlaceOrderClick('buy')}
            disabled={isPlacingOrder}
            className="flex-1 py-2.5 text-[12px] font-bold text-blue-400 bg-blue-500/8 hover:bg-blue-500/15 transition-colors disabled:opacity-40"
          >
            Buy
            {latestQuote && <span className="ml-1.5 tabular-nums text-[11px] font-normal opacity-70">{formatPairPrice(latestQuote.currentPrice, selectedPair)}</span>}
          </button>
        </div>
      )}

      {/* Order Confirmation Modal - MT5 style */}
      {orderConfirmation.show && (
        <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50">
          <div className="bg-[#161b26] border border-[#1c2333] rounded-lg p-5 w-80 max-w-full mx-4 shadow-2xl">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-sm font-bold text-trading-text uppercase tracking-wide">
                {orderConfirmation.side === 'buy' ? 'Buy' : 'Sell'} {selectedPair.symbol}
              </h3>
              <button onClick={handleCancelOrder} className="text-trading-muted hover:text-trading-text"><X size={14} /></button>
            </div>
            <div className="space-y-2.5 mb-5 text-[12px]">
              <div className="flex justify-between">
                <span className="text-trading-muted">Symbol</span>
                <span className="font-semibold text-trading-text tabular-nums">{selectedPair.symbol}</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-trading-muted">Volume</span>
                <input
                  type="number"
                  value={orderConfirmation.quantity}
                  onChange={(e) => setOrderConfirmation(prev => ({ ...prev, quantity: parseFloat(e.target.value) || 0 }))}
                  className="bg-[#0d1117] border border-[#1c2333] text-trading-text text-right rounded px-2 py-1 w-20 text-[12px] tabular-nums focus:outline-none focus:border-trading-accent"
                  step="0.01"
                  min="0.01"
                />
              </div>
              <div className="flex justify-between">
                <span className="text-trading-muted">Type</span>
                <span className="font-semibold text-trading-text">Market Execution</span>
              </div>
              <div className="flex justify-between">
                <span className="text-trading-muted">Price</span>
                <span className="font-semibold text-trading-text tabular-nums">{formatPairPrice(orderConfirmation.price, selectedPair)}</span>
              </div>
              {lastAnalysis?.symbol === selectedPair.symbol && (
                <div className="border-t border-[#1c2333] pt-2 space-y-1">
                  <div className="flex justify-between text-[11px]">
                    <span className="text-trading-muted">Stop Loss</span>
                    <span className="text-red-400 tabular-nums">{lastAnalysis.stopLoss.toFixed(2)}</span>
                  </div>
                  <div className="flex justify-between text-[11px]">
                    <span className="text-trading-muted">Take Profit</span>
                    <span className="text-emerald-400 tabular-nums">{lastAnalysis.takeProfit1.toFixed(2)}</span>
                  </div>
                </div>
              )}
            </div>
            <div className="flex gap-2">
              <button onClick={handleCancelOrder} disabled={isPlacingOrder} className="flex-1 py-2.5 rounded text-[12px] font-semibold bg-[#1c2333] hover:bg-[#252d3d] text-trading-muted transition-colors">Cancel</button>
              <button
                onClick={handleConfirmOrder}
                disabled={isPlacingOrder}
                className={`flex-1 py-2.5 rounded text-[12px] font-semibold text-white transition-colors ${
                  orderConfirmation.side === 'buy'
                    ? 'bg-blue-600 hover:bg-blue-700'
                    : 'bg-red-600 hover:bg-red-700'
                }`}
              >
                {isPlacingOrder ? 'Placing...' : `${orderConfirmation.side === 'buy' ? 'Buy' : 'Sell'} by Market`}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Modify SL/TP Modal */}
      {modifyModal.show && (
        <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50">
          <div className="bg-[#161b26] border border-[#1c2333] rounded-lg p-5 w-80 max-w-full mx-4 shadow-2xl">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-sm font-bold text-trading-text uppercase tracking-wide">
                Modify {modifyModal.symbol}
              </h3>
              <button onClick={() => setModifyModal(prev => ({ ...prev, show: false }))} className="text-trading-muted hover:text-trading-text"><X size={14} /></button>
            </div>
            <div className="space-y-3 mb-5">
              <div className="flex items-center gap-2 text-[11px] text-trading-muted mb-2">
                <span className={`font-bold ${modifyModal.side === 'long' ? 'text-blue-400' : 'text-red-400'}`}>
                  {modifyModal.side === 'long' ? 'BUY' : 'SELL'}
                </span>
                <span>Trade #{modifyModal.positionId}</span>
              </div>
              <div>
                <label className="text-[11px] text-trading-muted block mb-1">Stop Loss</label>
                <input
                  type="number"
                  step="any"
                  value={modifyModal.newSL}
                  onChange={(e) => setModifyModal(prev => ({ ...prev, newSL: e.target.value }))}
                  placeholder={modifyModal.currentSL ? String(modifyModal.currentSL) : 'Not set'}
                  className="w-full bg-[#0d1117] border border-[#1c2333] text-trading-text rounded px-2 py-1.5 text-[12px] tabular-nums focus:outline-none focus:border-red-400"
                />
              </div>
              <div>
                <label className="text-[11px] text-trading-muted block mb-1">Take Profit</label>
                <input
                  type="number"
                  step="any"
                  value={modifyModal.newTP1}
                  onChange={(e) => setModifyModal(prev => ({ ...prev, newTP1: e.target.value }))}
                  placeholder={modifyModal.currentTP1 ? String(modifyModal.currentTP1) : 'Not set'}
                  className="w-full bg-[#0d1117] border border-[#1c2333] text-trading-text rounded px-2 py-1.5 text-[12px] tabular-nums focus:outline-none focus:border-emerald-400"
                />
              </div>
            </div>
            <div className="flex gap-2">
              <button
                onClick={() => setModifyModal(prev => ({ ...prev, show: false }))}
                disabled={isModifying}
                className="flex-1 py-2.5 rounded text-[12px] font-semibold bg-[#1c2333] hover:bg-[#252d3d] text-trading-muted transition-colors"
              >Cancel</button>
              <button
                onClick={handleConfirmModify}
                disabled={isModifying}
                className="flex-1 py-2.5 rounded text-[12px] font-semibold text-white bg-blue-600 hover:bg-blue-700 transition-colors disabled:opacity-50"
              >
                {isModifying ? 'Modifying...' : 'Modify Trade'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default LiveTrading
