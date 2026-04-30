import { useEffect, useMemo, useRef, useState } from 'react'
import {
  AlertTriangle,
  ArrowRight,
  Bell,
  BookmarkPlus,
  Bot,
  ChevronDown,
  ChevronUp,
  Download,
  LayoutDashboard,
  LineChart,
  MoreHorizontal,
  Play,
  Plus,
  RefreshCw,
  Search,
  SlidersHorizontal,
  Sparkles,
} from 'lucide-react'
import ScannerBuilder from '../components/ScannerBuilder'
import ScannerPresets from '../components/ScannerPresets'
import { DataSourceBadge } from '../components/DataSourceBadge'
import { FreshnessPill } from '../components/FreshnessPill'
import { SimpleToastContainer, useSimpleToast } from '../components/AlertToast'
import { useScanner } from '../hooks/useScanner'
import { ALL_FOREX_PAIRS } from '../config/forexPairs'
import type { ForexPair, ScannerTimeframe } from '../types'

interface ScannerProps {
  onPairChange?: (pair: ForexPair) => void
  onOpenDashboard?: () => void
  onOpenLiveTrading?: () => void
  onOpenBacktest?: () => void
  onAddToWatchlist?: (pair: ForexPair) => void
  activeWatchlistSymbols?: string[]
  recentPairs?: ForexPair[]
}

const CATEGORY_OPTIONS: Array<{ value: 'all' | ForexPair['category']; label: string }> = [
  { value: 'all', label: 'All markets' },
  { value: 'major', label: 'Majors' },
  { value: 'minor', label: 'Minors' },
  { value: 'exotic', label: 'Exotics' },
  { value: 'crypto', label: 'Crypto' },
  { value: 'commodity', label: 'Commodities' },
  { value: 'index', label: 'Indices' },
]

const SORT_OPTIONS = [
  { value: 'opportunity', label: 'Opportunity' },
  { value: 'score', label: 'Match score' },
  { value: 'symbol', label: 'Symbol' },
  { value: 'volume', label: 'Volume ratio' },
] as const

type SortOption = (typeof SORT_OPTIONS)[number]['value']

function signalBg(signal?: string) {
  const s = (signal || '').toUpperCase()
  if (s === 'BUY') return 'bg-trading-buy/15 text-emerald-300 border-trading-buy/30'
  if (s === 'SELL') return 'bg-trading-sell/15 text-red-300 border-trading-sell/30'
  return 'bg-slate-500/10 text-slate-400 border-slate-500/20'
}

function scoreBar(score: number) {
  if (score >= 0.8) return 'bg-trading-buy'
  if (score >= 0.6) return 'bg-yellow-500'
  return 'bg-trading-sell'
}

function toCsv(results: Array<Array<string | number | undefined>>) {
  return results
    .map((row) => row.map((cell) => `"${String(cell).split('"').join('""')}"`).join(','))
    .join('\n')
}

function downloadResults(
  results: Array<{
    symbol: string
    signal?: string
    score: number
    opportunity_score?: number
    confidence?: number
    timeframe?: string
    trade_style?: string
    reason?: string
  }>
) {
  const rows = [
    ['Symbol', 'Signal', 'Score', 'Opportunity', 'Confidence', 'Timeframe', 'Trade Style', 'Reason'],
    ...results.map((r) => [r.symbol, r.signal, r.score, r.opportunity_score, r.confidence, r.timeframe, r.trade_style, r.reason]),
  ]
  const blob = new Blob([toCsv(rows)], { type: 'text/csv;charset=utf-8;' })
  const link = document.createElement('a')
  link.href = URL.createObjectURL(blob)
  link.download = `scanner-results-${Date.now()}.csv`
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
}

function conditionSummaryText(
  conditions: Array<{ indicator: string; operator: string; value: number; value2?: number; compare_indicator?: string }>
) {
  return conditions
    .slice(0, 3)
    .map((c) => {
      if (c.compare_indicator) return `${c.indicator} ${c.operator} ${c.compare_indicator}`
      if (c.operator === 'between') return `${c.indicator} ${c.value}–${c.value2 ?? '?'}`
      return `${c.indicator} ${c.operator} ${c.value}`
    })
    .join(', ') + (conditions.length > 3 ? ` +${conditions.length - 3} more` : '')
}

export default function Scanner({
  onPairChange,
  onOpenDashboard,
  onOpenLiveTrading,
  onOpenBacktest,
  onAddToWatchlist,
  activeWatchlistSymbols,
  recentPairs,
}: ScannerProps) {
  const [categoryFilter, setCategoryFilter] = useState<'all' | ForexPair['category']>('all')
  const [sortBy, setSortBy] = useState<SortOption>('opportunity')
  const [saveName, setSaveName] = useState('')
  const [showSaveDialog, setShowSaveDialog] = useState(false)

  // Layout state
  const [configExpanded, setConfigExpanded] = useState(true)
  const [configTab, setConfigTab] = useState<'builder' | 'presets'>('presets')
  const [openMenuId, setOpenMenuId] = useState<string | null>(null)
  const [expandedIndicators, setExpandedIndicators] = useState<Set<string>>(new Set())
  const [activeScannerKey, setActiveScannerKey] = useState<string>('custom')
  const menuRef = useRef<HTMLDivElement>(null)

  const { toasts, showToast, dismissToast } = useSimpleToast()

  const filteredUniverse = useMemo(
    () => (categoryFilter === 'all' ? ALL_FOREX_PAIRS : ALL_FOREX_PAIRS.filter((p) => p.category === categoryFilter)),
    [categoryFilter]
  )

  const {
    config,
    selectedPairs,
    results,
    totalScanned,
    loading,
    error,
    warnings,
    presets,
    savedScanners,
    loadingMetadata,
    loadingSaved,
    supportedIndicators,
    summary,
    hasRun,
    lastRunAt,
    groups,
    setGroups,
    setLogic,
    setSelectedPairs,
    setScannerName,
    setTradeStyle,
    setTimeframe,
    applyPreset,
    loadSavedScanner,
    runScan,
    saveScanner,
    deleteSavedScanner,
    armScannerAlert,
    addGroup,
    removeGroup,
    resetScanner,
    clearResults,
  } = useScanner(filteredUniverse.map((p) => p.symbol))

  const scopeLabel = categoryFilter === 'all' ? 'all markets' : `${categoryFilter} pairs`
  const allPairs = ALL_FOREX_PAIRS

  // Auto-collapse config when results arrive
  useEffect(() => {
    if (hasRun && results.length > 0) {
      setConfigExpanded(false)
    }
  }, [hasRun, results.length])

  // Close dropdown menu on outside click
  useEffect(() => {
    if (!openMenuId) return
    const handler = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setOpenMenuId(null)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [openMenuId])

  const sortedResults = useMemo(() => {
    const items = [...results]
    items.sort((a, b) => {
      switch (sortBy) {
        case 'score':
          return b.score - a.score
        case 'symbol':
          return a.symbol.localeCompare(b.symbol)
        case 'volume':
          return (b.indicator_values?.Volume || 0) - (a.indicator_values?.Volume || 0)
        case 'opportunity':
        default:
          return (b.opportunity_score || 0) - (a.opportunity_score || 0)
      }
    })
    return items
  }, [results, sortBy])

  const recentPairsSection = useMemo(
    () => (recentPairs || []).filter((p) => filteredUniverse.some((item) => item.symbol === p.symbol)).slice(0, 6),
    [filteredUniverse, recentPairs]
  )

  const handleRunScan = () => {
    runScan(filteredUniverse.map((p) => p.symbol))
  }

  const handleApplyPreset = (preset: (typeof presets)[number]) => {
    applyPreset(preset)
    setActiveScannerKey(`preset:${preset.id}`)
    setConfigTab('builder')
    setConfigExpanded(true)
    showToast({ title: `${preset.name} loaded`, message: 'Review the rules or run the scanner.', tone: 'success' })
  }

  const handleLoadSaved = (scanner: (typeof savedScanners)[number]) => {
    loadSavedScanner(scanner)
    setActiveScannerKey(`saved:${scanner.id}`)
    setConfigTab('builder')
    setConfigExpanded(true)
    showToast({ title: `${scanner.name} loaded`, message: 'Saved scanner restored.', tone: 'info' })
  }

  const handleResetScanner = () => {
    resetScanner()
    setActiveScannerKey('custom')
    setConfigTab('presets')
  }

  const handleDeleteSaved = async (scannerId: number) => {
    try {
      await deleteSavedScanner(scannerId)
      showToast({ title: 'Scanner removed', message: 'Deleted from saved scanners.', tone: 'warning' })
    } catch (err) {
      showToast({ title: 'Delete failed', message: err instanceof Error ? err.message : 'Unable to delete.', tone: 'error' })
    }
  }

  const openSaveDialog = () => {
    setSaveName(config.name || '')
    setShowSaveDialog(true)
  }

  const submitSave = async () => {
    try {
      setScannerName(saveName.trim())
      await saveScanner()
      setShowSaveDialog(false)
      showToast({ title: 'Scanner saved', message: `${saveName.trim() || 'Custom Scanner'} saved.`, tone: 'success' })
    } catch (err) {
      showToast({ title: 'Save failed', message: err instanceof Error ? err.message : 'Unable to save.', tone: 'error' })
    }
  }

  const handleTradeClick = (symbol: string) => {
    const pair = ALL_FOREX_PAIRS.find((item) => item.symbol === symbol)
    if (pair && onPairChange) {
      onPairChange(pair)
      onOpenLiveTrading?.()
      showToast({ title: `${symbol} selected`, message: 'Opening live trading dashboard.', tone: 'info' })
    }
  }

  const handleExport = () => {
    downloadResults(sortedResults)
    showToast({ title: 'Exported', message: 'Results downloaded as CSV.', tone: 'success' })
  }

  const handleArmAlert = async () => {
    try {
      await armScannerAlert()
      showToast({ title: 'Alert armed', message: `${config.name?.trim() || 'Custom Scanner'} added to alerts.`, tone: 'success' })
    } catch (err) {
      showToast({ title: 'Alert failed', message: err instanceof Error ? err.message : 'Could not arm alert.', tone: 'error' })
    }
  }

  const toggleIndicators = (key: string) => {
    setExpandedIndicators((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  const pairCount = selectedPairs.length || filteredUniverse.length

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <SimpleToastContainer toasts={toasts} onDismiss={dismissToast} />

      {/* ── Compact header bar ── */}
      <div className="flex shrink-0 items-center gap-3 border-b border-trading-border bg-trading-bg px-4 py-2.5 sm:px-6">
        <Search size={18} className="shrink-0 text-trading-accent" />
        <h1 className="text-base font-bold text-trading-text sm:text-lg">Scanner</h1>

        <div className="mx-2 hidden h-5 w-px bg-trading-border sm:block" />

        <div className="flex flex-1 flex-wrap items-center gap-2">
          <div className="flex rounded-md border border-trading-border bg-trading-card p-0.5">
            {(['swing', 'scalp'] as const).map((style) => (
              <button
                key={style}
                onClick={() => setTradeStyle(style)}
                className={`rounded px-2.5 py-1 text-xs font-medium capitalize transition-colors ${
                  config.trade_style === style ? 'bg-trading-accent text-white' : 'text-trading-muted hover:text-trading-text'
                }`}
              >
                {style}
              </button>
            ))}
          </div>
          <select
            value={config.timeframe}
            onChange={(e) => setTimeframe(e.target.value as ScannerTimeframe)}
            className="rounded-md border border-trading-border bg-trading-card px-2 py-1 text-xs text-trading-text"
          >
            {['1m', '5m', '15m', '1h', '4h', '1d'].map((tf) => (
              <option key={tf} value={tf}>{tf.toUpperCase()}</option>
            ))}
          </select>
          <select
            value={categoryFilter}
            onChange={(e) => setCategoryFilter(e.target.value as typeof categoryFilter)}
            className="rounded-md border border-trading-border bg-trading-card px-2 py-1 text-xs text-trading-text"
          >
            {CATEGORY_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>
        </div>

        {/* Right side: config summary */}
        <div className="hidden items-center gap-3 text-xs text-trading-muted lg:flex">
          <span>
            Using {config.name?.trim() || 'Custom Scanner'} &middot; {config.conditions.length} rules &middot; {config.logic}
          </span>
          {lastRunAt ? (
            <>
              <span className="h-3 w-px bg-trading-border" />
              <span>Last: {new Date(lastRunAt).toLocaleTimeString()}</span>
              <span className={`font-medium ${summary.total > 0 ? 'text-trading-buy' : 'text-trading-muted'}`}>
                {summary.total}/{totalScanned}
              </span>
            </>
          ) : null}
        </div>
      </div>

      {/* ── Main scrollable area ── */}
      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto max-w-[1400px] px-4 py-4 sm:px-6 sm:py-5">
          <div className="mb-4 overflow-hidden rounded-2xl border border-trading-border bg-trading-card">
            <div className="relative px-4 py-4 sm:px-5">
              <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_left,rgba(59,130,246,0.20),transparent_35%),radial-gradient(circle_at_bottom_right,rgba(16,185,129,0.12),transparent_32%)]" />
              <div className="relative flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
                <div className="max-w-3xl">
                  <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.22em] text-trading-accent">
                    <Sparkles size={14} />
                    Scanner control room
                  </div>
                  <h2 className="mt-2 text-2xl font-black tracking-tight text-trading-text sm:text-3xl">
                    Pick a bot, scan the market, then trade the strongest setups.
                  </h2>
                  <p className="mt-2 text-sm leading-6 text-trading-muted">
                    Instead of one generic scanner, this page now works like a scanner desk: choose Trend, Momentum, Volatility, Volume, or your own saved bot profile.
                  </p>
                </div>
                <div className="grid min-w-[260px] grid-cols-3 gap-2">
                  <div className="rounded-xl border border-trading-border bg-trading-bg/70 p-3">
                    <div className="text-[10px] uppercase tracking-wider text-trading-muted">Active bot</div>
                    <div className="mt-1 truncate text-sm font-bold text-trading-text">{config.name?.trim() || 'Custom'}</div>
                  </div>
                  <div className="rounded-xl border border-trading-border bg-trading-bg/70 p-3">
                    <div className="text-[10px] uppercase tracking-wider text-trading-muted">Library</div>
                    <div className="mt-1 text-sm font-bold text-trading-text">{presets.length + savedScanners.length}</div>
                  </div>
                  <div className="rounded-xl border border-trading-border bg-trading-bg/70 p-3">
                    <div className="text-[10px] uppercase tracking-wider text-trading-muted">Scope</div>
                    <div className="mt-1 text-sm font-bold text-trading-text">{pairCount}</div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* ── Collapsible configuration section ── */}
          <div className="mb-4 rounded-lg border border-trading-border bg-trading-card">
            {/* Collapse toggle bar */}
            <button
              onClick={() => setConfigExpanded(!configExpanded)}
              className="flex w-full items-center justify-between px-4 py-2.5"
            >
              <div className="flex items-center gap-3">
                {configTab === 'presets' ? <Bot size={16} className="text-trading-accent" /> : <SlidersHorizontal size={16} className="text-trading-accent" />}
                <span className="text-sm font-semibold text-trading-text">
                  {config.name?.trim() || 'Custom Scanner'}
                </span>
                <span className="hidden text-xs text-trading-muted sm:inline">
                  {conditionSummaryText(config.conditions)} &middot; {pairCount} pairs
                </span>
              </div>
              <div className="flex items-center gap-2">
                {!configExpanded ? (
                  <span className="rounded-md bg-trading-bg px-2 py-0.5 text-[10px] font-medium text-trading-muted">
                    {config.conditions.length} rules
                  </span>
                ) : null}
                {configExpanded ? <ChevronUp size={16} className="text-trading-muted" /> : <ChevronDown size={16} className="text-trading-muted" />}
              </div>
            </button>

            {/* Expanded config content */}
            {configExpanded ? (
              <div className="border-t border-trading-border">
                {/* Tab bar + actions */}
                <div className="flex items-center justify-between border-b border-trading-border/50 px-4 py-2">
                  <div className="flex gap-1">
                    {([{ key: 'builder' as const, label: 'Build Scan' }, { key: 'presets' as const, label: 'Presets & Saved' }]).map((tab) => (
                      <button
                        key={tab.key}
                        onClick={() => setConfigTab(tab.key)}
                        className={`rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
                          configTab === tab.key ? 'bg-trading-accent text-white' : 'text-trading-muted hover:text-trading-text'
                        }`}
                      >
                        {tab.label}
                      </button>
                    ))}
                  </div>
                  <div className="flex gap-1.5">
                    <button onClick={clearResults} title="Clear results" className="rounded-md p-1.5 text-trading-muted transition-colors hover:bg-trading-bg hover:text-trading-text">
                      <RefreshCw size={14} />
                    </button>
                    <button onClick={handleArmAlert} title="Arm alert" className="rounded-md p-1.5 text-trading-muted transition-colors hover:bg-trading-bg hover:text-trading-text">
                      <Bell size={14} />
                    </button>
                    <button onClick={openSaveDialog} title="Save scanner" className="rounded-md p-1.5 text-trading-accent transition-colors hover:bg-trading-accent/10">
                      <BookmarkPlus size={14} />
                    </button>
                  </div>
                </div>

                {/* Tab content */}
                <div className="px-4 py-4">
                  {configTab === 'builder' ? (
                    <div>
                      <input
                        type="text"
                        value={config.name || ''}
                        onChange={(e) => {
                          setScannerName(e.target.value)
                          setActiveScannerKey('custom')
                        }}
                        placeholder="Scanner name (e.g. London session breakout)"
                        className="mb-4 w-full rounded-md border border-trading-border bg-trading-bg px-3 py-2 text-sm text-trading-text placeholder:text-trading-muted focus:border-trading-accent focus:outline-none"
                      />
                      {loadingMetadata ? (
                        <div className="rounded-lg border border-trading-border bg-trading-bg p-4 text-sm text-trading-muted">
                          Loading scanner metadata...
                        </div>
                      ) : (
                        <ScannerBuilder
                          groups={groups}
                          onGroupsChange={setGroups}
                          logic={config.logic}
                          onLogicChange={setLogic}
                          selectedPairs={selectedPairs}
                          onPairsChange={setSelectedPairs}
                          onRunScan={handleRunScan}
                          onReset={handleResetScanner}
                          isScanning={loading}
                          allPairs={allPairs}
                          supportedIndicators={supportedIndicators}
                          categoryFilter={categoryFilter}
                          onUseCategoryUniverse={() => setSelectedPairs([])}
                          scopeLabel={scopeLabel}
                          onAddGroup={addGroup}
                          onRemoveGroup={removeGroup}
                          showRunButton={false}
                        />
                      )}
                    </div>
                  ) : (
                    <ScannerPresets
                      presets={presets}
                      savedScanners={savedScanners}
                      loading={loadingMetadata}
                      loadingSaved={loadingSaved}
                      activeScannerKey={activeScannerKey}
                      onApplyPreset={handleApplyPreset}
                      onApplySaved={handleLoadSaved}
                      onDeleteSaved={handleDeleteSaved}
                    />
                  )}
                </div>
              </div>
            ) : null}
          </div>

          {/* ── Sticky run button bar ── */}
          <div className="mb-4 flex items-center gap-3 rounded-lg border border-trading-border bg-trading-card px-4 py-2.5">
            <div className="min-w-0 flex-1 text-xs text-trading-muted">
              <span className="hidden sm:inline">
                {conditionSummaryText(config.conditions)} &middot;{' '}
              </span>
              <span className="font-medium text-trading-text">{pairCount}</span> pairs &middot; {config.timeframe?.toUpperCase()} &middot; {config.trade_style}
            </div>
            <button
              onClick={openSaveDialog}
              className="hidden items-center gap-1.5 rounded-md border border-trading-border px-3 py-1.5 text-xs font-medium text-trading-muted transition-colors hover:text-trading-text sm:inline-flex"
            >
              <BookmarkPlus size={13} />
              Save
            </button>
            <button
              onClick={handleRunScan}
              disabled={loading || config.conditions.length === 0}
              className="inline-flex items-center gap-2 rounded-md bg-trading-accent px-4 py-1.5 text-sm font-medium text-white transition-colors hover:bg-blue-600 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {loading ? (
                <>
                  <div className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-white/30 border-t-white" />
                  Scanning {pairCount}...
                </>
              ) : (
                <>
                  <Play size={14} />
                  Run Scan
                </>
              )}
            </button>
          </div>

          {/* ── Error / warnings ── */}
          {error ? (
            <div className="mb-4 flex items-start gap-3 rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-200">
              <AlertTriangle size={16} className="mt-0.5 shrink-0" />
              <div>
                <p className="font-semibold">Scan failed</p>
                <p className="mt-0.5 text-xs text-red-100/80">{error}</p>
              </div>
            </div>
          ) : null}
          {warnings.length > 0 ? (
            <div className="mb-4 rounded-lg border border-yellow-500/30 bg-yellow-500/10 p-3">
              <div className="flex items-center gap-2 text-xs font-semibold text-yellow-200">
                <AlertTriangle size={14} />
                Warnings
              </div>
              <ul className="mt-1 space-y-0.5 text-xs text-yellow-100/80">
                {warnings.map((w) => <li key={w}>- {w}</li>)}
              </ul>
            </div>
          ) : null}

          {/* ── Results section ── */}
          {results.length > 0 ? (
            <>
              {/* Inline stats bar */}
              <div className="mb-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
                <span className="font-semibold text-trading-text">{summary.total} matches</span>
                <span className="text-trading-buy">{summary.buy} BUY</span>
                <span className="text-trading-sell">{summary.sell} SELL</span>
                <span className="text-trading-muted">{summary.neutral} neutral</span>
                <span className="text-trading-muted">Avg opp: {summary.averageOpportunity}%</span>

                <div className="ml-auto flex items-center gap-2">
                  <select
                    value={sortBy}
                    onChange={(e) => setSortBy(e.target.value as SortOption)}
                    className="rounded-md border border-trading-border bg-trading-card px-2 py-1 text-xs text-trading-text"
                  >
                    {SORT_OPTIONS.map((opt) => (
                      <option key={opt.value} value={opt.value}>Sort: {opt.label}</option>
                    ))}
                  </select>
                  <button
                    onClick={handleExport}
                    title="Export CSV"
                    className="rounded-md border border-trading-border p-1.5 text-trading-muted transition-colors hover:text-trading-text"
                  >
                    <Download size={14} />
                  </button>
                </div>
              </div>

              {/* Flat result cards */}
              <div className="divide-y divide-trading-border rounded-lg border border-trading-border bg-trading-card">
                {sortedResults.map((result) => {
                  const pair = ALL_FOREX_PAIRS.find((item) => item.symbol === result.symbol)
                  const resultKey = `${result.symbol}-${result.timeframe}-${result.trade_style}`
                  const isMenuOpen = openMenuId === resultKey
                  const showIndicators = expandedIndicators.has(resultKey)

                  return (
                    <div key={resultKey} className="px-4 py-3 transition-colors hover:bg-trading-bg/30">
                      {/* Row 1: Symbol + signal + score + actions */}
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0 flex-1">
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="text-base font-bold text-trading-text">{result.symbol}</span>
                            {pair ? <span className="hidden text-xs text-trading-muted sm:inline">{pair.name}</span> : null}
                            <span className={`rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase ${signalBg(result.signal)}`}>
                              {result.signal || 'NEUTRAL'}
                            </span>
                            <div className="flex items-center gap-1.5">
                              <div className="h-1.5 w-16 overflow-hidden rounded-full bg-trading-bg sm:w-24">
                                <div className={`h-full ${scoreBar(result.score)} transition-all`} style={{ width: `${result.score * 100}%` }} />
                              </div>
                              <span className="text-xs font-medium text-trading-text">{Math.round(result.score * 100)}%</span>
                            </div>
                          </div>
                          <p className="mt-1 text-xs text-trading-muted">{result.reason || 'Matched scanner conditions.'}</p>
                        </div>

                        {/* Actions: primary + overflow menu */}
                        <div className="flex shrink-0 items-center gap-1.5">
                          <button
                            onClick={() => handleTradeClick(result.symbol)}
                            className="inline-flex items-center gap-1 rounded-md bg-trading-accent px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-blue-600"
                          >
                            Trade <ArrowRight size={12} />
                          </button>
                          <div className="relative" ref={isMenuOpen ? menuRef : undefined}>
                            <button
                              onClick={() => setOpenMenuId(isMenuOpen ? null : resultKey)}
                              className="rounded-md border border-trading-border p-1.5 text-trading-muted transition-colors hover:text-trading-text"
                            >
                              <MoreHorizontal size={14} />
                            </button>
                            {isMenuOpen ? (
                              <div className="absolute right-0 top-full z-30 mt-1 min-w-[160px] rounded-md border border-trading-border bg-trading-card py-1 shadow-xl">
                                <button
                                  onClick={() => {
                                    if (pair && onAddToWatchlist) {
                                      onAddToWatchlist(pair)
                                      showToast({ title: `${pair.symbol} added to watchlist`, message: '', tone: 'success' })
                                    }
                                    setOpenMenuId(null)
                                  }}
                                  disabled={!pair || !onAddToWatchlist || activeWatchlistSymbols?.includes(result.symbol)}
                                  className="flex w-full items-center gap-2 px-3 py-2 text-xs text-trading-text transition-colors hover:bg-trading-bg disabled:opacity-50"
                                >
                                  <Plus size={12} />
                                  {activeWatchlistSymbols?.includes(result.symbol) ? 'Watching' : 'Add to watchlist'}
                                </button>
                                <button
                                  onClick={() => {
                                    handleTradeClick(result.symbol)
                                    onOpenDashboard?.()
                                    setOpenMenuId(null)
                                  }}
                                  className="flex w-full items-center gap-2 px-3 py-2 text-xs text-trading-text transition-colors hover:bg-trading-bg"
                                >
                                  <LayoutDashboard size={12} />
                                  Open dashboard
                                </button>
                                <button
                                  onClick={() => {
                                    handleTradeClick(result.symbol)
                                    onOpenBacktest?.()
                                    setOpenMenuId(null)
                                  }}
                                  className="flex w-full items-center gap-2 px-3 py-2 text-xs text-trading-text transition-colors hover:bg-trading-bg"
                                >
                                  <LineChart size={12} />
                                  Run backtest
                                </button>
                              </div>
                            ) : null}
                          </div>
                        </div>
                      </div>

                      {/* Row 2: Metrics pills + badges */}
                      <div className="mt-2 flex flex-wrap items-center gap-1.5">
                        <span className="rounded-md bg-trading-bg px-2 py-0.5 text-[10px] font-medium text-trading-text">
                          Opp: {Math.round(result.opportunity_score || 0)}%
                        </span>
                        <span className="rounded-md bg-trading-bg px-2 py-0.5 text-[10px] font-medium text-trading-text">
                          Conf: {Math.round(result.confidence || 0)}%
                        </span>
                        <span className="rounded-md bg-trading-bg px-2 py-0.5 text-[10px] font-medium text-trading-text">
                          Vol: {(result.indicator_values?.Volume || 0).toFixed(1)}x
                        </span>
                        {result.source_metadata ? (
                          <>
                            <DataSourceBadge
                              sourceType={result.source_metadata.sourceType}
                              sourceName={result.source_metadata.sourceName}
                              contextLabel={result.trade_style === 'scalp' ? 'Scalp Mode' : result.symbol === 'XAU/USD' ? 'Swing Mode' : undefined}
                            />
                            <FreshnessPill freshnessSeconds={result.source_metadata.freshnessSeconds} marketStatus={result.source_metadata.marketStatus} />
                          </>
                        ) : null}
                        {result.market_regime ? (
                          <span className="rounded-md bg-trading-bg px-2 py-0.5 text-[10px] text-trading-muted">{result.market_regime}</span>
                        ) : null}
                        {result.timeframe ? (
                          <span className="rounded-md bg-trading-bg px-2 py-0.5 text-[10px] text-trading-muted">{result.timeframe.toUpperCase()}</span>
                        ) : null}
                      </div>

                      {/* Row 3: Matching conditions as tags */}
                      <div className="mt-2 flex flex-wrap gap-1">
                        {result.matching_conditions.map((cond) => (
                          <span key={`${result.symbol}-${cond}`} className="rounded-md bg-trading-bg px-2 py-0.5 text-[10px] text-trading-muted">
                            {cond}
                          </span>
                        ))}
                        {result.indicator_values && Object.keys(result.indicator_values).length > 0 ? (
                          <button
                            onClick={() => toggleIndicators(resultKey)}
                            className="rounded-md px-2 py-0.5 text-[10px] text-trading-accent transition-colors hover:bg-trading-accent/10"
                          >
                            {showIndicators ? 'Hide indicators' : 'Show indicators'}
                          </button>
                        ) : null}
                      </div>

                      {/* Row 4: Expandable indicator values */}
                      {showIndicators && result.indicator_values ? (
                        <div className="mt-2 grid grid-cols-2 gap-1.5 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6">
                          {Object.entries(result.indicator_values).map(([key, value]) => (
                            <div key={key} className="rounded-md bg-trading-bg px-2 py-1.5">
                              <div className="text-[9px] uppercase tracking-wider text-trading-muted">{key}</div>
                              <div className="text-xs font-semibold text-trading-text">{value}</div>
                            </div>
                          ))}
                        </div>
                      ) : null}
                    </div>
                  )
                })}
              </div>
            </>
          ) : (
            <div className="flex h-64 flex-col items-center justify-center rounded-lg border border-dashed border-trading-border bg-trading-card text-center sm:h-72">
              <Search size={40} className="mb-3 text-trading-muted opacity-30" />
              <p className="text-base font-medium text-trading-text">
                {hasRun ? 'No pairs matched this scan' : 'Run a scan to find opportunities'}
              </p>
              <p className="mt-1 max-w-md text-xs text-trading-muted">
                {hasRun
                  ? 'Try broadening thresholds, switching to OR logic, or scanning a wider universe.'
                  : 'Load a preset or configure rules, then hit Run Scan.'}
              </p>
              {recentPairsSection.length > 0 && !hasRun ? (
                <div className="mt-3 flex flex-wrap justify-center gap-1.5">
                  {recentPairsSection.map((pair) => (
                    <button
                      key={pair.symbol}
                      onClick={() => setSelectedPairs(Array.from(new Set([...selectedPairs, pair.symbol])))}
                      className="rounded-full border border-trading-border px-2.5 py-1 text-[11px] text-trading-muted transition-colors hover:text-trading-text"
                    >
                      + {pair.symbol}
                    </button>
                  ))}
                </div>
              ) : null}
            </div>
          )}
        </div>
      </div>

      {/* Save dialog modal */}
      {showSaveDialog ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="w-full max-w-sm rounded-lg border border-trading-border bg-trading-card p-5 shadow-2xl">
            <h3 className="text-base font-semibold text-trading-text">Save scanner</h3>
            <p className="mt-1 text-xs text-trading-muted">Store this configuration to reuse later.</p>
            <input
              type="text"
              value={saveName}
              onChange={(e) => setSaveName(e.target.value)}
              placeholder="Scanner name"
              className="mt-3 w-full rounded-md border border-trading-border bg-trading-bg px-3 py-2 text-sm text-trading-text placeholder:text-trading-muted focus:border-trading-accent focus:outline-none"
              autoFocus
            />
            <div className="mt-4 flex gap-2">
              <button
                onClick={() => setShowSaveDialog(false)}
                className="flex-1 rounded-md bg-trading-bg px-3 py-2 text-sm text-trading-text transition-colors hover:bg-trading-border"
              >
                Cancel
              </button>
              <button
                onClick={submitSave}
                disabled={!saveName.trim()}
                className="flex-1 rounded-md bg-trading-accent px-3 py-2 text-sm text-white transition-colors hover:bg-blue-600 disabled:cursor-not-allowed disabled:opacity-50"
              >
                Save
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  )
}
