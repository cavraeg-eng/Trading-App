import { useMemo, useState } from 'react'
import { X, Plus, Search, RotateCcw, Filter, Layers3, GitBranchPlus, Network, ChevronDown, ChevronUp } from 'lucide-react'
import type {
  ForexPair,
  IndicatorCondition,
  ScannerConditionGroup,
  ScannerIndicatorDefinition,
  ScannerLogic,
} from '../types'

interface ScannerBuilderProps {
  groups: ScannerConditionGroup[]
  onGroupsChange: (groups: ScannerConditionGroup[]) => void
  logic: ScannerLogic
  onLogicChange: (logic: ScannerLogic) => void
  selectedPairs: string[]
  onPairsChange: (pairs: string[]) => void
  onRunScan: () => void
  onReset: () => void
  isScanning: boolean
  allPairs: ForexPair[]
  supportedIndicators: ScannerIndicatorDefinition[]
  categoryFilter: ForexPair['category'] | 'all'
  onUseCategoryUniverse: () => void
  scopeLabel: string
  onAddGroup: () => void
  onRemoveGroup: (groupId: string) => void
  showRunButton?: boolean
}

const OPERATOR_LABELS: Record<string, string> = {
  '>': 'greater than',
  '<': 'less than',
  '>=': 'greater or equal',
  '<=': 'less or equal',
  '=': 'equals',
  between: 'between',
  crosses_above: 'crosses above',
  crosses_below: 'crosses below',
}

function defaultCondition(indicators: ScannerIndicatorDefinition[]): IndicatorCondition {
  const rsi = indicators.find((indicator) => indicator.key === 'RSI') ?? indicators[0]
  return {
    indicator: rsi?.key || 'RSI',
    operator: rsi?.operators?.[0] || '<',
    value: rsi?.defaultValue ?? 30,
  }
}

export default function ScannerBuilder({
  groups,
  onGroupsChange,
  logic,
  onLogicChange,
  selectedPairs,
  onPairsChange,
  onRunScan,
  onReset,
  isScanning,
  allPairs,
  supportedIndicators,
  categoryFilter,
  onUseCategoryUniverse,
  scopeLabel,
  onAddGroup,
  onRemoveGroup,
  showRunButton = true,
}: ScannerBuilderProps) {
  const [searchQuery, setSearchQuery] = useState('')
  const [universeExpanded, setUniverseExpanded] = useState(false)

  const indicatorMap = useMemo(
    () => Object.fromEntries(supportedIndicators.map((indicator) => [indicator.key, indicator])),
    [supportedIndicators]
  )

  const addCondition = (groupId: string) => {
    onGroupsChange(
      groups.map((group) =>
        group.id === groupId
          ? {
              ...group,
              conditions: [...group.conditions, defaultCondition(supportedIndicators)],
            }
          : group
      )
    )
  }

  const removeCondition = (groupId: string, index: number) => {
    onGroupsChange(
      groups.map((group) =>
        group.id === groupId
          ? {
              ...group,
              conditions: group.conditions.filter((_, conditionIndex) => conditionIndex !== index),
            }
          : group
      )
    )
  }

  const updateCondition = (groupId: string, index: number, nextCondition: IndicatorCondition) => {
    onGroupsChange(
      groups.map((group) => {
        if (group.id !== groupId) return group
        const updatedConditions = [...group.conditions]
        updatedConditions[index] = nextCondition
        return { ...group, conditions: updatedConditions }
      })
    )
  }

  const filteredPairs = useMemo(() => {
    const normalizedQuery = searchQuery.trim().toLowerCase()
    const pairsByCategory =
      categoryFilter === 'all'
        ? allPairs
        : allPairs.filter((pair) => pair.category === categoryFilter)

    if (!normalizedQuery) return pairsByCategory

    return pairsByCategory.filter((pair) => {
      const label = `${pair.symbol} ${pair.name} ${pair.nickname}`.toLowerCase()
      return label.includes(normalizedQuery)
    })
  }, [allPairs, categoryFilter, searchQuery])

  const togglePair = (symbol: string) => {
    if (selectedPairs.includes(symbol)) {
      onPairsChange(selectedPairs.filter((pair) => pair !== symbol))
      return
    }
    onPairsChange([...selectedPairs, symbol])
  }

  const selectVisiblePairs = () => {
    const visibleSymbols = filteredPairs.map((pair) => pair.symbol)
    const merged = Array.from(new Set([...selectedPairs, ...visibleSymbols]))
    onPairsChange(merged)
  }

  const clearPairSelection = () => onPairsChange([])

  const hasCustomSelection = selectedPairs.length > 0
  const pairSelectionSummary = hasCustomSelection
    ? `${selectedPairs.length} selected`
    : `Using ${scopeLabel}`

  const totalConditions = groups.reduce((sum, group) => sum + group.conditions.length, 0)

  const pairCount = hasCustomSelection
    ? selectedPairs.length
    : (categoryFilter === 'all' ? allPairs : allPairs.filter((p) => p.category === categoryFilter)).length

  return (
    <div className="space-y-4">
      {/* Matching logic — compact single line */}
      <div className="flex items-center justify-between gap-3 rounded-lg border border-trading-border bg-trading-bg px-3 py-2.5">
        <div className="flex items-center gap-2 text-sm">
          <Network size={14} className="text-trading-accent" />
          <span className="font-medium text-trading-text">
            {logic === 'AND' ? 'Match all' : 'Match any'} groups
          </span>
          <span className="text-trading-muted">
            ({groups.length} {groups.length === 1 ? 'group' : 'groups'}, {totalConditions} {totalConditions === 1 ? 'rule' : 'rules'})
          </span>
        </div>
        <div className="flex rounded-md border border-trading-border bg-trading-card p-0.5">
          {(['AND', 'OR'] as const).map((mode) => (
            <button
              key={mode}
              onClick={() => onLogicChange(mode)}
              className={`rounded px-3 py-1 text-xs font-medium transition-colors ${
                logic === mode ? 'bg-trading-accent text-white' : 'text-trading-muted hover:text-trading-text'
              }`}
            >
              {mode}
            </button>
          ))}
        </div>
      </div>

      {/* Condition groups */}
      <div className="space-y-3">
        {groups.map((group, groupIndex) => (
          <div key={group.id} className="rounded-lg border border-trading-border bg-trading-bg p-3">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium text-trading-text">{group.name || `Group ${groupIndex + 1}`}</span>
                <span className="rounded-full bg-trading-card px-2 py-0.5 text-[10px] uppercase tracking-wide text-trading-muted">
                  {group.logic}
                </span>
              </div>
              <div className="flex gap-1.5">
                <div className="flex rounded-md border border-trading-border bg-trading-card p-0.5">
                  {(['AND', 'OR'] as const).map((mode) => (
                    <button
                      key={`${group.id}-${mode}`}
                      onClick={() =>
                        onGroupsChange(
                          groups.map((item) => (item.id === group.id ? { ...item, logic: mode } : item))
                        )
                      }
                      className={`rounded px-2.5 py-1 text-xs font-medium transition-colors ${
                        group.logic === mode ? 'bg-trading-accent text-white' : 'text-trading-muted hover:text-trading-text'
                      }`}
                    >
                      {mode}
                    </button>
                  ))}
                </div>
                <button
                  onClick={() => onRemoveGroup(group.id)}
                  disabled={groups.length === 1}
                  className="rounded-md border border-trading-border px-2.5 py-1 text-xs font-medium text-trading-muted transition-colors hover:text-trading-sell disabled:cursor-not-allowed disabled:opacity-50"
                >
                  Remove
                </button>
              </div>
            </div>

            <div className="space-y-2">
              {group.conditions.map((condition, index) => {
                const indicator = indicatorMap[condition.indicator] ?? supportedIndicators[0]
                const operators = indicator?.operators ?? []
                const compareCandidates = supportedIndicators.filter((item) => item.key !== condition.indicator)
                const usesBetween = condition.operator === 'between'
                const supportsCompare = !!indicator?.supportsCompareIndicator && !usesBetween
                const valueRange = indicator?.range

                return (
                  <div key={`${group.id}-${condition.indicator}-${index}`} className="rounded-lg border border-trading-border/60 bg-trading-card p-3">
                    <div className="mb-2 flex items-center justify-between gap-2">
                      <span className="text-xs font-medium text-trading-muted">
                        {indicator?.description || `Condition ${index + 1}`}
                      </span>
                      <button
                        onClick={() => removeCondition(group.id, index)}
                        className="rounded p-1 text-trading-muted transition-colors hover:bg-trading-bg hover:text-trading-sell disabled:cursor-not-allowed disabled:opacity-50"
                        disabled={group.conditions.length === 1}
                      >
                        <X size={14} />
                      </button>
                    </div>

                    <div className="grid gap-2 lg:grid-cols-[1.3fr_1fr_1fr_1fr]">
                      <select
                        value={condition.indicator}
                        onChange={(event) => {
                          const nextIndicator = indicatorMap[event.target.value] ?? supportedIndicators[0]
                          updateCondition(group.id, index, {
                            indicator: nextIndicator.key,
                            operator: nextIndicator.operators[0],
                            value: nextIndicator.defaultValue,
                          })
                        }}
                        className="w-full rounded-md border border-trading-border bg-trading-bg px-2.5 py-1.5 text-sm text-trading-text focus:border-trading-accent focus:outline-none"
                      >
                        {supportedIndicators.map((item) => (
                          <option key={item.key} value={item.key}>
                            {item.label}
                          </option>
                        ))}
                      </select>

                      <select
                        value={condition.operator}
                        onChange={(event) => {
                          const nextOperator = event.target.value
                          updateCondition(group.id, index, {
                            ...condition,
                            operator: nextOperator,
                            value2: nextOperator === 'between' ? condition.value2 ?? condition.value + (valueRange?.step ?? 1) * 5 : undefined,
                            compare_indicator: nextOperator === 'between' ? undefined : condition.compare_indicator,
                          })
                        }}
                        className="w-full rounded-md border border-trading-border bg-trading-bg px-2.5 py-1.5 text-sm text-trading-text focus:border-trading-accent focus:outline-none"
                      >
                        {operators.map((operator) => (
                          <option key={operator} value={operator}>
                            {OPERATOR_LABELS[operator] || operator}
                          </option>
                        ))}
                      </select>

                      {supportsCompare ? (
                        <div className="space-y-1.5">
                          <select
                            value={condition.compare_indicator ?? ''}
                            onChange={(event) =>
                              updateCondition(group.id, index, {
                                ...condition,
                                compare_indicator: event.target.value || undefined,
                              })
                            }
                            className="w-full rounded-md border border-trading-border bg-trading-bg px-2.5 py-1.5 text-sm text-trading-text focus:border-trading-accent focus:outline-none"
                          >
                            <option value="">Numeric value</option>
                            {compareCandidates.map((candidate) => (
                              <option key={candidate.key} value={candidate.key}>
                                {candidate.label}
                              </option>
                            ))}
                          </select>
                          {!condition.compare_indicator ? (
                            <input
                              type="number"
                              min={valueRange?.min}
                              max={valueRange?.max}
                              step={valueRange?.step}
                              value={condition.value}
                              onChange={(event) =>
                                updateCondition(group.id, index, {
                                  ...condition,
                                  value: Number(event.target.value),
                                })
                              }
                              className="w-full rounded-md border border-trading-border bg-trading-bg px-2.5 py-1.5 text-sm text-trading-text focus:border-trading-accent focus:outline-none"
                            />
                          ) : null}
                        </div>
                      ) : (
                        <input
                          type="number"
                          min={valueRange?.min}
                          max={valueRange?.max}
                          step={valueRange?.step}
                          value={condition.value}
                          onChange={(event) =>
                            updateCondition(group.id, index, {
                              ...condition,
                              value: Number(event.target.value),
                            })
                          }
                          className="w-full rounded-md border border-trading-border bg-trading-bg px-2.5 py-1.5 text-sm text-trading-text focus:border-trading-accent focus:outline-none"
                        />
                      )}

                      {usesBetween ? (
                        <input
                          type="number"
                          min={valueRange?.min}
                          max={valueRange?.max}
                          step={valueRange?.step}
                          value={condition.value2 ?? ''}
                          onChange={(event) =>
                            updateCondition(group.id, index, {
                              ...condition,
                              value2: Number(event.target.value),
                            })
                          }
                          className="w-full rounded-md border border-trading-border bg-trading-bg px-2.5 py-1.5 text-sm text-trading-text focus:border-trading-accent focus:outline-none"
                        />
                      ) : (
                        <div className="rounded-md border border-dashed border-trading-border/40 bg-trading-bg px-2.5 py-1.5 text-sm text-trading-muted">
                          &mdash;
                        </div>
                      )}
                    </div>
                  </div>
                )
              })}
            </div>

            <button
              onClick={() => addCondition(group.id)}
              className="mt-2 inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium text-trading-muted transition-colors hover:text-trading-accent"
            >
              <Plus size={14} />
              Add condition
            </button>
          </div>
        ))}
      </div>

      {/* Group actions */}
      <div className="flex flex-wrap gap-2">
        <button
          onClick={onAddGroup}
          className="inline-flex items-center gap-1.5 rounded-md border border-dashed border-trading-border px-3 py-1.5 text-xs font-medium text-trading-muted transition-colors hover:border-trading-accent hover:text-trading-accent"
        >
          <GitBranchPlus size={14} />
          Add group
        </button>
        <button
          onClick={() => addCondition(groups[0]?.id)}
          className="inline-flex items-center gap-1.5 rounded-md border border-dashed border-trading-border px-3 py-1.5 text-xs font-medium text-trading-muted transition-colors hover:border-trading-accent hover:text-trading-accent"
        >
          <Plus size={14} />
          Add condition
        </button>
        <button
          onClick={onReset}
          className="inline-flex items-center gap-1.5 rounded-md border border-trading-border px-3 py-1.5 text-xs font-medium text-trading-muted transition-colors hover:text-trading-text"
        >
          <RotateCcw size={14} />
          Reset
        </button>
      </div>

      {/* Scan universe — collapsible */}
      <div className="rounded-lg border border-trading-border bg-trading-bg">
        <button
          onClick={() => setUniverseExpanded(!universeExpanded)}
          className="flex w-full items-center justify-between px-3 py-2.5 text-left"
        >
          <div className="flex items-center gap-2">
            <Layers3 size={14} className="text-trading-accent" />
            <span className="text-sm font-medium text-trading-text">Scan universe</span>
            <span className="text-xs text-trading-muted">
              {pairSelectionSummary} ({pairCount} pairs)
            </span>
          </div>
          <span className="text-trading-muted">
            {universeExpanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
          </span>
        </button>

        {universeExpanded ? (
          <div className="border-t border-trading-border px-3 pb-3 pt-3">
            <div className="mb-2 flex flex-wrap gap-2">
              <button
                onClick={onUseCategoryUniverse}
                className="rounded-md border border-trading-border px-2.5 py-1 text-xs text-trading-muted transition-colors hover:text-trading-text"
              >
                Use {scopeLabel}
              </button>
              <button
                onClick={selectVisiblePairs}
                className="rounded-md border border-trading-border px-2.5 py-1 text-xs text-trading-muted transition-colors hover:text-trading-text"
              >
                Select visible
              </button>
              <button
                onClick={clearPairSelection}
                className="rounded-md border border-trading-border px-2.5 py-1 text-xs text-trading-muted transition-colors hover:text-trading-text"
              >
                Clear
              </button>
            </div>

            <div className="mb-2 flex items-center gap-2 rounded-md border border-trading-border bg-trading-card px-2.5 py-1.5">
              <Search size={14} className="text-trading-muted" />
              <input
                value={searchQuery}
                onChange={(event) => setSearchQuery(event.target.value)}
                placeholder="Search pairs..."
                className="w-full bg-transparent text-sm text-trading-text placeholder:text-trading-muted focus:outline-none"
              />
              <Filter size={14} className="text-trading-muted" />
            </div>

            <div className="grid max-h-48 gap-1.5 overflow-y-auto rounded-md border border-trading-border bg-trading-card p-1.5 md:grid-cols-2">
              {filteredPairs.map((pair) => {
                const checked = selectedPairs.includes(pair.symbol)
                return (
                  <label
                    key={pair.symbol}
                    className={`flex cursor-pointer items-center gap-2 rounded-md border px-2.5 py-2 transition-colors ${
                      checked ? 'border-trading-accent bg-trading-accent/10' : 'border-transparent hover:border-trading-border'
                    }`}
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() => togglePair(pair.symbol)}
                      className="rounded border-trading-border text-trading-accent focus:ring-trading-accent"
                    />
                    <span className="text-sm font-medium text-trading-text">{pair.symbol}</span>
                    <span className="text-xs text-trading-muted">{pair.name}</span>
                  </label>
                )
              })}
              {filteredPairs.length === 0 ? (
                <div className="col-span-full px-3 py-4 text-center text-sm text-trading-muted">
                  No pairs match your filter.
                </div>
              ) : null}
            </div>
          </div>
        ) : null}
      </div>

      {/* Run scan button — conditionally shown */}
      {showRunButton ? (
        <button
          onClick={onRunScan}
          disabled={isScanning || totalConditions === 0}
          className="flex w-full items-center justify-center gap-2 rounded-lg bg-trading-accent py-2.5 font-medium text-white transition-colors hover:bg-blue-600 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {isScanning ? (
            <>
              <div className="h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white" />
              Scanning...
            </>
          ) : (
            'Run scan'
          )}
        </button>
      ) : null}
    </div>
  )
}
