import { useMemo, useState } from 'react'
import type { AutomationCenterState } from '../types'

interface AutomationCenterCardProps {
  automationCenter: AutomationCenterState | null
}

export function AutomationCenterCard({ automationCenter }: AutomationCenterCardProps) {
  if (!automationCenter?.activeStrategy) return null

  const { activeStrategy, activeMode, template, performanceSnapshot } = automationCenter
  const [actionFilter, setActionFilter] = useState<'all' | 'worker' | 'analyze' | 'execute'>('all')
  const [statusFilter, setStatusFilter] = useState<'all' | 'success' | 'skipped' | 'error' | 'started' | 'stopped'>('all')
  const filteredExecutions = useMemo(() => {
    const rows = automationCenter.executions || []
    return rows.filter((item) => {
      const actionOk = actionFilter === 'all' || item.action === actionFilter
      const statusOk = statusFilter === 'all' || item.status === statusFilter
      return actionOk && statusOk
    })
  }, [actionFilter, automationCenter.executions, statusFilter])

  return (
    <div className="bg-trading-card border border-trading-border rounded-lg p-4">
      <h3 className="text-sm font-semibold text-trading-text mb-3">Automation Center</h3>
      <div className="space-y-2 text-sm">
        <div className="flex justify-between">
          <span className="text-trading-muted">Strategy</span>
          <span className="font-medium text-trading-text">{activeStrategy.name}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-trading-muted">Mode</span>
          <span className="font-medium text-trading-text">{activeMode}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-trading-muted">Allocation</span>
          <span className="font-medium text-trading-text">{template?.allocationPercent ?? 0}%</span>
        </div>
        <div className="flex justify-between">
          <span className="text-trading-muted">Max Positions</span>
          <span className="font-medium text-trading-text">{template?.maxPositions ?? 0}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-trading-muted">Enabled</span>
          <span className="font-medium text-trading-text">{template?.enabled ? 'yes' : 'no'}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-trading-muted">Worker</span>
          <span className="font-medium text-trading-text">{automationCenter.worker?.running ? 'running' : 'stopped'}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-trading-muted">Cooldown</span>
          <span className="font-medium text-trading-text">{template?.cooldownSeconds ?? 120}s</span>
        </div>
        <div className="flex justify-between">
          <span className="text-trading-muted">Max Exec / Hour</span>
          <span className="font-medium text-trading-text">{template?.maxExecutionsPerHour ?? 2}</span>
        </div>
      </div>
      {performanceSnapshot && (
        <div className="mt-4 rounded-lg border border-trading-border p-3 text-sm">
          <div className="mb-2 font-semibold text-trading-text">Latest Snapshot</div>
          <div className="grid grid-cols-2 gap-2">
            <div>
              <div className="text-trading-muted">Return</div>
              <div className="font-medium text-trading-text">{performanceSnapshot.metrics.totalReturn}%</div>
            </div>
            <div>
              <div className="text-trading-muted">Win Rate</div>
              <div className="font-medium text-trading-text">{performanceSnapshot.metrics.winRate}%</div>
            </div>
            <div>
              <div className="text-trading-muted">PF</div>
              <div className="font-medium text-trading-text">{performanceSnapshot.metrics.profitFactor}</div>
            </div>
            <div>
              <div className="text-trading-muted">Trades</div>
              <div className="font-medium text-trading-text">{performanceSnapshot.metrics.numTrades}</div>
            </div>
          </div>
        </div>
      )}
      {automationCenter.worker?.lastError && (
        <div className="mt-3 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-200">
          Worker error: {automationCenter.worker.lastError}
        </div>
      )}
      {automationCenter.executions && automationCenter.executions.length > 0 && (
        <div className="mt-4 rounded-lg border border-trading-border p-3 text-sm">
          <div className="mb-2 flex items-center justify-between gap-2">
            <div className="font-semibold text-trading-text">Execution History</div>
            <div className="flex gap-2">
              <select
                value={actionFilter}
                onChange={(e) => setActionFilter(e.target.value as 'all' | 'worker' | 'analyze' | 'execute')}
                className="rounded-lg border border-trading-border bg-trading-bg px-2 py-1 text-xs text-trading-text"
              >
                <option value="all">all actions</option>
                <option value="worker">worker</option>
                <option value="analyze">analyze</option>
                <option value="execute">execute</option>
              </select>
              <select
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value as 'all' | 'success' | 'skipped' | 'error' | 'started' | 'stopped')}
                className="rounded-lg border border-trading-border bg-trading-bg px-2 py-1 text-xs text-trading-text"
              >
                <option value="all">all status</option>
                <option value="success">success</option>
                <option value="skipped">skipped</option>
                <option value="error">error</option>
                <option value="started">started</option>
                <option value="stopped">stopped</option>
              </select>
            </div>
          </div>
          <div className="space-y-2">
            {filteredExecutions.slice(0, 6).map((item) => (
              <div key={item.id} className="flex items-start justify-between gap-3">
                <div>
                  <div className="font-medium text-trading-text">{item.action} · {item.status}</div>
                  <div className="text-xs text-trading-muted">{item.symbol} · {item.created_at}</div>
                </div>
                <div className="text-right text-xs text-trading-muted">
                  {Object.keys(item.detail || {}).length > 0 ? JSON.stringify(item.detail) : '—'}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}