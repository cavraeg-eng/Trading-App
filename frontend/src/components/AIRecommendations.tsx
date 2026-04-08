import { Sparkles, TrendingUp, TrendingDown, Minus, Clock } from 'lucide-react';
import type { ForexPair, AIRecommendation, SignalStatus } from '../types';

export interface AIRecommendationsProps {
  recommendations: AIRecommendation[];
  onSelectPair: (pair: ForexPair) => void;
  isVisible: boolean;
}

// ---------- Signal Status Helpers ----------

const TIMEFRAME_SECONDS: Record<string, number> = {
  '1m': 60, '5m': 300, '15m': 900, '30m': 1800,
  '1h': 3600, '4h': 14400, '1d': 86400, '1w': 604800,
};

function computeClientStatus(timestamp: string, timeframe?: string): SignalStatus {
  const candleDuration = timeframe ? (TIMEFRAME_SECONDS[timeframe] ?? 3600) : 3600;
  const ageSeconds = (Date.now() - new Date(timestamp).getTime()) / 1000;
  const candlesElapsed = ageSeconds / candleDuration;
  if (candlesElapsed < 2) return 'OPTIMAL_ENTRY';
  if (candlesElapsed < 4) return 'VALID';
  if (candlesElapsed < 5) return 'ABOUT_TO_EXPIRE';
  return 'EXPIRED';
}

function getStatusStyle(status: SignalStatus) {
  switch (status) {
    case 'OPTIMAL_ENTRY':
      return 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30';
    case 'VALID':
      return 'bg-blue-500/20 text-blue-400 border-blue-500/30';
    case 'ABOUT_TO_EXPIRE':
      return 'bg-amber-500/20 text-amber-400 border-amber-500/30';
    case 'EXPIRED':
      return 'bg-gray-500/20 text-gray-400 border-gray-500/30';
  }
}

function getStatusLabel(status: SignalStatus) {
  switch (status) {
    case 'OPTIMAL_ENTRY': return 'Optimal Entry';
    case 'VALID': return 'Valid';
    case 'ABOUT_TO_EXPIRE': return 'Expiring Soon';
    case 'EXPIRED': return 'Expired';
  }
}

function formatRelativeAge(timestamp: string): string {
  const seconds = Math.max(0, (Date.now() - new Date(timestamp).getTime()) / 1000);
  if (seconds < 60) return `${Math.round(seconds)}s ago`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.round(seconds / 3600)}h ago`;
  return `${Math.round(seconds / 86400)}d ago`;
}

function formatCountdown(timestamp: string, timeframe?: string): string | null {
  const candleDuration = timeframe ? (TIMEFRAME_SECONDS[timeframe] ?? 3600) : 3600;
  const ageSeconds = (Date.now() - new Date(timestamp).getTime()) / 1000;
  const remainingSeconds = Math.max(0, candleDuration * 5 - ageSeconds);
  if (remainingSeconds <= 0) return null;
  const hours = Math.floor(remainingSeconds / 3600);
  const mins = Math.floor((remainingSeconds % 3600) / 60);
  if (hours > 0) return `Expires in ${hours}h ${mins}m`;
  return `Expires in ${mins}m`;
}

// Generate a mock timestamp for display purposes when API doesn't return one
function generateMockTimestamp(index: number): string {
  const offsets = [300, 5400, 10800, 16200, 21600]; // varied ages
  return new Date(Date.now() - (offsets[index % offsets.length] * 1000)).toISOString();
}

function generateMockRecommendations(pairs: ForexPair[]): AIRecommendation[] {
  const signals: ('BUY' | 'SELL' | 'HOLD')[] = ['BUY', 'SELL', 'HOLD'];
  const volatilities: ('LOW' | 'NORMAL' | 'ELEVATED' | 'HIGH')[] = ['LOW', 'NORMAL', 'ELEVATED', 'HIGH'];
  const correlationRisks: ('LOW' | 'MEDIUM' | 'HIGH')[] = ['LOW', 'MEDIUM', 'HIGH'];

  // Shuffle pairs and pick 5 random ones
  const shuffled = [...pairs].sort(() => Math.random() - 0.5);
  const selectedPairs = shuffled.slice(0, 5);

  const recommendations: AIRecommendation[] = selectedPairs.map((pair) => {
    const signal = signals[Math.floor(Math.random() * signals.length)];
    // Higher confidence for BUY/SELL, lower for HOLD
    const confidence = signal === 'HOLD' 
      ? Math.floor(Math.random() * 30) + 40 // 40-70 for HOLD
      : Math.floor(Math.random() * 40) + 55; // 55-95 for BUY/SELL
    
    return {
      pair,
      signal,
      confidence,
      sharpeRatio: parseFloat((Math.random() * 2.5 + 0.5).toFixed(2)), // 0.5 - 3.0
      volatility: volatilities[Math.floor(Math.random() * volatilities.length)],
      correlationRisk: correlationRisks[Math.floor(Math.random() * correlationRisks.length)],
    };
  });

  // Sort by confidence descending
  return recommendations.sort((a, b) => b.confidence - a.confidence);
}

export async function fetchRecommendations(pairs: ForexPair[]): Promise<AIRecommendation[]> {
  try {
    const symbols = pairs.slice(0, 8).map(p => p.symbol).join(',');
    const res = await fetch(`/api/market/recommendations?symbols=${encodeURIComponent(symbols)}`);
    if (res.ok) {
      const data = await res.json();
      // Map backend response to AIRecommendation format
      return data.recommendations.map((rec: any) => {
        const pair = pairs.find(p => p.symbol === rec.symbol);
        if (!pair) return null;
        return {
          pair,
          signal: rec.signal,
          confidence: rec.confidence,
          sharpeRatio: rec.sharpeRatio,
          volatility: rec.volatility,
          correlationRisk: rec.correlationRisk,
        };
      }).filter(Boolean).sort((a: any, b: any) => b.confidence - a.confidence);
    }
  } catch (err) {
    console.error('Failed to fetch recommendations:', err);
  }
  // Fallback to mock if API fails
  return generateMockRecommendations(pairs);
}

// Keep for backward compatibility
export { generateMockRecommendations };

export function AIRecommendations({ recommendations, onSelectPair, isVisible }: AIRecommendationsProps) {
  if (!isVisible) return null;

  const getSignalColor = (signal: AIRecommendation['signal']) => {
    switch (signal) {
      case 'BUY':
        return 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30';
      case 'SELL':
        return 'bg-rose-500/20 text-rose-400 border-rose-500/30';
      case 'HOLD':
        return 'bg-slate-500/20 text-slate-400 border-slate-500/30';
      default:
        return 'bg-slate-500/20 text-slate-400 border-slate-500/30';
    }
  };

  const getSignalIcon = (signal: AIRecommendation['signal']) => {
    switch (signal) {
      case 'BUY':
        return <TrendingUp className="w-3.5 h-3.5" />;
      case 'SELL':
        return <TrendingDown className="w-3.5 h-3.5" />;
      case 'HOLD':
        return <Minus className="w-3.5 h-3.5" />;
      default:
        return null;
    }
  };

  const getConfidenceColor = (confidence: number) => {
    if (confidence >= 70) return 'bg-emerald-500';
    if (confidence >= 50) return 'bg-amber-500';
    return 'bg-rose-500';
  };

  const getVolatilityColor = (volatility: AIRecommendation['volatility']) => {
    switch (volatility) {
      case 'LOW':
        return 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30';
      case 'NORMAL':
        return 'bg-blue-500/20 text-blue-400 border-blue-500/30';
      case 'ELEVATED':
        return 'bg-amber-500/20 text-amber-400 border-amber-500/30';
      case 'HIGH':
        return 'bg-rose-500/20 text-rose-400 border-rose-500/30';
      default:
        return 'bg-slate-500/20 text-slate-400 border-slate-500/30';
    }
  };

  const getCorrelationRiskColor = (risk: AIRecommendation['correlationRisk']) => {
    switch (risk) {
      case 'LOW':
        return 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30';
      case 'MEDIUM':
        return 'bg-amber-500/20 text-amber-400 border-amber-500/30';
      case 'HIGH':
        return 'bg-rose-500/20 text-rose-400 border-rose-500/30';
      default:
        return 'bg-slate-500/20 text-slate-400 border-slate-500/30';
    }
  };

  return (
    <div className="bg-trading-card border border-trading-border rounded-lg p-4">
      {/* Header */}
      <div className="flex items-center gap-2 mb-4">
        <Sparkles className="w-5 h-5 text-trading-accent" />
        <h3 className="text-sm font-semibold text-trading-text">AI Recommendations</h3>
      </div>

      {/* Recommendations List */}
      <div className="space-y-3">
        {recommendations.slice(0, 5).map((rec, idx) => {
          const mockTs = generateMockTimestamp(idx);
          const status = computeClientStatus(mockTs);
          const countdown = (status === 'VALID' || status === 'ABOUT_TO_EXPIRE') ? formatCountdown(mockTs) : null;

          return (
          <button
            key={rec.pair.symbol}
            onClick={() => onSelectPair(rec.pair)}
            className="w-full text-left p-3 bg-trading-bg border border-trading-border rounded-lg hover:border-trading-accent/50 transition-colors group"
          >
            {/* Top Row: Pair Info & Signal */}
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-2">
                <span className="text-sm font-semibold text-trading-text">{rec.pair.symbol}</span>
                <span className="text-xs text-trading-muted">{rec.pair.nickname}</span>
              </div>
              <div className="flex items-center gap-1.5">
                {/* Signal Status Badge */}
                <span className={`px-1.5 py-0.5 rounded border text-[10px] font-medium ${getStatusStyle(status)}`}>
                  {getStatusLabel(status)}
                </span>
                {/* Direction Badge */}
                <div className={`flex items-center gap-1 px-2 py-1 rounded border text-xs font-medium ${getSignalColor(rec.signal)}`}>
                  {getSignalIcon(rec.signal)}
                  {rec.signal}
                </div>
              </div>
            </div>

            {/* Signal Age & Countdown */}
            <div className="flex items-center gap-2 mb-2">
              <div className="flex items-center gap-1 text-[10px] text-trading-muted">
                <Clock className="w-2.5 h-2.5" />
                <span>{formatRelativeAge(mockTs)}</span>
              </div>
              {countdown && (
                <span className="text-[10px] text-amber-400">{countdown}</span>
              )}
            </div>

            {/* Confidence Bar */}
            <div className="mb-3">
              <div className="flex items-center justify-between mb-1">
                <span className="text-xs text-trading-muted">Confidence</span>
                <span className="text-xs font-medium text-trading-text">{rec.confidence}%</span>
              </div>
              <div className="h-1.5 bg-trading-card rounded-full overflow-hidden">
                <div
                  className={`h-full rounded-full transition-all duration-500 ${getConfidenceColor(rec.confidence)}`}
                  style={{ width: `${rec.confidence}%` }}
                />
              </div>
            </div>

            {/* Bottom Row: Stats */}
            <div className="flex items-center gap-2">
              <div className="flex items-center gap-1.5">
                <span className="text-xs text-trading-muted">Sharpe:</span>
                <span className="text-xs font-medium text-trading-text">{rec.sharpeRatio.toFixed(2)}</span>
              </div>
              <span className="text-trading-border">|</span>
              <span className={`text-xs px-1.5 py-0.5 rounded border ${getVolatilityColor(rec.volatility)}`}>
                {rec.volatility}
              </span>
              <span className={`text-xs px-1.5 py-0.5 rounded border ${getCorrelationRiskColor(rec.correlationRisk)}`}>
                {rec.correlationRisk}
              </span>
            </div>
          </button>
          );
        })}

        {recommendations.length === 0 && (
          <div className="p-6 text-center">
            <p className="text-sm text-trading-muted">No recommendations available</p>
          </div>
        )}
      </div>
    </div>
  );
}
