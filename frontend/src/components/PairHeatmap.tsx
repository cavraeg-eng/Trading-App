import { useState, useEffect } from 'react';
import type { ForexPair } from '../types';

export interface PairHeatmapProps {
  pairs: ForexPair[];
  selectedPair: ForexPair;
  onSelectPair: (pair: ForexPair) => void;
  performance?: Map<string, number>; // symbol -> daily change %
}

export function PairHeatmap({ pairs, selectedPair, onSelectPair, performance }: PairHeatmapProps) {
  // Generate mock performance data if not provided
  const [mockPerformance, setMockPerformance] = useState<Map<string, number>>(new Map());

  useEffect(() => {
    if (!performance) {
      const mockData = new Map<string, number>();
      pairs.forEach((pair) => {
        // Generate random daily change between -2% and +2%
        const change = parseFloat((Math.random() * 4 - 2).toFixed(2));
        mockData.set(pair.symbol, change);
      });
      setMockPerformance(mockData);
    }
  }, [pairs, performance]);

  const performanceData = performance || mockPerformance;

  const getCellColor = (change: number | undefined): string => {
    if (change === undefined) return 'bg-trading-card';
    
    // Normalize change to 0-1 range for intensity (assuming -2% to +2% range)
    const normalized = Math.max(-2, Math.min(2, change)) / 2; // -1 to 1
    
    if (normalized > 0) {
      // Green gradient for positive changes
      const intensity = Math.abs(normalized);
      if (intensity > 0.75) return 'bg-emerald-600';
      if (intensity > 0.5) return 'bg-emerald-500';
      if (intensity > 0.25) return 'bg-emerald-400/80';
      return 'bg-emerald-400/50';
    } else if (normalized < 0) {
      // Red gradient for negative changes
      const intensity = Math.abs(normalized);
      if (intensity > 0.75) return 'bg-rose-600';
      if (intensity > 0.5) return 'bg-rose-500';
      if (intensity > 0.25) return 'bg-rose-400/80';
      return 'bg-rose-400/50';
    }
    
    return 'bg-trading-card';
  };

  const getTextColor = (change: number | undefined): string => {
    if (change === undefined) return 'text-trading-text';
    
    const normalized = Math.max(-2, Math.min(2, change)) / 2;
    const intensity = Math.abs(normalized);
    
    // Use white text for darker backgrounds, dark text for lighter backgrounds
    if (intensity > 0.5) return 'text-white';
    return 'text-trading-text';
  };

  const formatChange = (change: number | undefined): string => {
    if (change === undefined) return '0.00%';
    const sign = change >= 0 ? '+' : '';
    return `${sign}${change.toFixed(2)}%`;
  };

  return (
    <div className="bg-trading-card border border-trading-border rounded-lg p-4">
      {/* Header */}
      <div className="mb-3">
        <h3 className="text-sm font-semibold text-trading-text">Pair Heatmap</h3>
      </div>

      {/* Heatmap Grid */}
      <div className="grid grid-cols-3 gap-1">
        {pairs.map((pair) => {
          const change = performanceData.get(pair.symbol);
          const isSelected = selectedPair.symbol === pair.symbol;

          return (
            <button
              key={pair.symbol}
              onClick={() => onSelectPair(pair)}
              className={`
                relative p-2 rounded-md transition-all duration-200
                ${getCellColor(change)}
                ${isSelected ? 'ring-2 ring-trading-accent ring-offset-1 ring-offset-trading-card' : ''}
                hover:opacity-90 hover:scale-[1.02]
              `}
              title={`${pair.symbol} - ${pair.nickname}`}
            >
              {/* Pair Symbol */}
              <div className={`text-xs font-semibold ${getTextColor(change)}`}>
                {pair.symbol}
              </div>
              
              {/* Change Percentage */}
              <div className={`text-[10px] ${getTextColor(change)} opacity-90`}>
                {formatChange(change)}
              </div>

              {/* Selected Indicator */}
              {isSelected && (
                <div className="absolute top-0.5 right-0.5 w-1.5 h-1.5 bg-trading-accent rounded-full" />
              )}
            </button>
          );
        })}
      </div>

      {/* Legend */}
      <div className="mt-3 flex items-center justify-between text-[10px] text-trading-muted">
        <span>-2%</span>
        <div className="flex-1 mx-2 h-1 rounded-full bg-gradient-to-r from-rose-500 via-trading-card to-emerald-500" />
        <span>+2%</span>
      </div>
    </div>
  );
}
