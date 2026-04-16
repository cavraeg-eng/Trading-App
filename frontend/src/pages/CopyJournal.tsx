import { useCallback, useEffect, useMemo, useState } from 'react'
import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { ArrowDownUp, BookText, CalendarDays, ChevronLeft, ChevronRight, Download, Filter } from 'lucide-react'
import api from '../lib/api'
import { formatDateTimeWithZone } from '../lib/time'
import type { CopyTradeHistoryResponse, CopyTradePosition, CopyTradeStats } from '../types'

type DirectionFilter = 'ALL' | 'BUY' | 'SELL'
type RangeFilter = 'all' | '7d' | '30d' | '90d'
type SortField = 'closed_at' | 'created_at' | 'symbol' | 'direction' | 'status' | 'realized_pnl' | 'confidence'
type SortDirection = 'asc' | 'desc'

const PAGE_SIZE = 20

const statusOptions = [
  { value: 'all', label: 'All Outcomes' },
  { value: 'closed_tp3', label: 'TP3' },
  { value: 'closed_sl', label: 'Stop Loss' },
  { value: 'closed_manual', label: 'Manual Close' },
]

const sortOptions: Array<{ value: SortField; label: string }> = [
  { value: 'closed_at', label: 'Closed Time' },
  { value: 'created_at', label: 'Opened Time' },
  { value: 'realized_pnl', label: 'Realized P&L' },
  { value: 'confidence', label: 'Confidence' },
  { value: 'symbol', label: 'Symbol' },
  { value: 'status', label: 'Status' },
]

const formatDuration = (seconds?: number | null) => {
  if (seconds == null) return '—'
  if (seconds < 60) return `${Math.round(seconds)}s`
  if (seconds < 3600) return `${Math.round(seconds / 60)}m`
  if (seconds < 86400) return `${(seconds / 3600).toFixed(1)}h`
  return `${(seconds / 86400).toFixed(1)}d`
}

const formatClosedAt = (timestamp?: number | null) => {
  if (!timestamp) return '—'
  return formatDateTimeWithZone(timestamp * 1000)
}

const formatOpenedAt = (timestamp?: number | null) => {
  if (!timestamp) return '—'
  return formatDateTimeWithZone(timestamp * 1000)
}

const calcFromTs = (range: RangeFilter) => {
  const nowSeconds = Math.floor(Date.now() / 1000)
  if (range === '7d') return nowSeconds - 7 * 24 * 60 * 60
  if (range === '30d') return nowSeconds - 30 * 24 * 60 * 60
  if (range === '90d') return nowSeconds - 90 * 24 * 60 * 60
  return undefined
}

const calcRMultiple = (trade: CopyTradePosition) => {
  if (trade.initial_stop_loss == null) return null
  const unitRisk = Math.abs(trade.entry_price - trade.initial_stop_loss)
  if (unitRisk <= 0 || trade.quantity <= 0) return null
  return trade.realized_pnl / (unitRisk * trade.quantity)
}

export default function CopyJournal() {
  const [history, setHistory] = useState<CopyTradePosition[]>([])
  const [stats, setStats] = useState<CopyTradeStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [symbolFilter, setSymbolFilter] = useState('all')
  const [directionFilter, setDirectionFilter] = useState<DirectionFilter>('ALL')
  const [statusFilter, setStatusFilter] = useState('all')
  const [rangeFilter, setRangeFilter] = useState<RangeFilter>('30d')
  const [sortBy, setSortBy] = useState<SortField>('closed_at')
  const [sortDir, setSortDir] = useState<SortDirection>('desc')
  const [page, setPage] = useState(0)
  const [historyMeta, setHistoryMeta] = useState<Pick<CopyTradeHistoryResponse, 'total' | 'limit' | 'offset'>>({})

  const refresh = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const symbol = symbolFilter !== 'all' ? symbolFilter : undefined
      const direction = directionFilter !== 'ALL' ? directionFilter : undefined
      const status = statusFilter !== 'all' ? statusFilter : undefined
      const fromTs = calcFromTs(rangeFilter)
      const offset = page * PAGE_SIZE
      const [statsRes, historyRes] = await Promise.all([
        api.fetchCopyStats(),
        api.fetchCopyHistoryFiltered({
          limit: PAGE_SIZE,
          offset,
          symbol,
          direction,
          status,
          fromTs,
          sortBy,
          sortDir,
        }),
      ])
      setStats(statsRes)
      setHistory(historyRes.history || [])
      setHistoryMeta({
        total: historyRes.total ?? historyRes.count,
        limit: historyRes.limit ?? PAGE_SIZE,
        offset: historyRes.offset ?? offset,
      })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load copy journal')
    } finally {
      setLoading(false)
    }
  }, [directionFilter, page, rangeFilter, sortBy, sortDir, statusFilter, symbolFilter])

  useEffect(() => {
    refresh()
  }, [refresh])

  useEffect(() => {
    setPage(0)
  }, [directionFilter, rangeFilter, sortBy, sortDir, statusFilter, symbolFilter])

  const knownSymbols = useMemo(() => {
    const fromStats = stats?.symbol_breakdown?.map((item) => item.symbol) ?? []
    const fromHistory = history.map((trade) => trade.symbol)
    return Array.from(new Set([...fromStats, ...fromHistory])).sort()
  }, [history, stats])

  const exportHref = useMemo(() => {
    const params = new URLSearchParams()
    params.set('limit', '1000')
    if (symbolFilter !== 'all') params.set('symbol', symbolFilter)
    if (directionFilter !== 'ALL') params.set('direction', directionFilter)
    if (statusFilter !== 'all') params.set('status', statusFilter)
    const fromTs = calcFromTs(rangeFilter)
    if (fromTs != null) params.set('from_ts', String(fromTs))
    return `/api/copy-trading/history/export?${params.toString()}`
  }, [directionFilter, rangeFilter, statusFilter, symbolFilter])

  const totalItems = historyMeta.total ?? history.length
  const totalPages = Math.max(1, Math.ceil(totalItems / PAGE_SIZE))
  const pageStart = totalItems === 0 ? 0 : page * PAGE_SIZE + 1
  const pageEnd = Math.min(totalItems, page * PAGE_SIZE + history.length)

  return (
    <div className="mx-auto max-w-7xl p-6">
      <div className="mb-6 flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-trading-text">Copy Trade Journal</h1>
          <p className="text-trading-muted">Review closed copy trades with filters, analytics, and export controls.</p>
        </div>
        <a
          href={exportHref}
          className="inline-flex items-center justify-center gap-2 rounded-lg border border-trading-accent/30 px-4 py-2 text-sm font-semibold text-trading-accent hover:bg-trading-accent/10"
        >
          <Download size={16} />
          Export Filtered CSV
        </a>
      </div>

      <div className="mb-6 grid grid-cols-1 gap-4 xl:grid-cols-[1.4fr_1fr]">
        <div className="card">
          <div className="mb-3 flex items-center gap-2">
            <BookText size={18} className="text-trading-accent" />
            <h2 className="text-lg font-semibold text-trading-text">Performance Snapshot</h2>
          </div>
          {stats ? (
            <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
              <div className="rounded-lg border border-trading-border bg-trading-bg px-3 py-2">
                <div className="text-xs text-trading-muted">Realized P&L</div>
                <div className={`text-lg font-bold ${stats.total_pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                  {stats.total_pnl >= 0 ? '+' : ''}${stats.total_pnl.toFixed(2)}
                </div>
              </div>
              <div className="rounded-lg border border-trading-border bg-trading-bg px-3 py-2">
                <div className="text-xs text-trading-muted">Expectancy</div>
                <div className={`text-lg font-bold ${stats.expectancy >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                  {stats.expectancy >= 0 ? '+' : ''}${stats.expectancy.toFixed(2)}
                </div>
              </div>
              <div className="rounded-lg border border-trading-border bg-trading-bg px-3 py-2">
                <div className="text-xs text-trading-muted">Profit Factor</div>
                <div className="text-lg font-bold text-trading-text">{stats.profit_factor != null ? stats.profit_factor.toFixed(2) : '∞'}</div>
              </div>
              <div className="rounded-lg border border-trading-border bg-trading-bg px-3 py-2">
                <div className="text-xs text-trading-muted">Avg R</div>
                <div className="text-lg font-bold text-trading-text">{stats.avg_r_multiple != null ? `${stats.avg_r_multiple.toFixed(2)}R` : '—'}</div>
              </div>
              <div className="rounded-lg border border-trading-border bg-trading-bg px-3 py-2">
                <div className="text-xs text-trading-muted">Max Drawdown</div>
                <div className="text-lg font-bold text-trading-text">${stats.max_drawdown.toFixed(2)}</div>
              </div>
              <div className="rounded-lg border border-trading-border bg-trading-bg px-3 py-2">
                <div className="text-xs text-trading-muted">Win Rate</div>
                <div className="text-lg font-bold text-trading-text">{stats.win_rate.toFixed(1)}%</div>
              </div>
              <div className="rounded-lg border border-trading-border bg-trading-bg px-3 py-2">
                <div className="text-xs text-trading-muted">Loss Streak</div>
                <div className="text-lg font-bold text-trading-text">{stats.current_loss_streak} / {stats.max_loss_streak}</div>
              </div>
              <div className="rounded-lg border border-trading-border bg-trading-bg px-3 py-2">
                <div className="text-xs text-trading-muted">Avg Hold</div>
                <div className="text-lg font-bold text-trading-text">{formatDuration(stats.avg_hold_seconds)}</div>
              </div>
            </div>
          ) : (
            <p className="text-sm text-trading-muted">Loading performance snapshot…</p>
          )}
        </div>

        <div className="card">
          <div className="mb-3 flex items-center gap-2">
            <ArrowDownUp size={18} className="text-trading-accent" />
            <h2 className="text-lg font-semibold text-trading-text">Equity Curve</h2>
          </div>
          <div className="h-56">
            {stats && stats.equity_curve.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={stats.equity_curve}>
                  <defs>
                    <linearGradient id="journalEquityGradient" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#38bdf8" stopOpacity={0.35} />
                      <stop offset="95%" stopColor="#38bdf8" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <XAxis dataKey="symbol" tick={{ fill: '#94a3b8', fontSize: 11 }} />
                  <YAxis tick={{ fill: '#94a3b8', fontSize: 11 }} />
                  <Tooltip
                    contentStyle={{ background: '#0f172a', border: '1px solid #334155', borderRadius: 8, fontSize: 12 }}
                    formatter={(value: number) => [`$${value.toFixed(2)}`, 'Cumulative P&L']}
                  />
                  <Area type="monotone" dataKey="cumulative_pnl" stroke="#38bdf8" fill="url(#journalEquityGradient)" strokeWidth={2} />
                </AreaChart>
              </ResponsiveContainer>
            ) : (
              <div className="flex h-full items-center justify-center text-sm text-trading-muted">No closed trades yet</div>
            )}
          </div>
        </div>
      </div>

      <div className="card mb-6">
        <div className="mb-3 flex items-center gap-2">
          <Filter size={18} className="text-trading-accent" />
          <h2 className="text-lg font-semibold text-trading-text">Journal Filters</h2>
        </div>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-6">
          <select value={symbolFilter} onChange={(event) => setSymbolFilter(event.target.value)} className="input-field">
            <option value="all">All Symbols</option>
            {knownSymbols.map((symbol) => <option key={symbol} value={symbol}>{symbol}</option>)}
          </select>
          <select value={directionFilter} onChange={(event) => setDirectionFilter(event.target.value as DirectionFilter)} className="input-field">
            <option value="ALL">All Directions</option>
            <option value="BUY">BUY</option>
            <option value="SELL">SELL</option>
          </select>
          <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)} className="input-field">
            {statusOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
          </select>
          <div className="flex items-center gap-2 rounded border border-trading-border bg-trading-bg px-3 py-2">
            <CalendarDays size={16} className="text-trading-muted" />
            <select value={rangeFilter} onChange={(event) => setRangeFilter(event.target.value as RangeFilter)} className="w-full bg-transparent text-trading-text outline-none">
              <option value="all">All Time</option>
              <option value="7d">Last 7 Days</option>
              <option value="30d">Last 30 Days</option>
              <option value="90d">Last 90 Days</option>
            </select>
          </div>
          <select value={sortBy} onChange={(event) => setSortBy(event.target.value as SortField)} className="input-field">
            {sortOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
          </select>
          <select value={sortDir} onChange={(event) => setSortDir(event.target.value as SortDirection)} className="input-field">
            <option value="desc">Descending</option>
            <option value="asc">Ascending</option>
          </select>
        </div>
      </div>

      <div className="card">
        <div className="mb-4 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h2 className="text-lg font-semibold text-trading-text">Closed Trades</h2>
            <p className="text-sm text-trading-muted">
              {loading ? 'Loading journal…' : `${pageStart}-${pageEnd} of ${totalItems} filtered trades`}
            </p>
          </div>
          <div className="flex items-center gap-2 text-sm text-trading-muted">
            <button
              onClick={() => setPage((value) => Math.max(0, value - 1))}
              disabled={page === 0 || loading}
              className="inline-flex items-center gap-1 rounded border border-trading-border px-3 py-1.5 disabled:opacity-50"
            >
              <ChevronLeft size={14} />
              Prev
            </button>
            <span>Page {Math.min(page + 1, totalPages)} / {totalPages}</span>
            <button
              onClick={() => setPage((value) => (value + 1 < totalPages ? value + 1 : value))}
              disabled={page + 1 >= totalPages || loading}
              className="inline-flex items-center gap-1 rounded border border-trading-border px-3 py-1.5 disabled:opacity-50"
            >
              Next
              <ChevronRight size={14} />
            </button>
          </div>
        </div>

        {error && (
          <div className="mb-4 rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">
            {error}
          </div>
        )}

        <div className="overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <thead>
              <tr className="border-b border-trading-border text-trading-muted">
                <th className="px-3 py-2 font-medium">Closed</th>
                <th className="px-3 py-2 font-medium">Symbol</th>
                <th className="px-3 py-2 font-medium">Setup</th>
                <th className="px-3 py-2 font-medium">Lifecycle</th>
                <th className="px-3 py-2 font-medium">Confidence</th>
                <th className="px-3 py-2 font-medium">Duration</th>
                <th className="px-3 py-2 font-medium text-right">R</th>
                <th className="px-3 py-2 font-medium text-right">Realized P&L</th>
              </tr>
            </thead>
            <tbody>
              {!loading && history.length === 0 && (
                <tr>
                  <td colSpan={8} className="px-3 py-10 text-center text-trading-muted">No trades match the current filters.</td>
                </tr>
              )}
              {history.map((trade) => {
                const rMultiple = calcRMultiple(trade)
                return (
                  <tr key={trade.copy_trade_id} className="border-b border-trading-border/60 last:border-b-0">
                    <td className="px-3 py-3 text-trading-muted">
                      <div>Opened: {formatOpenedAt(trade.created_at)}</div>
                      <div>Closed: {formatClosedAt(trade.closed_at)}</div>
                    </td>
                    <td className="px-3 py-3">
                      <div className="font-semibold text-trading-text">{trade.symbol}</div>
                      <div className={`text-xs ${trade.direction === 'BUY' ? 'text-emerald-400' : 'text-red-400'}`}>{trade.direction}</div>
                    </td>
                    <td className="px-3 py-3 text-trading-muted">
                      <div>{trade.quantity.toFixed(2)} lots @ {trade.entry_price.toFixed(trade.entry_price < 10 ? 4 : 2)}</div>
                      <div className="text-xs">{trade.timeframe} · {trade.trade_style}</div>
                    </td>
                    <td className="px-3 py-3 text-trading-muted">
                      <div className="font-medium text-trading-text">{trade.status.replace(/_/g, ' ')}</div>
                      <div className="text-xs">{trade.partial_exit_count ?? 0} partials</div>
                    </td>
                    <td className="px-3 py-3 text-trading-text">{trade.confidence}%</td>
                    <td className="px-3 py-3 text-trading-muted">{formatDuration(trade.holding_seconds)}</td>
                    <td className="px-3 py-3 text-right text-trading-muted">{rMultiple != null ? `${rMultiple.toFixed(2)}R` : '—'}</td>
                    <td className={`px-3 py-3 text-right font-semibold ${trade.realized_pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                      {trade.realized_pnl >= 0 ? '+' : ''}${trade.realized_pnl.toFixed(2)}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}