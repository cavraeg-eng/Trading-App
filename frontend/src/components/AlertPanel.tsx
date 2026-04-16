import { useState, useEffect } from 'react'
import { Zap, Grid3X3, Layers, TrendingUp, CheckCheck, Inbox } from 'lucide-react'
import { api } from '../lib/api'
import type { SmartAlert } from '../types'

const ALERT_TYPE_CONFIG: Record<SmartAlert['alert_type'], { color: string; bg: string; icon: typeof Zap }> = {
  STRONG_SIGNAL:   { color: 'text-green-400',  bg: 'bg-green-400/10',  icon: Zap },
  PATTERN_COMPLETE:{ color: 'text-blue-400',   bg: 'bg-blue-400/10',   icon: Grid3X3 },
  MULTITF_ALIGNED: { color: 'text-purple-400', bg: 'bg-purple-400/10', icon: Layers },
  SCORE_CHANGE:    { color: 'text-orange-400', bg: 'bg-orange-400/10', icon: TrendingUp },
  SCANNER_MATCH:   { color: 'text-cyan-400',   bg: 'bg-cyan-400/10',   icon: Layers },
}

function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime()
  const secs = Math.floor(diff / 1000)
  if (secs < 60) return 'just now'
  const mins = Math.floor(secs / 60)
  if (mins < 60) return `${mins} min ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  const days = Math.floor(hrs / 24)
  return `${days}d ago`
}

interface AlertPanelProps {
  onClose: () => void
  onAlertsChanged: () => void
}

export default function AlertPanel({ onClose: _onClose, onAlertsChanged }: AlertPanelProps) {
  const [alerts, setAlerts] = useState<SmartAlert[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.fetchAlerts(undefined, 20)
      .then(setAlerts)
      .catch(() => setAlerts([]))
      .finally(() => setLoading(false))
  }, [])

  const handleMarkRead = async (alertId: number) => {
    await api.markAlertRead(alertId)
    setAlerts(prev => prev.map(a => a.id === alertId ? { ...a, read: 1 } : a))
    onAlertsChanged()
  }

  const handleMarkAllRead = async () => {
    await api.markAllAlertsRead()
    setAlerts(prev => prev.map(a => ({ ...a, read: 1 })))
    onAlertsChanged()
  }

  return (
    <div className="absolute right-0 top-full mt-2 w-96 bg-trading-card border border-trading-border rounded-lg shadow-xl z-50">
      {/* Header */}
      <div className="flex items-center justify-between p-3 border-b border-trading-border">
        <span className="text-sm font-semibold text-trading-text">Alerts</span>
        <button
          onClick={handleMarkAllRead}
          className="flex items-center gap-1 text-xs text-trading-accent hover:text-trading-accent/80 transition-colors"
        >
          <CheckCheck size={14} />
          Mark all read
        </button>
      </div>

      {/* Alert list */}
      <div className="max-h-[400px] overflow-y-auto">
        {loading ? (
          <div className="flex items-center justify-center py-10 text-trading-muted text-sm">Loading...</div>
        ) : alerts.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-10 text-trading-muted">
            <Inbox size={32} className="mb-2 opacity-50" />
            <span className="text-sm">No alerts yet</span>
          </div>
        ) : (
          alerts.map(alert => {
            const cfg = ALERT_TYPE_CONFIG[alert.alert_type]
            const Icon = cfg.icon
            return (
              <button
                key={alert.id}
                onClick={() => alert.read === 0 && handleMarkRead(alert.id)}
                className={`w-full text-left flex gap-3 p-3 border-b border-trading-border/50 hover:bg-trading-border/30 transition-colors ${
                  alert.read === 0 ? 'bg-trading-border/10' : ''
                }`}
              >
                <div className={`flex-shrink-0 w-8 h-8 rounded-md flex items-center justify-center ${cfg.bg}`}>
                  <Icon size={16} className={cfg.color} />
                </div>
                <div className="flex-1 min-w-0">
                  <p className={`text-sm leading-tight ${alert.read === 0 ? 'font-semibold text-trading-text' : 'text-trading-muted'}`}>
                    {alert.title}
                  </p>
                  <p className="text-xs text-trading-muted mt-0.5 line-clamp-2">{alert.message}</p>
                  <p className="text-[10px] text-trading-muted/60 mt-1">{relativeTime(alert.created_at)}</p>
                </div>
                {alert.read === 0 && (
                  <span className="flex-shrink-0 w-2 h-2 rounded-full bg-trading-accent mt-1.5" />
                )}
              </button>
            )
          })
        )}
      </div>
    </div>
  )
}
