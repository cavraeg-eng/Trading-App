export interface Position {
  id: string;
  symbol: string;
  side: 'long' | 'short';
  size: number;
  entryPrice: number;
  currentPrice: number;
  pnl: number;
  pnlPercent: number;
  entryTime: string;
}

export interface Trade {
  id: string;
  symbol: string;
  side: 'buy' | 'sell';
  price: number;
  size: number;
  pnl?: number;
  time: string;
}

export interface AccountMetrics {
  balance: number;
  equity: number;
  openPnL: number;
  dayPnL: number;
  totalReturn: number;
  maxDrawdown: number;
  sharpeRatio: number;
  winRate: number;
  totalTrades: number;
}

export interface BacktestResult {
  totalReturn: number;
  sharpeRatio: number;
  maxDrawdown: number;
  winRate: number;
  profitFactor: number;
  numTrades: number;
  equityCurve: { time: string; value: number }[];
}

export interface ForexPair {
  symbol: string;       // e.g. "EUR/USD"
  name: string;         // e.g. "Euro / US Dollar"
  nickname: string;     // e.g. "Fiber"
  category: 'major' | 'minor' | 'exotic' | 'commodity' | 'crypto' | 'index';
  baseSpread: number;   // typical spread in pips, e.g. 0.2
  basePriceApprox: number; // approximate base price for mock data generation, e.g. 1.08
}

export type ChartType = 'candlestick' | 'line' | 'area' | 'bar' | 'heikin-ashi';

export type IndicatorType = 'RSI' | 'MACD' | 'BollingerBands' | 'EMA' | 'Volume' | 'ATR';

export interface AIRecommendation {
  pair: ForexPair;
  signal: 'BUY' | 'SELL' | 'HOLD';
  confidence: number;     // 0-100
  sharpeRatio: number;
  volatility: 'LOW' | 'NORMAL' | 'ELEVATED' | 'HIGH';
  correlationRisk: 'LOW' | 'MEDIUM' | 'HIGH';
}

export interface IndicatorCondition {
  indicator: string;
  operator: string;
  value: number;
  value2?: number;
  compare_indicator?: string;
}

export type ScannerTimeframe = '1m' | '5m' | '15m' | '1h' | '4h' | '1d';
export type TradeStyle = 'scalp' | 'swing';
export type ScannerLogic = 'AND' | 'OR';

export interface ScannerConditionGroup {
  id: string;
  name?: string;
  logic: ScannerLogic;
  conditions: IndicatorCondition[];
}

export interface ScannerConfig {
  name: string;
  conditions: IndicatorCondition[];
  logic: ScannerLogic;
  groups?: ScannerConditionGroup[];
  pairs?: string[];
  trade_style?: TradeStyle;
  timeframe?: ScannerTimeframe;
}

export interface ScanResult {
  symbol: string;
  signal?: string;
  score: number;
  matching_conditions: string[];
  indicator_values: Record<string, number>;
  confidence?: number;
  market_regime?: string;
  trade_style?: TradeStyle | string;
  timeframe?: ScannerTimeframe | string;
  opportunity_score?: number;
  source_score?: number;
  source_metadata?: SourceMetadata;
  reason?: string;
  entry_range?: { min: number; max: number };
  stop_loss?: number;
  take_profit1?: number;
  take_profit2?: number;
  take_profit3?: number;
  current_price?: number;
  risk_gate?: 'low' | 'medium' | 'high';
  risk_context?: { volatility_regime: string; market_status: string };
  atr?: number;
  scan_status?: 'matched' | 'warning' | 'error';
  error_message?: string;
  evaluation_latency_ms?: number;
  prediction_latency_ms?: number;
  group_results?: Array<{ name: string; logic: string; passed: boolean; score: number; matched_count: number; total_count: number }>;
}

export interface ScannerRunMetadata {
  batch_duration_ms?: number;
  concurrency_limit?: number;
  total_symbols?: number;
  succeeded?: number;
  failed?: number;
  unmatched?: number;
}

export interface ScannerPreset {
  id: string;
  name: string;
  description: string;
  icon: string;
  conditions: IndicatorCondition[];
  logic?: ScannerLogic;
  groups?: ScannerConditionGroup[];
  trade_style?: TradeStyle;
  timeframe?: ScannerTimeframe;
  recommended_pairs?: string[];
  tags?: string[];
  category?: string;
  best_for?: string;
  cadence?: string;
  risk?: 'low' | 'medium' | 'high';
  popularity?: string;
  accent?: string;
}

export interface ScannerIndicatorDefinition {
  key: string;
  label: string;
  description: string;
  supported: boolean;
  supportsCompareIndicator: boolean;
  operators: string[];
  range: {
    min: number;
    max: number;
    step: number;
  };
  defaultValue: number;
}

export interface ScannerMetadata {
  indicators: ScannerIndicatorDefinition[];
  operators: { value: string; label: string }[];
  supportedTimeframes: ScannerTimeframe[];
  supportedTradeStyles: TradeStyle[];
  supportedCategories: ForexPair['category'][];
}

export interface SavedScanner {
  id: number;
  name: string;
  config: ScannerConfig;
  created_at: string;
  updated_at?: string;
}

export interface IndicatorContribution {
  name: string;
  value: number;
  signal: 'bullish' | 'bearish' | 'neutral';
  weight: number;
  contribution: number;
  description?: string;
}

export interface SignalBreakdownData {
  symbol: string;
  direction: 'BUY' | 'SELL' | 'HOLD';
  confidence: number;
  signalStrength: number;
  indicators: IndicatorContribution[];
  patternAccuracy: number | null;
  explanation: string;
  timestamp: string;
}

export interface DetectedPattern {
  name: string;
  type: 'breakout' | 'breakdown' | 'continuation' | 'reversal';
  direction: 'bullish' | 'bearish';
  confidence: number;
  targetPrice: number;
  successRate: number;
  description: string;
}

export interface AIScoreData {
  value: number;
  label: 'Strong' | 'Favorable' | 'Neutral' | 'Cautious';
  factors: {
    modelConfidence: number;
    indicatorConsensus: number;
    marketRegimeFit: number;
    patternStrength: number;
    sentimentScore: number;
    volumeMomentum: number;
  };
}

export interface SourceMetadata {
  symbol?: string;
  timeframe?: string;
  tradeStyle?: 'scalp' | 'swing' | string;
  sourceName: string;
  sourceType: string;
  priceSource: string;
  isFallback: boolean;
  freshnessSeconds: number | null;
  qualityFlags: string[];
  lastBarTimestamp: number | null;
  marketStatus: 'live' | 'delayed' | 'stale' | 'unknown' | string;
}

export interface GoldContextData {
  symbol: string;
  timestamp: number;
  session: 'asia' | 'london' | 'new_york' | 'after_hours' | string;
  dxy: {
    value: number | null;
    change: number | null;
  };
  yields10y: {
    value: number | null;
    change: number | null;
  };
  gold: {
    value: number | null;
  };
  volatilityRegime: 'calm' | 'normal' | 'elevated' | 'high' | 'unknown' | string;
  macroRisk: 'normal' | 'elevated' | string;
}

export interface SpotProviderStatus {
  available: boolean;
  cooldownRemainingSeconds: number;
  cooldownUntil: number | null;
}

export interface DatasourceHealthResponse {
  sources: Record<string, {
    status: string;
    last_success?: number | null;
    last_failure?: number | null;
    success_count?: number;
    failure_count?: number;
    fallback_count?: number;
    last_error?: string | null;
    median_latency_ms?: number | null;
    p95_latency_ms?: number | null;
  }>;
  spotProviders: Record<string, SpotProviderStatus>;
  cache: {
    entries: number;
    oldest_entry_age_s: number | null;
    sources: Record<string, number>;
  };
  timestamp: number;
}

export interface OpportunityRow {
  symbol: string;
  timeframe: string;
  tradeStyle: 'scalp' | 'swing' | string;
  signal: string;
  confidence: number;
  marketRegime: string;
  reason: string;
  currentPrice: number;
  opportunityScore: number;
  confidenceScore: number;
  aiScore: number;
  sourceScore: number;
  regimeScore: number;
  signalStrength: string;
  sourceMetadata: SourceMetadata;
}

export interface StrategyDefinition {
  id: string;
  name: string;
  symbol: string;
  tradeStyle: 'scalp' | 'swing' | string;
  category: string;
  description: string;
  bestTimeframes: string[];
  bestSession: string;
  riskLevel: string;
  sourcePolicy: string;
  tags: string[];
  performance: {
    winRate: number;
    profitFactor: number;
    maxDrawdown: number;
    expectancy: number;
  };
  isActive?: boolean;
  activeMode?: string | null;
  performanceSnapshot?: StrategyPerformanceSnapshot | null;
}

export interface AutomationTemplate {
  strategyId: string;
  mode: string;
  allocationPercent: number;
  maxPositions: number;
  enabled: boolean;
  cooldownSeconds?: number;
  maxExecutionsPerHour?: number;
}

export interface StrategyPerformanceSnapshot {
  symbol: string;
  timeframe: string;
  tradeStyle: string;
  metrics: {
    totalReturn: number;
    sharpeRatio: number;
    maxDrawdown: number;
    winRate: number;
    profitFactor: number;
    numTrades: number;
  };
  report?: Record<string, unknown>;
  savedAt: string;
}

export interface AutomationCenterState {
  activeStrategy: StrategyDefinition | null;
  activeMode: string;
  template: AutomationTemplate | null;
  performanceSnapshot: StrategyPerformanceSnapshot | null;
  worker?: {
    running: boolean;
    lastRun: number | null;
    lastExecution: number | null;
    lastError: string | null;
  };
  executions?: Array<{
    id: number;
    strategy_id: string;
    symbol: string;
    action: string;
    status: string;
    detail: Record<string, unknown>;
    created_at: string;
  }>;
}

export interface SentimentHeadline {
  title: string;
  source: string;
  sentiment: number;
  timestamp: string;
  url?: string;
}

export interface SentimentData {
  symbol: string;
  score: number;
  label: 'bullish' | 'bearish' | 'neutral';
  headlines: SentimentHeadline[];
  trend: number[];
  lastUpdated: string;
  sourceCount: number;
}

export interface LeaderboardEntry {
  rank: number;
  username: string;
  avatar: string;
  monthlyReturn: number;
  winRate: number;
  sharpeRatio: number;
  totalTrades: number;
  followers: number;
  isFollowing?: boolean;
}

export interface SignalPost {
  id: string;
  username: string;
  avatar: string;
  symbol: string;
  direction: 'BUY' | 'SELL' | 'HOLD';
  confidence: number;
  entryPrice: number;
  stopLoss?: number;
  takeProfit?: number;
  result?: 'won' | 'lost' | 'open';
  pnl?: number;
  timestamp: string;
  likes: number;
  comments: number;
  isLiked?: boolean;
}

// Signal validity status
export type SignalStatus = 'OPTIMAL_ENTRY' | 'VALID' | 'ABOUT_TO_EXPIRE' | 'EXPIRED';

export type TradeLevelOverlayKind = 'entry' | 'stop_loss' | 'take_profit' | 'current' | 'exit';
export type TradeLevelOverlayStatus = 'active' | 'pending' | 'closed';

export interface TradeLevelOverlay {
  id: string;
  kind: TradeLevelOverlayKind;
  label: string;
  price: number | null | undefined;
  status: TradeLevelOverlayStatus;
  direction?: 'BUY' | 'SELL' | 'HOLD';
  targetIndex?: number;
}

// Chart signal marker for overlay on Lightweight Charts
export interface ChartSignalMarker {
  entry?: number | null;
  entryMin?: number | null;
  entryMax?: number | null;
  stopLoss?: number | null;
  takeProfit1?: number | null;
  takeProfit2?: number | null;
  takeProfit3?: number | null;
  signalId?: string;
  direction: 'BUY' | 'SELL' | 'HOLD';
  timestamp: string; // ISO format
  status: SignalStatus;
  setupStatus?: TradeLevelOverlayStatus;
  confidence: number; // 0-100
  symbol: string;
  expiresAt?: string; // ISO format
}

export interface CopyTradingSettings {
  enabled: boolean;
  max_position_size_lots: number;
  max_risk_percent: number;
  max_concurrent_positions: number;
  lot_size_scale: number;
  auto_close_on_signal_expire: boolean;
  allowed_symbols: string[];
  min_confidence: number;
}

export interface CopyTradePosition {
  copy_trade_id: string;
  signal_id?: string;
  symbol: string;
  direction: 'BUY' | 'SELL';
  quantity: number;
  remaining_quantity: number;
  entry_price: number;
  current_price: number;
  initial_stop_loss?: number;
  stop_loss: number;
  take_profit1: number;
  take_profit2?: number;
  take_profit3?: number;
  confidence: number;
  risk_percent: number;
  status: string;
  unrealized_pnl: number;
  realized_pnl: number;
  realized_pnl_tp1?: number;
  realized_pnl_tp2?: number;
  partial_exit_count?: number;
  tp1_hit?: boolean;
  tp2_hit?: boolean;
  tp3_hit?: boolean;
  stop_moved_to_breakeven?: boolean;
  trailing_stop_active?: boolean;
  max_favorable_price?: number | null;
  max_adverse_price?: number | null;
  created_at: number;
  closed_at?: number | null;
  holding_seconds?: number | null;
  trade_style: string;
  timeframe: string;
  signal_source: string;
}

export interface CopyTradeHistoryResponse {
  history: CopyTradePosition[];
  count: number;
  total?: number;
  offset?: number;
  limit?: number;
}

export interface CopyTradeStats {
  total_trades: number;
  open_trades: number;
  closed_trades: number;
  total_pnl: number;
  total_unrealized_pnl: number;
  win_rate: number;
  avg_pnl: number;
  expectancy: number;
  profit_factor: number | null;
  best_trade: number;
  worst_trade: number;
  max_drawdown: number;
  current_loss_streak: number;
  max_loss_streak: number;
  avg_hold_seconds: number;
  avg_r_multiple: number | null;
  avg_mfe?: number | null;
  avg_mae?: number | null;
  partial_exit_trades: number;
  symbol_breakdown: Array<{
    symbol: string;
    total_trades: number;
    win_rate: number;
    total_pnl: number;
    avg_pnl: number;
  }>;
  recent_closed: Array<{
    copy_trade_id: string;
    symbol: string;
    status: string;
    realized_pnl: number;
    closed_at?: number | null;
    holding_seconds?: number | null;
    r_multiple?: number | null;
    mfe?: number | null;
    mae?: number | null;
  }>;
  equity_curve: Array<{
    copy_trade_id: string;
    symbol: string;
    closed_at?: number | null;
    cumulative_pnl: number;
  }>;
}

// Smart Alert from backend
export interface SmartAlert {
  id: number;
  symbol: string;
  alert_type: 'STRONG_SIGNAL' | 'PATTERN_COMPLETE' | 'MULTITF_ALIGNED' | 'SCORE_CHANGE' | 'SCANNER_MATCH';
  title: string;
  message: string;
  severity: 'info' | 'warning' | 'critical';
  data: string;
  read: number;
  created_at: string;
}

// OHLCV candle data from backend
export interface CandleData {
  time: number; // Unix timestamp in seconds
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

// Multi-TF Alignment from /api/ai/alignment
export interface AlignmentTimeframe {
  tf: string;
  direction: string;
  confidence: number;
  signal: string;
  aligned: boolean;
  weight: number;
}

export interface AlignmentData {
  symbol: string;
  alignmentScore: number;
  strength: string;
  dominantDirection: string;
  agreeing: number;
  total: number;
  timeframes: AlignmentTimeframe[];
  timestamp: string;
}

// Active position overlay for TradingChart MT5-style display
export interface ActivePositionOverlay {
  entryPrice: number;
  currentPrice: number;
  side: 'long' | 'short';
  unrealizedPnl: number;
  quantity: number;
  positionId?: string;
  status?: TradeLevelOverlayStatus;
  stopLoss?: number;
  takeProfit1?: number;
  takeProfit2?: number;
  takeProfit3?: number;
}

// Ghost overlay for closed trade history visualization
export interface GhostTradeOverlay {
  entryPrice: number;
  exitPrice: number;
  side: 'buy' | 'sell';
  realizedPnl: number;
  symbol: string;
  stopLoss?: number;
  takeProfit1?: number;
  takeProfit2?: number;
  takeProfit3?: number;
}

// Signal backtest result from POST /api/backtest/signal
export interface SignalBacktestResult {
  symbol: string;
  direction: string;
  lookbackDays: number;
  totalReturn: number;
  sharpeRatio: number;
  maxDrawdown: number;
  winRate: number;
  profitFactor: number;
  numTrades: number;
  avgHoldingPeriod: string;
  bestTrade: number;
  worstTrade: number;
  avgRiskReward: number;
  confidenceCalibration: {
    description: string;
    profitablePercent: number;
  };
  equityCurve: Array<{ time: string; value: number }>;
}
