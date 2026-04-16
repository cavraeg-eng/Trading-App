import type { DatasourceHealthResponse } from '../types'

interface SpotProviderStatusCardProps {
  health: DatasourceHealthResponse | null
}

function statusClass(available: boolean) {
  return available
    ? 'text-emerald-300 bg-emerald-500/10 border-emerald-500/30'
    : 'text-red-300 bg-red-500/10 border-red-500/30'
}

export function SpotProviderStatusCard({ health }: SpotProviderStatusCardProps) {
  if (!health) return null

  const providers = Object.entries(health.spotProviders || {})
  if (!providers.length) return null

  return (
    <div className="bg-trading-card border border-trading-border rounded-lg p-4">
      <h3 className="text-sm font-semibold mb-3 text-trading-text">Spot Providers</h3>
      <div className="space-y-2">
        {providers.map(([name, provider]) => (
          <div key={name} className="flex items-center justify-between gap-3">
            <span className="text-sm text-trading-muted">{name}</span>
            <span className={`rounded-full border px-2 py-1 text-[11px] font-medium ${statusClass(provider.available)}`}>
              {provider.available ? 'available' : `cooldown ${Math.ceil(provider.cooldownRemainingSeconds)}s`}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}