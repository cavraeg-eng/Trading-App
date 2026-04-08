import { X, Plus } from 'lucide-react';
import type { IndicatorCondition } from '../types';

interface ScannerBuilderProps {
  conditions: IndicatorCondition[];
  onConditionsChange: (conditions: IndicatorCondition[]) => void;
  logic: 'AND' | 'OR';
  onLogicChange: (logic: 'AND' | 'OR') => void;
  selectedPairs: string[];
  onPairsChange: (pairs: string[]) => void;
  onRunScan: () => void;
  isScanning: boolean;
  allPairs: { symbol: string; name: string }[];
}

const INDICATORS = [
  'RSI',
  'MACD',
  'Bollinger Bands',
  'EMA',
  'ATR',
  'Volume',
  'Stochastic',
  'OBV',
  'Williams %R',
];

const OPERATORS = [
  { value: '>', label: '>' },
  { value: '<', label: '<' },
  { value: '=', label: '=' },
  { value: '>=', label: '>=' },
  { value: '<=', label: '<=' },
  { value: 'crosses_above', label: 'crosses above' },
  { value: 'crosses_below', label: 'crosses below' },
  { value: 'between', label: 'between' },
];

export default function ScannerBuilder({
  conditions,
  onConditionsChange,
  logic,
  onLogicChange,
  selectedPairs,
  onPairsChange,
  onRunScan,
  isScanning,
  allPairs,
}: ScannerBuilderProps) {
  const addCondition = () => {
    onConditionsChange([
      ...conditions,
      { indicator: 'RSI', operator: '>', value: 50 },
    ]);
  };

  const removeCondition = (index: number) => {
    onConditionsChange(conditions.filter((_, i) => i !== index));
  };

  const updateCondition = (
    index: number,
    field: keyof IndicatorCondition,
    value: string | number
  ) => {
    const updated = [...conditions];
    if (field === 'value' || field === 'value2') {
      updated[index] = { ...updated[index], [field]: Number(value) };
    } else {
      updated[index] = { ...updated[index], [field]: value as string };
    }
    onConditionsChange(updated);
  };

  const isAllPairs = selectedPairs.length === 0;

  return (
    <div className="space-y-6">
      {/* Conditions */}
      <div className="space-y-3">
        {conditions.map((condition, index) => (
          <div key={index} className="space-y-2">
            {index > 0 && (
              <div className="flex justify-center">
                <button
                  onClick={() => onLogicChange(logic === 'AND' ? 'OR' : 'AND')}
                  className="px-3 py-1 text-xs font-medium rounded-full bg-trading-border text-trading-text hover:bg-trading-accent transition-colors"
                >
                  {logic}
                </button>
              </div>
            )}
            <div className="flex items-center gap-2 bg-trading-bg p-3 rounded-lg border border-trading-border">
              <select
                value={condition.indicator}
                onChange={(e) =>
                  updateCondition(index, 'indicator', e.target.value)
                }
                className="flex-1 bg-trading-card border border-trading-border rounded px-3 py-2 text-sm text-trading-text focus:outline-none focus:border-trading-accent"
              >
                {INDICATORS.map((ind) => (
                  <option key={ind} value={ind}>
                    {ind}
                  </option>
                ))}
              </select>

              <select
                value={condition.operator}
                onChange={(e) =>
                  updateCondition(index, 'operator', e.target.value)
                }
                className="w-32 bg-trading-card border border-trading-border rounded px-3 py-2 text-sm text-trading-text focus:outline-none focus:border-trading-accent"
              >
                {OPERATORS.map((op) => (
                  <option key={op.value} value={op.value}>
                    {op.label}
                  </option>
                ))}
              </select>

              <input
                type="number"
                value={condition.value}
                onChange={(e) =>
                  updateCondition(index, 'value', e.target.value)
                }
                className="w-20 bg-trading-card border border-trading-border rounded px-3 py-2 text-sm text-trading-text focus:outline-none focus:border-trading-accent"
                placeholder="Value"
              />

              {condition.operator === 'between' && (
                <>
                  <span className="text-trading-muted text-sm">and</span>
                  <input
                    type="number"
                    value={condition.value2 || ''}
                    onChange={(e) =>
                      updateCondition(index, 'value2', e.target.value)
                    }
                    className="w-20 bg-trading-card border border-trading-border rounded px-3 py-2 text-sm text-trading-text focus:outline-none focus:border-trading-accent"
                    placeholder="Value 2"
                  />
                </>
              )}

              <button
                onClick={() => removeCondition(index)}
                className="p-2 text-trading-muted hover:text-trading-sell transition-colors"
                disabled={conditions.length === 1}
              >
                <X size={18} />
              </button>
            </div>
          </div>
        ))}
      </div>

      {/* Add Condition Button */}
      <button
        onClick={addCondition}
        className="w-full flex items-center justify-center gap-2 px-4 py-2 border border-dashed border-trading-border rounded-lg text-trading-muted hover:border-trading-accent hover:text-trading-accent transition-colors"
      >
        <Plus size={18} />
        <span>Add Condition</span>
      </button>

      {/* Pair Scope Selector */}
      <div className="space-y-3 pt-4 border-t border-trading-border">
        <label className="text-sm font-medium text-trading-text">
          Scan Scope
        </label>
        <div className="flex gap-2">
          <button
            onClick={() => onPairsChange([])}
            className={`flex-1 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
              isAllPairs
                ? 'bg-trading-accent text-white'
                : 'bg-trading-card text-trading-muted hover:text-trading-text'
            }`}
          >
            All Pairs
          </button>
          <button
            onClick={() => onPairsChange([allPairs[0]?.symbol || 'EUR/USD'])}
            className={`flex-1 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
              !isAllPairs
                ? 'bg-trading-accent text-white'
                : 'bg-trading-card text-trading-muted hover:text-trading-text'
            }`}
          >
            Select Pairs
          </button>
        </div>

        {!isAllPairs && (
          <div className="max-h-40 overflow-y-auto bg-trading-bg border border-trading-border rounded-lg p-2">
            {allPairs.map((pair) => (
              <label
                key={pair.symbol}
                className="flex items-center gap-2 px-2 py-1.5 hover:bg-trading-card rounded cursor-pointer"
              >
                <input
                  type="checkbox"
                  checked={selectedPairs.includes(pair.symbol)}
                  onChange={(e) => {
                    if (e.target.checked) {
                      onPairsChange([...selectedPairs, pair.symbol]);
                    } else {
                      onPairsChange(
                        selectedPairs.filter((s) => s !== pair.symbol)
                      );
                    }
                  }}
                  className="rounded border-trading-border text-trading-accent focus:ring-trading-accent"
                />
                <span className="text-sm text-trading-text">{pair.symbol}</span>
                <span className="text-xs text-trading-muted">{pair.name}</span>
              </label>
            ))}
          </div>
        )}
      </div>

      {/* Run Scan Button */}
      <button
        onClick={onRunScan}
        disabled={isScanning || conditions.length === 0}
        className="w-full py-3 bg-trading-accent text-white font-medium rounded-lg hover:bg-blue-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center justify-center gap-2"
      >
        {isScanning ? (
          <>
            <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
            <span>Scanning...</span>
          </>
        ) : (
          <span>Run Scan</span>
        )}
      </button>
    </div>
  );
}
