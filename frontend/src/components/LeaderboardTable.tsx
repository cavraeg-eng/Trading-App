import { useState, useEffect } from 'react';
import { Trophy, Medal, UserPlus, UserCheck, ArrowUpDown } from 'lucide-react';
import type { LeaderboardEntry } from '../types';

interface LeaderboardTableProps {
  period: 'week' | 'month' | 'all';
}

type SortKey = 'rank' | 'monthlyReturn' | 'winRate' | 'sharpeRatio' | 'totalTrades' | 'followers';
type SortOrder = 'asc' | 'desc';

export default function LeaderboardTable({ period }: LeaderboardTableProps) {
  const [entries, setEntries] = useState<LeaderboardEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [sortKey, setSortKey] = useState<SortKey>('rank');
  const [sortOrder, setSortOrder] = useState<SortOrder>('asc');
  const [following, setFollowing] = useState<Set<string>>(new Set());

  useEffect(() => {
    fetchLeaderboard();
  }, [period]);

  const fetchLeaderboard = async () => {
    setLoading(true);
    try {
      const response = await fetch(`/api/social/leaderboard?timeframe=${period === 'week' ? 'weekly' : period === 'month' ? 'monthly' : 'all-time'}&limit=20`);
      if (response.ok) {
        const data = await response.json();
        // Map snake_case to camelCase
        const mappedData = data.map((entry: any) => ({
          rank: entry.rank,
          username: entry.username,
          avatar: entry.avatar,
          monthlyReturn: entry.monthly_return,
          winRate: entry.win_rate,
          sharpeRatio: entry.sharpe_ratio,
          totalTrades: entry.total_trades,
          followers: entry.followers,
          isFollowing: entry.is_following || false,
        }));
        setEntries(mappedData);
        // Initialize following state
        const initialFollowing = new Set<string>();
        mappedData.forEach((entry: LeaderboardEntry) => {
          if (entry.isFollowing) initialFollowing.add(entry.username);
        });
        setFollowing(initialFollowing);
      }
    } catch (error) {
      console.error('Failed to fetch leaderboard:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc');
    } else {
      setSortKey(key);
      setSortOrder('desc');
    }
  };

  const toggleFollow = (username: string) => {
    setFollowing(prev => {
      const newFollowing = new Set(prev);
      if (newFollowing.has(username)) {
        newFollowing.delete(username);
      } else {
        newFollowing.add(username);
      }
      return newFollowing;
    });
  };

  const getRankBadge = (rank: number) => {
    if (rank === 1) return <Trophy className="w-5 h-5 text-yellow-400" />;
    if (rank === 2) return <Medal className="w-5 h-5 text-gray-400" />;
    if (rank === 3) return <Medal className="w-5 h-5 text-amber-600" />;
    return <span className="text-trading-muted font-medium">#{rank}</span>;
  };

  const getRowBorderColor = (rank: number) => {
    if (rank === 1) return 'border-l-4 border-l-yellow-400';
    if (rank === 2) return 'border-l-4 border-l-gray-400';
    if (rank === 3) return 'border-l-4 border-l-amber-600';
    return 'border-l-4 border-l-transparent';
  };

  const sortedEntries = [...entries].sort((a, b) => {
    let comparison = 0;
    switch (sortKey) {
      case 'rank':
        comparison = a.rank - b.rank;
        break;
      case 'monthlyReturn':
        comparison = a.monthlyReturn - b.monthlyReturn;
        break;
      case 'winRate':
        comparison = a.winRate - b.winRate;
        break;
      case 'sharpeRatio':
        comparison = a.sharpeRatio - b.sharpeRatio;
        break;
      case 'totalTrades':
        comparison = a.totalTrades - b.totalTrades;
        break;
      case 'followers':
        comparison = a.followers - b.followers;
        break;
    }
    return sortOrder === 'asc' ? comparison : -comparison;
  });

  const SortHeader = ({ label, sortKeyValue }: { label: string; sortKeyValue: SortKey }) => (
    <button
      onClick={() => handleSort(sortKeyValue)}
      className="flex items-center gap-1 hover:text-white transition-colors"
    >
      {label}
      <ArrowUpDown className="w-3 h-3" />
    </button>
  );

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-trading-accent"></div>
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full">
        <thead>
          <tr className="text-left text-trading-muted text-sm border-b border-trading-border">
            <th className="pb-3 pl-4">
              <SortHeader label="Rank" sortKeyValue="rank" />
            </th>
            <th className="pb-3">Trader</th>
            <th className="pb-3">
              <SortHeader label="Return %" sortKeyValue="monthlyReturn" />
            </th>
            <th className="pb-3">
              <SortHeader label="Win Rate" sortKeyValue="winRate" />
            </th>
            <th className="pb-3">
              <SortHeader label="Sharpe" sortKeyValue="sharpeRatio" />
            </th>
            <th className="pb-3">
              <SortHeader label="Trades" sortKeyValue="totalTrades" />
            </th>
            <th className="pb-3">
              <SortHeader label="Followers" sortKeyValue="followers" />
            </th>
            <th className="pb-3 pr-4">Action</th>
          </tr>
        </thead>
        <tbody>
          {sortedEntries.map((entry) => (
            <tr
              key={entry.username}
              className={`border-b border-trading-border/50 hover:bg-trading-border/20 transition-colors ${getRowBorderColor(entry.rank)}`}
            >
              <td className="py-4 pl-4">
                <div className="flex items-center justify-center w-8">
                  {getRankBadge(entry.rank)}
                </div>
              </td>
              <td className="py-4">
                <div className="flex items-center gap-3">
                  <img
                    src={entry.avatar}
                    alt={entry.username}
                    className="w-10 h-10 rounded-full bg-trading-border"
                  />
                  <span className="font-medium text-trading-text">{entry.username}</span>
                </div>
              </td>
              <td className="py-4">
                <span className={`font-medium ${entry.monthlyReturn >= 0 ? 'text-trading-buy' : 'text-trading-sell'}`}>
                  {entry.monthlyReturn >= 0 ? '+' : ''}{entry.monthlyReturn.toFixed(2)}%
                </span>
              </td>
              <td className="py-4">
                <span className="text-trading-text">{entry.winRate.toFixed(1)}%</span>
              </td>
              <td className="py-4">
                <span className="text-trading-text">{entry.sharpeRatio.toFixed(2)}</span>
              </td>
              <td className="py-4">
                <span className="text-trading-text">{entry.totalTrades}</span>
              </td>
              <td className="py-4">
                <span className="text-trading-text">{entry.followers.toLocaleString()}</span>
              </td>
              <td className="py-4 pr-4">
                <button
                  onClick={() => toggleFollow(entry.username)}
                  className={`flex items-center gap-1 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                    following.has(entry.username)
                      ? 'bg-trading-accent/20 text-trading-accent hover:bg-trading-accent/30'
                      : 'bg-trading-border text-trading-muted hover:bg-trading-border/80 hover:text-trading-text'
                  }`}
                >
                  {following.has(entry.username) ? (
                    <>
                      <UserCheck className="w-4 h-4" />
                      Following
                    </>
                  ) : (
                    <>
                      <UserPlus className="w-4 h-4" />
                      Follow
                    </>
                  )}
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
