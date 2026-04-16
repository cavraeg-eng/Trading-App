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
    <div className="flex items-center gap-0.5">
      {TIMEFRAMES.map((tf) => (
        <button
          key={tf.value}
          onClick={() => onTimeframeChange(tf.value)}
          className={`
            px-2 py-1 rounded text-[11px] font-medium
            transition-colors
            ${timeframe === tf.value
              ? 'bg-[#4fc3f7]/15 text-[#4fc3f7]'
              : 'text-[#5c6a7e] hover:text-[#8b99ae] hover:bg-[#161b26]'
            }
          `}
        >
          {tf.label}
        </button>
      ))}
    </div>
  );
}
