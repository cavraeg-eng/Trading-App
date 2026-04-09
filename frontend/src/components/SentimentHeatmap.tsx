import { useState, useEffect, useCallback } from 'react';
import { TrendingUp, TrendingDown, Minus } from 'lucide-react';
import type { ForexPair } from '../types';

interface SentimentHeatmapProps {
  onSelectPair: (pair: ForexPair) => void;
}

interface SentimentOverviewItem {
  symbol: string;
  score: number;
  label: 'bullish' | 'bearish' | 'neutral';
}

// Use relative URLs so the Vite proxy handles routing to the backend
const API_URL = '';

// Map sentiment symbols to ForexPair objects
const SYMBOL_TO_PAIR: Record<string, Partial<ForexPair>> = {
  'EUR/USD': { symbol: 'EUR/USD', name: 'Euro / US Dollar', nickname: 'Fiber', category: 'major', baseSpread: 0.2, basePriceApprox: 1.08 },
  'GBP/USD': { symbol: 'GBP/USD', name: 'British Pound / US Dollar', nickname: 'Cable', category: 'major', baseSpread: 0.3, basePriceApprox: 1.26 },
  'USD/JPY': { symbol: 'USD/JPY', name: 'US Dollar / Japanese Yen', nickname: 'Ninja', category: 'major', baseSpread: 0.2, basePriceApprox: 148.5 },
  'AUD/USD': { symbol: 'AUD/USD', name: 'Australian Dollar / US Dollar', nickname: 'Aussie', category: 'major', baseSpread: 0.3, basePriceApprox: 0.65 },
  'USD/CAD': { symbol: 'USD/CAD', name: 'US Dollar / Canadian Dollar', nickname: 'Loonie', category: 'major', baseSpread: 0.3, basePriceApprox: 1.35 },
  'USD/CHF': { symbol: 'USD/CHF', name: 'US Dollar / Swiss Franc', nickname: 'Swissy', category: 'major', baseSpread: 0.4, basePriceApprox: 0.88 },
  'NZD/USD': { symbol: 'NZD/USD', name: 'New Zealand Dollar / US Dollar', nickname: 'Kiwi', category: 'major', baseSpread: 0.4, basePriceApprox: 0.61 },
  'BTC/USD': { symbol: 'BTC/USD', name: 'Bitcoin / US Dollar', nickname: 'Bitcoin', category: 'crypto', baseSpread: 15, basePriceApprox: 42000 },
  'ETH/USD': { symbol: 'ETH/USD', name: 'Ethereum / US Dollar', nickname: 'Ethereum', category: 'crypto', baseSpread: 1.2, basePriceApprox: 2500 },
  'XAU/USD': { symbol: 'XAU/USD', name: 'Gold / US Dollar', nickname: 'Gold', category: 'commodity', baseSpread: 0.3, basePriceApprox: 2030 },
  'XAG/USD': { symbol: 'XAG/USD', name: 'Silver / US Dollar', nickname: 'Silver', category: 'commodity', baseSpread: 0.02, basePriceApprox: 23 },
  'SPX500': { symbol: 'SPX500', name: 'S&P 500 Index', nickname: 'S&P 500', category: 'index', baseSpread: 0.5, basePriceApprox: 4800 },
};

function getSentimentColor(label: string): string {
  if (label === 'bullish') {
    return 'bg-emerald-500';
  }
  if (label === 'bearish') {
    return 'bg-red-500';
  }
  // Neutral
  return 'bg-gray-500';
}

function getSentimentBgColor(label: string): string {
  if (label === 'bullish') {
    return 'bg-emerald-500/10 border-emerald-500/30 hover:bg-emerald-500/20';
  }
  if (label === 'bearish') {
    return 'bg-red-500/10 border-red-500/30 hover:bg-red-500/20';
  }
  return 'bg-gray-500/10 border-gray-500/30 hover:bg-gray-500/20';
}

function SentimentBadge({ label }: { label: string }) {
  const getIcon = () => {
    switch (label) {
      case 'bullish': return <TrendingUp size={10} className="text-emerald-400" />;
      case 'bearish': return <TrendingDown size={10} className="text-red-400" />;
      default: return <Minus size={10} className="text-gray-400" />;
    }
  };

  const getTextColor = () => {
    switch (label) {
      case 'bullish': return 'text-emerald-400';
      case 'bearish': return 'text-red-400';
      default: return 'text-gray-400';
    }
  };

  return (
    <div className="flex items-center gap-1">
      {getIcon()}
      <span className={`text-[10px] font-medium ${getTextColor()}`}>
        {label.charAt(0).toUpperCase() + label.slice(1)}
      </span>
    </div>
  );
}

// Loading Skeleton
function HeatmapSkeleton() {
  return (
    <div className="animate-pulse grid grid-cols-3 gap-2">
      {Array.from({ length: 9 }).map((_, i) => (
        <div key={i} className="h-14 bg-trading-border rounded" />
      ))}
    </div>
  );
}

export function SentimentHeatmap({ onSelectPair }: SentimentHeatmapProps) {
  const [sentiments, setSentiments] = useState<SentimentOverviewItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchSentiments = useCallback(async () => {
    try {
      const response = await fetch(`${API_URL}/api/sentiment/overview`);
      if (!response.ok) {
        throw new Error('Failed to fetch sentiment overview');
      }
      const data = await response.json();
      setSentiments(data.symbols || []);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load sentiments');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchSentiments();
    
    // Refresh every 60 seconds
    const interval = setInterval(fetchSentiments, 60000);
    return () => clearInterval(interval);
  }, [fetchSentiments]);

  const handleClick = (symbol: string) => {
    const pairData = SYMBOL_TO_PAIR[symbol];
    if (pairData) {
      onSelectPair(pairData as ForexPair);
    }
  };

  if (loading) {
    return (
      <div className="bg-trading-card border border-trading-border rounded-lg p-4">
        <h3 className="text-sm font-semibold mb-3">Sentiment Heatmap</h3>
        <HeatmapSkeleton />
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-trading-card border border-trading-border rounded-lg p-4">
        <h3 className="text-sm font-semibold mb-3">Sentiment Heatmap</h3>
        <div className="text-center py-4 text-trading-muted text-sm">
          {error}
        </div>
      </div>
    );
  }

  // Sort by absolute sentiment strength
  const sortedSentiments = [...sentiments].sort((a, b) => Math.abs(b.score) - Math.abs(a.score));

  return (
    <div className="bg-trading-card border border-trading-border rounded-lg p-4">
      <h3 className="text-sm font-semibold mb-3">Sentiment Heatmap</h3>
      
      <div className="grid grid-cols-3 gap-2">
        {sortedSentiments.map((item) => (
          <button
            key={item.symbol}
            onClick={() => handleClick(item.symbol)}
            className={`
              p-2 rounded border text-left transition-colors
              ${getSentimentBgColor(item.label)}
            `}
          >
            <div className="flex items-center justify-between mb-1">
              <span className="text-xs font-semibold text-trading-text">
                {item.symbol}
              </span>
              <div className={`w-2 h-2 rounded-full ${getSentimentColor(item.label)}`} />
            </div>
            <SentimentBadge label={item.label} />
            <div className="text-[10px] text-trading-muted mt-0.5">
              {item.score > 0 ? '+' : ''}{item.score.toFixed(2)}
            </div>
          </button>
        ))}
      </div>

      {/* Legend */}
      <div className="mt-3 pt-2 border-t border-trading-border">
        <div className="flex items-center justify-center gap-3 text-[10px] text-trading-muted">
          <div className="flex items-center gap-1">
            <div className="w-2 h-2 rounded-full bg-emerald-500" />
            <span>Bullish</span>
          </div>
          <div className="flex items-center gap-1">
            <div className="w-2 h-2 rounded-full bg-gray-500" />
            <span>Neutral</span>
          </div>
          <div className="flex items-center gap-1">
            <div className="w-2 h-2 rounded-full bg-red-500" />
            <span>Bearish</span>
          </div>
        </div>
      </div>
    </div>
  );
}
