import { useState, useCallback, useEffect } from 'react';
import { Search, Save, ArrowRight } from 'lucide-react';
import ScannerBuilder from '../components/ScannerBuilder';
import ScannerPresets from '../components/ScannerPresets';
import { ALL_FOREX_PAIRS } from '../config/forexPairs';
import type { IndicatorCondition, ScanResult, ForexPair } from '../types';

interface ScannerProps {
  onPairChange?: (pair: ForexPair) => void;
  recentPairs?: ForexPair[];
}

export default function Scanner({ onPairChange, recentPairs: _recentPairs }: ScannerProps) {
  const [conditions, setConditions] = useState<IndicatorCondition[]>([
    { indicator: 'RSI', operator: '<', value: 30 },
  ]);
  const [logic, setLogic] = useState<'AND' | 'OR'>('AND');
  const [selectedPairs, setSelectedPairs] = useState<string[]>([]);
  const [isScanning, setIsScanning] = useState(false);
  const [results, setResults] = useState<ScanResult[]>([]);
  const [totalScanned, setTotalScanned] = useState(0);
  const [sortBy, setSortBy] = useState<'score' | 'symbol' | 'volume'>('score');
  const [scannerName, setScannerName] = useState('');
  const [showSaveDialog, setShowSaveDialog] = useState(false);
  const [autoRunScan, setAutoRunScan] = useState(false);

  const allPairs = ALL_FOREX_PAIRS.map((p) => ({
    symbol: p.symbol,
    name: p.name,
  }));

  const runScan = useCallback(async () => {
    setIsScanning(true);
    try {
      const response = await fetch('/api/scanner/scan', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: scannerName || 'Custom Scanner',
          conditions,
          logic,
          pairs: selectedPairs.length > 0 ? selectedPairs : undefined,
        }),
      });
      const data = await response.json();
      setResults(data.results || []);
      setTotalScanned(data.total_scanned || 0);
    } catch (err) {
      console.error('Scan failed:', err);
    } finally {
      setIsScanning(false);
    }
  }, [conditions, logic, selectedPairs, scannerName]);

  const handlePresetSelect = useCallback(
    (preset: { name: string; conditions: IndicatorCondition[]; logic: 'AND' | 'OR' }) => {
      setScannerName(preset.name);
      setConditions(preset.conditions);
      setLogic(preset.logic);
      setAutoRunScan(true);
    },
    []
  );

  // Auto-run scan when triggered by preset selection
  useEffect(() => {
    if (autoRunScan && conditions.length > 0) {
      runScan();
      setAutoRunScan(false);
    }
  }, [autoRunScan, conditions]);

  const saveScanner = async () => {
    if (!scannerName.trim()) {
      setShowSaveDialog(true);
      return;
    }
    try {
      await fetch('/api/scanner/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: scannerName,
          conditions,
          logic,
          pairs: selectedPairs.length > 0 ? selectedPairs : undefined,
        }),
      });
      setShowSaveDialog(false);
    } catch (err) {
      console.error('Save failed:', err);
    }
  };

  const handleTradeClick = (symbol: string) => {
    const pair = ALL_FOREX_PAIRS.find((p) => p.symbol === symbol);
    if (pair && onPairChange) {
      onPairChange(pair);
    }
  };

  const sortedResults = [...results].sort((a, b) => {
    switch (sortBy) {
      case 'score':
        return b.score - a.score;
      case 'symbol':
        return a.symbol.localeCompare(b.symbol);
      case 'volume':
        return (b.indicator_values?.Volume || 0) - (a.indicator_values?.Volume || 0);
      default:
        return 0;
    }
  });

  const getScoreColor = (score: number) => {
    if (score >= 0.8) return 'bg-trading-buy';
    if (score >= 0.6) return 'bg-yellow-500';
    return 'bg-trading-sell';
  };

  const getPairBySymbol = (symbol: string) => {
    return ALL_FOREX_PAIRS.find((p) => p.symbol === symbol);
  };

  return (
    <div className="h-full overflow-auto p-6">
      {/* Header */}
      <div className="mb-6">
        <div className="flex items-center gap-3 mb-2">
          <Search className="text-trading-accent" size={28} />
          <h1 className="text-2xl font-bold text-trading-text">Custom Scanner</h1>
        </div>
        <p className="text-trading-muted">
          Build custom scanning criteria to find trading opportunities across all markets
        </p>
      </div>

      {/* Main Content Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
        {/* Left Panel - Scanner Builder */}
        <div className="bg-trading-card border border-trading-border rounded-xl p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-trading-text">Scanner Builder</h2>
            <button
              onClick={() => setShowSaveDialog(true)}
              className="flex items-center gap-2 px-3 py-1.5 text-sm text-trading-accent hover:bg-trading-accent/10 rounded-lg transition-colors"
            >
              <Save size={16} />
              <span>Save</span>
            </button>
          </div>

          <input
            type="text"
            value={scannerName}
            onChange={(e) => setScannerName(e.target.value)}
            placeholder="Scanner name (optional)"
            className="w-full mb-4 bg-trading-bg border border-trading-border rounded-lg px-4 py-2 text-trading-text placeholder:text-trading-muted focus:outline-none focus:border-trading-accent"
          />

          <ScannerBuilder
            conditions={conditions}
            onConditionsChange={setConditions}
            logic={logic}
            onLogicChange={setLogic}
            selectedPairs={selectedPairs}
            onPairsChange={setSelectedPairs}
            onRunScan={runScan}
            isScanning={isScanning}
            allPairs={allPairs}
          />
        </div>

        {/* Right Panel - Results */}
        <div className="bg-trading-card border border-trading-border rounded-xl p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-trading-text">Scan Results</h2>
            {results.length > 0 && (
              <div className="flex items-center gap-2">
                <span className="text-sm text-trading-muted">Sort by:</span>
                <select
                  value={sortBy}
                  onChange={(e) => setSortBy(e.target.value as typeof sortBy)}
                  className="bg-trading-bg border border-trading-border rounded px-2 py-1 text-sm text-trading-text"
                >
                  <option value="score">Score</option>
                  <option value="symbol">Symbol</option>
                  <option value="volume">Volume</option>
                </select>
              </div>
            )}
          </div>

          {results.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-64 text-trading-muted">
              <Search size={48} className="mb-4 opacity-30" />
              <p className="text-lg font-medium">Run a scan to find trading opportunities</p>
              <p className="text-sm mt-1">Configure conditions and click Run Scan</p>
            </div>
          ) : (
            <div className="space-y-4">
              <div className="text-sm text-trading-muted">
                <span className="font-medium text-trading-text">{results.length}</span> pairs
                matched out of <span className="font-medium text-trading-text">{totalScanned}</span>{' '}
                scanned
              </div>

              <div className="space-y-3 max-h-[500px] overflow-y-auto">
                {sortedResults.map((result) => {
                  const pair = getPairBySymbol(result.symbol);
                  return (
                    <div
                      key={result.symbol}
                      className="bg-trading-bg border border-trading-border rounded-lg p-4 hover:border-trading-accent/50 transition-colors"
                    >
                      <div className="flex items-start justify-between mb-3">
                        <div>
                          <div className="flex items-center gap-2">
                            <span className="font-semibold text-trading-text">
                              {result.symbol}
                            </span>
                            {pair && (
                              <span className="text-xs text-trading-muted">{pair.name}</span>
                            )}
                          </div>
                        </div>
                        <button
                          onClick={() => handleTradeClick(result.symbol)}
                          className="flex items-center gap-1 px-3 py-1.5 bg-trading-accent text-white text-sm font-medium rounded-lg hover:bg-blue-600 transition-colors"
                        >
                          <span>Trade</span>
                          <ArrowRight size={14} />
                        </button>
                      </div>

                      {/* Score Bar */}
                      <div className="mb-3">
                        <div className="flex items-center justify-between text-sm mb-1">
                          <span className="text-trading-muted">Match Score</span>
                          <span className="font-medium text-trading-text">
                            {Math.round(result.score * 100)}%
                          </span>
                        </div>
                        <div className="h-2 bg-trading-card rounded-full overflow-hidden">
                          <div
                            className={`h-full ${getScoreColor(result.score)} transition-all`}
                            style={{ width: `${result.score * 100}%` }}
                          />
                        </div>
                      </div>

                      {/* Matching Conditions */}
                      <div className="mb-3">
                        <p className="text-xs text-trading-muted mb-1">Matching Conditions</p>
                        <div className="flex flex-wrap gap-1">
                          {result.matching_conditions.map((cond, idx) => (
                            <span
                              key={idx}
                              className="text-xs px-2 py-0.5 bg-trading-card text-trading-text rounded"
                            >
                              {cond}
                            </span>
                          ))}
                        </div>
                      </div>

                      {/* Indicator Values */}
                      {result.indicator_values && (
                        <div className="flex flex-wrap gap-3 pt-3 border-t border-trading-border">
                          {Object.entries(result.indicator_values).map(([key, value]) => (
                            <div key={key} className="flex items-center gap-1">
                              <span className="text-xs text-trading-muted">{key}:</span>
                              <span className="text-xs font-medium text-trading-text">
                                {value}
                              </span>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Bottom Section - Presets */}
      <div className="bg-trading-card border border-trading-border rounded-xl p-6">
        <h2 className="text-lg font-semibold text-trading-text mb-4">Quick Scan Presets</h2>
        <ScannerPresets onSelectPreset={handlePresetSelect} />
      </div>

      {/* Save Dialog */}
      {showSaveDialog && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-trading-card border border-trading-border rounded-xl p-6 w-full max-w-md mx-4">
            <h3 className="text-lg font-semibold text-trading-text mb-4">Save Scanner</h3>
            <input
              type="text"
              value={scannerName}
              onChange={(e) => setScannerName(e.target.value)}
              placeholder="Enter scanner name"
              className="w-full mb-4 bg-trading-bg border border-trading-border rounded-lg px-4 py-2 text-trading-text placeholder:text-trading-muted focus:outline-none focus:border-trading-accent"
              autoFocus
            />
            <div className="flex gap-3">
              <button
                onClick={() => setShowSaveDialog(false)}
                className="flex-1 px-4 py-2 bg-trading-bg text-trading-text rounded-lg hover:bg-trading-border transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={saveScanner}
                disabled={!scannerName.trim()}
                className="flex-1 px-4 py-2 bg-trading-accent text-white rounded-lg hover:bg-blue-600 disabled:opacity-50 transition-colors"
              >
                Save
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
