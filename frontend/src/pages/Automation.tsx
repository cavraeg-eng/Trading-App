import { useEffect, useState } from 'react'
import api from '../lib/api'
import type { AutomationCenterState, StrategyDefinition } from '../types'
import { StrategyCatalog } from '../components/StrategyCatalog'
import { AutomationTemplateCard } from '../components/AutomationTemplateCard'
import { AutomationCenterCard } from '../components/AutomationCenterCard'

export default function Automation() {
  const [strategies, setStrategies] = useState<StrategyDefinition[]>([])
  const [selectedStrategy, setSelectedStrategy] = useState<StrategyDefinition | null>(null)
  const [automationCenter, setAutomationCenter] = useState<AutomationCenterState | null>(null)
  const [message, setMessage] = useState<string | null>(null)

  const refresh = async () => {
    const [strategyData, centerData] = await Promise.all([
      api.fetchStrategies(),
      api.fetchAutomationCenter(),
    ])
    setStrategies(strategyData.results || [])
    setAutomationCenter(centerData)
    if (centerData.activeStrategy && !selectedStrategy) {
      setSelectedStrategy(centerData.activeStrategy)
    }
  }

  useEffect(() => {
    refresh().catch(() => {
      setStrategies([])
      setAutomationCenter(null)
    })
  }, [])

  const toggleAutomationEnabled = async (enabled: boolean) => {
    const activeStrategy = automationCenter?.activeStrategy
    const template = automationCenter?.template
    if (!activeStrategy || !template) return
    await api.saveAutomationTemplate(activeStrategy.id, {
      mode: template.mode,
      allocationPercent: template.allocationPercent,
      maxPositions: template.maxPositions,
      cooldownSeconds: template.cooldownSeconds,
      maxExecutionsPerHour: template.maxExecutionsPerHour,
      enabled,
    })
    await refresh()
    setMessage(`Automation ${enabled ? 'resumed' : 'paused'} for ${activeStrategy.name}`)
  }

  return (
    <div className="mx-auto max-w-7xl p-6">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-trading-text">Automation Center</h1>
        <p className="text-trading-muted">Manage active strategy automation, templates, and latest snapshots.</p>
      </div>

      {message && (
        <div className="mb-4 rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-200">
          {message}
        </div>
      )}

      <div className="mb-4 flex gap-2">
        <button
          onClick={async () => {
            await api.startAutomationWorker()
            await refresh()
            setMessage('Automation worker started')
          }}
          className="rounded-lg bg-trading-accent px-3 py-2 text-sm font-medium text-white"
        >
          Start Worker
        </button>
        <button
          onClick={async () => {
            await api.stopAutomationWorker()
            await refresh()
            setMessage('Automation worker stopped')
          }}
          className="rounded-lg border border-trading-border px-3 py-2 text-sm font-medium text-trading-text"
        >
          Stop Worker
        </button>
        {automationCenter?.activeStrategy && automationCenter?.template && (
          <button
            onClick={async () => {
              await toggleAutomationEnabled(!automationCenter.template?.enabled)
            }}
            className="rounded-lg border border-trading-border px-3 py-2 text-sm font-medium text-trading-text"
          >
            {automationCenter.template?.enabled ? 'Pause Automation' : 'Resume Automation'}
          </button>
        )}
      </div>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-3">
        <div className="xl:col-span-2">
          <StrategyCatalog
            strategies={strategies}
            onSelectStrategy={setSelectedStrategy}
            onActivate={async (strategy, mode) => {
              await api.activateStrategy(strategy.id, mode, true)
              await refresh()
              setSelectedStrategy(strategy)
              setMessage(`Activated ${strategy.name} in ${mode} mode`)
            }}
          />
        </div>

        <div className="space-y-6">
          <AutomationCenterCard automationCenter={automationCenter} />
          <AutomationTemplateCard
            strategy={selectedStrategy}
            onSaved={async () => {
              await refresh()
              setMessage(`Saved automation template for ${selectedStrategy?.name}`)
            }}
          />
        </div>
      </div>
    </div>
  )
}