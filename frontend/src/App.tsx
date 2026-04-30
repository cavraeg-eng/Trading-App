import { useState, useCallback, useEffect, useRef, lazy, Suspense, useTransition } from 'react'
import { BookText, Bot, LayoutDashboard, LineChart, Play, Settings, ScanLine, Users, WalletCards } from 'lucide-react'
import { api, type BackendStatus } from './lib/api'
import { MAJOR_PAIRS, DEFAULT_PAIR, getPairBySymbol } from './config/forexPairs'
import type { ForexPair } from './types'
import AlertBell from './components/AlertBell'
import AlertToastContainer, { useAlertToast } from './components/AlertToast'

// Lazy-load page components for code splitting
const Dashboard = lazy(() => import('./pages/Dashboard'))
const Backtest = lazy(() => import('./pages/Backtest'))
const LiveTrading = lazy(() => import('./pages/LiveTrading'))
const SettingsPage = lazy(() => import('./pages/Settings'))
const Scanner = lazy(() => import('./pages/Scanner'))
const Social = lazy(() => import('./pages/Social'))
const Automation = lazy(() => import('./pages/Automation'))
const CopyJournal = lazy(() => import('./pages/CopyJournal'))
const LiveTradeJournal = lazy(() => import('./pages/LiveTradeJournal'))

type Tab = 'dashboard' | 'scanner' | 'backtest' | 'live' | 'automation' | 'live-journal' | 'journal' | 'social' | 'settings'

const RECENT_PAIRS_KEY = 'tradingApp_recentPairs'
const DEFAULT_PAIR_KEY = 'tradingApp_defaultPair'
const ACTIVE_PAIRS_KEY = 'tradingApp_activePairs'
const MAX_RECENT_PAIRS = 8
const BACKEND_STATUS_KEY = 'tradingApp_backendStatus'

type ActiveBrokerSnapshot = {
  id?: string
  connected?: boolean
  name?: string
  environment?: string | null
} | null

const loadStoredBackendStatus = (): BackendStatus | null => {
  try {
    const raw = sessionStorage.getItem(BACKEND_STATUS_KEY)
    if (!raw) return null
    return JSON.parse(raw) as BackendStatus
  } catch {
    return null
  }
}

function App() {
  const [activeTab, setActiveTab] = useState<Tab>('dashboard')
  const [, startTransition] = useTransition()

  // Smart Alerts state
  const [unreadCount, setUnreadCount] = useState(0)
  const prevUnreadRef = useRef(0)
  const { toasts, showToast, dismissToast } = useAlertToast()

  const refreshUnreadCount = useCallback(() => {
    api.fetchUnreadCount()
      .then(({ count }) => {
        setUnreadCount(() => {
          // If count increased, fetch latest alert and show toast
          if (count > prevUnreadRef.current && prevUnreadRef.current >= 0) {
            api.fetchAlerts(true, 1).then(alerts => {
              if (alerts.length > 0) showToast(alerts[0])
            }).catch(() => {})
          }
          prevUnreadRef.current = count
          return count
        })
      })
      .catch(() => {})
  }, [showToast])

  // Poll unread count every 30s
  useEffect(() => {
    // Initial fetch — set baseline without triggering toast
    api.fetchUnreadCount()
      .then(({ count }) => {
        prevUnreadRef.current = count
        setUnreadCount(count)
      })
      .catch(() => {})
    const id = setInterval(refreshUnreadCount, 30000)
    return () => clearInterval(id)
  }, [refreshUnreadCount])
  const [selectedPair, setSelectedPair] = useState<ForexPair>(() => {
    try {
      const stored = localStorage.getItem(DEFAULT_PAIR_KEY)
      if (stored) {
        const pair = getPairBySymbol(stored)
        if (pair) return pair
      }
    } catch {
      // Ignore parse errors
    }
    return DEFAULT_PAIR
  })
  const [activePairs, setActivePairs] = useState<ForexPair[]>(() => {
    try {
      const stored = localStorage.getItem(ACTIVE_PAIRS_KEY)
      if (stored) {
        const symbols = JSON.parse(stored) as string[]
        return symbols
          .map(symbol => getPairBySymbol(symbol))
          .filter((pair): pair is ForexPair => pair !== undefined)
      }
    } catch {
      // Ignore parse errors
    }
    return MAJOR_PAIRS
  })

  // Backend health polling
  const [backendStatus, setBackendStatus] = useState<BackendStatus | null>(() => loadStoredBackendStatus())
  const backendStatusRef = useRef<BackendStatus | null>(backendStatus)
  useEffect(() => {
    backendStatusRef.current = backendStatus
    if (!backendStatus) return
    try {
      sessionStorage.setItem(BACKEND_STATUS_KEY, JSON.stringify(backendStatus))
    } catch {
      // Ignore storage errors
    }
  }, [backendStatus])
  useEffect(() => {
    let cancelled = false

    const check = async () => {
      const previous = backendStatusRef.current
      try {
        const [healthRes, brokerRes] = await Promise.allSettled([
          fetch('/api/health', { cache: 'no-store' }),
          fetch('/api/broker/active', { cache: 'no-store' }),
        ])

        let nextStatus: BackendStatus = previous ?? {
          api: { status: 'unreachable', version: '', uptime: 0 },
          broker: null,
          dataFreshness: 'unknown',
        }

        if (healthRes.status === 'fulfilled' && healthRes.value.ok) {
          const health = await healthRes.value.json() as { status: string; version: string; uptime: number }
          nextStatus = {
            api: { status: 'healthy', version: health.version, uptime: health.uptime },
            broker: previous?.broker ?? null,
            dataFreshness: 'live',
          }
        }

        if (brokerRes.status === 'fulfilled' && brokerRes.value.ok) {
          const broker = await brokerRes.value.json() as ActiveBrokerSnapshot
          nextStatus = {
            ...nextStatus,
            broker: broker ? {
              id: broker.id ?? null,
              connected: !!broker.connected,
              name: broker.name ?? broker.id ?? null,
              environment: broker.environment ?? null,
              lastSync: Date.now(),
            } : null,
          }
        }

        if (!cancelled) {
          setBackendStatus(nextStatus)
        }
      } catch {
        if (!cancelled) {
          setBackendStatus(previous ?? {
            api: { status: 'unreachable', version: '', uptime: 0 },
            broker: null,
            dataFreshness: 'unknown',
          })
        }
      }
    }
    check()
    const id = setInterval(check, 15000)
    return () => {
      cancelled = true
      clearInterval(id)
    }
  }, [])
  
  // Load recent pairs from localStorage on init
  const [recentPairs, setRecentPairs] = useState<ForexPair[]>(() => {
    try {
      const stored = localStorage.getItem(RECENT_PAIRS_KEY)
      if (stored) {
        const symbols = JSON.parse(stored) as string[]
        const pairs = symbols
          .map(symbol => getPairBySymbol(symbol))
          .filter((pair): pair is ForexPair => pair !== undefined)
        return pairs
      }
    } catch {
      // Ignore parse errors
    }
    return []
  })

  // Default pair symbol state
  const [defaultPairSymbol, setDefaultPairSymbol] = useState<string>(() => {
    try {
      const stored = localStorage.getItem(DEFAULT_PAIR_KEY)
      if (stored && getPairBySymbol(stored)) return stored
    } catch {
      // Ignore
    }
    return DEFAULT_PAIR.symbol
  })

  useEffect(() => {
    try {
      localStorage.setItem(ACTIVE_PAIRS_KEY, JSON.stringify(activePairs.map((pair) => pair.symbol)))
    } catch {
      // Ignore storage errors
    }
  }, [activePairs])

  const handleActivePairsChange = (pairs: ForexPair[]) => {
    setActivePairs(pairs)
  }

  // Handle pair change with recent pairs tracking
  const handlePairChange = useCallback((pair: ForexPair) => {
    setSelectedPair(pair)
    setRecentPairs(prev => {
      // Remove duplicate if exists
      const filtered = prev.filter(p => p.symbol !== pair.symbol)
      // Add to front, limit to MAX_RECENT_PAIRS
      const updated = [pair, ...filtered].slice(0, MAX_RECENT_PAIRS)
      // Save to localStorage (only symbols)
      localStorage.setItem(RECENT_PAIRS_KEY, JSON.stringify(updated.map(p => p.symbol)))
      return updated
    })
  }, [])

  // Handle setting default pair
  const handleSetDefaultPair = useCallback((pair: ForexPair) => {
    setDefaultPairSymbol(pair.symbol)
    localStorage.setItem(DEFAULT_PAIR_KEY, pair.symbol)
  }, [])

  const tabs = [
    { id: 'dashboard' as Tab, label: 'Dashboard', icon: LayoutDashboard },
    { id: 'scanner' as Tab, label: 'Scanner', icon: ScanLine },
    { id: 'backtest' as Tab, label: 'Backtest', icon: LineChart },
    { id: 'live' as Tab, label: 'Live Trading', icon: Play },
    { id: 'automation' as Tab, label: 'Automation', icon: Bot },
    { id: 'live-journal' as Tab, label: 'Live Journal', icon: WalletCards },
    { id: 'journal' as Tab, label: 'Copy Journal', icon: BookText },
    { id: 'social' as Tab, label: 'Social', icon: Users },
    { id: 'settings' as Tab, label: 'Settings', icon: Settings },
  ]

  return (
    <div className="flex h-screen bg-trading-bg">
      {/* Sidebar */}
      <aside className="w-64 bg-trading-card border-r border-trading-border flex flex-col">
        <div className="p-4 border-b border-trading-border">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-xl font-bold text-trading-text">AI Trading Bot</h1>
              <p className="text-sm text-trading-muted">{selectedPair.symbol} Trading Interface</p>
            </div>
            <AlertBell unreadCount={unreadCount} onCountRefresh={refreshUnreadCount} />
          </div>
        </div>
        
        <nav className="flex-1 p-4">
          {tabs.map((tab) => {
            const Icon = tab.icon
            return (
              <button
                key={tab.id}
                onClick={() => startTransition(() => setActiveTab(tab.id))}
                className={`w-full flex items-center gap-3 px-4 py-3 rounded-lg mb-2 transition-colors ${
                  activeTab === tab.id
                    ? 'bg-trading-accent text-white'
                    : 'text-trading-muted hover:bg-trading-border hover:text-trading-text'
                }`}
              >
                <Icon size={20} />
                <span>{tab.label}</span>
              </button>
            )
          })}
        </nav>
        
        <div className="p-4 border-t border-trading-border">
          <div className="text-xs text-trading-muted">
            {backendStatus?.api.status === 'healthy' ? (
              <p>API: <span className="text-trading-buy">● Connected</span></p>
            ) : backendStatus?.api.status === 'unreachable' ? (
              <p>API: <span className="text-red-400">● Disconnected</span></p>
            ) : (
              <p>API: <span className="text-yellow-400">● Checking...</span></p>
            )}
            {backendStatus?.broker ? (
              <p className="mt-1">Broker: <span className={backendStatus.broker.connected ? 'text-trading-buy' : 'text-red-400'}>
                {backendStatus.broker.connected ? '●' : '○'} {backendStatus.broker.name || 'None'}
              </span></p>
            ) : (
              <p className="mt-1">Broker: <span className="text-trading-muted">Not configured</span></p>
            )}
            <p className="mt-1">v1.0.0</p>
          </div>
        </div>
      </aside>

      {/* Main Content */}
      <main className="flex-1 overflow-auto">
        <Suspense fallback={<div className="flex items-center justify-center h-full text-trading-muted">Loading...</div>}>
        {activeTab === 'dashboard' && (
          <Dashboard
            selectedPair={selectedPair}
            onPairChange={handlePairChange}
            activePairs={activePairs}
            recentPairs={recentPairs}
            defaultPairSymbol={defaultPairSymbol}
            onSetDefaultPair={handleSetDefaultPair}
            apiConnected={backendStatus?.api.status === 'healthy'}
            backendBroker={backendStatus?.broker ?? null}
          />
        )}
        {activeTab === 'scanner' && (
          <Scanner
            onPairChange={handlePairChange}
            onOpenDashboard={() => startTransition(() => setActiveTab('dashboard'))}
            onOpenLiveTrading={() => startTransition(() => setActiveTab('live'))}
            onOpenBacktest={() => startTransition(() => setActiveTab('backtest'))}
            onAddToWatchlist={(pair) => {
              setActivePairs((prev) => {
                if (prev.some((item) => item.symbol === pair.symbol)) return prev
                return [...prev, pair]
              })
            }}
            activeWatchlistSymbols={activePairs.map((pair) => pair.symbol)}
            recentPairs={recentPairs}
          />
        )}
        {activeTab === 'backtest' && (
          <Backtest
            selectedPair={selectedPair}
            activePairs={activePairs}
            onPairChange={handlePairChange}
            recentPairs={recentPairs}
          />
        )}
        {activeTab === 'live' && (
          <LiveTrading
            selectedPair={selectedPair}
            onPairChange={handlePairChange}
            activePairs={activePairs}
            recentPairs={recentPairs}
            backendBroker={backendStatus?.broker ?? null}
          />
        )}
        {activeTab === 'automation' && <Automation />}
        {activeTab === 'live-journal' && <LiveTradeJournal />}
        {activeTab === 'journal' && <CopyJournal />}
        {activeTab === 'social' && <Social />}
        {activeTab === 'settings' && (
          <SettingsPage
            activePairs={activePairs}
            onActivePairsChange={handleActivePairsChange}
          />
        )}
        </Suspense>
      </main>

      {/* Alert toasts */}
      <AlertToastContainer toasts={toasts} onDismiss={dismissToast} />
    </div>
  )
}

export default App
