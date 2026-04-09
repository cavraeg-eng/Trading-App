import { useState, useCallback, useEffect, lazy, Suspense, useTransition } from 'react'
import { LayoutDashboard, LineChart, Play, Settings, ScanLine, Users } from 'lucide-react'
import { api, type BackendStatus } from './lib/api'
import { MAJOR_PAIRS, DEFAULT_PAIR, getPairBySymbol } from './config/forexPairs'
import type { ForexPair } from './types'

// Lazy-load page components for code splitting
const Dashboard = lazy(() => import('./pages/Dashboard'))
const Backtest = lazy(() => import('./pages/Backtest'))
const LiveTrading = lazy(() => import('./pages/LiveTrading'))
const SettingsPage = lazy(() => import('./pages/Settings'))
const Scanner = lazy(() => import('./pages/Scanner'))
const Social = lazy(() => import('./pages/Social'))

type Tab = 'dashboard' | 'scanner' | 'backtest' | 'live' | 'social' | 'settings'

const RECENT_PAIRS_KEY = 'tradingApp_recentPairs'
const DEFAULT_PAIR_KEY = 'tradingApp_defaultPair'
const MAX_RECENT_PAIRS = 8

function App() {
  const [activeTab, setActiveTab] = useState<Tab>('dashboard')
  const [, startTransition] = useTransition()
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
  const [activePairs, setActivePairs] = useState<ForexPair[]>(MAJOR_PAIRS)

  // Backend health polling
  const [backendStatus, setBackendStatus] = useState<BackendStatus | null>(null)
  useEffect(() => {
    const check = () => api.health().then(setBackendStatus)
    check()
    const id = setInterval(check, 15000)
    return () => clearInterval(id)
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
    { id: 'social' as Tab, label: 'Social', icon: Users },
    { id: 'settings' as Tab, label: 'Settings', icon: Settings },
  ]

  return (
    <div className="flex h-screen bg-trading-bg">
      {/* Sidebar */}
      <aside className="w-64 bg-trading-card border-r border-trading-border flex flex-col">
        <div className="p-4 border-b border-trading-border">
          <h1 className="text-xl font-bold text-trading-text">AI Trading Bot</h1>
          <p className="text-sm text-trading-muted">{selectedPair.symbol} Trading Interface</p>
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
          />
        )}
        {activeTab === 'scanner' && (
          <Scanner onPairChange={handlePairChange} recentPairs={recentPairs} />
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
          />
        )}
        {activeTab === 'social' && <Social />}
        {activeTab === 'settings' && (
          <SettingsPage
            activePairs={activePairs}
            onActivePairsChange={handleActivePairsChange}
          />
        )}
        </Suspense>
      </main>
    </div>
  )
}

export default App
