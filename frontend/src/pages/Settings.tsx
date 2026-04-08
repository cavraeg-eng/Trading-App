import { useState, useEffect } from 'react'
import { Key, Shield, Bell, Save, Eye, EyeOff, DollarSign, Check, X, RefreshCw, TrendingUp } from 'lucide-react'
import type { ForexPair } from '../types'
import { MAJOR_PAIRS, MINOR_PAIRS, EXOTIC_PAIRS, COMMODITY_PAIRS, CRYPTO_PAIRS, INDEX_PAIRS, ALL_FOREX_PAIRS } from '../config/forexPairs'

interface SettingsProps {
  activePairs: ForexPair[]
  onActivePairsChange: (pairs: ForexPair[]) => void
}

interface Broker {
  id: string
  name: string
  type: string
  connected: boolean
  supported_markets: string[]
}

interface BrokerCredential {
  apiKey: string
  apiSecret: string
  apiToken: string
  accountId: string
  environment: 'sandbox' | 'practice' | 'paper' | 'live'
}

const BROKER_INFO: Record<string, { name: string; icon: string; markets: string[]; description: string }> = {
  binance: {
    name: 'Binance',
    icon: 'B',
    markets: ['Crypto', 'Futures'],
    description: 'World\'s largest crypto exchange'
  },
  bybit: {
    name: 'Bybit',
    icon: 'By',
    markets: ['Crypto', 'Futures'],
    description: 'Crypto derivatives exchange'
  },
  okx: {
    name: 'OKX',
    icon: 'OK',
    markets: ['Crypto', 'Futures'],
    description: 'Global crypto trading platform'
  },
  kraken: {
    name: 'Kraken',
    icon: 'K',
    markets: ['Crypto', 'Futures'],
    description: 'Secure crypto exchange'
  },
  oanda: {
    name: 'OANDA',
    icon: 'O',
    markets: ['Forex', 'CFDs'],
    description: 'Leading forex broker'
  },
  alpaca: {
    name: 'Alpaca',
    icon: 'A',
    markets: ['Stocks', 'Crypto'],
    description: 'Commission-free stock trading'
  }
}

function Settings({ activePairs, onActivePairsChange }: SettingsProps) {
  // API Configuration State
  const [selectedBroker, setSelectedBroker] = useState<string>('')
  const [, setBrokers] = useState<Broker[]>([])
  const [activeBroker, setActiveBroker] = useState<string>('')
  const [connectionStatus, setConnectionStatus] = useState<Record<string, boolean>>({})
  
  // Credential States
  const [credentials, setCredentials] = useState<Record<string, BrokerCredential>>({
    binance: { apiKey: '', apiSecret: '', apiToken: '', accountId: '', environment: 'sandbox' },
    bybit: { apiKey: '', apiSecret: '', apiToken: '', accountId: '', environment: 'sandbox' },
    okx: { apiKey: '', apiSecret: '', apiToken: '', accountId: '', environment: 'sandbox' },
    kraken: { apiKey: '', apiSecret: '', apiToken: '', accountId: '', environment: 'sandbox' },
    oanda: { apiKey: '', apiSecret: '', apiToken: '', accountId: '', environment: 'practice' },
    alpaca: { apiKey: '', apiSecret: '', apiToken: '', accountId: '', environment: 'paper' }
  })
  
  // UI States
  const [showApiKey, setShowApiKey] = useState(false)
  const [showApiSecret, setShowApiSecret] = useState(false)
  const [showApiToken, setShowApiToken] = useState(false)
  const [isConnecting, setIsConnecting] = useState(false)
  const [connectionMessage, setConnectionMessage] = useState<{type: 'success' | 'error', message: string} | null>(null)

  // Trading Settings
  const [maxPositionSize, setMaxPositionSize] = useState('10')
  const [stopLoss, setStopLoss] = useState('2')
  const [takeProfit, setTakeProfit] = useState('4')
  const [maxDailyLoss, setMaxDailyLoss] = useState('100')
  const [telegramToken, setTelegramToken] = useState('')
  const [discordWebhook, setDiscordWebhook] = useState('')

  // Fetch brokers on mount
  useEffect(() => {
    fetchBrokers()
  }, [])

  const fetchBrokers = async () => {
    try {
      const response = await fetch('/api/broker/list')
      if (response.ok) {
        const data = await response.json()
        setBrokers(data)
        // Update connection status
        const status: Record<string, boolean> = {}
        data.forEach((broker: Broker) => {
          status[broker.id] = broker.connected
        })
        setConnectionStatus(status)
        
        // Find active broker
        const active = data.find((b: Broker) => b.connected)
        if (active) {
          setActiveBroker(active.id)
        }
      }
    } catch (error) {
      console.error('Failed to fetch brokers:', error)
    }
  }

  const handleSave = () => {
    alert('Settings saved successfully!')
  }

  const handleBrokerSelect = (brokerId: string) => {
    setSelectedBroker(brokerId)
    setConnectionMessage(null)
  }

  const handleCredentialChange = (brokerId: string, field: keyof BrokerCredential, value: string) => {
    setCredentials(prev => ({
      ...prev,
      [brokerId]: {
        ...prev[brokerId],
        [field]: value
      }
    }))
  }

  const handleTestConnection = async () => {
    if (!selectedBroker) return
    
    setIsConnecting(true)
    setConnectionMessage(null)
    
    const creds = credentials[selectedBroker]
    const brokerType = BROKER_INFO[selectedBroker]?.markets.includes('Forex') ? 'oanda' : 
                       BROKER_INFO[selectedBroker]?.markets.includes('Stocks') ? 'alpaca' : 'ccxt'
    
    let requestBody: Record<string, string> = {}
    
    if (brokerType === 'oanda') {
      requestBody = {
        api_token: creds.apiToken,
        account_id: creds.accountId,
        environment: creds.environment
      }
    } else if (brokerType === 'alpaca') {
      requestBody = {
        api_key: creds.apiKey,
        api_secret: creds.apiSecret,
        environment: creds.environment
      }
    } else {
      requestBody = {
        api_key: creds.apiKey,
        api_secret: creds.apiSecret,
        environment: creds.environment
      }
    }
    
    try {
      const response = await fetch(`/api/broker/connect/${selectedBroker}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(requestBody)
      })
      
      if (response.ok) {
        const data = await response.json()
        setConnectionMessage({ type: 'success', message: data.message })
        setConnectionStatus(prev => ({ ...prev, [selectedBroker]: true }))
        setActiveBroker(selectedBroker)
        await fetchBrokers()
      } else {
        const error = await response.json()
        setConnectionMessage({ type: 'error', message: error.detail || 'Connection failed' })
      }
    } catch (error) {
      setConnectionMessage({ type: 'error', message: 'Network error. Please try again.' })
    } finally {
      setIsConnecting(false)
    }
  }

  const handleDisconnect = async (brokerId: string) => {
    try {
      const response = await fetch(`/api/broker/disconnect/${brokerId}`, {
        method: 'POST'
      })
      
      if (response.ok) {
        setConnectionStatus(prev => ({ ...prev, [brokerId]: false }))
        if (activeBroker === brokerId) {
          setActiveBroker('')
        }
        await fetchBrokers()
      }
    } catch (error) {
      console.error('Failed to disconnect:', error)
    }
  }

  const isPairActive = (pair: ForexPair) => {
    return activePairs.some((p) => p.symbol === pair.symbol)
  }

  const togglePair = (pair: ForexPair) => {
    if (isPairActive(pair)) {
      onActivePairsChange(activePairs.filter((p) => p.symbol !== pair.symbol))
    } else {
      onActivePairsChange([...activePairs, pair])
    }
  }

  const selectAllInCategory = (pairs: ForexPair[]) => {
    const newPairs = [...activePairs]
    pairs.forEach((pair) => {
      if (!newPairs.some((p) => p.symbol === pair.symbol)) {
        newPairs.push(pair)
      }
    })
    onActivePairsChange(newPairs)
  }

  const deselectAllInCategory = (pairs: ForexPair[]) => {
    const symbolsToRemove = new Set(pairs.map((p) => p.symbol))
    onActivePairsChange(activePairs.filter((p) => !symbolsToRemove.has(p.symbol)))
  }

  const areAllSelected = (pairs: ForexPair[]) => {
    return pairs.every((pair) => isPairActive(pair))
  }

  const renderPairCategory = (title: string, pairs: ForexPair[]) => {
    const allSelected = areAllSelected(pairs)
    return (
      <div className="mb-4">
        <div className="flex items-center justify-between mb-2">
          <h4 className="text-sm font-medium text-trading-text">{title}</h4>
          <button
            onClick={() => allSelected ? deselectAllInCategory(pairs) : selectAllInCategory(pairs)}
            className="text-xs text-trading-accent hover:text-blue-400 transition-colors"
          >
            {allSelected ? 'Deselect All' : 'Select All'}
          </button>
        </div>
        <div className="space-y-1 max-h-32 overflow-y-auto">
          {pairs.map((pair) => (
            <label
              key={pair.symbol}
              className="flex items-center gap-3 p-2 rounded hover:bg-trading-bg cursor-pointer transition-colors"
            >
              <input
                type="checkbox"
                checked={isPairActive(pair)}
                onChange={() => togglePair(pair)}
                className="rounded bg-trading-bg border-trading-border text-trading-accent focus:ring-trading-accent"
              />
              <span className="font-semibold text-trading-text w-20">{pair.symbol}</span>
              <span className="text-sm text-trading-muted flex-1">{pair.nickname || pair.name}</span>
              <span className="text-xs text-trading-muted">{pair.baseSpread} pips</span>
            </label>
          ))}
        </div>
      </div>
    )
  }

  const getCredentialInputs = () => {
    if (!selectedBroker) return null
    
    const creds = credentials[selectedBroker]
    const isOanda = BROKER_INFO[selectedBroker]?.markets.includes('Forex')
    const isAlpaca = BROKER_INFO[selectedBroker]?.markets.includes('Stocks')
    
    if (isOanda) {
      return (
        <div className="space-y-4">
          <div>
            <label className="block text-sm text-trading-muted mb-2">API Token</label>
            <div className="relative">
              <input
                type={showApiToken ? 'text' : 'password'}
                value={creds.apiToken}
                onChange={(e) => handleCredentialChange(selectedBroker, 'apiToken', e.target.value)}
                placeholder="Enter your OANDA API token"
                className="input-field w-full pr-10"
              />
              <button
                onClick={() => setShowApiToken(!showApiToken)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-trading-muted hover:text-trading-text"
              >
                {showApiToken ? <EyeOff size={18} /> : <Eye size={18} />}
              </button>
            </div>
          </div>
          
          <div>
            <label className="block text-sm text-trading-muted mb-2">Account ID</label>
            <input
              type="text"
              value={creds.accountId}
              onChange={(e) => handleCredentialChange(selectedBroker, 'accountId', e.target.value)}
              placeholder="Enter your OANDA account ID"
              className="input-field w-full"
            />
          </div>
          
          <div>
            <label className="block text-sm text-trading-muted mb-2">Environment</label>
            <select
              value={creds.environment}
              onChange={(e) => handleCredentialChange(selectedBroker, 'environment', e.target.value)}
              className="input-field w-full"
            >
              <option value="practice">Practice (Demo)</option>
              <option value="live">Live</option>
            </select>
          </div>
        </div>
      )
    }
    
    if (isAlpaca) {
      return (
        <div className="space-y-4">
          <div>
            <label className="block text-sm text-trading-muted mb-2">API Key</label>
            <div className="relative">
              <input
                type={showApiKey ? 'text' : 'password'}
                value={creds.apiKey}
                onChange={(e) => handleCredentialChange(selectedBroker, 'apiKey', e.target.value)}
                placeholder="Enter your Alpaca API key"
                className="input-field w-full pr-10"
              />
              <button
                onClick={() => setShowApiKey(!showApiKey)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-trading-muted hover:text-trading-text"
              >
                {showApiKey ? <EyeOff size={18} /> : <Eye size={18} />}
              </button>
            </div>
          </div>
          
          <div>
            <label className="block text-sm text-trading-muted mb-2">Secret Key</label>
            <div className="relative">
              <input
                type={showApiSecret ? 'text' : 'password'}
                value={creds.apiSecret}
                onChange={(e) => handleCredentialChange(selectedBroker, 'apiSecret', e.target.value)}
                placeholder="Enter your Alpaca secret key"
                className="input-field w-full pr-10"
              />
              <button
                onClick={() => setShowApiSecret(!showApiSecret)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-trading-muted hover:text-trading-text"
              >
                {showApiSecret ? <EyeOff size={18} /> : <Eye size={18} />}
              </button>
            </div>
          </div>
          
          <div>
            <label className="block text-sm text-trading-muted mb-2">Environment</label>
            <select
              value={creds.environment}
              onChange={(e) => handleCredentialChange(selectedBroker, 'environment', e.target.value)}
              className="input-field w-full"
            >
              <option value="paper">Paper Trading</option>
              <option value="live">Live</option>
            </select>
          </div>
        </div>
      )
    }
    
    // CCXT brokers (Binance, Bybit, OKX, Kraken)
    return (
      <div className="space-y-4">
        <div>
          <label className="block text-sm text-trading-muted mb-2">API Key</label>
          <div className="relative">
            <input
              type={showApiKey ? 'text' : 'password'}
              value={creds.apiKey}
              onChange={(e) => handleCredentialChange(selectedBroker, 'apiKey', e.target.value)}
              placeholder={`Enter your ${BROKER_INFO[selectedBroker]?.name} API key`}
              className="input-field w-full pr-10"
            />
            <button
              onClick={() => setShowApiKey(!showApiKey)}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-trading-muted hover:text-trading-text"
            >
              {showApiKey ? <EyeOff size={18} /> : <Eye size={18} />}
            </button>
          </div>
        </div>
        
        <div>
          <label className="block text-sm text-trading-muted mb-2">API Secret</label>
          <div className="relative">
            <input
              type={showApiSecret ? 'text' : 'password'}
              value={creds.apiSecret}
              onChange={(e) => handleCredentialChange(selectedBroker, 'apiSecret', e.target.value)}
              placeholder={`Enter your ${BROKER_INFO[selectedBroker]?.name} API secret`}
              className="input-field w-full pr-10"
            />
            <button
              onClick={() => setShowApiSecret(!showApiSecret)}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-trading-muted hover:text-trading-text"
            >
              {showApiSecret ? <EyeOff size={18} /> : <Eye size={18} />}
            </button>
          </div>
        </div>
        
        <div>
          <label className="block text-sm text-trading-muted mb-2">Environment</label>
          <select
            value={creds.environment}
            onChange={(e) => handleCredentialChange(selectedBroker, 'environment', e.target.value)}
            className="input-field w-full"
          >
            <option value="sandbox">Sandbox (Testnet)</option>
            <option value="live">Live</option>
          </select>
        </div>
      </div>
    )
  }

  return (
    <div className="p-6">
      <header className="mb-6">
        <h2 className="text-2xl font-bold text-trading-text">Settings</h2>
        <p className="text-trading-muted">Configure your trading bot parameters</p>
      </header>

      <div className="grid grid-cols-2 gap-6">
        {/* Trading Pairs */}
        <div className="card col-span-2">
          <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
            <DollarSign size={20} />
            Trading Pairs
          </h3>
          
          <div className="mb-4">
            <p className="text-sm text-trading-muted">
              {activePairs.length} of {ALL_FOREX_PAIRS.length} pairs selected
            </p>
          </div>

          <div className="grid grid-cols-3 gap-6">
            {renderPairCategory('Major Pairs', MAJOR_PAIRS)}
            {renderPairCategory('Minor Pairs', MINOR_PAIRS)}
            {renderPairCategory('Exotic Pairs', EXOTIC_PAIRS)}
            {renderPairCategory('Commodity Pairs', COMMODITY_PAIRS)}
            {renderPairCategory('Crypto Pairs', CRYPTO_PAIRS)}
            {renderPairCategory('Index Pairs', INDEX_PAIRS)}
          </div>
        </div>

        {/* API Configuration - Enhanced Broker Selection */}
        <div className="card col-span-2">
          <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
            <Key size={20} />
            API Configuration
            {activeBroker && (
              <span className="ml-auto text-sm px-3 py-1 rounded-full bg-emerald-500/20 text-emerald-400 flex items-center gap-2">
                <Check size={14} />
                Active: {BROKER_INFO[activeBroker]?.name || activeBroker}
              </span>
            )}
          </h3>
          
          {/* Broker Selection Cards */}
          <div className="grid grid-cols-6 gap-3 mb-6">
            {Object.entries(BROKER_INFO).map(([id, info]) => {
              const isConnected = connectionStatus[id]
              const isSelected = selectedBroker === id
              
              return (
                <button
                  key={id}
                  onClick={() => handleBrokerSelect(id)}
                  className={`p-4 rounded-lg border-2 transition-all text-left relative ${
                    isSelected
                      ? 'border-trading-accent bg-trading-accent/10'
                      : 'border-trading-border hover:border-trading-accent/50'
                  }`}
                >
                  {/* Connection Status Indicator */}
                  <div className={`absolute top-2 right-2 w-2 h-2 rounded-full ${
                    isConnected ? 'bg-emerald-500' : 'bg-gray-500'
                  }`} />
                  
                  {/* Broker Icon */}
                  <div className="w-10 h-10 rounded-lg bg-trading-accent/20 flex items-center justify-center text-trading-accent font-bold mb-2">
                    {info.icon}
                  </div>
                  
                  {/* Broker Name */}
                  <h4 className="font-semibold text-trading-text text-sm">{info.name}</h4>
                  
                  {/* Market Tags */}
                  <div className="flex flex-wrap gap-1 mt-2">
                    {info.markets.map(market => (
                      <span key={market} className="text-xs px-1.5 py-0.5 rounded bg-trading-bg text-trading-muted">
                        {market}
                      </span>
                    ))}
                  </div>
                </button>
              )
            })}
          </div>

          {/* Credential Inputs */}
          {selectedBroker && (
            <div className="bg-trading-bg/50 rounded-lg p-4">
              <div className="flex items-center justify-between mb-4">
                <h4 className="font-semibold text-trading-text">
                  {BROKER_INFO[selectedBroker]?.name} Credentials
                </h4>
                {connectionStatus[selectedBroker] && (
                  <button
                    onClick={() => handleDisconnect(selectedBroker)}
                    className="text-sm text-red-400 hover:text-red-300 flex items-center gap-1"
                  >
                    <X size={14} />
                    Disconnect
                  </button>
                )}
              </div>
              
              {getCredentialInputs()}
              
              {/* Test Connection Button */}
              <div className="mt-4 flex items-center gap-3">
                <button
                  onClick={handleTestConnection}
                  disabled={isConnecting}
                  className="btn-buy flex items-center gap-2 px-4 py-2 disabled:opacity-50"
                >
                  {isConnecting ? (
                    <RefreshCw size={18} className="animate-spin" />
                  ) : (
                    <Check size={18} />
                  )}
                  {isConnecting ? 'Connecting...' : 'Test Connection'}
                </button>
                
                {connectionMessage && (
                  <span className={`text-sm ${
                    connectionMessage.type === 'success' ? 'text-emerald-400' : 'text-red-400'
                  }`}>
                    {connectionMessage.message}
                  </span>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Risk Management */}
        <div className="card">
          <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
            <Shield size={20} />
            Risk Management
          </h3>
          
          <div className="space-y-4">
            <div>
              <label className="block text-sm text-trading-muted mb-2">Max Position Size (lots)</label>
              <input
                type="number"
                value={maxPositionSize}
                onChange={(e) => setMaxPositionSize(e.target.value)}
                className="input-field w-full"
                step="0.1"
                min="0.1"
              />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm text-trading-muted mb-2">Stop Loss (%)</label>
                <input
                  type="number"
                  value={stopLoss}
                  onChange={(e) => setStopLoss(e.target.value)}
                  className="input-field w-full"
                  step="0.1"
                  min="0.1"
                />
              </div>
              <div>
                <label className="block text-sm text-trading-muted mb-2">Take Profit (%)</label>
                <input
                  type="number"
                  value={takeProfit}
                  onChange={(e) => setTakeProfit(e.target.value)}
                  className="input-field w-full"
                  step="0.1"
                  min="0.1"
                />
              </div>
            </div>

            <div>
              <label className="block text-sm text-trading-muted mb-2">Max Daily Loss ($)</label>
              <input
                type="number"
                value={maxDailyLoss}
                onChange={(e) => setMaxDailyLoss(e.target.value)}
                className="input-field w-full"
                min="1"
              />
            </div>

            <div>
              <label className="block text-sm text-trading-muted mb-2">Kelly Criterion</label>
              <select className="input-field w-full">
                <option value="full">Full Kelly</option>
                <option value="half">Half Kelly</option>
                <option value="quarter">Quarter Kelly</option>
                <option value="disabled">Disabled</option>
              </select>
            </div>
          </div>
        </div>

        {/* Notifications */}
        <div className="card">
          <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
            <Bell size={20} />
            Notifications
          </h3>
          
          <div className="space-y-4">
            <div>
              <label className="block text-sm text-trading-muted mb-2">Telegram Bot Token</label>
              <input
                type="password"
                value={telegramToken}
                onChange={(e) => setTelegramToken(e.target.value)}
                placeholder="Enter Telegram bot token"
                className="input-field w-full"
              />
            </div>

            <div>
              <label className="block text-sm text-trading-muted mb-2">Discord Webhook URL</label>
              <input
                type="password"
                value={discordWebhook}
                onChange={(e) => setDiscordWebhook(e.target.value)}
                placeholder="Enter Discord webhook URL"
                className="input-field w-full"
              />
            </div>

            <div className="space-y-2">
              <label className="flex items-center gap-2">
                <input type="checkbox" className="rounded bg-trading-bg border-trading-border" />
                <span className="text-sm">Trade notifications</span>
              </label>
              <label className="flex items-center gap-2">
                <input type="checkbox" className="rounded bg-trading-bg border-trading-border" />
                <span className="text-sm">Daily summary</span>
              </label>
              <label className="flex items-center gap-2">
                <input type="checkbox" className="rounded bg-trading-bg border-trading-border" />
                <span className="text-sm">Risk alerts</span>
              </label>
            </div>
          </div>
        </div>

        {/* Model Settings */}
        <div className="card">
          <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
            <TrendingUp size={20} />
            Model Configuration
          </h3>
          
          <div className="space-y-4">
            <div>
              <label className="block text-sm text-trading-muted mb-2">Default Model</label>
              <select className="input-field w-full">
                <option value="ppo">PPO (Proximal Policy Optimization)</option>
                <option value="sac">SAC (Soft Actor-Critic)</option>
                <option value="a2c">A2C (Advantage Actor-Critic)</option>
              </select>
            </div>

            <div>
              <label className="block text-sm text-trading-muted mb-2">Observation Window</label>
              <select className="input-field w-full">
                <option value="50">50 periods</option>
                <option value="100">100 periods</option>
                <option value="200">200 periods</option>
              </select>
            </div>

            <div>
              <label className="block text-sm text-trading-muted mb-2">Action Space</label>
              <select className="input-field w-full">
                <option value="discrete">Discrete (Buy/Hold/Sell)</option>
                <option value="continuous">Continuous (Position sizing)</option>
              </select>
            </div>

            <div>
              <label className="block text-sm text-trading-muted mb-2">Reward Function</label>
              <select className="input-field w-full">
                <option value="returns">Returns-based</option>
                <option value="sharpe">Sharpe Ratio</option>
                <option value="sortino">Sortino Ratio</option>
                <option value="calmar">Calmar Ratio</option>
              </select>
            </div>
          </div>
        </div>
      </div>

      {/* Save Button */}
      <div className="mt-6 flex justify-end">
        <button
          onClick={handleSave}
          className="btn-buy flex items-center gap-2 px-6 py-3"
        >
          <Save size={20} />
          Save Settings
        </button>
      </div>
    </div>
  )
}

export default Settings
