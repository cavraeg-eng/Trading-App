import { useState, useEffect, useRef } from 'react';
import { Search, ChevronDown, Sparkles, Star, Clock } from 'lucide-react';
import type { ForexPair } from '../types';
import { MAJOR_PAIRS, MINOR_PAIRS, EXOTIC_PAIRS, COMMODITY_PAIRS, CRYPTO_PAIRS, INDEX_PAIRS } from '../config/forexPairs';

export interface PairSelectorProps {
  selectedPair: ForexPair;
  onPairChange: (pair: ForexPair) => void;
  onAISuggest: () => void;
  recentPairs?: ForexPair[];
  defaultPairSymbol?: string;
  onSetDefaultPair?: (pair: ForexPair) => void;
}

type CategoryTab = 'all' | 'forex' | 'commodities' | 'crypto' | 'indices';

const CATEGORY_TABS: { id: CategoryTab; label: string }[] = [
  { id: 'all', label: 'All' },
  { id: 'forex', label: 'Forex' },
  { id: 'commodities', label: 'Commodities' },
  { id: 'crypto', label: 'Crypto' },
  { id: 'indices', label: 'Indices' },
];

const FOREX_COUNT = MAJOR_PAIRS.length + MINOR_PAIRS.length + EXOTIC_PAIRS.length;
const COMMODITY_COUNT = COMMODITY_PAIRS.length;
const CRYPTO_COUNT = CRYPTO_PAIRS.length;
const INDEX_COUNT = INDEX_PAIRS.length;

export function PairSelector({
  selectedPair,
  onPairChange,
  onAISuggest,
  recentPairs,
  defaultPairSymbol,
  onSetDefaultPair,
}: PairSelectorProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [activeTab, setActiveTab] = useState<CategoryTab>('all');
  const dropdownRef = useRef<HTMLDivElement>(null);

  // Close dropdown on outside click
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const filterPairs = (pairs: ForexPair[]) => {
    if (!searchQuery.trim()) return pairs;
    const query = searchQuery.toLowerCase();
    return pairs.filter(
      (pair) =>
        pair.symbol.toLowerCase().includes(query) ||
        pair.name.toLowerCase().includes(query) ||
        pair.nickname.toLowerCase().includes(query)
    );
  };

  const handleSelectPair = (pair: ForexPair) => {
    onPairChange(pair);
    setIsOpen(false);
    setSearchQuery('');
  };

  const getCategoryColor = (category: ForexPair['category']) => {
    switch (category) {
      case 'major':
        return 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30';
      case 'minor':
        return 'bg-amber-500/20 text-amber-400 border-amber-500/30';
      case 'exotic':
        return 'bg-rose-500/20 text-rose-400 border-rose-500/30';
      case 'commodity':
        return 'bg-orange-500/20 text-orange-400 border-orange-500/30';
      case 'crypto':
        return 'bg-purple-500/20 text-purple-400 border-purple-500/30';
      case 'index':
        return 'bg-teal-500/20 text-teal-400 border-teal-500/30';
      default:
        return 'bg-slate-500/20 text-slate-400 border-slate-500/30';
    }
  };

  const getCategoryLabel = (category: ForexPair['category']) => {
    return category.charAt(0).toUpperCase() + category.slice(1);
  };

  const getTabCount = (tab: CategoryTab): number | null => {
    switch (tab) {
      case 'forex': return FOREX_COUNT;
      case 'commodities': return COMMODITY_COUNT;
      case 'crypto': return CRYPTO_COUNT;
      case 'indices': return INDEX_COUNT;
      default: return null;
    }
  };

  const renderPairRow = (pair: ForexPair) => {
    const isDefault = pair.symbol === defaultPairSymbol;
    const isSelected = pair.symbol === selectedPair.symbol;
    return (
      <button
        key={pair.symbol}
        onClick={() => handleSelectPair(pair)}
        className={`w-full flex items-center gap-3 px-3 py-2.5 hover:bg-trading-bg transition-colors ${
          isSelected ? 'bg-trading-accent/10 border-l-2 border-trading-accent' : ''
        }`}
      >
        <div className="flex flex-col items-start flex-1 min-w-0">
          <span className="text-sm font-semibold text-trading-text">{pair.symbol}</span>
          <span className="text-xs text-trading-muted truncate">{pair.name}</span>
        </div>
        <span className={`text-xs px-2 py-0.5 rounded border shrink-0 ${getCategoryColor(pair.category)}`}>
          {getCategoryLabel(pair.category)}
        </span>
        <span className="text-xs text-trading-muted shrink-0">{pair.baseSpread}p</span>
        <button
          onClick={(e) => { e.stopPropagation(); onSetDefaultPair?.(pair); }}
          className="shrink-0 p-0.5 hover:bg-trading-border rounded transition-colors"
          title={isDefault ? 'Default pair' : 'Set as default'}
        >
          <Star
            size={14}
            className={isDefault ? 'text-amber-400 fill-amber-400' : 'text-trading-muted hover:text-amber-400'}
            fill={isDefault ? 'currentColor' : 'none'}
          />
        </button>
      </button>
    );
  };

  const renderPairGroup = (pairs: ForexPair[], label: string) => {
    if (pairs.length === 0) return null;
    return (
      <div>
        <div className="px-3 py-1.5 text-xs font-medium text-trading-muted uppercase tracking-wider sticky top-0 bg-trading-card">
          {label}
        </div>
        {pairs.map(pair => renderPairRow(pair))}
      </div>
    );
  };

  const isSearching = searchQuery.trim().length > 0;

  // Build the pair list content based on tab + search
  const renderPairList = () => {
    if (isSearching) {
      // Search across ALL pairs, flat list
      const allPairs = [...MAJOR_PAIRS, ...MINOR_PAIRS, ...EXOTIC_PAIRS, ...COMMODITY_PAIRS, ...CRYPTO_PAIRS, ...INDEX_PAIRS];
      const filtered = filterPairs(allPairs);
      if (filtered.length === 0) {
        return (
          <div className="p-6 text-center">
            <p className="text-sm text-trading-muted">No pairs found</p>
          </div>
        );
      }
      return <div>{filtered.map(pair => renderPairRow(pair))}</div>;
    }

    switch (activeTab) {
      case 'all':
        return (
          <>
            {renderPairGroup(MAJOR_PAIRS, 'Majors')}
            {renderPairGroup(MINOR_PAIRS, 'Minors')}
            {renderPairGroup(EXOTIC_PAIRS, 'Exotics')}
            {renderPairGroup(COMMODITY_PAIRS, 'Commodities')}
            {renderPairGroup(CRYPTO_PAIRS, 'Crypto')}
            {renderPairGroup(INDEX_PAIRS, 'Indices')}
          </>
        );
      case 'forex':
        return (
          <>
            {renderPairGroup(MAJOR_PAIRS, 'Majors')}
            {renderPairGroup(MINOR_PAIRS, 'Minors')}
            {renderPairGroup(EXOTIC_PAIRS, 'Exotics')}
          </>
        );
      case 'commodities':
        return <>{COMMODITY_PAIRS.map(pair => renderPairRow(pair))}</>;
      case 'crypto':
        return <>{CRYPTO_PAIRS.map(pair => renderPairRow(pair))}</>;
      case 'indices':
        return <>{INDEX_PAIRS.map(pair => renderPairRow(pair))}</>;
      default:
        return null;
    }
  };

  return (
    <div className="relative" ref={dropdownRef}>
      <div className="flex items-center gap-2">
        {/* Main Selector Button */}
        <button
          onClick={() => setIsOpen(!isOpen)}
          className="flex items-center gap-3 px-4 py-2.5 bg-trading-card border border-trading-border rounded-lg hover:border-trading-accent/50 transition-colors min-w-[200px]"
        >
          <div className="flex flex-col items-start">
            <span className="text-sm font-semibold text-trading-text">{selectedPair.symbol}</span>
            <span className="text-xs text-trading-muted">{selectedPair.nickname}</span>
          </div>
          <ChevronDown
            className={`w-4 h-4 text-trading-muted ml-auto transition-transform ${isOpen ? 'rotate-180' : ''}`}
          />
        </button>

        {/* AI Suggest Button */}
        <button
          onClick={onAISuggest}
          className="flex items-center justify-center w-10 h-10 bg-trading-card border border-trading-border rounded-lg hover:border-trading-accent/50 hover:bg-trading-accent/10 transition-colors"
          title="Get AI Suggestions"
        >
          <Sparkles className="w-4 h-4 text-trading-accent" />
        </button>
      </div>

      {/* Dropdown Panel */}
      {isOpen && (
        <div className="absolute top-full left-0 mt-2 w-[520px] bg-trading-card border border-trading-border rounded-lg shadow-xl shadow-black/50 z-50">
          {/* Search Input */}
          <div className="p-3 border-b border-trading-border">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-trading-muted" />
              <input
                type="text"
                placeholder="Search pairs..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full pl-9 pr-3 py-2 bg-trading-bg border border-trading-border rounded-md text-sm text-trading-text placeholder-trading-muted focus:outline-none focus:border-trading-accent/50"
                autoFocus
              />
            </div>
          </div>

          {/* Category Tabs */}
          <div className="px-3 py-2 border-b border-trading-border flex flex-wrap gap-1.5">
            {CATEGORY_TABS.map((tab) => {
              const count = getTabCount(tab.id);
              return (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={`px-3 py-1.5 rounded-full text-xs font-medium whitespace-nowrap transition-colors ${
                    activeTab === tab.id
                      ? 'bg-trading-accent text-white'
                      : 'bg-trading-bg text-trading-muted hover:text-trading-text hover:bg-trading-border'
                  }`}
                >
                  {tab.label}{count !== null ? ` (${count})` : ''}
                </button>
              );
            })}
          </div>

          {/* Recent Pairs Chips */}
          {recentPairs && recentPairs.length > 0 && !isSearching && (
            <div className="px-3 py-2 border-b border-trading-border flex items-center gap-2 overflow-x-auto">
              <span className="flex items-center gap-1 text-xs text-trading-muted shrink-0">
                <Clock size={12} />
                Recent
              </span>
              {recentPairs.map((pair) => (
                <button
                  key={`recent-${pair.symbol}`}
                  onClick={() => handleSelectPair(pair)}
                  className="px-2.5 py-1 rounded-md bg-trading-bg text-xs text-trading-text hover:bg-trading-border transition-colors whitespace-nowrap shrink-0"
                >
                  {pair.symbol}
                </button>
              ))}
            </div>
          )}

          {/* Pairs List */}
          <div className="max-h-[400px] overflow-y-auto">
            {renderPairList()}
          </div>
        </div>
      )}
    </div>
  );
}
