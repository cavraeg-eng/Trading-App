import {
  Activity,
  BarChart3,
  Bookmark,
  Bot,
  CheckCircle2,
  Clock3,
  Layers3,
  RefreshCw,
  ShieldCheck,
  Sparkles,
  Target,
  Trash2,
  TrendingUp,
  Zap,
} from 'lucide-react'
import type { SavedScanner, ScannerPreset } from '../types'

interface ScannerPresetsProps {
  presets: ScannerPreset[]
  savedScanners: SavedScanner[]
  loading: boolean
  loadingSaved: boolean
  activeScannerKey?: string
  riskFilter?: 'all' | 'low' | 'medium' | 'high'
  styleFilter?: 'all' | 'swing' | 'scalp'
  onApplyPreset: (preset: ScannerPreset) => void
  onApplySaved: (scanner: SavedScanner) => void
  onDeleteSaved: (scannerId: number) => void
  onRiskFilterChange?: (filter: 'all' | 'low' | 'medium' | 'high') => void
  onStyleFilterChange?: (filter: 'all' | 'swing' | 'scalp') => void
}

const iconMap: Record<string, React.ElementType> = {
  'trending-up': TrendingUp,
  zap: Zap,
  activity: Activity,
  'bar-chart': BarChart3,
  'refresh-cw': RefreshCw,
  bot: Bot,
  target: Target,
  shield: ShieldCheck,
  sparkles: Sparkles,
}

function MetaPill({ label }: { label: string }) {
  return (
    <span className="rounded-full bg-trading-card px-2 py-0.5 text-[10px] font-medium text-trading-muted">
      {label}
    </span>
  )
}

function rulesCount(scanner: Pick<ScannerPreset, 'conditions' | 'groups'>) {
  return scanner.groups?.length
    ? scanner.groups.reduce((total, group) => total + group.conditions.length, 0)
    : scanner.conditions.length
}

function savedRulesCount(scanner: SavedScanner) {
  return scanner.config.groups?.length
    ? scanner.config.groups.reduce((total, group) => total + group.conditions.length, 0)
    : scanner.config.conditions?.length || 0
}

function accentClasses(accent?: string) {
  const styles: Record<string, { icon: string; line: string; glow: string }> = {
    emerald: {
      icon: 'bg-emerald-400/10 text-emerald-300 ring-emerald-400/20',
      line: 'from-emerald-400 via-teal-300 to-cyan-300',
      glow: 'shadow-[0_0_35px_rgba(16,185,129,0.12)]',
    },
    amber: {
      icon: 'bg-amber-400/10 text-amber-300 ring-amber-400/20',
      line: 'from-amber-300 via-orange-300 to-red-300',
      glow: 'shadow-[0_0_35px_rgba(245,158,11,0.12)]',
    },
    sky: {
      icon: 'bg-sky-400/10 text-sky-300 ring-sky-400/20',
      line: 'from-sky-300 via-blue-300 to-indigo-300',
      glow: 'shadow-[0_0_35px_rgba(56,189,248,0.12)]',
    },
    violet: {
      icon: 'bg-violet-400/10 text-violet-300 ring-violet-400/20',
      line: 'from-violet-300 via-fuchsia-300 to-pink-300',
      glow: 'shadow-[0_0_35px_rgba(167,139,250,0.12)]',
    },
    rose: {
      icon: 'bg-rose-400/10 text-rose-300 ring-rose-400/20',
      line: 'from-rose-300 via-red-300 to-orange-300',
      glow: 'shadow-[0_0_35px_rgba(251,113,133,0.12)]',
    },
  }
  return styles[accent || ''] || styles.sky
}

function riskDotColor(risk?: string) {
  if (risk === 'low') return 'bg-emerald-400'
  if (risk === 'high') return 'bg-rose-400'
  return 'bg-amber-400'
}

export default function ScannerPresets({
  presets,
  savedScanners,
  loading,
  loadingSaved,
  activeScannerKey,
  riskFilter = 'all',
  styleFilter = 'all',
  onApplyPreset,
  onApplySaved,
  onDeleteSaved,
  onRiskFilterChange,
  onStyleFilterChange,
}: ScannerPresetsProps) {
  return (
    <div className="space-y-5">
      {presets.length > 0 || loading ? (
        <section>
          <div className="mb-3 flex flex-wrap items-end justify-between gap-3">
            <div>
              <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.2em] text-trading-accent">
                <Bot size={14} />
                Scanner bot library
              </div>
              <h3 className="mt-1 text-lg font-bold text-trading-text">Choose the market scanner you want to run</h3>
              <p className="mt-1 max-w-2xl text-xs text-trading-muted">
                Each bot loads a different rule stack, timeframe, and trading style so you can switch workflows without rebuilding conditions.
              </p>
            </div>
            <div className="flex gap-2 text-[11px] text-trading-muted">
              <span className="rounded-full border border-trading-border bg-trading-bg px-2.5 py-1">{presets.length} built-in bots</span>
              <span className="rounded-full border border-trading-border bg-trading-bg px-2.5 py-1">{savedScanners.length} saved</span>
            </div>
          </div>

          {/* Filter bar */}
          {onRiskFilterChange || onStyleFilterChange ? (
            <div className="mb-3 flex flex-wrap items-center gap-2">
              {onRiskFilterChange ? (
                <div className="flex items-center gap-1.5">
                  <span className="text-[10px] uppercase tracking-wider text-trading-muted">Risk</span>
                  <div className="flex rounded-md border border-trading-border bg-trading-card p-0.5">
                    {(['all', 'low', 'medium', 'high'] as const).map((r) => (
                      <button
                        key={r}
                        onClick={() => onRiskFilterChange(r)}
                        className={`rounded px-2 py-0.5 text-[10px] font-medium capitalize transition-colors ${
                          riskFilter === r ? 'bg-trading-accent text-white' : 'text-trading-muted hover:text-trading-text'
                        }`}
                      >
                        {r}
                      </button>
                    ))}
                  </div>
                </div>
              ) : null}
              {onStyleFilterChange ? (
                <div className="flex items-center gap-1.5">
                  <span className="text-[10px] uppercase tracking-wider text-trading-muted">Style</span>
                  <div className="flex rounded-md border border-trading-border bg-trading-card p-0.5">
                    {(['all', 'swing', 'scalp'] as const).map((s) => (
                      <button
                        key={s}
                        onClick={() => onStyleFilterChange(s)}
                        className={`rounded px-2 py-0.5 text-[10px] font-medium capitalize transition-colors ${
                          styleFilter === s ? 'bg-trading-accent text-white' : 'text-trading-muted hover:text-trading-text'
                        }`}
                      >
                        {s}
                      </button>
                    ))}
                  </div>
                </div>
              ) : null}
            </div>
          ) : null}

          {loading ? (
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
              {[...Array(6)].map((_, index) => (
                <div
                  key={index}
                  className="animate-pulse rounded-xl border border-trading-border bg-trading-bg/70 p-4"
                >
                  <div className="mb-3 h-10 w-10 rounded-lg bg-trading-border" />
                  <div className="mb-2 h-4 w-2/3 rounded bg-trading-border" />
                  <div className="mb-3 h-10 rounded bg-trading-border" />
                  <div className="grid grid-cols-3 gap-2">
                    <div className="h-12 rounded bg-trading-border" />
                    <div className="h-12 rounded bg-trading-border" />
                    <div className="h-12 rounded bg-trading-border" />
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
              {presets.map((preset) => {
                const Icon = iconMap[preset.icon] || Activity
                const selected = activeScannerKey === `preset:${preset.id}`
                const accent = accentClasses(preset.accent)
                return (
                  <div
                    key={preset.id}
                    className={`group relative overflow-hidden rounded-xl border bg-trading-bg/70 p-4 text-left transition-all hover:-translate-y-0.5 hover:border-trading-accent/50 ${
                      selected
                        ? `border-trading-accent/70 ring-1 ring-trading-accent/40 ${accent.glow}`
                        : 'border-trading-border'
                    }`}
                  >
                    <div className={`absolute inset-x-0 top-0 h-0.5 bg-gradient-to-r ${accent.line}`} />
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex items-center gap-3">
                        <div className={`flex h-10 w-10 items-center justify-center rounded-lg ring-1 ${accent.icon}`}>
                          <Icon size={18} />
                        </div>
                        <div>
                          <div className="flex items-center gap-2">
                            <h4 className="text-sm font-semibold text-trading-text">{preset.name}</h4>
                            {selected ? <CheckCircle2 size={14} className="text-trading-accent" /> : null}
                          </div>
                          <p className="text-[11px] uppercase tracking-[0.18em] text-trading-muted">{preset.category || 'Strategy bot'}</p>
                        </div>
                      </div>
                      <div className="flex items-center gap-1.5">
                        <span className="flex items-center gap-1 rounded-full border border-trading-border bg-trading-card px-2 py-0.5 text-[10px] font-medium text-trading-muted">
                          <span className={`inline-block h-1.5 w-1.5 rounded-full ${riskDotColor(preset.risk)}`} />
                          {preset.risk || 'medium'}
                        </span>
                        <span className="rounded-full border border-trading-border bg-trading-card px-2 py-0.5 text-[10px] font-medium text-trading-muted">
                          {preset.popularity || 'Ready'}
                        </span>
                      </div>
                    </div>
                    <p className="mt-3 min-h-[2.5rem] text-xs leading-5 text-trading-muted">{preset.description}</p>
                    <div className="mt-3 grid grid-cols-3 gap-2">
                      <div className="rounded-lg border border-trading-border bg-trading-card/70 p-2">
                        <div className="flex items-center gap-1 text-[10px] uppercase tracking-wider text-trading-muted">
                          <Layers3 size={11} />
                          Rules
                        </div>
                        <div className="mt-1 text-sm font-semibold text-trading-text">{rulesCount(preset)}</div>
                      </div>
                      <div className="rounded-lg border border-trading-border bg-trading-card/70 p-2">
                        <div className="flex items-center gap-1 text-[10px] uppercase tracking-wider text-trading-muted">
                          <Clock3 size={11} />
                          Cadence
                        </div>
                        <div className="mt-1 text-sm font-semibold text-trading-text">{preset.cadence || preset.timeframe?.toUpperCase() || '1H'}</div>
                      </div>
                      <div className="rounded-lg border border-trading-border bg-trading-card/70 p-2">
                        <div className="flex items-center gap-1 text-[10px] uppercase tracking-wider text-trading-muted">
                          <ShieldCheck size={11} />
                          Risk
                        </div>
                        <div className="mt-1 text-sm font-semibold capitalize text-trading-text">{preset.risk || 'medium'}</div>
                      </div>
                    </div>
                    <p className="mt-3 text-[11px] text-trading-muted">
                      <span className="font-medium text-trading-text">Best for:</span> {preset.best_for || 'General opportunity scanning'}
                    </p>
                    <div className="mt-3 flex flex-wrap gap-1">
                      <MetaPill label={`${rulesCount(preset)} rules`} />
                      {preset.timeframe ? <MetaPill label={preset.timeframe.toUpperCase()} /> : null}
                      {preset.trade_style ? <MetaPill label={preset.trade_style} /> : null}
                      {preset.tags?.slice(0, 2).map((tag) => <MetaPill key={tag} label={tag} />)}
                    </div>
                    <button
                      onClick={() => onApplyPreset(preset)}
                      className={`mt-4 w-full rounded-lg px-3 py-2 text-xs font-semibold transition-colors ${
                        selected
                          ? 'bg-trading-accent text-white'
                          : 'bg-trading-card text-trading-text hover:bg-trading-accent hover:text-white'
                      }`}
                    >
                      {selected ? 'Selected scanner' : 'Use this scanner'}
                    </button>
                  </div>
                )
              })}
            </div>
          )}
        </section>
      ) : null}

      {savedScanners.length > 0 || loadingSaved ? (
        <section>
          <div className="mb-3 flex items-center gap-2">
            <Bookmark size={14} className="text-trading-accent" />
            <h3 className="text-sm font-semibold text-trading-text">Your saved scanners</h3>
          </div>
          {loadingSaved ? (
            <div className="rounded-lg border border-trading-border bg-trading-card p-3 text-sm text-trading-muted">
              Loading saved scanners...
            </div>
          ) : savedScanners.length === 0 ? null : (
            <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
              {savedScanners.map((scanner) => (
                <div
                  key={scanner.id}
                  className={`flex items-center justify-between gap-3 rounded-lg border bg-trading-bg px-3 py-2.5 ${
                    activeScannerKey === `saved:${scanner.id}` ? 'border-trading-accent/70 ring-1 ring-trading-accent/30' : 'border-trading-border'
                  }`}
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <Bookmark size={12} className="shrink-0 text-trading-accent" />
                      <span className="truncate text-sm font-medium text-trading-text">{scanner.name}</span>
                      <MetaPill label={`${savedRulesCount(scanner)} rules`} />
                      {scanner.config.timeframe ? <MetaPill label={scanner.config.timeframe.toUpperCase()} /> : null}
                    </div>
                  </div>
                  <div className="flex shrink-0 gap-1">
                    <button
                      onClick={() => onApplySaved(scanner)}
                      aria-label={`Load ${scanner.name}`}
                      className="rounded-md px-2.5 py-1 text-xs font-medium text-trading-text transition-colors hover:bg-trading-card hover:text-trading-accent"
                    >
                      Load
                    </button>
                    <button
                      onClick={() => onDeleteSaved(scanner.id)}
                      aria-label={`Delete ${scanner.name}`}
                      title={`Delete ${scanner.name}`}
                      className="rounded-md px-2 py-1 text-xs text-trading-muted transition-colors hover:bg-trading-card hover:text-red-300"
                    >
                      <Trash2 size={12} />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>
      ) : null}

      {!loading && !loadingSaved && presets.length === 0 && savedScanners.length === 0 ? (
        <div className="rounded-lg border border-dashed border-trading-border bg-trading-card px-4 py-6 text-center text-sm text-trading-muted">
          No presets or saved scanners available.
        </div>
      ) : null}
    </div>
  )
}