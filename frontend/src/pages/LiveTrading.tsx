import { useState, useEffect, useMemo } from 'react'
import { Power, Wifi, WifiOff, Activity, ChevronDown, AlertCircle, Check, X } from 'lucide-react'
import type { ForexPair } from '../types'

interface LiveTradingProps {
  selectedPair: ForexPair
  onPairChange: (pair: ForexPair) => void
  activePairs: ForexPair[]
  recentPairs?: ForexPair[]
}

interface Broker {
  id: string
  name: string
  type: string
  connected: boolean
  supported_markets: string[]
}

interface Position {
  symbol: string
  broker_id: string
  quantity: number
  side: string
  avg_entry: number
  current_price: number
  unrealized_pnl: number
  unrealized_pnl_pct: number
}

interface OrderConfirmation {
  show: boolean
  side: 'buy' | 'sell'
  quantity: number
  price: number;
}

function generateMockOrderBook(pair: ForexPair) {
  const basePrice = pair.basePriceApprox
  const spread = pair.baseSpread / 10000 // Convert pips to price
  
  return {
    bids: [
      { price: basePrice - spread * 0.5, size: 2.5 },
      { price: basePrice - spread * 1.5, size: 1.8 },
      { price: basePrice - spread * 2.5, size: 3.2 },
      { price: basePrice - spread * 3.5, size: 4.1 },
      { price: basePrice - spread * 4.5, size: 2.9 },
    ],
    asks: [
      { price: basePrice + spread * 0.5, size: 1.5 },
      { price: basePrice + spread * 1.5, size: 2.3 },
      { price: basePrice + spread * 2.5, size: 3.8 },
      { price: basePrice + spread * 3.5, size: 2.1 },
      { price: basePrice + spread * 4.5, size: 4.5 },
    ],
  }
}

function generateMockActivity(pair: ForexPair) {
  const basePrice = pair.basePriceApprox
  const decimals = pair.basePriceApprox > 100 ? 2 : pair.basePriceApprox > 10 ? 3 : 4
  
  return [
    { time: '14:32:15', action: 'Buy', price: basePrice + Math.random() * 0.01, size: 1.5, pnl: null },
    { time: '14:28:42', action: 'Sell', price: basePrice - Math.random() * 0.01, size: 1.0, pnl: 0.40 },
    { time: '14:15:33', action: 'Buy', price: basePrice - Math.random() * 0.02, size: 2.0, pnl: null },
    { time: '14:02:11', action: 'Sell', price: basePrice + Math.random() * 0.005, size: 1.5, pnl: -1.05 },
    { time: '13:45:58', action: 'Buy', price: basePrice - Math.random() * 0.015, size: 1.0, pnl: null },
  ].map(a => ({ ...a, price: Number(a.price.toFixed(decimals)) }))
}

function LiveTrading({ selectedPair, onPairChange, activePairs, recentPairs: _recentPairs }: LiveTradingProps) {
  const [isTrading, setIsTrading] = useState(false)
  const [isConnected, setIsConnected] = useState(true)
  const [currentPnL, setCurrentPnL] = useState(0)
  const [dailyPnL] = useState(45.20)
  const [tradesToday] = useState(12)
  
  // Broker State
  const [activeBroker, setActiveBroker] = useState<Broker | null>(null)
  const [positions, setPositions] = useState<Position[]>([])
  const [isLoadingPositions, setIsLoadingPositions] = useState(false)
  
  // Order State
  const [orderConfirmation, setOrderConfirmation] = useState<OrderConfirmation>({
    show: false,
    side: 'buy',
    quantity: 1.0,
    price: 0
  })
  const [isPlacingOrder, setIsPlacingOrder] = useState(false)
  const [orderMessage, setOrderMessage] = useState<{type: 'success' | 'error', message: string} | null>(null)

  const mockOrderBook = useMemo(() => generateMockOrderBook(selectedPair), [selectedPair])
  const mockActivity = useMemo(() => generateMockActivity(selectedPair), [selectedPair])

  // Fetch active broker and positions on mount
  useEffect(() => {
    fetchActiveBroker()
    fetchPositions()
  }, [])

  // Refresh positions periodically when trading
  useEffect(() => {
    if (!isTrading) return
    
    const interval = setInterval(() => {
      fetchPositions()
    }, 5000)
    
    return () => clearInterval(interval)
  }, [isTrading])

  useEffect(() => {
    if (!isTrading) return
    
    const interval = setInterval(() => {
      setCurrentPnL(prev => prev + (Math.random() - 0.5) * 2)
    }, 1000)
    
    return () => clearInterval(interval)
  }, [isTrading])

  const fetchActiveBroker = async () => {
    try {
      const response = await fetch('/api/broker/active')
      if (response.ok) {
        const data = await response.json()
        if (data) {
          setActiveBroker(data)
          setIsConnected(data.connected)
        }
      }
    } catch (error) {
      console.error('Failed to fetch active broker:', error)
    }
  }

  const fetchPositions = async () => {
    setIsLoadingPositions(true)
    try {
      const response = await fetch('/api/broker/positions')
      if (response.ok) {
        const data = await response.json()
        setPositions(data)
      }
    } catch (error) {
      console.error('Failed to fetch positions:', error)
    } finally {
      setIsLoadingPositions(false)
    }
  }

  const handleToggleTrading = () => {
    setIsTrading(!isTrading)
  }

  const handlePlaceOrderClick = (side: 'buy' | 'sell') => {
    if (!activeBroker?.connected) {
      setOrderMessage({
        type: 'error',
        message: 'Please connect a broker in Settings first'
      })
      return
    }
    
    const currentPrice = selectedPair.basePriceApprox
    setOrderConfirmation({
      show: true,
      side,
      quantity: 1.0,
      price: currentPrice
    })
  }

  const handleConfirmOrder = async () => {
    if (!activeBroker) return
    
    setIsPlacingOrder(true)
    setOrderMessage(null)
    
    try {
      const response = await fetch('/api/broker/order', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          broker_id: activeBroker.id,
          symbol: selectedPair.symbol,
          side: orderConfirmation.side,
          quantity: orderConfirmation.quantity,
          order_type: 'market',
          price: null
        })
      })
      
      if (response.ok) {
        const data = await response.json()
        setOrderMessage({
          type: 'success',
          message: `Order placed: ${data.message}`
        })
        // Refresh positions after order
        await fetchPositions()
      } else {
        const error = await response.json()
        setOrderMessage({
          type: 'error',
          message: error.detail || 'Failed to place order'
        })
      }
    } catch (error) {
      setOrderMessage({
        type: 'error',
        message: 'Network error. Please try again.'
      })
    } finally {
      setIsPlacingOrder(false)
      setOrderConfirmation(prev => ({ ...prev, show: false }))
    }
  }

  const handleCancelOrder = () => {
    setOrderConfirmation(prev => ({ ...prev, show: false }))
  }

  return (
    <div className="p-6">
      <header className="mb-6">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-2xl font-bold text-trading-text">Live Trading</h2>
            <p className="text-trading-muted">Real-time {selectedPair.symbol} trading with AI</p>
          </div>
          <div className="flex items-center gap-4">
            {/* Broker Status Indicator */}
            {activeBroker && (
              <div className={`flex items-center gap-2 px-3 py-1.5 rounded-full text-sm ${
                activeBroker.connected 
                  ? 'bg-emerald-500/20 text-emerald-400' 
                  : 'bg-red-500/20 text-red-400'
              }`}>
                {activeBroker.connected ? <Wifi size={14} /> : <WifiOff size={14} />}
                <span>{activeBroker.name}</span>
                <span className="w-2 h-2 rounded-full bg-current" />
              </div>
            )}
            
            {/* Pair Selector */}
            <div className="relative">
              <select
                value={selectedPair.symbol}
                onChange={(e) => {
                  const pair = activePairs.find((p) => p.symbol === e.target.value)
                  if (pair) onPairChange(pair)
                }}
                className="input-field appearance-none pr-10 cursor-pointer"
              >
                {activePairs.map((pair) => (
                  <option key={pair.symbol} value={pair.symbol}>
                    {pair.symbol}
                  </option>
                ))}
              </select>
              <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 text-trading-muted pointer-events-none" size={16} />
            </div>
          </div>
        </div>
      </header>

      {/* Order Message */}
      {orderMessage && (
        <div className={`mb-4 p-3 rounded-lg flex items-center gap-2 ${
          orderMessage.type === 'success' 
            ? 'bg-emerald-500/20 text-emerald-400' 
            : 'bg-red-500/20 text-red-400'
        }`}>
          {orderMessage.type === 'success' ? <Check size={18} /> : <AlertCircle size={18} />}
          <span>{orderMessage.message}</span>
          <button 
            onClick={() => setOrderMessage(null)}
            className="ml-auto hover:opacity-70"
          >
            <X size={16} />
          </button>
        </div>
      )}

      <div className="grid grid-cols-12 gap-6">
        {/* Status Panel */}
        <div className="col-span-4">
          <div className="card">
            <h3 className="text-lg font-semibold mb-4">Connection Status</h3>
            
            <div className="space-y-4">
              <div className="flex items-center justify-between p-4 bg-trading-bg rounded-lg">
                <div className="flex items-center gap-3">
                  {isConnected ? (
                    <Wifi className="text-trading-buy" size={24} />
                  ) : (
                    <WifiOff className="text-trading-sell" size={24} />
                  )}
                  <div>
                    <p className="font-semibold">
                      {activeBroker ? `${activeBroker.name} API` : 'Exchange API'}
                    </p>
                    <p className="text-sm text-trading-muted">
                      {isConnected ? 'Connected' : 'Disconnected'}
                    </p>
                  </div>
                </div>
                <span className={`px-3 py-1 rounded-full text-sm ${isConnected ? 'bg-emerald-500/20 text-emerald-400' : 'bg-red-500/20 text-red-400'}`}>
                  {isConnected ? 'Live' : 'Offline'}
                </span>
              </div>

              <div className="flex items-center justify-between p-4 bg-trading-bg rounded-lg">
                <div className="flex items-center gap-3">
                  <Activity className="text-trading-accent" size={24} />
                  <div>
                    <p className="font-semibold">AI Model</p>
                    <p className="text-sm text-trading-muted">PPO v1.2.3</p>
                  </div>
                </div>
                <span className="px-3 py-1 rounded-full text-sm bg-blue-500/20 text-blue-400">
                  Active
                </span>
              </div>

              <button
                onClick={handleToggleTrading}
                className={`w-full py-4 rounded-lg font-semibold flex items-center justify-center gap-2 transition-colors ${
                  isTrading 
                    ? 'bg-red-500 hover:bg-red-600 text-white' 
                    : 'bg-emerald-500 hover:bg-emerald-600 text-white'
                }`}
              >
                <Power size={20} />
                {isTrading ? 'Stop Trading' : 'Start Trading'}
              </button>
            </div>
          </div>

          {/* P&L Display */}
          <div className="card mt-6">
            <h3 className="text-lg font-semibold mb-4">Performance</h3>
            <div className="space-y-4">
              <div className="p-4 bg-trading-bg rounded-lg">
                <p className="text-sm text-trading-muted">Current P&L</p>
                <p className={`text-3xl font-bold ${currentPnL >= 0 ? 'text-trading-buy' : 'text-trading-sell'}`}>
                  {currentPnL >= 0 ? '+' : ''}${currentPnL.toFixed(2)}
                </p>
              </div>
              <div className="p-4 bg-trading-bg rounded-lg">
                <p className="text-sm text-trading-muted">Daily P&L</p>
                <p className={`text-3xl font-bold ${dailyPnL >= 0 ? 'text-trading-buy' : 'text-trading-sell'}`}>
                  {dailyPnL >= 0 ? '+' : ''}${dailyPnL.toFixed(2)}
                </p>
              </div>
              <div className="p-4 bg-trading-bg rounded-lg">
                <p className="text-sm text-trading-muted">Trades Today</p>
                <p className="text-3xl font-bold text-trading-text">{tradesToday}</p>
              </div>
            </div>
          </div>

          {/* Positions Panel */}
          <div className="card mt-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold">Positions</h3>
              {isLoadingPositions && (
                <span className="text-xs text-trading-muted">Loading...</span>
              )}
            </div>
            <div className="space-y-3 max-h-64 overflow-y-auto">
              {positions.length === 0 ? (
                <p className="text-sm text-trading-muted text-center py-4">
                  No open positions
                </p>
              ) : (
                positions.map((pos, i) => (
                  <div key={i} className="p-3 bg-trading-bg rounded-lg">
                    <div className="flex items-center justify-between mb-1">
                      <span className="font-semibold text-trading-text">{pos.symbol}</span>
                      <span className={`text-xs px-2 py-0.5 rounded ${
                        pos.side === 'long' 
                          ? 'bg-emerald-500/20 text-emerald-400' 
                          : 'bg-red-500/20 text-red-400'
                      }`}>
                        {pos.side.toUpperCase()}
                      </span>
                    </div>
                    <div className="flex items-center justify-between text-sm">
                      <span className="text-trading-muted">Qty: {pos.quantity}</span>
                      <span className={`font-semibold ${
                        pos.unrealized_pnl >= 0 ? 'text-trading-buy' : 'text-trading-sell'
                      }`}>
                        {pos.unrealized_pnl >= 0 ? '+' : ''}${pos.unrealized_pnl.toFixed(2)}
                      </span>
                    </div>
                    <div className="text-xs text-trading-muted mt-1">
                      Entry: {pos.avg_entry.toFixed(4)} | Current: {pos.current_price.toFixed(4)}
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>

          {/* Quick Trade Buttons */}
          <div className="grid grid-cols-2 gap-3 mt-6">
            <button
              onClick={() => handlePlaceOrderClick('buy')}
              disabled={isPlacingOrder || !activeBroker?.connected}
              className="py-4 rounded-lg font-semibold bg-emerald-500 hover:bg-emerald-600 text-white disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              Buy {selectedPair.symbol.split('/')[0]}
            </button>
            <button
              onClick={() => handlePlaceOrderClick('sell')}
              disabled={isPlacingOrder || !activeBroker?.connected}
              className="py-4 rounded-lg font-semibold bg-red-500 hover:bg-red-600 text-white disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              Sell {selectedPair.symbol.split('/')[0]}
            </button>
          </div>
          
          {!activeBroker?.connected && (
            <p className="text-xs text-trading-muted text-center mt-2">
              Connect a broker in Settings to trade
            </p>
          )}
        </div>

        {/* Order Book */}
        <div className="col-span-4">
          <div className="card h-full">
            <h3 className="text-lg font-semibold mb-4">Order Book</h3>
            
            <div className="space-y-1">
              {/* Asks */}
              <div className="space-y-1">
                {[...mockOrderBook.asks].reverse().map((ask, i) => (
                  <div key={i} className="flex items-center justify-between text-sm">
                    <span className="text-trading-sell w-20">{ask.price.toFixed(2)}</span>
                    <div className="flex-1 mx-2 h-4 bg-trading-bg rounded overflow-hidden">
                      <div 
                        className="h-full bg-red-500/30"
                        style={{ width: `${(ask.size / 5) * 100}%` }}
                      />
                    </div>
                    <span className="text-trading-muted w-12 text-right">{ask.size}</span>
                  </div>
                ))}
              </div>

              {/* Spread */}
              <div className="py-2 text-center border-y border-trading-border">
                <span className="text-trading-muted text-sm">Spread: </span>
                <span className="text-trading-text font-semibold">
                  {(mockOrderBook.asks[0].price - mockOrderBook.bids[0].price).toFixed(2)}
                </span>
              </div>

              {/* Bids */}
              <div className="space-y-1">
                {mockOrderBook.bids.map((bid, i) => (
                  <div key={i} className="flex items-center justify-between text-sm">
                    <span className="text-trading-buy w-20">{bid.price.toFixed(2)}</span>
                    <div className="flex-1 mx-2 h-4 bg-trading-bg rounded overflow-hidden">
                      <div 
                        className="h-full bg-emerald-500/30"
                        style={{ width: `${(bid.size / 5) * 100}%` }}
                      />
                    </div>
                    <span className="text-trading-muted w-12 text-right">{bid.size}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>

        {/* Recent Activity */}
        <div className="col-span-4">
          <div className="card h-full">
            <h3 className="text-lg font-semibold mb-4">Recent Activity</h3>
            
            <div className="space-y-3">
              {mockActivity.map((activity, i) => (
                <div key={i} className="flex items-center justify-between p-3 bg-trading-bg rounded-lg">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className={`text-xs px-2 py-0.5 rounded ${activity.action === 'Buy' ? 'bg-emerald-500/20 text-emerald-400' : 'bg-red-500/20 text-red-400'}`}>
                        {activity.action}
                      </span>
                      <span className="text-sm text-trading-muted">{activity.time}</span>
                    </div>
                    <p className="text-sm mt-1">
                      {activity.size} {selectedPair.symbol.split('/')[0]} @ {activity.price}
                    </p>
                  </div>
                  {activity.pnl !== null && (
                    <span className={`text-sm font-semibold ${activity.pnl >= 0 ? 'text-trading-buy' : 'text-trading-sell'}`}>
                      {activity.pnl >= 0 ? '+' : ''}{activity.pnl.toFixed(2)}
                    </span>
                  )}
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Order Confirmation Modal */}
      {orderConfirmation.show && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-trading-card rounded-lg p-6 w-96 max-w-full mx-4">
            <h3 className="text-xl font-bold text-trading-text mb-4">
              Confirm {orderConfirmation.side.toUpperCase()} Order
            </h3>
            
            <div className="space-y-3 mb-6">
              <div className="flex justify-between">
                <span className="text-trading-muted">Symbol:</span>
                <span className="font-semibold text-trading-text">{selectedPair.symbol}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-trading-muted">Side:</span>
                <span className={`font-semibold ${
                  orderConfirmation.side === 'buy' ? 'text-emerald-400' : 'text-red-400'
                }`}>
                  {orderConfirmation.side.toUpperCase()}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-trading-muted">Quantity:</span>
                <input
                  type="number"
                  value={orderConfirmation.quantity}
                  onChange={(e) => setOrderConfirmation(prev => ({
                    ...prev,
                    quantity: parseFloat(e.target.value) || 0
                  }))}
                  className="input-field w-24 text-right"
                  step="0.01"
                  min="0.01"
                />
              </div>
              <div className="flex justify-between">
                <span className="text-trading-muted">Type:</span>
                <span className="font-semibold text-trading-text">MARKET</span>
              </div>
              <div className="flex justify-between">
                <span className="text-trading-muted">Est. Price:</span>
                <span className="font-semibold text-trading-text">
                  {orderConfirmation.price.toFixed(4)}
                </span>
              </div>
            </div>
            
            <div className="flex gap-3">
              <button
                onClick={handleCancelOrder}
                disabled={isPlacingOrder}
                className="flex-1 py-3 rounded-lg font-semibold bg-trading-border hover:bg-trading-border/80 text-trading-text transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleConfirmOrder}
                disabled={isPlacingOrder}
                className={`flex-1 py-3 rounded-lg font-semibold text-white transition-colors ${
                  orderConfirmation.side === 'buy'
                    ? 'bg-emerald-500 hover:bg-emerald-600'
                    : 'bg-red-500 hover:bg-red-600'
                }`}
              >
                {isPlacingOrder ? 'Placing...' : 'Confirm'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default LiveTrading
