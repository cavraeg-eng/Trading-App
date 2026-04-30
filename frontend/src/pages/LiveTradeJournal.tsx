import { useCallback, useEffect, useMemo, useState } from 'react'
import { ArrowDownUp, BookOpen, CalendarDays, ChevronLeft, ChevronRight, Download, Filter, RefreshCw } from 'lucide-react'
import api from '../lib/api'
import { formatDateTimeWithZone } from '../lib/time'

type LedgerEntry = Awaited<ReturnType<typeof api.fetchTradeLedger>>['entries'][number]
type LedgerMetrics = Awaited<ReturnType<typeof api.fetchLedgerMetrics>>
type StatusFilter = 'all' | 'open' | 'filled' | 'closed' | 'cancelled' | 'rejected'
type OutcomeFilter = 'all' | 'TP_HIT' | 'SL_HIT' | 'WIN' | 'LOSS' | 'BREAKEVEN'
type RangeFilter = 'all' | '7d' | '30d' | '90d'

const PAGE_SIZE = 25

function formatOptionalPrice(value?: number | null) {
  if (value == null || !Number.isFinite(value)) return '—'
  return value.toFixed(Math.abs(value) < 10 ? 5 : 2)
}

function formatCurrency(value: number) {
  return `${value >= 0 ? '+' : '-'}$${Math.abs(value).toFixed(2)}`
}

function formatDate(value?: string | null) {
  if (!value) return '—'
  const parsed = Date.parse(value)
  if (!Number.isFinite(parsed)) return value
  return formatDateTimeWithZone(parsed)
}

function isWithinRange(entry: LedgerEntry, range: RangeFilter) {
  if (range === 'all') return true
  const reference = Date.parse(entry.closed_at || entry.opened_at || entry.updated_at)
  if (!Number.isFinite(reference)) return true
  const days = range === '7d' ? 7 : range === '30d' ? 30 : 90
  return reference >= Date.now() - days * 24 * 60 * 60 * 1000
}

function matchesSearch(entry: LedgerEntry, search: string) {
  const needle = search.trim().toLowerCase()
  if (!needle) return true
  return [
    entry.symbol,
    entry.broker_id,
    entry.source_type,
    entry.source_id,
    entry.status,
    entry.outcome,
    entry.signal_id,
  ].some((value) => String(value ?? '').toLowerCase().includes(needle))
}

function outcomeTone(outcome?: string | null) {
  if (outcome === 'TP_HIT' || outcome === 'WIN') return 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20'
  if (outcome === 'SL_HIT' || outcome === 'LOSS') return 'text-red-400 bg-red-500/10 border-red-500/20'
  if (outcome === 'BREAKEVEN') return 'text-amber-300 bg-amber-500/10 border-amber-500/20'
  return 'text-slate-400 bg-slate-500/10 border-slate-500/20'
}

function metricValue(value: number | null | undefined, suffix = '') {
  return value == null ? '—' : `${value.toFixed(2)}${suffix}`
}

export default function LiveTradeJournal() {
  const [entries, setEntries] = useState<LedgerEntry[]>([])
  const [metrics, setMetrics] = useState<LedgerMetrics | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [symbolFilter, setSymbolFilter] = useState('all')
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all')
  const [outcomeFilter, setOutcomeFilter] = useState<OutcomeFilter>('all')
  const [rangeFilter, setRangeFilter] = useState<RangeFilter>('30d')
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(0)

  const refresh = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [ledger, ledgerMetrics] = await Promise.all([
        api.fetchTradeLedger(undefined, 500),
        api.fetchLedgerMetrics(),
      ])
      setEntries(ledger.entries)
      setMetrics(ledgerMetrics)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load live trade journal')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    refresh()
  }, [refresh])

  useEffect(() => {
    setPage(0)
  }, [outcomeFilter, rangeFilter, search, statusFilter, symbolFilter])

  const knownSymbols = useMemo(
    () => Array.from(new Set(entries.map((entry) => entry.symbol))).sort(),
    [entries],
  )

  const filteredEntries = useMemo(() => entries.filter((entry) => {
    if (symbolFilter !== 'all' && entry.symbol !== symbolFilter) return false
    if (statusFilter !== 'all' && entry.status !== statusFilter) return false
    if (outcomeFilter !== 'all' && entry.outcome !== outcomeFilter) return false
    if (!isWithinRange(entry, rangeFilter)) return false
    if (!matchesSearch(entry, search)) return false
    return true
  }), [entries, outcomeFilter, rangeFilter, search, statusFilter, symbolFilter])

  const pageCount = Math.max(1, Math.ceil(filteredEntries.length / PAGE_SIZE))
  const pageEntries = filteredEntries.slice(page * PAGE_SIZE, page * PAGE_SIZE + PAGE_SIZE)
  const pageStart = filteredEntries.length === 0 ? 0 : page * PAGE_SIZE + 1
  const pageEnd = Math.min(filteredEntries.length, page * PAGE_SIZE + pageEntries.length)
  const exportHref = useMemo(() => api.buildTradeLedgerExportUrl({
    symbol: symbolFilter !== 'all' ? symbolFilter : undefined,
    status: statusFilter !== 'all' ? statusFilter : undefined,
    count: 2000,
  }), [statusFilter, symbolFilter])

  return (
    <div className="mx-auto max-w-7xl p-6">
      <div className="mb-6 flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-trading-text">Live Trade Journal</h1>
          <p className="text-trading-muted">Broker-reconciled orders, positions, outcomes, R multiples, and MFE/MAE from the unified ledger.</p>
        </div>
        <div className="flex gap-2">
          <a
            href={exportHref}
            className="inline-flex items-center justify-center gap-2 rounded-lg border border-trading-accent/30 px-4 py-2 text-sm font-semibold text-trading-accent hover:bg-trading-accent/10"
          >
            <Download size={16} />
            Export CSV
          </a>
          <button
            onClick={() => void refresh()}
            disabled={loading}
            className="inline-flex items-center justify-center gap-2 rounded-lg border border-trading-accent/30 px-4 py-2 text-sm font-semibold text-trading-accent hover:bg-trading-accent/10 disabled:opacity-50"
          >
            <RefreshCw size={16} className={loading ? 'animate-spin' : ''} />
            Refresh
          </button>
        </div>
      </div>

      <div className="mb-6 grid grid-cols-2 gap-3 lg:grid-cols-6">
        <div className="card">
          <div className="text-xs text-trading-muted">Realized P&L</div>
          <div className={`text-xl font-bold ${metrics && metrics.realized_pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
            {metrics ? formatCurrency(metrics.realized_pnl) : '—'}
          </div>
        </div>
        <div className="card">
          <div className="text-xs text-trading-muted">Open P&L</div>
          <div className={`text-xl font-bold ${metrics && metrics.unrealized_pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
            {metrics ? formatCurrency(metrics.unrealized_pnl) : '—'}
          </div>
        </div>
        <div className="card">
          <div className="text-xs text-trading-muted">Win Rate</div>
          <div className="text-xl font-bold text-trading-text">{metrics ? `${metrics.win_rate.toFixed(1)}%` : '—'}</div>
        </div>
        <div className="card">
          <div className="text-xs text-trading-muted">Avg R</div>
          <div className="text-xl font-bold text-trading-text">{metricValue(metrics?.avg_r_multiple, 'R')}</div>
        </div>
        <div className="card">
          <div className="text-xs text-trading-muted">MFE / MAE</div>
          <div className="text-xl font-bold text-trading-text">{metricValue(metrics?.avg_mfe)} / {metricValue(metrics?.avg_mae)}</div>
        </div>
        <div className="card">
          <div className="text-xs text-trading-muted">Ledger</div>
          <div className="text-xl font-bold text-trading-text">{metrics ? `${metrics.open_entries} / ${metrics.closed_entries}` : '—'}</div>
          <div className="text-xs text-trading-muted">open / closed</div>
        </div>
      </div>

      <div className="card mb-6">
        <div className="mb-3 flex items-center gap-2">
          <Filter size={18} className="text-trading-accent" />
          <h2 className="text-lg font-semibold text-trading-text">Ledger Filters</h2>
        </div>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-6">
          <input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search symbol, broker, id..."
            className="input-field"
          />
          <select value={symbolFilter} onChange={(event) => setSymbolFilter(event.target.value)} className="input-field">
            <option value="all">All Symbols</option>
            {knownSymbols.map((symbol) => <option key={symbol} value={symbol}>{symbol}</option>)}
          </select>
          <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value as StatusFilter)} className="input-field">
            <option value="all">All Statuses</option>
            <option value="open">Open</option>
            <option value="filled">Filled</option>
            <option value="closed">Closed</option>
            <option value="cancelled">Cancelled</option>
            <option value="rejected">Rejected</option>
          </select>
          <select value={outcomeFilter} onChange={(event) => setOutcomeFilter(event.target.value as OutcomeFilter)} className="input-field">
            <option value="all">All Outcomes</option>
            <option value="TP_HIT">TP Hit</option>
            <option value="SL_HIT">SL Hit</option>
            <option value="WIN">Win</option>
            <option value="LOSS">Loss</option>
            <option value="BREAKEVEN">Breakeven</option>
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
          <div className="rounded border border-trading-border bg-trading-bg px-3 py-2 text-sm text-trading-muted">
            {loading ? 'Loading…' : `${pageStart}-${pageEnd} of ${filteredEntries.length}`}
          </div>
        </div>
      </div>

      <div className="card">
        <div className="mb-4 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-2">
            <BookOpen size={18} className="text-trading-accent" />
            <div>
              <h2 className="text-lg font-semibold text-trading-text">Broker Ledger Entries</h2>
              <p className="text-sm text-trading-muted">Source-normalized trades, orders, and positions.</p>
            </div>
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
            <span>Page {Math.min(page + 1, pageCount)} / {pageCount}</span>
            <button
              onClick={() => setPage((value) => (value + 1 < pageCount ? value + 1 : value))}
              disabled={page + 1 >= pageCount || loading}
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
                <th className="px-3 py-2 font-medium">Updated</th>
                <th className="px-3 py-2 font-medium">Source</th>
                <th className="px-3 py-2 font-medium">Symbol</th>
                <th className="px-3 py-2 font-medium">Status</th>
                <th className="px-3 py-2 font-medium">Entry / Current</th>
                <th className="px-3 py-2 font-medium">SL / TP</th>
                <th className="px-3 py-2 font-medium text-right">R</th>
                <th className="px-3 py-2 font-medium text-right">MFE / MAE</th>
                <th className="px-3 py-2 font-medium text-right">P&L</th>
              </tr>
            </thead>
            <tbody>
              {!loading && pageEntries.length === 0 && (
                <tr>
                  <td colSpan={9} className="px-3 py-10 text-center text-trading-muted">No ledger entries match the current filters.</td>
                </tr>
              )}
              {pageEntries.map((entry) => (
                <tr key={entry.ledger_id} className="border-b border-trading-border/60 last:border-b-0">
                  <td className="px-3 py-3 text-trading-muted">
                    <div>{formatDate(entry.updated_at)}</div>
                    <div className="text-xs">Opened: {formatDate(entry.opened_at)}</div>
                  </td>
                  <td className="px-3 py-3 text-trading-muted">
                    <div className="font-semibold text-trading-text">{entry.broker_id}</div>
                    <div className="text-xs">{entry.source_type} · {entry.source_id}</div>
                  </td>
                  <td className="px-3 py-3">
                    <div className="font-semibold text-trading-text">{entry.symbol}</div>
                    <div className={`text-xs ${entry.side === 'buy' || entry.side === 'long' ? 'text-emerald-400' : 'text-red-400'}`}>{entry.side}</div>
                    <div className="text-xs text-trading-muted">{entry.quantity} units</div>
                  </td>
                  <td className="px-3 py-3">
                    <div className="font-medium text-trading-text">{entry.status.replace(/_/g, ' ')}</div>
                    <span className={`mt-1 inline-flex rounded border px-1.5 py-0.5 text-xs ${outcomeTone(entry.outcome)}`}>
                      {entry.outcome ?? 'unresolved'}
                    </span>
                  </td>
                  <td className="px-3 py-3 text-trading-muted tabular-nums">
                    <div>{formatOptionalPrice(entry.entry_price)}</div>
                    <div className="text-trading-text">{formatOptionalPrice(entry.current_price ?? entry.exit_price)}</div>
                  </td>
                  <td className="px-3 py-3 text-trading-muted tabular-nums">
                    <div>SL: <span className="text-red-400">{formatOptionalPrice(entry.stop_loss)}</span></div>
                    <div>TP: <span className="text-emerald-400">{formatOptionalPrice(entry.take_profit_1)}</span> / <span className="text-emerald-400">{formatOptionalPrice(entry.take_profit_2)}</span> / <span className="text-emerald-400">{formatOptionalPrice(entry.take_profit_3)}</span></div>
                  </td>
                  <td className="px-3 py-3 text-right text-trading-muted tabular-nums">
                    {entry.r_multiple != null ? `${entry.r_multiple.toFixed(2)}R` : '—'}
                  </td>
                  <td className="px-3 py-3 text-right text-trading-muted tabular-nums">
                    {entry.mfe != null ? entry.mfe.toFixed(2) : '—'} / {entry.mae != null ? entry.mae.toFixed(2) : '—'}
                  </td>
                  <td className={`px-3 py-3 text-right font-semibold tabular-nums ${(entry.realized_pnl || entry.unrealized_pnl) >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                    {formatCurrency(entry.closed_at ? entry.realized_pnl : entry.unrealized_pnl)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {metrics && metrics.by_symbol.length > 0 && (
          <div className="mt-6 border-t border-trading-border pt-4">
            <div className="mb-3 flex items-center gap-2">
              <ArrowDownUp size={16} className="text-trading-accent" />
              <h3 className="font-semibold text-trading-text">Symbol Performance</h3>
            </div>
            <div className="grid grid-cols-1 gap-2 md:grid-cols-2 xl:grid-cols-4">
              {metrics.by_symbol.slice(0, 8).map((item) => (
                <div key={item.symbol} className="rounded-lg border border-trading-border bg-trading-bg px-3 py-2">
                  <div className="flex items-center justify-between">
                    <span className="font-semibold text-trading-text">{item.symbol}</span>
                    <span className={`font-semibold ${item.realized_pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>{formatCurrency(item.realized_pnl)}</span>
                  </div>
                  <div className="mt-1 text-xs text-trading-muted">{item.total} closed · {item.win_rate.toFixed(1)}% win</div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}