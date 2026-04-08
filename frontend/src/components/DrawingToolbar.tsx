import { MousePointer2, TrendingUp, Minus, Hash, GitBranch, Square, Undo2, Trash2 } from 'lucide-react';
import { DrawingTool, DRAWING_COLORS } from '../utils/drawings';

interface DrawingToolbarProps {
  activeTool: DrawingTool;
  onToolChange: (tool: DrawingTool) => void;
  activeColor: string;
  onColorChange: (color: string) => void;
  onClearAll: () => void;
  onUndo: () => void;
  drawingCount: number;
}

const tools: { id: DrawingTool; icon: React.ElementType; label: string }[] = [
  { id: 'crosshair', icon: MousePointer2, label: 'Crosshair (Default)' },
  { id: 'trendline', icon: TrendingUp, label: 'Trend Line' },
  { id: 'horizontal', icon: Minus, label: 'Horizontal Line' },
  { id: 'fibonacci', icon: Hash, label: 'Fibonacci Retracement' },
  { id: 'channel', icon: GitBranch, label: 'Channel' },
  { id: 'rectangle', icon: Square, label: 'Rectangle' },
];

export function DrawingToolbar({
  activeTool,
  onToolChange,
  activeColor,
  onColorChange,
  onClearAll,
  onUndo,
  drawingCount,
}: DrawingToolbarProps) {
  const handleClearAll = () => {
    if (drawingCount > 0 && confirm(`Clear all ${drawingCount} drawings?`)) {
      onClearAll();
    }
  };

  return (
    <div className="flex flex-col items-center gap-1 p-1.5 bg-[#1e293b] rounded-lg border border-[#334155] shadow-lg opacity-80 hover:opacity-100 transition-opacity">
      {/* Drawing Tools */}
      {tools.map((tool) => {
        const Icon = tool.icon;
        const isActive = activeTool === tool.id;
        return (
          <button
            key={tool.id}
            onClick={() => onToolChange(tool.id)}
            className={`
              relative p-2 rounded-md transition-all duration-200 group
              ${isActive 
                ? 'bg-[#3b82f6] text-white' 
                : 'text-[#94a3b8] hover:text-white hover:bg-[#334155]'
              }
            `}
            title={tool.label}
          >
            <Icon size={18} strokeWidth={isActive ? 2.5 : 2} />
            {/* Tooltip */}
            <span className="absolute left-full ml-2 px-2 py-1 bg-[#0f172a] text-white text-xs rounded opacity-0 group-hover:opacity-100 pointer-events-none whitespace-nowrap z-50 border border-[#334155]">
              {tool.label}
            </span>
          </button>
        );
      })}

      {/* Separator */}
      <div className="w-6 h-px bg-[#334155] my-1" />

      {/* Color Picker */}
      <div className="relative group">
        <button
          className="w-7 h-7 rounded-full border-2 border-[#334155] transition-transform hover:scale-110"
          style={{ backgroundColor: activeColor }}
          title="Select Color"
        />
        {/* Color palette popup */}
        <div className="absolute left-full ml-2 top-0 flex flex-col gap-1 p-1.5 bg-[#1e293b] rounded-lg border border-[#334155] opacity-0 group-hover:opacity-100 pointer-events-none group-hover:pointer-events-auto transition-opacity z-50">
          {DRAWING_COLORS.map((color) => (
            <button
              key={color}
              onClick={() => onColorChange(color)}
              className={`w-5 h-5 rounded-full transition-transform hover:scale-110 ${
                activeColor === color ? 'ring-2 ring-white' : ''
              }`}
              style={{ backgroundColor: color }}
            />
          ))}
        </div>
      </div>

      {/* Separator */}
      <div className="w-6 h-px bg-[#334155] my-1" />

      {/* Undo */}
      <button
        onClick={onUndo}
        disabled={drawingCount === 0}
        className={`
          relative p-2 rounded-md transition-all duration-200 group
          ${drawingCount === 0
            ? 'text-[#475569] cursor-not-allowed'
            : 'text-[#94a3b8] hover:text-white hover:bg-[#334155]'
          }
        `}
        title="Undo Last Drawing"
      >
        <Undo2 size={18} />
        <span className="absolute left-full ml-2 px-2 py-1 bg-[#0f172a] text-white text-xs rounded opacity-0 group-hover:opacity-100 pointer-events-none whitespace-nowrap z-50 border border-[#334155]">
          Undo
        </span>
      </button>

      {/* Clear All */}
      <button
        onClick={handleClearAll}
        disabled={drawingCount === 0}
        className={`
          relative p-2 rounded-md transition-all duration-200 group
          ${drawingCount === 0
            ? 'text-[#475569] cursor-not-allowed'
            : 'text-[#94a3b8] hover:text-[#ef4444] hover:bg-[#334155]'
          }
        `}
        title="Clear All Drawings"
      >
        <Trash2 size={18} />
        <span className="absolute left-full ml-2 px-2 py-1 bg-[#0f172a] text-white text-xs rounded opacity-0 group-hover:opacity-100 pointer-events-none whitespace-nowrap z-50 border border-[#334155]">
          Clear All
        </span>
      </button>

      {/* Drawing count indicator */}
      {drawingCount > 0 && (
        <div className="mt-1 text-[10px] text-[#64748b] font-medium">
          {drawingCount}
        </div>
      )}
    </div>
  );
}
