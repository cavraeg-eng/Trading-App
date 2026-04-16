import { useEffect, useState } from 'react'
import type { AutomationTemplate, StrategyDefinition } from '../types'
import api from '../lib/api'

interface AutomationTemplateCardProps {
  strategy: StrategyDefinition | null
  onSaved?: () => void
}

export function AutomationTemplateCard({ strategy, onSaved }: AutomationTemplateCardProps) {
  const [template, setTemplate] = useState<AutomationTemplate | null>(null)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (!strategy) {
      setTemplate(null)
      return
    }
    api.fetchAutomationTemplate(strategy.id).then(setTemplate).catch(() => setTemplate(null))
  }, [strategy])

  if (!strategy || !template) return null

  return (
    <div className="bg-trading-card border border-trading-border rounded-lg p-4">
      <h3 className="text-sm font-semibold text-trading-text mb-3">Automation Template</h3>
      <div className="grid grid-cols-2 gap-3">
        <label className="text-sm text-trading-muted">
          Mode
          <select
            value={template.mode}
            onChange={(e) => setTemplate({ ...template, mode: e.target.value })}
            className="mt-1 w-full rounded-lg border border-trading-border bg-trading-bg px-3 py-2 text-trading-text"
          >
            <option value="paper">paper</option>
            <option value="live">live</option>
          </select>
        </label>
        <label className="text-sm text-trading-muted">
          Allocation %
          <input
            type="number"
            value={template.allocationPercent}
            onChange={(e) => setTemplate({ ...template, allocationPercent: Number(e.target.value) })}
            className="mt-1 w-full rounded-lg border border-trading-border bg-trading-bg px-3 py-2 text-trading-text"
          />
        </label>
        <label className="text-sm text-trading-muted">
          Max Positions
          <input
            type="number"
            value={template.maxPositions}
            onChange={(e) => setTemplate({ ...template, maxPositions: Number(e.target.value) })}
            className="mt-1 w-full rounded-lg border border-trading-border bg-trading-bg px-3 py-2 text-trading-text"
          />
        </label>
        <label className="text-sm text-trading-muted">
          Cooldown Seconds
          <input
            type="number"
            value={template.cooldownSeconds ?? 120}
            onChange={(e) => setTemplate({ ...template, cooldownSeconds: Number(e.target.value) })}
            className="mt-1 w-full rounded-lg border border-trading-border bg-trading-bg px-3 py-2 text-trading-text"
          />
        </label>
        <label className="text-sm text-trading-muted">
          Max Executions / Hour
          <input
            type="number"
            value={template.maxExecutionsPerHour ?? 2}
            onChange={(e) => setTemplate({ ...template, maxExecutionsPerHour: Number(e.target.value) })}
            className="mt-1 w-full rounded-lg border border-trading-border bg-trading-bg px-3 py-2 text-trading-text"
          />
        </label>
        <label className="flex items-center gap-2 text-sm text-trading-muted">
          <input
            type="checkbox"
            checked={template.enabled}
            onChange={(e) => setTemplate({ ...template, enabled: e.target.checked })}
          />
          Enabled
        </label>
      </div>
      <button
        onClick={async () => {
          setSaving(true)
          try {
            await api.saveAutomationTemplate(strategy.id, template)
            onSaved?.()
          } finally {
            setSaving(false)
          }
        }}
        className="mt-4 rounded-lg bg-trading-accent px-3 py-2 text-sm font-medium text-white"
      >
        {saving ? 'Saving...' : 'Save Automation'}
      </button>
    </div>
  )
}