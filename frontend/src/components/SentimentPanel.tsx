import { useState, useEffect, useCallback } from 'react';
import { Newspaper, TrendingUp, TrendingDown, Minus } from 'lucide-react';
import type { SentimentData, SentimentHeadline } from '../types';

interface SentimentPanelProps {
  symbol: string;
}

// Use relative URLs so the Vite proxy handles routing to the backend
const API_URL = '';

// Format time ago
function formatTimeAgo(timestamp: string): string {
  const date = new Date(timestamp);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMins / 60);
  
  if (diffMins < 1) return 'just now';
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  return `${Math.floor(diffHours / 24)}d ago`;
}

// Sentiment Gauge Component
function SentimentGauge({ score, label }: { score: number; label: string }) {
  // Map score (-1 to 1) to angle (0 to 180 degrees)
  const angle = ((score + 1) / 2) * 180;
  
  const getLabelColor = () => {
    switch (label) {
      case 'bullish': return 'text-emerald-400';
      case 'bearish': return 'text-red-400';
      default: return 'text-gray-400';
    }
  };

  const getLabelIcon = () => {
    switch (label) {
      case 'bullish': return <TrendingUp size={20} className="inline mr-1" />;
      case 'bearish': return <TrendingDown size={20} className="inline mr-1" />;
      default: return <Minus size={20} className="inline mr-1" />;
    }
  };

  return (
    <div className="flex flex-col items-center">
      {/* SVG Gauge */}
      <div className="relative w-40 h-20">
        <svg viewBox="0 0 100 50" className="w-full h-full">
          {/* Background arc */}
          <path
            d="M 10 50 A 40 40 0 0 1 90 50"
            fill="none"
            stroke="#1f2937"
            strokeWidth="8"
            strokeLinecap="round"
          />
          {/* Red zone (bearish) */}
          <path
            d="M 10 50 A 40 40 0 0 1 36.7 15.3"
            fill="none"
            stroke="#ef4444"
            strokeWidth="8"
            strokeLinecap="round"
          />
          {/* Gray zone (neutral) */}
          <path
            d="M 36.7 15.3 A 40 40 0 0 1 63.3 15.3"
            fill="none"
            stroke="#6b7280"
            strokeWidth="8"
            strokeLinecap="round"
          />
          {/* Green zone (bullish) */}
          <path
            d="M 63.3 15.3 A 40 40 0 0 1 90 50"
            fill="none"
            stroke="#10b981"
            strokeWidth="8"
            strokeLinecap="round"
          />
          {/* Needle */}
          <line
            x1="50"
            y1="50"
            x2={50 + 35 * Math.cos((angle - 180) * Math.PI / 180)}
            y2={50 + 35 * Math.sin((angle - 180) * Math.PI / 180)}
            stroke="#f3f4f6"
            strokeWidth="2"
            strokeLinecap="round"
          />
          {/* Center dot */}
          <circle cx="50" cy="50" r="4" fill="#f3f4f6" />
        </svg>
      </div>
      
      {/* Score and Label */}
      <div className="text-center -mt-2">
        <div className={`text-2xl font-bold ${getLabelColor()}`}>
          {getLabelIcon()}
          {label.charAt(0).toUpperCase() + label.slice(1)}
        </div>
        <div className="text-sm text-trading-muted">
          Score: {score > 0 ? '+' : ''}{score.toFixed(2)}
        </div>
      </div>
      
      {/* Scale labels */}
      <div className="flex justify-between w-40 text-[10px] text-trading-muted mt-1">
        <span>-1.0</span>
        <span>0</span>
        <span>+1.0</span>
      </div>
    </div>
  );
}

// Sparkline Component
function SentimentSparkline({ data }: { data: number[] }) {
  if (!data || data.length === 0) return null;
  
  const width = 100;
  const height = 30;
  const padding = 2;
  
  const min = Math.min(...data, -0.2);
  const max = Math.max(...data, 0.2);
  const range = max - min || 1;
  
  const points = data.map((val, i) => {
    const x = (i / (data.length - 1)) * (width - 2 * padding) + padding;
    const y = height - ((val - min) / range) * (height - 2 * padding) - padding;
    return `${x},${y}`;
  }).join(' ');
  
  // Create area path
  const areaPath = `${points} ${width - padding},${height} ${padding},${height}`;
  
  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="w-full h-8">
      {/* Area fill */}
      <polygon
        points={areaPath}
        fill="url(#sentimentGradient)"
        opacity="0.3"
      />
      {/* Line */}
      <polyline
        points={points}
        fill="none"
        stroke={data[data.length - 1] >= 0 ? '#10b981' : '#ef4444'}
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {/* Zero line */}
      <line
        x1={padding}
        y1={height - ((0 - min) / range) * (height - 2 * padding) - padding}
        x2={width - padding}
        y2={height - ((0 - min) / range) * (height - 2 * padding) - padding}
        stroke="#374151"
        strokeWidth="0.5"
        strokeDasharray="2,2"
      />
      <defs>
        <linearGradient id="sentimentGradient" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={data[data.length - 1] >= 0 ? '#10b981' : '#ef4444'} stopOpacity="0.5" />
          <stop offset="100%" stopColor={data[data.length - 1] >= 0 ? '#10b981' : '#ef4444'} stopOpacity="0" />
        </linearGradient>
      </defs>
    </svg>
  );
}

// Headline Item Component
function HeadlineItem({ headline }: { headline: SentimentHeadline }) {
  const getSentimentColor = (sentiment: number) => {
    if (sentiment > 0.2) return 'bg-emerald-500';
    if (sentiment < -0.2) return 'bg-red-500';
    return 'bg-gray-500';
  };

  return (
    <div className="flex items-start gap-2 py-2 border-b border-trading-border last:border-0">
      <div className={`w-2 h-2 rounded-full mt-1.5 flex-shrink-0 ${getSentimentColor(headline.sentiment)}`} />
      <div className="flex-1 min-w-0">
        <p className="text-xs text-trading-text leading-snug line-clamp-2" title={headline.title}>
          {headline.title}
        </p>
        <div className="flex items-center gap-2 mt-1">
          <span className="text-[10px] text-trading-muted">{headline.source}</span>
          <span className="text-[10px] text-trading-muted">•</span>
          <span className="text-[10px] text-trading-muted">{formatTimeAgo(headline.timestamp)}</span>
        </div>
      </div>
    </div>
  );
}

// Loading Skeleton
function SentimentSkeleton() {
  return (
    <div className="animate-pulse">
      <div className="flex flex-col items-center py-4">
        <div className="w-40 h-20 bg-trading-border rounded-full mb-2" />
        <div className="w-24 h-6 bg-trading-border rounded mb-1" />
        <div className="w-16 h-4 bg-trading-border rounded" />
      </div>
      <div className="space-y-2 mt-4">
        <div className="h-12 bg-trading-border rounded" />
        <div className="h-12 bg-trading-border rounded" />
        <div className="h-12 bg-trading-border rounded" />
      </div>
    </div>
  );
}

export function SentimentPanel({ symbol }: SentimentPanelProps) {
  const [sentiment, setSentiment] = useState<SentimentData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchSentiment = useCallback(async () => {
    try {
      const response = await fetch(`${API_URL}/api/sentiment/symbol/${encodeURIComponent(symbol)}`);
      if (!response.ok) {
        throw new Error('Failed to fetch sentiment');
      }
      const data = await response.json();
      
      // Transform snake_case to camelCase
      setSentiment({
        symbol: data.symbol,
        score: data.score,
        label: data.label,
        headlines: data.headlines,
        trend: data.trend,
        lastUpdated: data.last_updated,
        sourceCount: data.source_count,
      });
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load sentiment');
    } finally {
      setLoading(false);
    }
  }, [symbol]);

  useEffect(() => {
    setLoading(true);
    fetchSentiment();
    
    // Refresh every 60 seconds
    const interval = setInterval(fetchSentiment, 60000);
    return () => clearInterval(interval);
  }, [fetchSentiment]);

  if (loading) {
    return (
      <div className="bg-trading-card border border-trading-border rounded-lg p-4">
        <h3 className="text-sm font-semibold mb-3 flex items-center gap-2">
          <Newspaper size={16} />
          Market Sentiment
        </h3>
        <SentimentSkeleton />
      </div>
    );
  }

  if (error || !sentiment) {
    return (
      <div className="bg-trading-card border border-trading-border rounded-lg p-4">
        <h3 className="text-sm font-semibold mb-3 flex items-center gap-2">
          <Newspaper size={16} />
          Market Sentiment
        </h3>
        <div className="text-center py-4 text-trading-muted text-sm">
          {error || 'No sentiment data available'}
        </div>
      </div>
    );
  }

  // Get top 5 headlines
  const topHeadlines = sentiment.headlines.slice(0, 5);

  return (
    <div className="bg-trading-card border border-trading-border rounded-lg p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold flex items-center gap-2">
          <Newspaper size={16} />
          Market Sentiment
        </h3>
        <span className="text-[10px] text-trading-muted">
          {sentiment.sourceCount} sources
        </span>
      </div>

      {/* Sentiment Gauge */}
      <SentimentGauge score={sentiment.score} label={sentiment.label} />

      {/* Sparkline */}
      <div className="mt-4">
        <div className="flex items-center justify-between mb-1">
          <span className="text-[10px] text-trading-muted">24h Trend</span>
        </div>
        <SentimentSparkline data={sentiment.trend} />
      </div>

      {/* Headlines */}
      <div className="mt-4 pt-3 border-t border-trading-border">
        <h4 className="text-xs font-medium text-trading-muted mb-2">Latest Headlines</h4>
        <div className="max-h-48 overflow-y-auto">
          {topHeadlines.map((headline, index) => (
            <HeadlineItem key={index} headline={headline} />
          ))}
        </div>
      </div>

      {/* Last Updated */}
      <div className="mt-3 pt-2 border-t border-trading-border text-right">
        <span className="text-[10px] text-trading-muted">
          Updated {formatTimeAgo(sentiment.lastUpdated)}
        </span>
      </div>
    </div>
  );
}
