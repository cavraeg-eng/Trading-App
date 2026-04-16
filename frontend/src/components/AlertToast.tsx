import { useState, useCallback } from 'react'
import { Zap, Grid3X3, Layers, TrendingUp, X } from 'lucide-react'
import type { SmartAlert } from '../types'

const ALERT_TYPE_ICON: Record<SmartAlert['alert_type'], { color: string; icon: typeof Zap }> = {
  STRONG_SIGNAL:   { color: 'text-green-400',  icon: Zap },
  PATTERN_COMPLETE:{ color: 'text-blue-400',   icon: Grid3X3 },
  MULTITF_ALIGNED: { color: 'text-purple-400', icon: Layers },
  SCORE_CHANGE:    { color: 'text-orange-400', icon: TrendingUp },
  SCANNER_MATCH:   { color: 'text-cyan-400',   icon: Layers },
}

interface ToastItem {
  id: number
  alert: SmartAlert
  visible: boolean
}

let nextToastId = 0

export function useAlertToast() {
  const [toasts, setToasts] = useState<ToastItem[]>([])

  const showToast = useCallback((alert: SmartAlert) => {
    const toastId = nextToastId++
    setToasts(prev => [...prev, { id: toastId, alert, visible: false }])

    // Trigger slide-in on next frame
    requestAnimationFrame(() => {
      setToasts(prev => prev.map(t => t.id === toastId ? { ...t, visible: true } : t))
    })

    // Auto-dismiss after 5s
    setTimeout(() => {
      setToasts(prev => prev.map(t => t.id === toastId ? { ...t, visible: false } : t))
      setTimeout(() => {
        setToasts(prev => prev.filter(t => t.id !== toastId))
      }, 300) // wait for slide-out transition
    }, 5000)
  }, [])

  const dismissToast = useCallback((toastId: number) => {
    setToasts(prev => prev.map(t => t.id === toastId ? { ...t, visible: false } : t))
    setTimeout(() => {
      setToasts(prev => prev.filter(t => t.id !== toastId))
    }, 300)
  }, [])

  return { toasts, showToast, dismissToast }
}

interface AlertToastContainerProps {
  toasts: ToastItem[]
  onDismiss: (id: number) => void
}

export default function AlertToastContainer({ toasts, onDismiss }: AlertToastContainerProps) {
  if (toasts.length === 0) return null

  return (
    <div className="fixed bottom-4 right-4 z-[100] flex flex-col-reverse gap-2 pointer-events-none">
      {toasts.map(toast => {
        const cfg = ALERT_TYPE_ICON[toast.alert.alert_type]
        const Icon = cfg.icon
        return (
          <div
            key={toast.id}
            className={`pointer-events-auto flex items-start gap-3 w-80 p-3 bg-trading-card border border-trading-border rounded-lg shadow-2xl transition-all duration-300 ${
              toast.visible ? 'translate-x-0 opacity-100' : 'translate-x-full opacity-0'
            }`}
          >
            <Icon size={18} className={`flex-shrink-0 mt-0.5 ${cfg.color}`} />
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-trading-text truncate">{toast.alert.title}</p>
              <p className="text-xs text-trading-muted truncate">{toast.alert.symbol}</p>
            </div>
            <button
              onClick={() => onDismiss(toast.id)}
              className="flex-shrink-0 text-trading-muted hover:text-trading-text transition-colors"
            >
              <X size={14} />
            </button>
          </div>
        )
      })}
    </div>
  )
}

export interface SimpleToast {
  id: number
  title: string
  message?: string
  tone?: 'info' | 'success' | 'warning' | 'error'
  visible: boolean
}

let nextSimpleToastId = 10_000

export function useSimpleToast() {
  const [toasts, setToasts] = useState<SimpleToast[]>([])

  const showToast = useCallback((toast: Omit<SimpleToast, 'id' | 'visible'>) => {
    const toastId = nextSimpleToastId++
    setToasts(prev => [...prev, { id: toastId, visible: false, ...toast }])
    requestAnimationFrame(() => {
      setToasts(prev => prev.map(t => (t.id === toastId ? { ...t, visible: true } : t)))
    })
    setTimeout(() => {
      setToasts(prev => prev.map(t => (t.id === toastId ? { ...t, visible: false } : t)))
      setTimeout(() => {
        setToasts(prev => prev.filter(t => t.id !== toastId))
      }, 300)
    }, 4000)
  }, [])

  const dismissToast = useCallback((toastId: number) => {
    setToasts(prev => prev.map(t => (t.id === toastId ? { ...t, visible: false } : t)))
    setTimeout(() => {
      setToasts(prev => prev.filter(t => t.id !== toastId))
    }, 300)
  }, [])

  return { toasts, showToast, dismissToast }
}

const SIMPLE_TONE_STYLES: Record<NonNullable<SimpleToast['tone']>, string> = {
  info: 'border-blue-500/40',
  success: 'border-emerald-500/40',
  warning: 'border-yellow-500/40',
  error: 'border-red-500/40',
}

interface SimpleToastContainerProps {
  toasts: SimpleToast[]
  onDismiss: (id: number) => void
}

export function SimpleToastContainer({ toasts, onDismiss }: SimpleToastContainerProps) {
  if (toasts.length === 0) return null

  return (
    <div className="fixed top-4 right-4 z-[100] flex flex-col gap-2 pointer-events-none">
      {toasts.map(toast => (
        <div
          key={toast.id}
          className={`pointer-events-auto w-96 rounded-lg border bg-trading-card p-4 shadow-2xl transition-all duration-300 ${
            SIMPLE_TONE_STYLES[toast.tone ?? 'info']
          } ${toast.visible ? 'translate-y-0 opacity-100' : '-translate-y-3 opacity-0'}`}
        >
          <div className="flex items-start gap-3">
            <div className="min-w-0 flex-1">
              <p className="text-sm font-semibold text-trading-text">{toast.title}</p>
              {toast.message ? <p className="mt-1 text-xs text-trading-muted">{toast.message}</p> : null}
            </div>
            <button
              onClick={() => onDismiss(toast.id)}
              className="text-trading-muted transition-colors hover:text-trading-text"
            >
              <X size={14} />
            </button>
          </div>
        </div>
      ))}
    </div>
  )
}
