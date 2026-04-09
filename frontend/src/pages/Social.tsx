import { useState, useEffect } from 'react';
import { Trophy, Users, User, TrendingUp, Percent, Activity, Users2, Share2, X, TrendingDown, Target, Shield } from 'lucide-react';
import LeaderboardTable from '../components/LeaderboardTable';
import SignalFeed from '../components/SignalFeed';
import type { SignalPost } from '../types';

interface UserStats {
  totalReturn: number;
  winRate: number;
  sharpeRatio: number;
  followers: number;
  following: number;
}

type TabType = 'leaderboard' | 'feed' | 'profile';
type PeriodType = 'week' | 'month' | 'all';
type FilterType = 'all' | 'buy' | 'sell' | 'following';

const FOREX_PAIRS = [
  'EUR/USD', 'GBP/USD', 'USD/JPY', 'AUD/USD', 'USD/CHF', 
  'USD/CAD', 'EUR/GBP', 'EUR/JPY', 'GBP/JPY', 'XAU/USD',
  'BTC/USD', 'ETH/USD', 'SPX500'
];

export default function Social() {
  const [activeTab, setActiveTab] = useState<TabType>('leaderboard');
  const [leaderboardPeriod, setLeaderboardPeriod] = useState<PeriodType>('month');
  const [signalFilter, setSignalFilter] = useState<FilterType>('all');
  const [showShareModal, setShowShareModal] = useState(false);
  const [userStats, setUserStats] = useState<UserStats>({
    totalReturn: 23.5,
    winRate: 68.2,
    sharpeRatio: 1.85,
    followers: 1247,
    following: 89
  });
  const [_mySignals, _setMySignals] = useState<SignalPost[]>([]);
  
  // Share signal form state
  const [shareForm, setShareForm] = useState({
    symbol: 'EUR/USD',
    direction: 'BUY' as 'BUY' | 'SELL',
    confidence: 75,
    entryPrice: 1.0850,
    stopLoss: 1.0800,
    takeProfit: 1.0950
  });

  useEffect(() => {
    // Fetch mock user stats and signals
    fetchUserProfile();
  }, []);

  const fetchUserProfile = async () => {
    try {
      const response = await fetch('/api/social/user/current');
      if (response.ok) {
        const data = await response.json();
        setUserStats({
          totalReturn: data.stats?.avg_return * 10 || 23.5,
          winRate: data.stats?.win_rate || 68.2,
          sharpeRatio: data.stats?.sharpe_ratio || 1.85,
          followers: data.followers || 1247,
          following: data.following || 89
        });
      }
    } catch (error) {
      console.error('Failed to fetch user profile:', error);
    }
  };

  const sanitizeText = (text: string, maxLength: number = 500): string => {
    return text
      .replace(/<[^>]*>/g, '')  // Strip HTML tags
      .replace(/[<>"'&]/g, '')   // Remove dangerous chars
      .trim()
      .slice(0, maxLength)
  };

  const handleShareSignal = async () => {
    // Sanitize text fields before submission
    const sanitizedSymbol = sanitizeText(shareForm.symbol, 20);
    if (!sanitizedSymbol) return;

    try {
      const response = await fetch('/api/social/share', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          symbol: sanitizedSymbol,
          direction: shareForm.direction,
          confidence: shareForm.confidence / 100,
          entry_price: shareForm.entryPrice,
          stop_loss: shareForm.stopLoss,
          take_profit: shareForm.takeProfit
        })
      });
      
      if (response.ok) {
        setShowShareModal(false);
        // Refresh feed if on feed tab
        if (activeTab === 'feed') {
          window.location.reload();
        }
      }
    } catch (error) {
      console.error('Failed to share signal:', error);
    }
  };

  const StatCard = ({ icon: Icon, label, value, suffix = '', color = 'text-trading-accent' }: any) => (
    <div className="bg-trading-card border border-trading-border rounded-lg p-4">
      <div className="flex items-center gap-3 mb-2">
        <div className={`p-2 rounded-lg bg-trading-border/50 ${color}`}>
          <Icon className="w-5 h-5" />
        </div>
        <span className="text-sm text-trading-muted">{label}</span>
      </div>
      <p className="text-2xl font-bold text-trading-text">
        {value}{suffix}
      </p>
    </div>
  );

  return (
    <div className="p-6 max-w-7xl mx-auto">
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-trading-text mb-2">Social Trading</h1>
        <p className="text-trading-muted">Connect with top traders and share your signals</p>
      </div>

      {/* Tab Navigation */}
      <div className="flex flex-wrap gap-2 mb-6">
        <button
          onClick={() => setActiveTab('leaderboard')}
          className={`flex items-center gap-2 px-4 py-2 rounded-lg font-medium transition-colors ${
            activeTab === 'leaderboard'
              ? 'bg-trading-accent text-white'
              : 'bg-trading-card text-trading-muted hover:text-trading-text border border-trading-border'
          }`}
        >
          <Trophy className="w-4 h-4" />
          Top Traders
        </button>
        <button
          onClick={() => setActiveTab('feed')}
          className={`flex items-center gap-2 px-4 py-2 rounded-lg font-medium transition-colors ${
            activeTab === 'feed'
              ? 'bg-trading-accent text-white'
              : 'bg-trading-card text-trading-muted hover:text-trading-text border border-trading-border'
          }`}
        >
          <Users className="w-4 h-4" />
          Community Signals
        </button>
        <button
          onClick={() => setActiveTab('profile')}
          className={`flex items-center gap-2 px-4 py-2 rounded-lg font-medium transition-colors ${
            activeTab === 'profile'
              ? 'bg-trading-accent text-white'
              : 'bg-trading-card text-trading-muted hover:text-trading-text border border-trading-border'
          }`}
        >
          <User className="w-4 h-4" />
          My Profile
        </button>
      </div>

      {/* Leaderboard Tab */}
      {activeTab === 'leaderboard' && (
        <div>
          {/* Period Filter */}
          <div className="flex gap-2 mb-4">
            {(['week', 'month', 'all'] as PeriodType[]).map((period) => (
              <button
                key={period}
                onClick={() => setLeaderboardPeriod(period)}
                className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                  leaderboardPeriod === period
                    ? 'bg-trading-accent text-white'
                    : 'bg-trading-card text-trading-muted hover:text-trading-text border border-trading-border'
                }`}
              >
                {period === 'week' && 'This Week'}
                {period === 'month' && 'This Month'}
                {period === 'all' && 'All Time'}
              </button>
            ))}
          </div>

          {/* Leaderboard Table */}
          <div className="bg-trading-card border border-trading-border rounded-lg p-4">
            <LeaderboardTable period={leaderboardPeriod} />
          </div>
        </div>
      )}

      {/* Signal Feed Tab */}
      {activeTab === 'feed' && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Main Feed */}
          <div className="lg:col-span-2">
            {/* Filter Bar */}
            <div className="flex flex-wrap gap-2 mb-4">
              {(['all', 'buy', 'sell', 'following'] as FilterType[]).map((filter) => (
                <button
                  key={filter}
                  onClick={() => setSignalFilter(filter)}
                  className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                    signalFilter === filter
                      ? 'bg-trading-accent text-white'
                      : 'bg-trading-card text-trading-muted hover:text-trading-text border border-trading-border'
                  }`}
                >
                  {filter === 'all' && 'All Signals'}
                  {filter === 'buy' && 'BUY Only'}
                  {filter === 'sell' && 'SELL Only'}
                  {filter === 'following' && 'My Following'}
                </button>
              ))}
            </div>

            {/* Signal Feed */}
            <SignalFeed filter={signalFilter} />
          </div>

          {/* Sidebar */}
          <div className="space-y-4">
            {/* Share Signal Card */}
            <div className="bg-trading-card border border-trading-border rounded-lg p-4">
              <h3 className="font-medium text-trading-text mb-3">Share Your Signal</h3>
              <p className="text-sm text-trading-muted mb-4">
                Share your trading ideas with the community and build your following.
              </p>
              <button
                onClick={() => setShowShareModal(true)}
                className="w-full flex items-center justify-center gap-2 px-4 py-2 bg-trading-accent text-white rounded-lg hover:bg-trading-accent/90 transition-colors"
              >
                <Share2 className="w-4 h-4" />
                Share Signal
              </button>
            </div>

            {/* Trending Symbols */}
            <div className="bg-trading-card border border-trading-border rounded-lg p-4">
              <h3 className="font-medium text-trading-text mb-3">Trending Now</h3>
              <div className="space-y-2">
                {['EUR/USD', 'BTC/USD', 'XAU/USD'].map((symbol, i) => (
                  <div key={symbol} className="flex items-center justify-between py-2 border-b border-trading-border/50 last:border-0">
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-trading-muted">#{i + 1}</span>
                      <span className="font-medium text-trading-text">{symbol}</span>
                    </div>
                    <span className="text-sm text-trading-buy">+{2.5 + i}%</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Profile Tab */}
      {activeTab === 'profile' && (
        <div className="space-y-6">
          {/* Stats Grid */}
          <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
            <StatCard
              icon={TrendingUp}
              label="Total Return"
              value={userStats.totalReturn >= 0 ? '+' : ''}
              suffix={`${userStats.totalReturn.toFixed(1)}%`}
              color={userStats.totalReturn >= 0 ? 'text-trading-buy' : 'text-trading-sell'}
            />
            <StatCard
              icon={Percent}
              label="Win Rate"
              value={userStats.winRate.toFixed(1)}
              suffix="%"
              color="text-trading-accent"
            />
            <StatCard
              icon={Activity}
              label="Sharpe Ratio"
              value={userStats.sharpeRatio.toFixed(2)}
              color="text-purple-400"
            />
            <StatCard
              icon={Users2}
              label="Followers"
              value={userStats.followers.toLocaleString()}
              color="text-blue-400"
            />
            <StatCard
              icon={User}
              label="Following"
              value={userStats.following.toLocaleString()}
              color="text-orange-400"
            />
          </div>

          {/* Recent Signals & Share Button */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div className="lg:col-span-2">
              <div className="bg-trading-card border border-trading-border rounded-lg p-4">
                <h3 className="font-medium text-trading-text mb-4">Your Recent Signals</h3>
                <SignalFeed filter="all" />
              </div>
            </div>

            <div className="space-y-4">
              <div className="bg-trading-card border border-trading-border rounded-lg p-4">
                <h3 className="font-medium text-trading-text mb-3">Quick Actions</h3>
                <button
                  onClick={() => setShowShareModal(true)}
                  className="w-full flex items-center justify-center gap-2 px-4 py-2 bg-trading-accent text-white rounded-lg hover:bg-trading-accent/90 transition-colors mb-3"
                >
                  <Share2 className="w-4 h-4" />
                  Share New Signal
                </button>
                <p className="text-xs text-trading-muted text-center">
                  Share your best setups and grow your following
                </p>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Share Signal Modal */}
      {showShareModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-trading-card border border-trading-border rounded-lg w-full max-w-md">
            <div className="flex items-center justify-between p-4 border-b border-trading-border">
              <h3 className="font-medium text-trading-text">Share Signal</h3>
              <button
                onClick={() => setShowShareModal(false)}
                className="text-trading-muted hover:text-trading-text"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="p-4 space-y-4">
              {/* Pair Selector */}
              <div>
                <label className="block text-sm text-trading-muted mb-1">Trading Pair</label>
                <select
                  value={shareForm.symbol}
                  onChange={(e) => setShareForm({ ...shareForm, symbol: e.target.value })}
                  className="w-full px-3 py-2 bg-trading-bg border border-trading-border rounded-lg text-trading-text focus:outline-none focus:border-trading-accent"
                >
                  {FOREX_PAIRS.map(pair => (
                    <option key={pair} value={pair}>{pair}</option>
                  ))}
                </select>
              </div>

              {/* Direction */}
              <div>
                <label className="block text-sm text-trading-muted mb-1">Direction</label>
                <div className="flex gap-2">
                  <button
                    onClick={() => setShareForm({ ...shareForm, direction: 'BUY' })}
                    className={`flex-1 flex items-center justify-center gap-2 px-4 py-2 rounded-lg font-medium transition-colors ${
                      shareForm.direction === 'BUY'
                        ? 'bg-trading-buy text-white'
                        : 'bg-trading-border text-trading-muted'
                    }`}
                  >
                    <TrendingUp className="w-4 h-4" />
                    BUY
                  </button>
                  <button
                    onClick={() => setShareForm({ ...shareForm, direction: 'SELL' })}
                    className={`flex-1 flex items-center justify-center gap-2 px-4 py-2 rounded-lg font-medium transition-colors ${
                      shareForm.direction === 'SELL'
                        ? 'bg-trading-sell text-white'
                        : 'bg-trading-border text-trading-muted'
                    }`}
                  >
                    <TrendingDown className="w-4 h-4" />
                    SELL
                  </button>
                </div>
              </div>

              {/* Confidence Slider */}
              <div>
                <label className="block text-sm text-trading-muted mb-1">
                  Confidence: {shareForm.confidence}%
                </label>
                <input
                  type="range"
                  min="1"
                  max="100"
                  value={shareForm.confidence}
                  onChange={(e) => setShareForm({ ...shareForm, confidence: parseInt(e.target.value) })}
                  className="w-full h-2 bg-trading-border rounded-lg appearance-none cursor-pointer accent-trading-accent"
                />
              </div>

              {/* Entry Price */}
              <div>
                <label className="block text-sm text-trading-muted mb-1">Entry Price</label>
                <input
                  type="number"
                  step="0.0001"
                  value={shareForm.entryPrice}
                  onChange={(e) => setShareForm({ ...shareForm, entryPrice: parseFloat(e.target.value) })}
                  className="w-full px-3 py-2 bg-trading-bg border border-trading-border rounded-lg text-trading-text focus:outline-none focus:border-trading-accent"
                />
              </div>

              {/* Stop Loss */}
              <div>
                <label className="flex items-center gap-2 text-sm text-trading-muted mb-1">
                  <Shield className="w-3 h-3" />
                  Stop Loss
                </label>
                <input
                  type="number"
                  step="0.0001"
                  value={shareForm.stopLoss}
                  onChange={(e) => setShareForm({ ...shareForm, stopLoss: parseFloat(e.target.value) })}
                  className="w-full px-3 py-2 bg-trading-bg border border-trading-border rounded-lg text-trading-text focus:outline-none focus:border-trading-accent"
                />
              </div>

              {/* Take Profit */}
              <div>
                <label className="flex items-center gap-2 text-sm text-trading-muted mb-1">
                  <Target className="w-3 h-3" />
                  Take Profit
                </label>
                <input
                  type="number"
                  step="0.0001"
                  value={shareForm.takeProfit}
                  onChange={(e) => setShareForm({ ...shareForm, takeProfit: parseFloat(e.target.value) })}
                  className="w-full px-3 py-2 bg-trading-bg border border-trading-border rounded-lg text-trading-text focus:outline-none focus:border-trading-accent"
                />
              </div>
            </div>

            <div className="flex gap-2 p-4 border-t border-trading-border">
              <button
                onClick={() => setShowShareModal(false)}
                className="flex-1 px-4 py-2 bg-trading-border text-trading-text rounded-lg hover:bg-trading-border/80 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleShareSignal}
                className="flex-1 px-4 py-2 bg-trading-accent text-white rounded-lg hover:bg-trading-accent/90 transition-colors"
              >
                Share
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
