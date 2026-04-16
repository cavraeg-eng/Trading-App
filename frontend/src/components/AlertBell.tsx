import { useState, useEffect, useRef } from 'react'
import { Bell } from 'lucide-react'
import AlertPanel from './AlertPanel'

interface AlertBellProps {
  unreadCount: number
  onCountRefresh: () => void
}

export default function AlertBell({ unreadCount, onCountRefresh }: AlertBellProps) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  // Close panel when clicking outside
  useEffect(() => {
    if (!open) return
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [open])

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen(prev => !prev)}
        className="relative p-2 rounded-lg text-trading-muted hover:text-trading-text hover:bg-trading-border/40 transition-colors"
        aria-label="Alerts"
      >
        <Bell size={20} />
        {unreadCount > 0 && (
          <span className="absolute -top-0.5 -right-0.5 min-w-[18px] h-[18px] flex items-center justify-center rounded-full bg-red-500 text-white text-[10px] font-bold px-1">
            {unreadCount > 99 ? '99+' : unreadCount}
          </span>
        )}
      </button>

      {open && (
        <AlertPanel
          onClose={() => setOpen(false)}
          onAlertsChanged={onCountRefresh}
        />
      )}
    </div>
  )
}
