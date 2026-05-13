import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api, type ApiError } from '../lib/api'
import type {
  IndicatorCondition,
  SavedScanner,
  ScanResult,
  ScannerConditionGroup,
  ScannerConfig,
  ScannerLogic,
  ScannerMetadata,
  ScannerPreset,
  ScannerRunMetadata,
  ScannerTimeframe,
  TradeStyle,
} from '../types'

export interface ScannerSummary {
  total: number
  buy: number
  sell: number
  neutral: number
  averageOpportunity: number
}

const DEFAULT_CONDITIONS: IndicatorCondition[] = [{ indicator: 'RSI', operator: '<', value: 30 }]
const DEFAULT_GROUP_ID = 'group-primary'

function buildDefaultGroups(): ScannerConditionGroup[] {
  return [
    {
      id: DEFAULT_GROUP_ID,
      name: 'Primary setup',
      logic: 'AND',
      conditions: DEFAULT_CONDITIONS,
    },
  ]
}

function buildDefaultConfig(): ScannerConfig {
  return {
    name: '',
    conditions: DEFAULT_CONDITIONS,
    logic: 'AND',
    groups: buildDefaultGroups(),
    pairs: [],
    trade_style: 'swing',
    timeframe: '1h',
  }
}

export function useScanner(initialCategorySymbols: string[]) {
  const [config, setConfig] = useState<ScannerConfig>(buildDefaultConfig)
  const [results, setResults] = useState<ScanResult[]>([])
  const [totalScanned, setTotalScanned] = useState(0)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [warnings, setWarnings] = useState<string[]>([])
  const [metadata, setMetadata] = useState<ScannerMetadata | null>(null)
  const [scanMetadata, setScanMetadata] = useState<ScannerRunMetadata | null>(null)
  const [presets, setPresets] = useState<ScannerPreset[]>([])
  const [savedScanners, setSavedScanners] = useState<SavedScanner[]>([])
  const [loadingMetadata, setLoadingMetadata] = useState(true)
  const [loadingSaved, setLoadingSaved] = useState(true)
  const [lastRunAt, setLastRunAt] = useState<string | null>(null)
  const [riskFilter, setRiskFilter] = useState<'all' | 'low' | 'medium' | 'high'>('all')
  const [styleFilter, setStyleFilter] = useState<'all' | 'swing' | 'scalp'>('all')
  const [marketFilter, setMarketFilter] = useState<'all' | 'forex' | 'metals' | 'crypto' | 'indices'>('all')
  const abortRef = useRef<AbortController | null>(null)
  const requestIdRef = useRef(0)

  const selectedPairs = config.pairs ?? []
  const groups = config.groups?.length ? config.groups : buildDefaultGroups()

  useEffect(() => {
    let cancelled = false
    setLoadingMetadata(true)
    Promise.all([
      api.fetchScannerMetadata(),
      api.fetchScannerPresets(),
    ])
      .then(([metadataResponse, presetsResponse]) => {
        if (cancelled) return
        setMetadata(metadataResponse)
        setPresets(presetsResponse.presets || [])
      })
      .catch((err: ApiError | Error) => {
        if (cancelled) return
        setError('Failed to load scanner metadata. Check API connectivity.')
        console.error(err)
      })
      .finally(() => {
        if (!cancelled) setLoadingMetadata(false)
      })

    return () => {
      cancelled = true
    }
  }, [])

  const refreshSavedScanners = useCallback(async () => {
    setLoadingSaved(true)
    try {
      const response = await api.fetchSavedScanners()
      setSavedScanners(response.saved || [])
    } catch (err) {
      console.error(err)
    } finally {
      setLoadingSaved(false)
    }
  }, [])

  useEffect(() => {
    refreshSavedScanners()
  }, [refreshSavedScanners])

  const filteredPresets = useMemo(() => {
    return presets.filter((preset) => {
      const riskMatch = riskFilter === 'all' || (preset.risk ?? 'medium') === riskFilter
      const styleMatch = styleFilter === 'all' || preset.trade_style === styleFilter
      const presetMarkets = preset.markets ?? []
      const marketMatch = marketFilter === 'all' || presetMarkets.includes(marketFilter)
      return riskMatch && styleMatch && marketMatch
    })
  }, [presets, riskFilter, styleFilter, marketFilter])

  const supportedIndicators = useMemo(
    () => (metadata?.indicators ?? []).filter((indicator) => indicator.supported),
    [metadata]
  )

  const setConditions = useCallback((conditions: IndicatorCondition[]) => {
    setConfig((prev) => ({
      ...prev,
      conditions,
      groups: [
        ...(prev.groups?.slice(1) ?? []),
      ].length === 0
        ? [{ id: DEFAULT_GROUP_ID, name: 'Primary setup', logic: 'AND', conditions }]
        : [
            { ...(prev.groups?.[0] ?? { id: DEFAULT_GROUP_ID, name: 'Primary setup', logic: 'AND' }), conditions },
            ...(prev.groups?.slice(1) ?? []),
          ],
    }))
  }, [])

  const setLogic = useCallback((logic: ScannerLogic) => {
    setConfig((prev) => ({ ...prev, logic }))
  }, [])

  const setGroups = useCallback((nextGroups: ScannerConditionGroup[]) => {
    setConfig((prev) => ({
      ...prev,
      groups: nextGroups,
      conditions: nextGroups.flatMap((group) => group.conditions),
    }))
  }, [])

  const updateGroupLogic = useCallback((groupId: string, logic: ScannerLogic) => {
    setConfig((prev) => {
      const nextGroups = (prev.groups?.length ? prev.groups : buildDefaultGroups()).map((group) =>
        group.id === groupId ? { ...group, logic } : group
      )
      return {
        ...prev,
        groups: nextGroups,
        conditions: nextGroups.flatMap((group) => group.conditions),
      }
    })
  }, [])

  const updateGroupConditions = useCallback((groupId: string, conditions: IndicatorCondition[]) => {
    setConfig((prev) => {
      const currentGroups = prev.groups?.length ? prev.groups : buildDefaultGroups()
      const nextGroups = currentGroups.map((group) =>
        group.id === groupId ? { ...group, conditions } : group
      )
      return {
        ...prev,
        groups: nextGroups,
        conditions: nextGroups.flatMap((group) => group.conditions),
      }
    })
  }, [])

  const addGroup = useCallback(() => {
    setConfig((prev) => {
      const currentGroups = prev.groups?.length ? prev.groups : buildDefaultGroups()
      const nextGroups = [
        ...currentGroups,
        {
          id: `group-${Date.now()}`,
          name: `Alternative setup ${currentGroups.length + 1}`,
          logic: 'AND' as ScannerLogic,
          conditions: DEFAULT_CONDITIONS.map((condition) => ({ ...condition })),
        },
      ]
      return {
        ...prev,
        groups: nextGroups,
        conditions: nextGroups.flatMap((group) => group.conditions),
      }
    })
  }, [])

  const removeGroup = useCallback((groupId: string) => {
    setConfig((prev) => {
      const currentGroups = prev.groups?.length ? prev.groups : buildDefaultGroups()
      const remainingGroups = currentGroups.filter((group) => group.id !== groupId)
      const nextGroups = remainingGroups.length > 0 ? remainingGroups : buildDefaultGroups()
      return {
        ...prev,
        groups: nextGroups,
        conditions: nextGroups.flatMap((group) => group.conditions),
      }
    })
  }, [])

  const setSelectedPairs = useCallback((pairs: string[]) => {
    setConfig((prev) => ({ ...prev, pairs }))
  }, [])

  const setScannerName = useCallback((name: string) => {
    setConfig((prev) => ({ ...prev, name }))
  }, [])

  const setTradeStyle = useCallback((tradeStyle: TradeStyle) => {
    setConfig((prev) => ({ ...prev, trade_style: tradeStyle }))
  }, [])

  const setTimeframe = useCallback((timeframe: ScannerTimeframe) => {
    setConfig((prev) => ({ ...prev, timeframe }))
  }, [])

  const loadSavedScanner = useCallback((savedScanner: SavedScanner) => {
    const restoredGroups: ScannerConditionGroup[] =
      savedScanner.config.groups?.length
        ? savedScanner.config.groups
        : [
            {
              id: DEFAULT_GROUP_ID,
              name: 'Primary setup',
              logic: 'AND',
              conditions: savedScanner.config.conditions?.length ? savedScanner.config.conditions : DEFAULT_CONDITIONS,
            },
          ]
    setConfig({
      name: savedScanner.config.name || savedScanner.name,
      conditions: savedScanner.config.conditions?.length ? savedScanner.config.conditions : DEFAULT_CONDITIONS,
      logic: savedScanner.config.logic || 'AND',
      groups: restoredGroups,
      pairs: savedScanner.config.pairs || [],
      trade_style: savedScanner.config.trade_style || 'swing',
      timeframe: savedScanner.config.timeframe || '1h',
    })
    setWarnings([])
    setScanMetadata(null)
    setError(null)
  }, [])

  const applyPreset = useCallback((preset: ScannerPreset) => {
    const presetGroups: ScannerConditionGroup[] =
      preset.groups?.length
        ? preset.groups
        : [
            {
              id: DEFAULT_GROUP_ID,
              name: 'Primary setup',
              logic: preset.logic || 'AND',
              conditions: preset.conditions?.length ? preset.conditions : DEFAULT_CONDITIONS,
            },
          ]
    setConfig((prev) => ({
      ...prev,
      name: preset.name,
      conditions: preset.conditions?.length ? preset.conditions : DEFAULT_CONDITIONS,
      logic: preset.logic || 'AND',
      groups: presetGroups,
      trade_style: preset.trade_style || prev.trade_style || 'swing',
      timeframe: preset.timeframe || prev.timeframe || '1h',
      pairs: preset.recommended_pairs || prev.pairs || [],
    }))
    setWarnings([])
    setScanMetadata(null)
    setError(null)
  }, [])

  const resetScanner = useCallback(() => {
    abortRef.current?.abort()
    setConfig(buildDefaultConfig())
    setResults([])
    setTotalScanned(0)
    setWarnings([])
    setError(null)
    setLastRunAt(null)
  }, [])

  const clearResults = useCallback(() => {
    setResults([])
    setTotalScanned(0)
    setWarnings([])
    setError(null)
  }, [])

  const runScan = useCallback(
    async (fallbackPairs?: string[]) => {
      abortRef.current?.abort()
      const abortController = new AbortController()
      abortRef.current = abortController
      const requestId = ++requestIdRef.current

      setLoading(true)
      setError(null)
      setWarnings([])

      try {
        const response = await api.runScanner(
          {
            ...config,
            name: config.name?.trim() || 'Custom Scanner',
            pairs: selectedPairs.length > 0 ? selectedPairs : fallbackPairs ?? initialCategorySymbols,
          },
          abortController.signal
        )

        if (requestId !== requestIdRef.current) return

        setResults(response.results || [])
        setTotalScanned(response.total_scanned || 0)
        setWarnings(response.warnings || [])
        setScanMetadata(response.meta?.scan || null)
        setLastRunAt(new Date().toISOString())
      } catch (err) {
        if (abortController.signal.aborted) return
        const apiError = err as ApiError
        setError(apiError?.detail || 'Scanner request failed. Please try again.')
        setResults([])
        setTotalScanned(0)
        setScanMetadata(null)
      } finally {
        if (requestId === requestIdRef.current) {
          setLoading(false)
        }
      }
    },
    [config, initialCategorySymbols, selectedPairs]
  )

  const saveScanner = useCallback(
    async (existingId?: number) => {
      const payload: ScannerConfig = {
        ...config,
        name: config.name?.trim() || 'Custom Scanner',
      }
      if (!payload.name.trim()) {
        throw new Error('Scanner name is required.')
      }
      if (existingId) {
        await api.updateSavedScanner(existingId, payload)
      } else {
        await api.saveScanner(payload)
      }
      await refreshSavedScanners()
    },
    [config, refreshSavedScanners]
  )

  const deleteSavedScanner = useCallback(
    async (scannerId: number) => {
      await api.deleteSavedScanner(scannerId)
      await refreshSavedScanners()
    },
    [refreshSavedScanners]
  )

  const armScannerAlert = useCallback(async () => {
    const payload: ScannerConfig = {
      ...config,
      name: config.name?.trim() || 'Custom Scanner',
      groups,
      conditions: groups.flatMap((group) => group.conditions),
    }
    return api.createScannerAlert(payload)
  }, [config, groups])

  const summary = useMemo<ScannerSummary>(() => {
    const matchedResults = results.filter((row) => row.scan_status !== 'error')
    const buy = matchedResults.filter((row) => (row.signal || '').toUpperCase() === 'BUY').length
    const sell = matchedResults.filter((row) => (row.signal || '').toUpperCase() === 'SELL').length
    const neutral = matchedResults.filter((row) => !row.signal || row.signal.toUpperCase() === 'NEUTRAL').length
    const averageOpportunity = matchedResults.length
      ? Math.round(matchedResults.reduce((sum, row) => sum + (row.opportunity_score || 0), 0) / matchedResults.length)
      : 0
    return {
      total: matchedResults.length,
      buy,
      sell,
      neutral,
      averageOpportunity,
    }
  }, [results])

  const hasRun = lastRunAt !== null

  return {
    config,
    selectedPairs,
    groups,
    results,
    totalScanned,
    loading,
    error,
    warnings,
    metadata,
    scanMetadata,
    presets,
    filteredPresets,
    savedScanners,
    loadingMetadata,
    loadingSaved,
    supportedIndicators,
    summary,
    hasRun,
    lastRunAt,
    riskFilter,
    styleFilter,
    marketFilter,
    setConditions,
    setLogic,
    setGroups,
    updateGroupLogic,
    updateGroupConditions,
    addGroup,
    removeGroup,
    setSelectedPairs,
    setScannerName,
    setTradeStyle,
    setTimeframe,
    setRiskFilter,
    setStyleFilter,
    setMarketFilter,
    applyPreset,
    loadSavedScanner,
    runScan,
    saveScanner,
    deleteSavedScanner,
    armScannerAlert,
    resetScanner,
    clearResults,
    refreshSavedScanners,
  }
}
