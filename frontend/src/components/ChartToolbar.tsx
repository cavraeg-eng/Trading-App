import { Clock } from 'lucide-react';

interface ChartToolbarProps {
  timeframe: string;
  onTimeframeChange: (tf: string) => void;
}

const TIMEFRAMES = ['1m', '5m', '15m', '1H', '4H', '1D'];

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
            key={tf}
            onClick={() => onTimeframeChange(tf)}
            className={`
              px-2.5 py-1.5 rounded-md text-sm font-medium
              transition-all duration-200 ease-in-out
              ${timeframe === tf
                ? 'bg-[#3b82f6] text-white shadow-md'
                : 'bg-[#0f172a] text-[#94a3b8] hover:bg-[#334155] hover:text-white'
              }
            `}
          >
            {tf}
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
