import { useMemo, useState } from 'react'
import type { StrategyDefinition } from '../types'

interface StrategyCatalogProps {
  strategies: StrategyDefinition[]
  onActivate: (strategy: StrategyDefinition, mode: 'paper' | 'live') => void
  onSelectStrategy?: (strategy: StrategyDefinition) => void
}

export function StrategyCatalog({ strategies, onActivate, onSelectStrategy }: StrategyCatalogProps) {
  const [category, setCategory] = useState<'all' | 'gold' | 'forex'>('all')
  const filtered = useMemo(() => {
    if (category === 'all') return strategies
    return strategies.filter((strategy) => strategy.category === category)
  }, [strategies, category])

  return (
    <div className="bg-trading-card border border-trading-border rounded-lg p-4">
      <div className="mb-4 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-trading-text">Strategy Catalog</h3>
        <select
          value={category}
          onChange={(e) => setCategory(e.target.value as 'all' | 'gold' | 'forex')}
          className="rounded-lg border border-trading-border bg-trading-bg px-2 py-1 text-sm text-trading-text"
        >
          <option value="all">All</option>
          <option value="gold">Gold</option>
          <option value="forex">Forex</option>
        </select>
      </div>
      <div className="space-y-3">
        {filtered.map((strategy) => (
          <div key={strategy.id} className="rounded-lg border border-trading-border bg-trading-bg p-3">
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="flex items-center gap-2">
                  <span className="font-semibold text-trading-text">{strategy.name}</span>
                  {strategy.isActive && (
                    <span className="rounded-full border border-emerald-500/30 bg-emerald-500/10 px-2 py-0.5 text-[11px] text-emerald-300">
                      active · {strategy.activeMode}
                    </span>
                  )}
                </div>
                <p className="mt-1 text-sm text-trading-muted">{strategy.description}</p>
                <div className="mt-2 flex flex-wrap gap-2 text-[11px] text-trading-muted">
                  <span className="rounded-full border border-trading-border px-2 py-1">{strategy.symbol}</span>
                  <span className="rounded-full border border-trading-border px-2 py-1">{strategy.tradeStyle}</span>
                  <span className="rounded-full border border-trading-border px-2 py-1">{strategy.bestSession}</span>
                  <span className="rounded-full border border-trading-border px-2 py-1">{strategy.sourcePolicy}</span>
                </div>
              </div>
              <div className="grid min-w-[130px] grid-cols-2 gap-2 text-xs">
                <div className="rounded border border-trading-border p-2 text-center">
                  <div className="text-trading-muted">Win</div>
                  <div className="font-semibold text-trading-text">{strategy.performance.winRate}%</div>
                </div>
                <div className="rounded border border-trading-border p-2 text-center">
                  <div className="text-trading-muted">PF</div>
                  <div className="font-semibold text-trading-text">{strategy.performance.profitFactor}</div>
                </div>
              </div>
            </div>
            <div className="mt-3 flex gap-2">
              <button
                onClick={() => onSelectStrategy?.(strategy)}
                className="rounded-lg border border-trading-border px-3 py-1.5 text-sm font-medium text-trading-text"
              >
                Configure
              </button>
              <button
                onClick={() => onActivate(strategy, 'paper')}
                className="rounded-lg bg-trading-accent px-3 py-1.5 text-sm font-medium text-white"
              >
                Activate Paper
              </button>
              <button
                onClick={() => onActivate(strategy, 'live')}
                className="rounded-lg border border-trading-border px-3 py-1.5 text-sm font-medium text-trading-text"
              >
                Activate Live
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}