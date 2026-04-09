import { Clock } from 'lucide-react';

interface ChartToolbarProps {
  timeframe: string;
  onTimeframeChange: (tf: string) => void;
}

const TIMEFRAMES = [
  { label: '1m', value: '1m' },
  { label: '5m', value: '5m' },
  { label: '15m', value: '15m' },
  { label: '1H', value: '1h' },
  { label: '4H', value: '4h' },
  { label: '1D', value: '1d' },
];

export function ChartToolbar({
  timeframe,
  onTimeframeChange,
}: ChartToolbarProps) {
  return (
    <div className="flex flex-wrap items-center gap-4 p-3 bg-[#1e293b] rounded-lg border border-[#334155]">
      {/* Timeframe Selector */}
      <div className="flex items-center gap-1">
        <Clock className="w-4 h-4 text-[#94a3b8] mr-1" />
        <span className="text-xs text-[#94a3b8] mr-2 font-medium">Timeframe</span>
        {TIMEFRAMES.map((tf) => (
          <button
            key={tf.value}
            onClick={() => onTimeframeChange(tf.value)}
            className={`
              px-2.5 py-1.5 rounded-md text-sm font-medium
              transition-all duration-200 ease-in-out
              ${timeframe === tf.value
                ? 'bg-[#3b82f6] text-white shadow-md'
                : 'bg-[#0f172a] text-[#94a3b8] hover:bg-[#334155] hover:text-white'
              }
            `}
          >
            {tf.label}
          </button>
        ))}
      </div>

      {/* Info Note */}
      <div className="hidden md:flex items-center gap-2 ml-auto">
        <span className="text-xs text-[#64748b]">
          Chart type, indicators & drawings available in the widget toolbar
        </span>
      </div>
    </div>
  );
}
