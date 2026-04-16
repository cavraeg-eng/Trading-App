import { ArrowRight } from 'lucide-react'
import type { OpportunityRow } from '../types'
import { DataSourceBadge } from './DataSourceBadge'

interface OpportunityBoardProps {
  title: string
  rows: OpportunityRow[]
  onSelectSymbol?: (symbol: string) => void
}

function signalColor(signal: string) {
  if (signal === 'buy' || signal === 'BUY' || signal === 'strong_buy') return 'text-emerald-400'
  if (signal === 'sell' || signal === 'SELL' || signal === 'strong_sell') return 'text-red-400'
  return 'text-yellow-400'
}

export function OpportunityBoard({ title, rows, onSelectSymbol }: OpportunityBoardProps) {
  if (!rows.length) return null

  return (
    <div className="bg-trading-card border border-trading-border rounded-lg p-4">
      <h3 className="text-sm font-semibold mb-3 text-trading-text">{title}</h3>
      <div className="space-y-3">
        {rows.slice(0, 5).map((row) => (
          <button
            key={`${row.symbol}-${row.timeframe}-${row.tradeStyle}`}
            onClick={() => onSelectSymbol?.(row.symbol)}
            className="w-full rounded-lg border border-trading-border bg-trading-bg p-3 text-left transition-colors hover:border-trading-accent/50"
          >
            <div className="mb-2 flex items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <span className="font-semibold text-trading-text">{row.symbol}</span>
                <span className={`text-xs font-medium uppercase ${signalColor(row.signal)}`}>
                  {row.signal}
                </span>
              </div>
              <div className="flex items-center gap-1 text-trading-muted">
                <span className="text-sm font-semibold text-trading-text">{Math.round(row.opportunityScore)}%</span>
                <ArrowRight size={14} />
              </div>
            </div>
            <div className="mb-2 flex flex-wrap items-center gap-2">
              <DataSourceBadge
                sourceType={row.sourceMetadata?.sourceType}
                sourceName={row.sourceMetadata?.sourceName}
                contextLabel={row.tradeStyle === 'scalp' ? 'Scalp Mode' : row.symbol === 'XAU/USD' ? 'Swing Mode' : undefined}
              />
              <span className="rounded-full border border-trading-border px-2 py-1 text-[11px] text-trading-muted">
                {row.tradeStyle} · {row.timeframe}
              </span>
              <span className="rounded-full border border-trading-border px-2 py-1 text-[11px] text-trading-muted">
                {row.marketRegime}
              </span>
            </div>
            <div className="grid grid-cols-3 gap-2 text-xs">
              <div>
                <div className="text-trading-muted">Confidence</div>
                <div className="font-semibold text-trading-text">{row.confidence}%</div>
              </div>
              <div>
                <div className="text-trading-muted">AI Score</div>
                <div className="font-semibold text-trading-text">{Math.round(row.aiScore)}%</div>
              </div>
              <div>
                <div className="text-trading-muted">Source Score</div>
                <div className="font-semibold text-trading-text">{Math.round(row.sourceScore)}%</div>
              </div>
            </div>
            <div className="mt-2 line-clamp-2 text-xs text-trading-muted">{row.reason}</div>
          </button>
        ))}
      </div>
    </div>
  )
}