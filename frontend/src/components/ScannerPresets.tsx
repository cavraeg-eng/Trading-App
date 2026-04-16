import {
  Activity,
  BarChart3,
  Bookmark,
  RefreshCw,
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
  onApplyPreset: (preset: ScannerPreset) => void
  onApplySaved: (scanner: SavedScanner) => void
  onDeleteSaved: (scannerId: number) => void
}

const iconMap: Record<string, React.ElementType> = {
  'trending-up': TrendingUp,
  zap: Zap,
  activity: Activity,
  'bar-chart': BarChart3,
  'refresh-cw': RefreshCw,
}

function MetaPill({ label }: { label: string }) {
  return (
    <span className="rounded-full bg-trading-card px-2 py-0.5 text-[10px] font-medium text-trading-muted">
      {label}
    </span>
  )
}

export default function ScannerPresets({
  presets,
  savedScanners,
  loading,
  loadingSaved,
  onApplyPreset,
  onApplySaved,
  onDeleteSaved,
}: ScannerPresetsProps) {
  return (
    <div className="space-y-6">
      {/* Presets section */}
      {presets.length > 0 || loading ? (
        <section>
          {loading ? (
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
              {[...Array(4)].map((_, index) => (
                <div
                  key={index}
                  className="animate-pulse rounded-lg border border-trading-border bg-trading-card p-3"
                >
                  <div className="mb-2 h-8 w-8 rounded-md bg-trading-border" />
                  <div className="mb-1.5 h-4 w-2/3 rounded bg-trading-border" />
                  <div className="mb-3 h-3 w-full rounded bg-trading-border" />
                  <div className="h-8 rounded bg-trading-border" />
                </div>
              ))}
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
              {presets.map((preset) => {
                const Icon = iconMap[preset.icon] || Activity
                return (
                  <button
                    key={preset.id}
                    onClick={() => onApplyPreset(preset)}
                    className="group rounded-lg border border-trading-border bg-trading-card p-3 text-left transition-all hover:border-trading-accent/50 hover:bg-trading-accent/5"
                  >
                    <div className="mb-2 flex items-center gap-2">
                      <div className="flex h-8 w-8 items-center justify-center rounded-md bg-trading-bg">
                        <Icon size={16} className="text-trading-accent" />
                      </div>
                      <h4 className="text-sm font-semibold text-trading-text">{preset.name}</h4>
                    </div>
                    <p className="mb-2 line-clamp-2 text-xs text-trading-muted">{preset.description}</p>
                    <div className="flex flex-wrap gap-1">
                      <MetaPill label={`${preset.conditions.length} rules`} />
                      {preset.timeframe ? <MetaPill label={preset.timeframe.toUpperCase()} /> : null}
                      {preset.trade_style ? <MetaPill label={preset.trade_style} /> : null}
                    </div>
                  </button>
                )
              })}
            </div>
          )}
        </section>
      ) : null}

      {/* Saved scanners section */}
      {savedScanners.length > 0 || loadingSaved ? (
        <section>
          {loadingSaved ? (
            <div className="rounded-lg border border-trading-border bg-trading-card p-3 text-sm text-trading-muted">
              Loading saved scanners...
            </div>
          ) : savedScanners.length === 0 ? null : (
            <div className="divide-y divide-trading-border rounded-lg border border-trading-border bg-trading-card">
              {savedScanners.map((scanner) => (
                <div
                  key={scanner.id}
                  className="flex items-center justify-between gap-3 px-3 py-2.5"
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <Bookmark size={12} className="shrink-0 text-trading-accent" />
                      <span className="truncate text-sm font-medium text-trading-text">{scanner.name}</span>
                      <MetaPill label={`${scanner.config.conditions?.length || 0} rules`} />
                      {scanner.config.timeframe ? <MetaPill label={scanner.config.timeframe.toUpperCase()} /> : null}
                    </div>
                  </div>
                  <div className="flex shrink-0 gap-1">
                    <button
                      onClick={() => onApplySaved(scanner)}
                      className="rounded-md px-2.5 py-1 text-xs font-medium text-trading-text transition-colors hover:bg-trading-bg hover:text-trading-accent"
                    >
                      Load
                    </button>
                    <button
                      onClick={() => onDeleteSaved(scanner.id)}
                      className="rounded-md px-2 py-1 text-xs text-trading-muted transition-colors hover:bg-trading-bg hover:text-red-300"
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

      {/* Empty state when both are empty */}
      {!loading && !loadingSaved && presets.length === 0 && savedScanners.length === 0 ? (
        <div className="rounded-lg border border-dashed border-trading-border bg-trading-card px-4 py-6 text-center text-sm text-trading-muted">
          No presets or saved scanners available.
        </div>
      ) : null}
    </div>
  )
}
