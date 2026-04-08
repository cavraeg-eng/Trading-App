import { useEffect, useState } from 'react';
import {
  TrendingUp,
  Zap,
  Activity,
  BarChart3,
  RefreshCw,
  Play,
} from 'lucide-react';
import type { ScannerPreset, IndicatorCondition } from '../types';

interface ScannerPresetsProps {
  onSelectPreset: (preset: {
    name: string;
    conditions: IndicatorCondition[];
    logic: 'AND' | 'OR';
  }) => void;
}

const iconMap: Record<string, React.ElementType> = {
  'trending-up': TrendingUp,
  zap: Zap,
  activity: Activity,
  'bar-chart': BarChart3,
  'refresh-cw': RefreshCw,
};

export default function ScannerPresets({ onSelectPreset }: ScannerPresetsProps) {
  const [presets, setPresets] = useState<ScannerPreset[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch('/api/scanner/presets')
      .then((res) => res.json())
      .then((data) => {
        setPresets(data.presets || []);
        setLoading(false);
      })
      .catch((err) => {
        console.error('Failed to load presets:', err);
        setLoading(false);
      });
  }, []);

  if (loading) {
    return (
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-4">
        {[...Array(5)].map((_, i) => (
          <div
            key={i}
            className="bg-trading-card border border-trading-border rounded-lg p-4 animate-pulse"
          >
            <div className="w-10 h-10 bg-trading-border rounded-lg mb-3" />
            <div className="h-5 bg-trading-border rounded w-2/3 mb-2" />
            <div className="h-4 bg-trading-border rounded w-full mb-4" />
            <div className="h-8 bg-trading-border rounded" />
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-4">
      {presets.map((preset) => {
        const Icon = iconMap[preset.icon] || Activity;
        return (
          <div
            key={preset.id}
            className="bg-trading-card border border-trading-border rounded-lg p-4 hover:border-trading-accent/50 transition-colors group"
          >
            <div className="flex items-start justify-between mb-3">
              <div className="w-10 h-10 bg-trading-bg rounded-lg flex items-center justify-center">
                <Icon size={20} className="text-trading-accent" />
              </div>
              <span className="text-xs text-trading-muted bg-trading-bg px-2 py-1 rounded">
                {preset.conditions.length} condition
                {preset.conditions.length !== 1 ? 's' : ''}
              </span>
            </div>

            <h4 className="font-medium text-trading-text mb-1">{preset.name}</h4>
            <p className="text-xs text-trading-muted mb-4 line-clamp-2">
              {preset.description}
            </p>

            <button
              onClick={() =>
                onSelectPreset({
                  name: preset.name,
                  conditions: preset.conditions,
                  logic: 'AND',
                })
              }
              className="w-full flex items-center justify-center gap-2 px-3 py-2 bg-trading-bg hover:bg-trading-accent text-trading-text hover:text-white rounded-lg text-sm font-medium transition-colors"
            >
              <Play size={14} />
              <span>Run</span>
            </button>
          </div>
        );
      })}
    </div>
  );
}
