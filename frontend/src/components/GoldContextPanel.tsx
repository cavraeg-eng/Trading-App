import type { GoldContextData } from '../types'

interface GoldContextPanelProps {
  context: GoldContextData | null
}

function fmt(value: number | null | undefined, digits = 2) {
  if (value == null || Number.isNaN(value)) return '—'
  return value.toFixed(digits)
}

export function GoldContextPanel({ context }: GoldContextPanelProps) {
  if (!context) return null

  return (
    <div className="rounded-xl border border-trading-border bg-trading-surface p-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-trading-text">Gold Context</h3>
        <span className="text-xs text-trading-muted">{context.session}</span>
      </div>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
        <div className="rounded-lg bg-trading-bg p-3">
          <div className="text-[11px] text-trading-muted">Gold</div>
          <div className="text-sm font-semibold text-trading-text">{fmt(context.gold.value)}</div>
        </div>
        <div className="rounded-lg bg-trading-bg p-3">
          <div className="text-[11px] text-trading-muted">DXY</div>
          <div className="text-sm font-semibold text-trading-text">{fmt(context.dxy.value)}</div>
          <div className="text-[11px] text-trading-muted">{fmt(context.dxy.change, 3)}</div>
        </div>
        <div className="rounded-lg bg-trading-bg p-3">
          <div className="text-[11px] text-trading-muted">10Y Yield</div>
          <div className="text-sm font-semibold text-trading-text">{fmt(context.yields10y.value)}</div>
          <div className="text-[11px] text-trading-muted">{fmt(context.yields10y.change, 3)}</div>
        </div>
        <div className="rounded-lg bg-trading-bg p-3">
          <div className="text-[11px] text-trading-muted">Volatility</div>
          <div className="text-sm font-semibold text-trading-text">{context.volatilityRegime}</div>
        </div>
        <div className="rounded-lg bg-trading-bg p-3">
          <div className="text-[11px] text-trading-muted">Macro Risk</div>
          <div className="text-sm font-semibold text-trading-text">{context.macroRisk}</div>
        </div>
      </div>
    </div>
  )
}