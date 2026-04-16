interface FreshnessPillProps {
  freshnessSeconds?: number | null
  marketStatus?: string
}

function formatLabel(freshnessSeconds?: number | null, marketStatus?: string) {
  if (freshnessSeconds == null) return marketStatus ?? 'unknown'
  if (freshnessSeconds < 60) return `live · ${Math.round(freshnessSeconds)}s`
  if (freshnessSeconds < 3600) return `${marketStatus ?? 'delayed'} · ${Math.round(freshnessSeconds / 60)}m`
  return `${marketStatus ?? 'stale'} · ${Math.round(freshnessSeconds / 3600)}h`
}

function classFor(status?: string) {
  if (status === 'live') return 'bg-emerald-500/10 text-emerald-300 border border-emerald-500/30'
  if (status === 'delayed') return 'bg-yellow-500/10 text-yellow-300 border border-yellow-500/30'
  return 'bg-red-500/10 text-red-300 border border-red-500/30'
}

export function FreshnessPill({ freshnessSeconds, marketStatus }: FreshnessPillProps) {
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-1 text-[11px] font-medium ${classFor(marketStatus)}`}>
      {formatLabel(freshnessSeconds, marketStatus)}
    </span>
  )
}