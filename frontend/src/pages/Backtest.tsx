import { useEffect, useState } from 'react'
import { Play, Download, Calendar, Settings } from 'lucide-react'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'
import type { BacktestResult, ForexPair } from '../types'
import api from '../lib/api'
import { formatDateOnly } from '../lib/time'
import { StrategyCatalog } from '../components/StrategyCatalog'
import { AutomationTemplateCard } from '../components/AutomationTemplateCard'
import type { StrategyDefinition } from '../types'

interface BacktestProps {
  selectedPair: ForexPair
  activePairs: ForexPair[]
  onPairChange: (pair: ForexPair) => void
  recentPairs?: ForexPair[]
}

function Backtest({ selectedPair, activePairs, onPairChange, recentPairs: _recentPairs }: BacktestProps) {
  const [startDate, setStartDate] = useState('2024-01-01')
  const [endDate, setEndDate] = useState('2024-12-31')
  const [timeframe, setTimeframe] = useState('1h')
  const [tradeStyle, setTradeStyle] = useState<'scalp' | 'swing'>('swing')
  const [model, setModel] = useState('ppo')
  const [initialBalance, setInitialBalance] = useState(10000)
  const [isRunning, setIsRunning] = useState(false)
  const [result, setResult] = useState<BacktestResult | null>(null)
  const [report, setReport] = useState<any | null>(null)
  const [strategies, setStrategies] = useState<StrategyDefinition[]>([])
  const [selectedStrategy, setSelectedStrategy] = useState<StrategyDefinition | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.fetchStrategies().then((data) => setStrategies(data.results || [])).catch(() => setStrategies([]))
  }, [])

  const isDateValid = startDate && endDate && new Date(endDate) > new Date(startDate)

  const handleRunBacktest = async () => {
    setIsRunning(true)
    setResult(null)
    setError(null)
    try {
      const res = await fetch('/api/backtest/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          symbol: selectedPair.symbol,
          start_date: startDate,
          end_date: endDate,
          timeframe,
          trade_style: tradeStyle,
          strategy_id: selectedStrategy?.id,
          initial_balance: initialBalance,
        })
      })
      if (res.ok) {
        const data = await res.json()
        if (data.error) {
          setError(data.error)
        } else {
          setResult(data)
          try {
            const reportData = await api.fetchBacktestReport(selectedPair.symbol, timeframe, tradeStyle, startDate, endDate)
            setReport(reportData)
          } catch {
            setReport(null)
          }
        }
      } else {
        const errorData = await res.json().catch(() => null)
        setError(errorData?.detail || errorData?.error || `Backtest failed with status ${res.status}`)
        console.error('Backtest failed:', res.status, errorData)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Network error — is the backend running?')
      console.error('Backtest error:', err)
    } finally {
      setIsRunning(false)
    }
  }

  return (
    <div className="p-6">
      <header className="mb-6">
        <h2 className="text-2xl font-bold text-trading-text">Backtest</h2>
        <p className="text-trading-muted">Test your strategy on historical {selectedPair.symbol} data</p>
      </header>

      <div className="grid grid-cols-12 gap-6">
        {/* Configuration Panel */}
        <div className="col-span-4">
          <div className="card">
            <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
              <Settings size={20} />
              Configuration
            </h3>
            
            <div className="space-y-4">
              {/* Pair Selector */}
              <div>
                <label className="block text-sm text-trading-muted mb-2">Trading Pair</label>
                <select
                  value={selectedPair.symbol}
                  onChange={(e) => {
                    const pair = activePairs.find((p) => p.symbol === e.target.value)
                    if (pair) onPairChange(pair)
                  }}
                  className="input-field w-full"
                >
                  {activePairs.map((pair) => (
                    <option key={pair.symbol} value={pair.symbol}>
                      {pair.symbol} - {pair.nickname || pair.name}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-sm text-trading-muted mb-2">Date Range</label>
                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <label className="text-xs text-trading-muted">Start</label>
                    <input
                      type="date"
                      value={startDate}
                      onChange={(e) => setStartDate(e.target.value)}
                      className="input-field w-full"
                    />
                  </div>
                  <div>
                    <label className="text-xs text-trading-muted">End</label>
                    <input
                      type="date"
                      value={endDate}
                      onChange={(e) => setEndDate(e.target.value)}
                      className="input-field w-full"
                    />
                  </div>
                </div>
              </div>

              <div>
                <label className="block text-sm text-trading-muted mb-2">Timeframe</label>
                <select
                  value={timeframe}
                  onChange={(e) => setTimeframe(e.target.value)}
                  className="input-field w-full"
                >
                  <option value="1m">1 Minute</option>
                  <option value="5m">5 Minutes</option>
                  <option value="15m">15 Minutes</option>
                  <option value="1h">1 Hour</option>
                  <option value="4h">4 Hours</option>
                  <option value="1d">1 Day</option>
                </select>
              </div>

              <div>
                <label className="block text-sm text-trading-muted mb-2">Trade Style</label>
                <select
                  value={tradeStyle}
                  onChange={(e) => setTradeStyle(e.target.value as 'scalp' | 'swing')}
                  className="input-field w-full"
                >
                  <option value="swing">Swing</option>
                  <option value="scalp">Scalp</option>
                </select>
              </div>

              <div>
                <label className="block text-sm text-trading-muted mb-2">Model</label>
                <select
                  value={model}
                  onChange={(e) => setModel(e.target.value)}
                  className="input-field w-full"
                >
                  <option value="ppo">PPO (Proximal Policy Optimization)</option>
                  <option value="sac">SAC (Soft Actor-Critic)</option>
                  <option value="a2c">A2C (Advantage Actor-Critic)</option>
                </select>
              </div>

              <div>
                <label className="block text-sm text-trading-muted mb-2">Initial Balance</label>
                <input
                  type="number"
                  value={initialBalance}
                  onChange={(e) => setInitialBalance(Number(e.target.value))}
                  className="input-field w-full"
                />
              </div>

              <button
                onClick={handleRunBacktest}
                disabled={isRunning || !isDateValid}
                className="w-full btn-buy py-3 flex items-center justify-center gap-2"
              >
                {isRunning ? (
                  <>
                    <div className="animate-spin rounded-full h-5 w-5 border-2 border-white border-t-transparent" />
                    Running...
                  </>
                ) : (
                  <>
                    <Play size={20} />
                    Run Backtest
                  </>
                )}
              </button>

              <div className="mt-6">
                <StrategyCatalog
                  strategies={strategies}
                  onSelectStrategy={setSelectedStrategy}
                  onActivate={async (strategy, mode) => {
                    await api.activateStrategy(strategy.id, mode, true)
                    const data = await api.fetchStrategies()
                    setStrategies(data.results || [])
                    setSelectedStrategy(strategy)
                  }}
                />
                <div className="mt-4">
                  <AutomationTemplateCard strategy={selectedStrategy} />
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Results */}
        <div className="col-span-8">
          {error && (
            <div className="mb-4 p-3 rounded bg-red-500/10 border border-red-500/30 text-red-400 text-sm">
              {error}
            </div>
          )}
          {result ? (
            <>
              {/* Metrics */}
              <div className="grid grid-cols-3 gap-4 mb-6">
                <div className="card text-center">
                  <p className="text-sm text-trading-muted">Total Return</p>
                  <p className={`text-2xl font-bold ${result.totalReturn >= 0 ? 'text-trading-buy' : 'text-trading-sell'}`}>
                    {result.totalReturn >= 0 ? '+' : ''}{result.totalReturn.toFixed(2)}%
                  </p>
                </div>
                <div className="card text-center">
                  <p className="text-sm text-trading-muted">Sharpe Ratio</p>
                  <p className="text-2xl font-bold text-trading-text">{result.sharpeRatio.toFixed(2)}</p>
                </div>
                <div className="card text-center">
                  <p className="text-sm text-trading-muted">Max Drawdown</p>
                  <p className="text-2xl font-bold text-trading-sell">-{result.maxDrawdown.toFixed(2)}%</p>
                </div>
                <div className="card text-center">
                  <p className="text-sm text-trading-muted">Win Rate</p>
                  <p className="text-2xl font-bold text-trading-text">{result.winRate.toFixed(1)}%</p>
                </div>
                <div className="card text-center">
                  <p className="text-sm text-trading-muted">Profit Factor</p>
                  <p className="text-2xl font-bold text-trading-text">{result.profitFactor.toFixed(2)}</p>
                </div>
                <div className="card text-center">
                  <p className="text-sm text-trading-muted">Total Trades</p>
                  <p className="text-2xl font-bold text-trading-text">{result.numTrades}</p>
                </div>
              </div>

              {/* Equity Curve */}
              <div className="card">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-lg font-semibold">Equity Curve</h3>
                  <button className="text-trading-accent hover:text-blue-400 flex items-center gap-2">
                    <Download size={16} />
                    Export
                  </button>
                </div>
                <div className="h-80">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={result.equityCurve}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                      <XAxis 
                        dataKey="time" 
                        tickFormatter={(time) => formatDateOnly(time)}
                        stroke="#94a3b8"
                      />
                      <YAxis stroke="#94a3b8" />
                      <Tooltip 
                        contentStyle={{ backgroundColor: '#1e293b', border: '1px solid #334155' }}
                        labelStyle={{ color: '#94a3b8' }}
                        formatter={(value) => [`$${Number(value).toFixed(2)}`, 'Equity']}
                      />
                      <Line 
                        type="monotone" 
                        dataKey="value" 
                        stroke="#3b82f6" 
                        strokeWidth={2}
                        dot={false}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              </div>

              {report && (
                <div className="card mt-6">
                  <h3 className="text-lg font-semibold mb-4">Breakdown Report</h3>
                  <div className="grid grid-cols-3 gap-4">
                    <div>
                      <p className="text-sm text-trading-muted">Source</p>
                      <p className="text-trading-text font-semibold">{report.sourcePolicy}</p>
                    </div>
                    <div>
                      <p className="text-sm text-trading-muted">Trade Style</p>
                      <p className="text-trading-text font-semibold">{report.tradeStyle}</p>
                    </div>
                    <div>
                      <p className="text-sm text-trading-muted">Session Focus</p>
                      <p className="text-trading-text font-semibold">{report.bestSession}</p>
                    </div>
                  </div>
                  <div className="mt-4 grid grid-cols-2 gap-4">
                    <div className="rounded-lg border border-trading-border p-3">
                      <p className="text-sm text-trading-muted">Source Confidence</p>
                      <p className="text-xl font-bold text-trading-text">{report.sourceConfidence}%</p>
                    </div>
                    <div className="rounded-lg border border-trading-border p-3">
                      <p className="text-sm text-trading-muted">Regime Fit</p>
                      <p className="text-xl font-bold text-trading-text">{report.regimeFit}%</p>
                    </div>
                  </div>
                  <div className="mt-6 grid grid-cols-2 gap-4">
                    <div className="rounded-lg border border-trading-border p-3">
                      <p className="mb-2 text-sm font-semibold text-trading-text">Session Breakdown</p>
                      <div className="space-y-2 text-sm">
                        {(report.sessionBreakdown || []).map((row: any) => (
                          <div key={row.session} className="flex items-center justify-between">
                            <span className="text-trading-muted">{row.session}</span>
                            <span className="text-trading-text">
                              {row.trades > 0
                                ? `${row.trades} trades · ${row.winRate}% · ${row.netPnl >= 0 ? '+' : ''}${row.netPnl}`
                                : `${row.barsObserved || 0} bars observed`}
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                    <div className="rounded-lg border border-trading-border p-3">
                      <p className="mb-2 text-sm font-semibold text-trading-text">Source Breakdown</p>
                      <div className="space-y-2 text-sm">
                        {(report.sourceBreakdown || []).map((row: any) => (
                          <div key={row.source} className="flex items-center justify-between">
                            <span className="text-trading-muted">{row.source}</span>
                            <span className="text-trading-text">{row.weight}% · conf {row.confidence}%</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </>
          ) : (
            <div className="card h-96 flex items-center justify-center">
              <div className="text-center">
                <Calendar size={48} className="mx-auto text-trading-muted mb-4" />
                <p className="text-trading-muted">Configure and run a backtest to see results</p>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export default Backtest
