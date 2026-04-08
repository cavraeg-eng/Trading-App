export interface PriceData {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

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
}

export interface ScannerConfig {
  name: string;
  conditions: IndicatorCondition[];
  logic: 'AND' | 'OR';
  pairs?: string[];
}

export interface ScanResult {
  symbol: string;
  score: number;
  matching_conditions: string[];
  indicator_values: Record<string, number>;
}

export interface ScannerPreset {
  id: string;
  name: string;
  description: string;
  icon: string;
  conditions: IndicatorCondition[];
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

// Chart signal marker for overlay on Lightweight Charts
export interface ChartSignalMarker {
  entry: number;
  entryMin: number;
  entryMax: number;
  stopLoss: number;
  takeProfit1: number;
  takeProfit2: number;
  takeProfit3: number;
  direction: 'BUY' | 'SELL' | 'HOLD';
  timestamp: string; // ISO format
  status: SignalStatus;
  confidence: number; // 0-100
  symbol: string;
  expiresAt?: string; // ISO format
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
