import { useState, useEffect, useRef } from 'react'
import { CalendarDays } from 'lucide-react'
import type { ForexPair } from '../types'

interface EconomicCalendarProps {
  selectedPair: ForexPair
}

interface EconomicEvent {
  id: string
  name: string
  currency: string
  impact: 'high' | 'medium' | 'low'
  category: string
  previous?: string
  forecast?: string
  date: Date
}

interface EventTemplate {
  name: string
  currency: string
  impact: 'high' | 'medium' | 'low'
  category: string
  dayOfMonth: number        // approximate recurring day
  monthInterval: number     // 1 = monthly, 3 = quarterly
  previous?: string
  forecast?: string
}

const EVENT_TEMPLATES: EventTemplate[] = [
  // USD
  { name: 'FOMC Rate Decision', currency: 'USD', impact: 'high', category: 'Interest Rate', dayOfMonth: 15, monthInterval: 1, previous: '5.50%', forecast: '5.50%' },
  { name: 'Non-Farm Payrolls', currency: 'USD', impact: 'high', category: 'Employment', dayOfMonth: 7, monthInterval: 1, previous: '216K', forecast: '200K' },
  { name: 'US CPI', currency: 'USD', impact: 'high', category: 'Inflation', dayOfMonth: 12, monthInterval: 1, previous: '3.2%', forecast: '3.1%' },
  { name: 'US PPI', currency: 'USD', impact: 'medium', category: 'Inflation', dayOfMonth: 14, monthInterval: 1, previous: '0.2%', forecast: '0.1%' },
  { name: 'US GDP', currency: 'USD', impact: 'high', category: 'GDP', dayOfMonth: 25, monthInterval: 3, previous: '4.9%', forecast: '3.2%' },
  { name: 'ISM Manufacturing PMI', currency: 'USD', impact: 'high', category: 'PMI', dayOfMonth: 1, monthInterval: 1, previous: '49.2', forecast: '49.8' },
  { name: 'US Retail Sales', currency: 'USD', impact: 'medium', category: 'Consumer', dayOfMonth: 16, monthInterval: 1, previous: '0.7%', forecast: '0.4%' },
  { name: 'US Unemployment Claims', currency: 'USD', impact: 'medium', category: 'Employment', dayOfMonth: 20, monthInterval: 1, previous: '210K', forecast: '215K' },
  // EUR
  { name: 'ECB Rate Decision', currency: 'EUR', impact: 'high', category: 'Interest Rate', dayOfMonth: 11, monthInterval: 1, previous: '4.50%', forecast: '4.50%' },
  { name: 'Eurozone CPI', currency: 'EUR', impact: 'high', category: 'Inflation', dayOfMonth: 2, monthInterval: 1, previous: '2.9%', forecast: '2.7%' },
  { name: 'German PMI', currency: 'EUR', impact: 'medium', category: 'PMI', dayOfMonth: 22, monthInterval: 1, previous: '43.3', forecast: '44.0' },
  { name: 'Eurozone GDP', currency: 'EUR', impact: 'medium', category: 'GDP', dayOfMonth: 28, monthInterval: 3, previous: '0.1%', forecast: '0.2%' },
  // GBP
  { name: 'BOE Rate Decision', currency: 'GBP', impact: 'high', category: 'Interest Rate', dayOfMonth: 8, monthInterval: 1, previous: '5.25%', forecast: '5.25%' },
  { name: 'UK CPI', currency: 'GBP', impact: 'high', category: 'Inflation', dayOfMonth: 17, monthInterval: 1, previous: '4.0%', forecast: '3.8%' },
  { name: 'UK GDP', currency: 'GBP', impact: 'medium', category: 'GDP', dayOfMonth: 10, monthInterval: 3, previous: '-0.1%', forecast: '0.2%' },
  { name: 'UK PMI', currency: 'GBP', impact: 'medium', category: 'PMI', dayOfMonth: 23, monthInterval: 1, previous: '47.5', forecast: '48.0' },
  // JPY
  { name: 'BOJ Rate Decision', currency: 'JPY', impact: 'high', category: 'Interest Rate', dayOfMonth: 19, monthInterval: 1, previous: '-0.10%', forecast: '-0.10%' },
  { name: 'Japan CPI', currency: 'JPY', impact: 'medium', category: 'Inflation', dayOfMonth: 21, monthInterval: 1, previous: '2.8%', forecast: '2.6%' },
  { name: 'Tankan Survey', currency: 'JPY', impact: 'medium', category: 'Sentiment', dayOfMonth: 1, monthInterval: 3, previous: '9', forecast: '10' },
  // AUD
  { name: 'RBA Rate Decision', currency: 'AUD', impact: 'high', category: 'Interest Rate', dayOfMonth: 6, monthInterval: 1, previous: '4.35%', forecast: '4.35%' },
  { name: 'Australian Employment', currency: 'AUD', impact: 'medium', category: 'Employment', dayOfMonth: 18, monthInterval: 1, previous: '61.5K', forecast: '25.0K' },
  { name: 'Australian CPI', currency: 'AUD', impact: 'high', category: 'Inflation', dayOfMonth: 24, monthInterval: 3, previous: '5.4%', forecast: '4.3%' },
  // CAD
  { name: 'BOC Rate Decision', currency: 'CAD', impact: 'high', category: 'Interest Rate', dayOfMonth: 9, monthInterval: 1, previous: '5.00%', forecast: '5.00%' },
  { name: 'Canadian CPI', currency: 'CAD', impact: 'medium', category: 'Inflation', dayOfMonth: 19, monthInterval: 1, previous: '3.1%', forecast: '2.9%' },
  { name: 'Canadian Employment', currency: 'CAD', impact: 'medium', category: 'Employment', dayOfMonth: 8, monthInterval: 1, previous: '0.1K', forecast: '15.0K' },
  // CHF
  { name: 'SNB Rate Decision', currency: 'CHF', impact: 'high', category: 'Interest Rate', dayOfMonth: 13, monthInterval: 3, previous: '1.75%', forecast: '1.75%' },
  // NZD
  { name: 'RBNZ Rate Decision', currency: 'NZD', impact: 'high', category: 'Interest Rate', dayOfMonth: 10, monthInterval: 1, previous: '5.50%', forecast: '5.50%' },
  // CNY
  { name: 'Chinese PMI', currency: 'CNY', impact: 'medium', category: 'PMI', dayOfMonth: 30, monthInterval: 1, previous: '50.3', forecast: '50.5' },
  { name: 'Chinese CPI', currency: 'CNY', impact: 'medium', category: 'Inflation', dayOfMonth: 9, monthInterval: 1, previous: '-0.3%', forecast: '-0.1%' },
]

const INDEX_CURRENCY_MAP: Record<string, string> = {
  US30: 'USD', US500: 'USD', US100: 'USD', NAS100: 'USD',
  UK100: 'GBP', DE40: 'EUR', JP225: 'JPY', AU200: 'AUD',
}

function extractCurrencies(pair: ForexPair): string[] {
  const sym = pair.symbol

  // Indices
  for (const [idx, cur] of Object.entries(INDEX_CURRENCY_MAP)) {
    if (sym.startsWith(idx)) return [cur]
  }

  // Commodities / Crypto – only care about quote currency
  if (pair.category === 'commodity' || pair.category === 'crypto') {
    const parts = sym.split('/')
    return parts.length > 1 ? [parts[1]] : ['USD']
  }

  // Standard forex pair
  const parts = sym.split('/')
  if (parts.length === 2) return parts
  return [sym.slice(0, 3), sym.slice(3, 6)]
}

function generateUpcomingEvents(currencies: string[]): EconomicEvent[] {
  const now = new Date()
  const events: EconomicEvent[] = []
  const currSet = new Set(currencies.map(c => c.toUpperCase()))

  for (const tmpl of EVENT_TEMPLATES) {
    if (!currSet.has(tmpl.currency)) continue

    // Find next occurrence
    for (let offset = 0; offset < 3; offset++) {
      const candidate = new Date(now.getFullYear(), now.getMonth() + offset, tmpl.dayOfMonth)
      if (candidate > now) {
        // For quarterly events, only emit if month aligns
        if (tmpl.monthInterval === 3 && candidate.getMonth() % 3 !== 0) continue
        events.push({
          id: `${tmpl.currency}-${tmpl.name}-${candidate.getTime()}`,
          name: tmpl.name,
          currency: tmpl.currency,
          impact: tmpl.impact,
          category: tmpl.category,
          previous: tmpl.previous,
          forecast: tmpl.forecast,
          date: candidate,
        })
        break
      }
    }
  }

  events.sort((a, b) => a.date.getTime() - b.date.getTime())
  return events.slice(0, 6)
}

function formatEventDate(d: Date): string {
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

const impactStyles: Record<string, { dot: string; text: string }> = {
  high:   { dot: 'bg-red-500',   text: 'text-red-400' },
  medium: { dot: 'bg-amber-500', text: 'text-amber-400' },
  low:    { dot: 'bg-blue-500',  text: 'text-blue-400' },
}

export function EconomicCalendar({ selectedPair }: EconomicCalendarProps) {
  const [events, setEvents] = useState<EconomicEvent[]>([])
  const [countdown, setCountdown] = useState<string>('')
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    const currencies = extractCurrencies(selectedPair)
    setEvents(generateUpcomingEvents(currencies))
  }, [selectedPair.symbol])

  useEffect(() => {
    if (intervalRef.current) {
      clearInterval(intervalRef.current)
      intervalRef.current = null
    }

    if (events.length === 0) {
      setCountdown('')
      return
    }

    const nextEvent = events[0]
    const eventTime = new Date(nextEvent.date)
    eventTime.setUTCHours(13, 30, 0, 0)

    const updateCountdown = () => {
      const now = new Date()
      const diff = eventTime.getTime() - now.getTime()

      if (diff <= 0) {
        setCountdown('Now')
        return
      }

      const days = Math.floor(diff / (1000 * 60 * 60 * 24))
      const hours = Math.floor((diff % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60))
      const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60))
      const seconds = Math.floor((diff % (1000 * 60)) / 1000)

      if (days > 0) {
        setCountdown(`${days}d ${hours}h ${minutes}m`)
      } else if (hours > 0) {
        setCountdown(`${hours}h ${minutes}m ${seconds}s`)
      } else {
        setCountdown(`${minutes}m ${seconds}s`)
      }
    }

    updateCountdown()
    intervalRef.current = setInterval(updateCountdown, 1000)
    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current)
        intervalRef.current = null
      }
    }
  }, [events])

  return (
    <div className="bg-trading-card border border-trading-border rounded-lg p-4">
      <h3 className="text-sm font-semibold mb-3 flex items-center gap-2">
        <CalendarDays size={16} />
        Economic Calendar
        {countdown && (
          <span className="ml-auto text-[10px] font-mono px-2 py-0.5 rounded bg-trading-bg text-trading-accent">
            Next: {countdown}
          </span>
        )}
      </h3>

      {events.length === 0 ? (
        <p className="text-trading-muted text-center py-4 text-sm">
          No upcoming events for {selectedPair.symbol}
        </p>
      ) : (
        <div className="space-y-1">
          {events.map((evt, index) => {
            const style = impactStyles[evt.impact]
            const isNext = index === 0
            return (
              <div
                key={evt.id}
                className={`flex items-center gap-3 px-3 py-2 rounded-md transition-colors hover:bg-trading-bg/60${isNext ? ' border-l-2 border-trading-accent bg-trading-accent/5' : ''}`}
              >
                <span className="text-xs text-trading-muted w-14 shrink-0">{formatEventDate(evt.date)}</span>
                <span className="text-sm text-trading-text flex-1 truncate">{evt.name}</span>
                <span className="flex items-center gap-1.5 shrink-0">
                  <span className={`w-2 h-2 rounded-full ${style.dot}`} />
                  <span className={`text-xs capitalize ${style.text}`}>{evt.impact}</span>
                </span>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

export default EconomicCalendar
