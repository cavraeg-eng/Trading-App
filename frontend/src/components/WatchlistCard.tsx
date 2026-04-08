import { useState, useEffect, useRef } from 'react'
import { Eye } from 'lucide-react'
import type { ForexPair } from '../types'

interface WatchlistCardProps {
  pairs: ForexPair[]
  selectedPair: ForexPair
  onPairChange: (pair: ForexPair) => void
}

interface WatchlistData {
  price: number
  change: number
  changePercent: number
  signal: string
}

function formatWatchlistPrice(price: number): string {
  if (price < 10) return price.toFixed(5)
  if (price < 200) return price.toFixed(3)
  return price.toFixed(2)
}

function getSignalBadgeClasses(signal: string): string {
  const s = signal.toLowerCase()
  if (s === 'buy' || s === 'strong_buy') return 'bg-emerald-500/20 text-emerald-400'
  if (s === 'sell' || s === 'strong_sell') return 'bg-red-500/20 text-red-400'
  return 'bg-amber-500/20 text-amber-400'
}

function formatSignalLabel(signal: string): string {
  const s = signal.toLowerCase()
  if (s === 'strong_buy') return 'BUY'
  if (s === 'strong_sell') return 'SELL'
  return signal.toUpperCase()
}

export function WatchlistCard({ pairs, selectedPair, onPairChange }: WatchlistCardProps) {
  const [data, setData] = useState<Record<string, WatchlistData>>({})
  const [loading, setLoading] = useState(true)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const displayPairs = pairs.slice(0, 6)

  useEffect(() => {
    if (displayPairs.length === 0) {
      setLoading(false)
      return
    }

    const fetchAll = async () => {
      setLoading(true)
      const results = await Promise.allSettled(
        displayPairs.map(async (pair) => {
          const res = await fetch(`/api/market/analysis/${encodeURIComponent(pair.symbol)}?timeframe=1h`)
          if (!res.ok) throw new Error(`Failed: ${res.status}`)
          const json = await res.json()
          return {
            symbol: pair.symbol,
            price: json.currentPrice ?? pair.basePriceApprox,
            change: json.priceChange ?? 0,
            changePercent: json.priceChangePercent ?? 0,
            signal: json.signal ?? 'hold',
          }
        })
      )

      const map: Record<string, WatchlistData> = {}
      results.forEach((r) => {
        if (r.status === 'fulfilled') {
          const { symbol, ...rest } = r.value
          map[symbol] = rest
        }
      })
      setData(map)
      setLoading(false)
    }

    fetchAll()
    intervalRef.current = setInterval(fetchAll, 60000)
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current)
    }
  }, [pairs.map(p => p.symbol).join(',')])

  return (
    <div className="bg-trading-card border border-trading-border rounded-lg p-4">
      <h3 className="text-sm font-semibold mb-3 flex items-center gap-2">
        <Eye size={16} />
        Watchlist
      </h3>

      {displayPairs.length === 0 ? (
        <p className="text-trading-muted text-center py-4 text-sm">
          Add pairs to your watchlist
        </p>
      ) : loading ? (
        <div className="space-y-2">
          {displayPairs.map((p) => (
            <div key={p.symbol} className="h-9 bg-trading-bg rounded animate-pulse" />
          ))}
        </div>
      ) : (
        <div className="space-y-1">
          {displayPairs.map((pair) => {
            const info = data[pair.symbol]
            const isSelected = pair.symbol === selectedPair.symbol
            const price = info?.price ?? pair.basePriceApprox
            const changePct = info?.changePercent ?? 0
            const signal = info?.signal ?? 'hold'

            return (
              <button
                key={pair.symbol}
                onClick={() => onPairChange(pair)}
                className={`w-full flex items-center justify-between px-3 py-2 rounded-md text-sm transition-colors hover:bg-trading-bg/60 ${
                  isSelected ? 'bg-trading-accent/10' : ''
                }`}
              >
                <span className="font-semibold text-trading-text w-20 text-left">{pair.symbol}</span>
                <span className="text-trading-text tabular-nums">{formatWatchlistPrice(price)}</span>
                <span className={`tabular-nums text-xs w-16 text-right ${changePct >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                  {changePct >= 0 ? '+' : ''}{changePct.toFixed(2)}%
                </span>
                <span className={`text-[10px] px-1.5 py-0.5 rounded ml-2 ${getSignalBadgeClasses(signal)}`}>
                  {formatSignalLabel(signal)}
                </span>
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}

export default WatchlistCard
