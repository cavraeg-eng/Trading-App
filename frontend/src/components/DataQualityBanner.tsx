interface DataQualityBannerProps {
  qualityFlags?: string[]
}

type BannerSeverity = 'info' | 'warning' | 'critical'

interface BannerItem {
  key: string
  message: string
  severity: BannerSeverity
}

function formatHoursToAgeLabel(hours: number) {
  if (hours < 1) {
    const minutes = Math.max(1, Math.round(hours * 60))
    return `~${minutes}m old`
  }
  if (hours < 10) return `~${hours.toFixed(1)}h old`
  return `~${Math.round(hours)}h old`
}

function parseMaxPercent(flag: string) {
  const match = flag.match(/max=([0-9.]+)%/)
  return match ? Number(match[1]) : null
}

function parseFlag(flag: string): BannerItem {
  if (flag.startsWith('stale_data:')) {
    const match = flag.match(/stale_data:([0-9.]+)h_old/)
    const hours = match ? Number(match[1]) : null
    return {
      key: 'stale_data',
      message: hours != null ? `Feed is stale (${formatHoursToAgeLabel(hours)}).` : 'Feed is stale.',
      severity: 'warning',
    }
  }

  if (flag === 'stale_data') {
    return {
      key: 'stale_data',
      message: 'Feed is delayed or stale.',
      severity: 'warning',
    }
  }

  if (flag === 'fallback_source') {
    return {
      key: 'fallback_source',
      message: 'Fallback data provider is active.',
      severity: 'warning',
    }
  }

  if (flag === 'synthetic_spot') {
    return {
      key: 'synthetic_spot',
      message: 'Spot view is derived from futures candles.',
      severity: 'info',
    }
  }

  if (flag.startsWith('futures_roll_gap:')) {
    const max = parseMaxPercent(flag)
    return {
      key: 'futures_roll_gap',
      message: max != null
        ? `Historical futures roll gap detected (max ${max.toFixed(1)}%).`
        : 'Historical futures roll gap detected.',
      severity: 'info',
    }
  }

  if (flag.startsWith('price_jump:')) {
    const max = parseMaxPercent(flag)
    return {
      key: 'price_jump',
      message: max != null
        ? `Large source price jump detected (max ${max.toFixed(1)}%).`
        : 'Large source price jump detected.',
      severity: 'warning',
    }
  }

  if (flag === 'mock_data') {
    return {
      key: 'mock_data',
      message: 'Mock data is being displayed.',
      severity: 'critical',
    }
  }

  if (flag.startsWith('nan_inf_values')) {
    return {
      key: 'nan_inf_values',
      message: 'Some candles contained invalid numeric values.',
      severity: 'warning',
    }
  }

  if (flag.startsWith('high_below_low')) {
    return {
      key: 'high_below_low',
      message: 'Some candles had inconsistent high/low values.',
      severity: 'warning',
    }
  }

  if (flag.startsWith('missing_columns')) {
    return {
      key: 'missing_columns',
      message: 'Source response was missing required columns.',
      severity: 'critical',
    }
  }

  if (flag === 'empty_or_none') {
    return {
      key: 'empty_or_none',
      message: 'No market data was returned.',
      severity: 'critical',
    }
  }

  return {
    key: flag,
    message: flag.replace(/_/g, ' '),
    severity: 'warning',
  }
}

function normalizeFlags(qualityFlags: string[]) {
  const mapped = qualityFlags.map(parseFlag)
  const deduped = new Map<string, BannerItem>()

  for (const item of mapped) {
    if (!deduped.has(item.key) || item.message.includes('(')) {
      deduped.set(item.key, item)
    }
  }

  return Array.from(deduped.values())
}

function bannerTone(items: BannerItem[]) {
  if (items.some((item) => item.severity === 'critical')) {
    return {
      title: 'Data quality warning',
      cls: 'border-red-500/30 bg-red-500/10 text-red-200',
      dot: 'bg-red-300',
    }
  }

  if (items.some((item) => item.severity === 'warning')) {
    return {
      title: 'Data quality warning',
      cls: 'border-amber-500/30 bg-amber-500/10 text-amber-200',
      dot: 'bg-amber-300',
    }
  }

  return {
    title: 'Data quality note',
    cls: 'border-blue-500/30 bg-blue-500/10 text-blue-200',
    dot: 'bg-blue-300',
  }
}

export function DataQualityBanner({ qualityFlags = [] }: DataQualityBannerProps) {
  const items = normalizeFlags(qualityFlags)
  if (!items.length) return null

  const tone = bannerTone(items)

  return (
    <div className={`rounded-lg border px-3 py-2 text-xs ${tone.cls}`}>
      <div className="mb-1 font-semibold">{tone.title}</div>
      <ul className="space-y-1">
        {items.map((item) => (
          <li key={item.key} className="flex items-start gap-2">
            <span className={`mt-1.5 inline-flex h-1.5 w-1.5 shrink-0 rounded-full ${tone.dot}`} />
            <span>{item.message}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}