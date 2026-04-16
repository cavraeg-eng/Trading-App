interface DataSourceBadgeProps {
  sourceType?: string
  sourceName?: string
  contextLabel?: string
}

function labelFor(sourceType?: string, sourceName?: string) {
  if (sourceType === 'synthetic_spot_from_futures') return `Synthetic Spot · ${sourceName ?? 'spot_adjusted'}`
  if (sourceType === 'futures') return `Futures · ${sourceName ?? 'yfinance'}`
  if (sourceType === 'mock') return 'Mock Data'
  return sourceName ?? sourceType ?? 'Unknown'
}

function classFor(sourceType?: string) {
  if (sourceType === 'synthetic_spot_from_futures') return 'bg-amber-500/10 text-amber-300 border border-amber-500/30'
  if (sourceType === 'futures') return 'bg-blue-500/10 text-blue-300 border border-blue-500/30'
  if (sourceType === 'mock') return 'bg-slate-500/10 text-slate-300 border border-slate-500/30'
  return 'bg-zinc-500/10 text-zinc-300 border border-zinc-500/30'
}

export function DataSourceBadge({ sourceType, sourceName, contextLabel }: DataSourceBadgeProps) {
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-1 text-[11px] font-medium ${classFor(sourceType)}`}>
      {contextLabel ? `${contextLabel} · ` : ''}{labelFor(sourceType, sourceName)}
    </span>
  )
}