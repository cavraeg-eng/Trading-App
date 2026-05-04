/**
 * Centralized API client for the trading bot frontend.
 * All API calls go through relative `/api/...` paths so the Vite proxy handles routing.
 */

import type {
  SmartAlert,
  AlignmentData,
  SignalBacktestResult,
  GoldContextData,
  SourceMetadata,
  DatasourceHealthResponse,
  OpportunityRow,
  StrategyDefinition,
  AutomationTemplate,
  AutomationCenterState,
  SavedScanner,
  ScannerConfig,
  ScannerMetadata,
  ScannerPreset,
  ScanResult,
  CopyTradeHistoryResponse,
  CopyTradePosition,
  CopyTradeStats,
  CopyTradingSettings,
  PredictionAssetClass,
  PredictionResponse,
  PredictionStrategyMode,
  AIPrediction,
} from '../types';
import { normalizePredictionPayload } from './predictionPresentation';

const BASE = '';  // relative — Vite proxy forwards /api/* to the backend

export interface ApiError {
  status: number;
  detail: string;
}

export interface HealthStatus {
  status: 'healthy' | 'degraded' | 'unreachable';
  version: string;
  uptime: number;
}

export interface BackendStatus {
  api: HealthStatus;
  broker: {
    id: string | null;
    connected: boolean;
    name: string | null;
    environment?: string | null;
    lastSync: number | null;
  } | null;
  dataFreshness: 'live' | 'delayed' | 'stale' | 'unknown';
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${BASE}${path}`;
  // Default 20s timeout to prevent connection pile-up
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 20000);
  try {
    const res = await fetch(url, {
      ...init,
      headers: {
        'Content-Type': 'application/json',
        ...(init?.headers ?? {}),
      },
      signal: init?.signal ?? controller.signal,
    });
    clearTimeout(timeoutId);
    if (!res.ok) {
      let detail = `HTTP ${res.status}`;
      try {
        const body = await res.json();
        detail = body.detail ?? detail;
      } catch { /* ignore parse errors */ }
      throw { status: res.status, detail } as ApiError;
    }
    return res.json() as Promise<T>;
  } catch (err) {
    clearTimeout(timeoutId);
    if (err && typeof err === 'object' && 'status' in err) throw err;
    if (err instanceof DOMException && err.name === 'AbortError') {
      throw { status: 408, detail: 'Request timed out' } as ApiError;
    }
    throw { status: 0, detail: 'Failed to fetch' } as ApiError;
  }
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: 'POST', body: body != null ? JSON.stringify(body) : undefined }),
  delete: <T>(path: string) => request<T>(path, { method: 'DELETE' }),

  fetchScannerMetadata(): Promise<ScannerMetadata> {
    return request<ScannerMetadata>('/api/scanner/metadata');
  },

  fetchScannerPresets(): Promise<{ presets: ScannerPreset[] }> {
    return request<{ presets: ScannerPreset[] }>('/api/scanner/presets');
  },

  runScanner(
    config: ScannerConfig,
    signal?: AbortSignal
  ): Promise<{
    results: ScanResult[];
    total_scanned: number;
    total_matches: number;
    warnings?: string[];
    meta?: {
      timeframe: string;
      trade_style: string;
      logic: string;
      scan?: {
        batch_duration_ms?: number;
        concurrency_limit?: number;
        total_symbols?: number;
        succeeded?: number;
        failed?: number;
        unmatched?: number;
      };
    };
  }> {
    return request('/api/scanner/scan', {
      method: 'POST',
      body: JSON.stringify(config),
      signal,
    });
  },

  saveScanner(config: ScannerConfig): Promise<{ status: string; name: string; id: number }> {
    return request('/api/scanner/save', {
      method: 'POST',
      body: JSON.stringify(config),
    });
  },

  updateSavedScanner(scannerId: number, config: ScannerConfig): Promise<{ status: string; id: number; name: string }> {
    return request(`/api/scanner/saved/${scannerId}`, {
      method: 'PUT',
      body: JSON.stringify(config),
    });
  },

  fetchSavedScanners(): Promise<{ saved: SavedScanner[] }> {
    return request<{ saved: SavedScanner[] }>('/api/scanner/saved');
  },

  deleteSavedScanner(scannerId: number): Promise<{ status: string; id: number }> {
    return request(`/api/scanner/saved/${scannerId}`, {
      method: 'DELETE',
    });
  },

  createScannerAlert(config: ScannerConfig): Promise<{ status: string; id: number; name: string }> {
    return request('/api/scanner/alert', {
      method: 'POST',
      body: JSON.stringify(config),
    });
  },

  // Smart Alerts
  fetchAlerts(unreadOnly?: boolean, limit?: number): Promise<SmartAlert[]> {
    const params = new URLSearchParams();
    if (unreadOnly !== undefined) params.set('unread_only', String(unreadOnly));
    if (limit !== undefined) params.set('limit', String(limit));
    const qs = params.toString();
    return request<SmartAlert[]>(`/api/alerts${qs ? `?${qs}` : ''}`);
  },
  fetchUnreadCount(): Promise<{ count: number }> {
    return request<{ count: number }>('/api/alerts/unread-count');
  },
  markAlertRead(alertId: number): Promise<{ success: boolean }> {
    return request<{ success: boolean }>(`/api/alerts/${alertId}/read`, { method: 'POST' });
  },
  markAllAlertsRead(): Promise<{ success: boolean }> {
    return request<{ success: boolean }>('/api/alerts/read-all', { method: 'POST' });
  },

  // AI Score
  fetchAIScore(symbol: string, timeframe?: string, tradeStyle?: string): Promise<{
    symbol: string;
    tradeStyle?: string;
    score: number;
    label: string;
    change: number;
    factors: {
      modelConfidence: number;
      indicatorConsensus: number;
      marketRegimeFit: number;
      patternStrength: number;
      sentimentScore: number;
      volumeMomentum: number;
    };
    dataSource?: string;
    dataQuality?: string[];
    freshnessSeconds?: number | null;
    timestamp: string;
  }> {
    const params = new URLSearchParams();
    if (timeframe) params.set('timeframe', timeframe);
    if (tradeStyle) params.set('trade_style', tradeStyle);
    const qs = params.toString();
    return request(`/api/ai/score/${encodeURIComponent(symbol)}${qs ? `?${qs}` : ''}`);
  },

  fetchPredictionSuggestion(params: {
    symbol: string;
    assetClass?: PredictionAssetClass;
    timeframe?: string;
    strategyMode?: PredictionStrategyMode;
  }): Promise<PredictionResponse> {
    return request<PredictionResponse>('/api/predictions/suggestion', {
      method: 'POST',
      body: JSON.stringify({
        symbol: params.symbol,
        asset_class: params.assetClass ?? 'unknown',
        timeframe: params.timeframe ?? '1h',
        strategy_mode: params.strategyMode ?? 'swing',
      }),
    });
  },

  // Multi-TF Alignment
  fetchAlignment(symbol: string, tradeStyle?: string): Promise<AlignmentData> {
    const params = new URLSearchParams();
    if (tradeStyle) params.set('trade_style', tradeStyle);
    const qs = params.toString();
    return request<AlignmentData>(`/api/ai/alignment/${encodeURIComponent(symbol)}${qs ? `?${qs}` : ''}`);
  },

  // Signal Backtest
  backtestSignal(params: {
    symbol: string;
    timeframe: string;
    direction: string;
    lookback_days?: number;
    initial_balance?: number;
    risk_percent?: number;
  }): Promise<SignalBacktestResult> {
    return request<SignalBacktestResult>('/api/backtest/signal', {
      method: 'POST',
      body: JSON.stringify(params),
    });
  },

  /** Check backend health; returns a structured status even on failure. */
  async health(): Promise<BackendStatus> {
    try {
      const h = await request<{ status: string; version: string; uptime: number }>('/api/health');
      let broker: BackendStatus['broker'] = null;
      try {
        const b = await request<{ id?: string; name?: string; connected?: boolean; environment?: string } | null>('/api/broker/active');
        if (b) {
          broker = {
            id: b.id ?? null,
            connected: !!b.connected,
            name: b.name ?? b.id ?? null,
            environment: b.environment ?? null,
            lastSync: Date.now(),
          };
        }
      } catch { /* broker check is optional */ }

      return {
        api: { status: 'healthy', version: h.version, uptime: h.uptime },
        broker,
        dataFreshness: 'live',
      };
    } catch {
      return {
        api: { status: 'unreachable', version: '', uptime: 0 },
        broker: null,
        dataFreshness: 'unknown',
      };
    }
  },

  fetchGoldContext(): Promise<GoldContextData> {
    return request<GoldContextData>('/api/gold/context');
  },

  fetchDatasourceHealth(): Promise<DatasourceHealthResponse> {
    return request<DatasourceHealthResponse>('/api/health/datasources');
  },

  fetchTopOpportunities(timeframe?: string, tradeStyle?: string, symbols?: string[]): Promise<{ results: OpportunityRow[] }> {
    const params = new URLSearchParams();
    if (timeframe) params.set('timeframe', timeframe);
    if (tradeStyle) params.set('trade_style', tradeStyle);
    if (symbols?.length) params.set('symbols', symbols.join(','));
    const qs = params.toString();
    return request(`/api/opportunities/top${qs ? `?${qs}` : ''}`);
  },

  fetchXAUOpportunities(): Promise<{ results: OpportunityRow[] }> {
    return request('/api/opportunities/xau');
  },

  fetchBacktestReport(
    symbol: string,
    timeframe: string,
    tradeStyle: string,
    startDate: string,
    endDate: string,
  ): Promise<{
    symbol: string;
    timeframe: string;
    tradeStyle: string;
    sourcePolicy: string;
    bestSession: string;
    sourceConfidence: number;
    regimeFit: number;
    sessionBreakdown: Array<{
      session: string;
      trades: number;
      winRate: number;
      netPnl: number;
    }>;
    sourceBreakdown: Array<{
      source: string;
      weight: number;
      confidence: number;
    }>;
    startDate: string;
    endDate: string;
  }> {
    const params = new URLSearchParams({
      symbol,
      timeframe,
      trade_style: tradeStyle,
      start_date: startDate,
      end_date: endDate,
    });
    return request(`/api/reports/backtest?${params.toString()}`);
  },

  fetchStrategies(category?: string): Promise<{ results: StrategyDefinition[] }> {
    const qs = category ? `?category=${encodeURIComponent(category)}` : '';
    return request(`/api/strategies${qs}`);
  },

  activateStrategy(strategyId: string, mode: string, enabled = true): Promise<{
    success: boolean;
    strategy_id: string;
    enabled: boolean;
    mode: string;
  }> {
    return request('/api/strategies/activate', {
      method: 'POST',
      body: JSON.stringify({ strategy_id: strategyId, mode, enabled }),
    });
  },

  fetchAutomationTemplate(strategyId: string): Promise<AutomationTemplate> {
    return request(`/api/strategies/automation-template?strategy_id=${encodeURIComponent(strategyId)}`);
  },

  saveAutomationTemplate(strategyId: string, template: {
    mode: string;
    allocationPercent: number;
    maxPositions: number;
    cooldownSeconds?: number;
    maxExecutionsPerHour?: number;
    enabled: boolean;
  }): Promise<AutomationTemplate & { success: boolean }> {
    return request('/api/strategies/automation-template', {
      method: 'POST',
      body: JSON.stringify({
        strategy_id: strategyId,
        mode: template.mode,
        allocation_percent: template.allocationPercent,
        max_positions: template.maxPositions,
        cooldown_seconds: template.cooldownSeconds ?? 120,
        max_executions_per_hour: template.maxExecutionsPerHour ?? 2,
        enabled: template.enabled,
      }),
    });
  },

  fetchAutomationCenter(): Promise<AutomationCenterState> {
    return request<AutomationCenterState>('/api/strategies/automation-center');
  },

  startAutomationWorker(opts?: { mode?: string; broker_id?: string }): Promise<{ success: boolean; worker: AutomationCenterState['worker'] }> {
    const params = new URLSearchParams();
    if (opts?.mode) params.set('mode', opts.mode);
    if (opts?.broker_id) params.set('broker_id', opts.broker_id);
    const qs = params.toString();
    return request(`/api/strategies/automation-worker/start${qs ? `?${qs}` : ''}`, { method: 'POST' });
  },

  stopAutomationWorker(): Promise<{ success: boolean; worker: AutomationCenterState['worker'] }> {
    return request('/api/strategies/automation-worker/stop', { method: 'POST' });
  },

  fetchAutomationStatus(): Promise<{
    worker: AutomationCenterState['worker'];
    mode: string;
    brokerId: string | null;
    activeStrategy: StrategyDefinition | null;
    activeMode: string;
    lastAnalysis: {
      signal: string;
      confidence: number;
      reason: string;
      marketRegime: string;
      entryRange: { min: number; max: number } | null;
      stopLoss: number;
      takeProfit1: number;
      takeProfit2: number;
      takeProfit3: number;
      currentPrice: number;
      symbol: string;
      timeframe: string;
      tradeStyle: string;
      timestamp: number;
    } | null;
    executions: Array<{
      id: number;
      strategy_id: string;
      symbol: string;
      action: string;
      status: string;
      detail: Record<string, unknown>;
      created_at: string;
    }>;
  }> {
    return request('/api/strategies/automation-status');
  },

  fetchActiveSignal(): Promise<{
    hasSignal: boolean;
    signal?: string;
    confidence?: number;
    entryRange?: { min: number; max: number };
    stopLoss?: number;
    takeProfit1?: number;
    takeProfit2?: number;
    takeProfit3?: number;
    currentPrice?: number;
    symbol?: string;
    timestamp?: number;
  }> {
    return request('/api/strategies/active-signal');
  },

  fetchSignalBreakdown(symbol: string, timeframe: string, tradeStyle: string, actionable = false): Promise<{
    direction: string;
    confidence: number;
    entryMin: number;
    entryMax: number;
    stopLoss: number;
    takeProfit1: number;
    takeProfit2: number;
    takeProfit3: number;
    status: string;
    symbol: string;
    createdAt: string;
    expiresAt?: string;
    signalId?: string;
    currentPrice?: number;
    displaySource?: string;
    fallbackReason?: string;
    sourceTimeframe?: string;
    sourceTradeStyle?: string;
    aiScore: Record<string, unknown>;
  }> {
    const params = new URLSearchParams({ timeframe, trade_style: tradeStyle });
    if (actionable) params.set('actionable', 'true');
    return request<Record<string, unknown>>(`/api/signals/breakdown/${encodeURIComponent(symbol)}?${params.toString()}`)
      .then((payload) => {
        const readNumber = (...values: unknown[]) => {
          for (const value of values) {
            if (typeof value === 'number' && Number.isFinite(value)) return value;
            if (typeof value === 'string' && value.trim().length > 0) {
              const parsed = Number(value);
              if (Number.isFinite(parsed)) return parsed;
            }
          }
          return 0;
        };

        const readString = (...values: unknown[]) => {
          for (const value of values) {
            if (typeof value === 'string' && value.trim().length > 0) return value;
          }
          return '';
        };

        const aiScore = payload.aiScore;

        return {
          direction: readString(payload.direction).toUpperCase() || 'HOLD',
          confidence: readNumber(payload.confidence),
          entryMin: readNumber(payload.entryMin, payload.entry_min),
          entryMax: readNumber(payload.entryMax, payload.entry_max),
          stopLoss: readNumber(payload.stopLoss, payload.stop_loss),
          takeProfit1: readNumber(payload.takeProfit1, payload.take_profit1),
          takeProfit2: readNumber(payload.takeProfit2, payload.take_profit2),
          takeProfit3: readNumber(payload.takeProfit3, payload.take_profit3),
          status: readString(payload.status, payload.signal_status) || 'VALID',
          symbol: readString(payload.symbol) || symbol,
          createdAt: readString(payload.createdAt, payload.created_at, payload.timestamp) || new Date().toISOString(),
          expiresAt: readString(payload.expiresAt, payload.expires_at) || undefined,
          signalId: readString(payload.signalId, payload.signal_id) || undefined,
          currentPrice: readNumber(payload.currentPrice, payload.current_price),
          displaySource: readString(payload.displaySource, payload.display_source) || undefined,
          fallbackReason: readString(payload.fallbackReason, payload.fallback_reason) || undefined,
          sourceTimeframe: readString(payload.timeframe) || undefined,
          sourceTradeStyle: readString(payload.tradeStyle, payload.trade_style) || undefined,
          aiScore: typeof aiScore === 'object' && aiScore !== null ? aiScore as Record<string, unknown> : {},
        };
      });
  },

  fetchQuote(symbol: string, timeframe?: string, tradeStyle?: string): Promise<{
    symbol: string;
    timeframe: string;
    currentPrice: number;
    priceChange: number;
    priceChangePercent: number;
    data_fetched_at: number;
    source: string;
    priceSource: string;
    sourceMetadata: SourceMetadata;
  }> {
    const params = new URLSearchParams();
    if (timeframe) params.set('timeframe', timeframe);
    if (tradeStyle) params.set('trade_style', tradeStyle);
    const qs = params.toString();
    return request(`/api/market/quote/${encodeURIComponent(symbol)}${qs ? `?${qs}` : ''}`);
  },

  fetchCandles(symbol: string, timeframe: string, limit = 200, tradeStyle?: string): Promise<{
    candles: Array<{
      time: number;
      open: number;
      high: number;
      low: number;
      close: number;
      volume: number;
    }>;
    source: string;
    fetched_at: number;
    is_mock?: boolean;
    sourceMetadata?: SourceMetadata;
  }> {
    const params = new URLSearchParams({
      timeframe,
      limit: String(limit),
    });
    if (tradeStyle) params.set('trade_style', tradeStyle);
    return request(`/api/market/candles/${encodeURIComponent(symbol)}?${params.toString()}`);
  },

  fetchMarketPrediction(symbol: string, timeframe: string, tradeStyle: string): Promise<AIPrediction> {
    const params = new URLSearchParams({ timeframe, trade_style: tradeStyle });
    return request<Record<string, unknown>>(`/api/market/analysis/${encodeURIComponent(symbol)}?${params.toString()}`)
      .then((payload) => normalizePredictionPayload(payload, symbol));
  },

  fetchCopyTradingSettings(): Promise<CopyTradingSettings> {
    return request<CopyTradingSettings>('/api/copy-trading/settings');
  },

  fetchCopyPositions(): Promise<{ positions: CopyTradePosition[]; count: number }> {
    return request<{ positions: CopyTradePosition[]; count: number }>('/api/copy-trading/positions');
  },

  fetchCopyStats(): Promise<CopyTradeStats> {
    return request<CopyTradeStats>('/api/copy-trading/stats');
  },

  fetchCopyHistory(limit = 20, symbol?: string): Promise<CopyTradeHistoryResponse> {
    const params = new URLSearchParams();
    params.set('limit', String(limit));
    if (symbol) params.set('symbol', symbol);
    return request<CopyTradeHistoryResponse>(`/api/copy-trading/history?${params.toString()}`);
  },

  fetchBrokerPositions(brokerId?: string, symbol?: string): Promise<Array<{
    position_id?: string | null;
    symbol: string;
    broker_id: string;
    quantity: number;
    side: string;
    avg_entry: number;
    current_price: number;
    unrealized_pnl: number;
    unrealized_pnl_pct: number;
    opened_at?: string | null;
    last_updated?: string;
  }>> {
    const params = new URLSearchParams();
    if (brokerId) params.set('broker_id', brokerId);
    if (symbol) params.set('symbol', symbol);
    const qs = params.toString();
    return request(`/api/broker/positions${qs ? `?${qs}` : ''}`);
  },

  // Broker: close position
  closePosition(brokerId: string, symbol: string, positionId?: string): Promise<{ success: boolean; message: string }> {
    const params = new URLSearchParams();
    params.set('symbol', symbol);
    if (positionId) params.set('position_id', positionId);
    return request(`/api/broker/close-position/${encodeURIComponent(brokerId)}?${params.toString()}`, {
      method: 'POST',
    });
  },

  // Broker: account balance
  fetchBrokerBalance(brokerId: string): Promise<{
    broker_id: string;
    connected: boolean;
    total_equity?: number;
    available_margin?: number;
    used_margin?: number;
    currency?: string;
  }> {
    return request(`/api/broker/balance/${encodeURIComponent(brokerId)}`);
  },

  // Broker: trade history (closed trades from broker)
  fetchTradeHistory(brokerId?: string, count = 50, symbol?: string): Promise<Array<{
    trade_id: string;
    symbol: string;
    side: string;
    quantity: number;
    entry_price: number;
    exit_price: number;
    realized_pnl: number;
    opened_at: string;
    closed_at: string;
    state: string;
  }>> {
    const params = new URLSearchParams();
    if (brokerId) params.set('broker_id', brokerId);
    params.set('count', String(count));
    if (symbol) params.set('symbol', symbol);
    return request(`/api/broker/trade-history?${params.toString()}`);
  },

  fetchBrokerOrders(brokerId?: string, count = 20, status?: string, symbol?: string): Promise<Array<{
    order_id: string;
    symbol: string;
    side: string;
    order_type: string;
    quantity: number;
    price: number | null;
    status: string;
    filled_quantity: number;
    avg_fill_price: number;
    stop_loss?: number | null;
    take_profit_1?: number | null;
    take_profit_2?: number | null;
    take_profit_3?: number | null;
    broker_id: string;
    created_at: string | null;
    updated_at: string | null;
  }>> {
    const params = new URLSearchParams();
    if (brokerId) params.set('broker_id', brokerId);
    params.set('count', String(count));
    if (status) params.set('status', status);
    if (symbol) params.set('symbol', symbol);
    return request(`/api/broker/orders?${params.toString()}`);
  },

  fetchTradeLedger(brokerId?: string, count = 100, status?: string, symbol?: string): Promise<{
    entries: Array<{
      ledger_id: string;
      broker_id: string;
      source_type: string;
      source_id: string;
      signal_id?: string | null;
      symbol: string;
      side: string;
      status: string;
      quantity: number;
      remaining_quantity?: number | null;
      entry_price?: number | null;
      current_price?: number | null;
      exit_price?: number | null;
      stop_loss?: number | null;
      take_profit_1?: number | null;
      take_profit_2?: number | null;
      take_profit_3?: number | null;
      unrealized_pnl: number;
      realized_pnl: number;
      mfe?: number | null;
      mae?: number | null;
      r_multiple?: number | null;
      outcome?: string | null;
      opened_at?: string | null;
      closed_at?: string | null;
      updated_at: string;
      metadata?: Record<string, unknown>;
    }>;
    summary: {
      total_entries: number;
      open_entries: number;
      realized_pnl: number;
      unrealized_pnl: number;
      connected_brokers: string[];
    };
  }> {
    const params = new URLSearchParams();
    if (brokerId) params.set('broker_id', brokerId);
    params.set('count', String(count));
    if (status) params.set('status', status);
    if (symbol) params.set('symbol', symbol);
    return request(`/api/broker/ledger?${params.toString()}`);
  },

  fetchLedgerMetrics(brokerId?: string, symbol?: string, limit = 500): Promise<{
    total_entries: number;
    open_entries: number;
    closed_entries: number;
    realized_pnl: number;
    unrealized_pnl: number;
    win_rate: number;
    profit_factor: number | null;
    avg_r_multiple: number | null;
    avg_mfe: number | null;
    avg_mae: number | null;
    by_symbol: Array<{
      symbol: string;
      total: number;
      win_rate: number;
      realized_pnl: number;
    }>;
  }> {
    const params = new URLSearchParams();
    params.set('limit', String(limit));
    if (brokerId) params.set('broker_id', brokerId);
    if (symbol) params.set('symbol', symbol);
    return request(`/api/metrics/ledger?${params.toString()}`);
  },

  buildTradeLedgerExportUrl(params: {
    brokerId?: string;
    symbol?: string;
    status?: string;
    side?: string;
    outcome?: string;
    count?: number;
  } = {}): string {
    const query = new URLSearchParams();
    query.set('count', String(params.count ?? 1000));
    if (params.brokerId) query.set('broker_id', params.brokerId);
    if (params.symbol) query.set('symbol', params.symbol);
    if (params.status) query.set('status', params.status);
    if (params.side) query.set('side', params.side);
    if (params.outcome) query.set('outcome', params.outcome);
    return `/api/broker/ledger/export?${query.toString()}`;
  },

  placeBrokerOrder(order: {
    broker_id: string;
    symbol: string;
    side: 'buy' | 'sell';
    quantity: number;
    order_type?: 'market' | 'limit' | 'stop';
    price?: number | null;
    stop_loss?: number | null;
    take_profit_1?: number | null;
    take_profit_2?: number | null;
    take_profit_3?: number | null;
    signal_id?: string | null;
  }): Promise<{
    success: boolean;
    order_id: string;
    status: string;
    symbol: string;
    side: string;
    quantity: number;
    price: number | null;
    stop_loss?: number | null;
    take_profit_1?: number | null;
    take_profit_2?: number | null;
    take_profit_3?: number | null;
    message: string;
    timestamp: string;
  }> {
    return request('/api/broker/order', {
      method: 'POST',
      body: JSON.stringify(order),
    });
  },

  // Broker: modify trade SL/TP
  modifyTrade(brokerId: string, tradeId: string, params: {
    stop_loss?: number;
    take_profit?: number;
  }): Promise<{ success: boolean; trade_id: string; message: string }> {
    return request(`/api/broker/trade/${encodeURIComponent(brokerId)}/${encodeURIComponent(tradeId)}`, {
      method: 'PUT',
      body: JSON.stringify(params),
    });
  },

  fetchCopyHistoryFiltered(params: {
    limit?: number;
    offset?: number;
    symbol?: string;
    status?: string;
    direction?: 'BUY' | 'SELL';
    fromTs?: number;
    toTs?: number;
    sortBy?: 'closed_at' | 'created_at' | 'symbol' | 'direction' | 'status' | 'realized_pnl' | 'confidence';
    sortDir?: 'asc' | 'desc';
  }): Promise<CopyTradeHistoryResponse> {
    const qs = new URLSearchParams();
    qs.set('limit', String(params.limit ?? 50));
    if (params.offset != null) qs.set('offset', String(params.offset));
    if (params.symbol) qs.set('symbol', params.symbol);
    if (params.status) qs.set('status', params.status);
    if (params.direction) qs.set('direction', params.direction);
    if (params.fromTs != null) qs.set('from_ts', String(params.fromTs));
    if (params.toTs != null) qs.set('to_ts', String(params.toTs));
    if (params.sortBy) qs.set('sort_by', params.sortBy);
    if (params.sortDir) qs.set('sort_dir', params.sortDir);
    return request<CopyTradeHistoryResponse>(`/api/copy-trading/history?${qs.toString()}`);
  },
};

export default api;
