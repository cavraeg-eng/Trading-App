import { useState, useEffect } from 'react';
import { Heart, MessageCircle, TrendingUp, TrendingDown, Minus, Clock } from 'lucide-react';
import type { SignalPost } from '../types';

interface SignalFeedProps {
  filter: 'all' | 'buy' | 'sell' | 'following';
}

export default function SignalFeed({ filter }: SignalFeedProps) {
  const [posts, setPosts] = useState<SignalPost[]>([]);
  const [loading, setLoading] = useState(true);
  const [likedPosts, setLikedPosts] = useState<Set<string>>(new Set());

  useEffect(() => {
    fetchFeed();
  }, []);

  const fetchFeed = async () => {
    setLoading(true);
    try {
      const response = await fetch('/api/social/feed?limit=30');
      if (response.ok) {
        const data = await response.json();
        // Map snake_case to camelCase
        const mappedData = data.map((post: any) => ({
          id: post.id,
          username: post.username,
          avatar: post.avatar,
          symbol: post.symbol,
          direction: post.direction,
          confidence: post.confidence,
          entryPrice: post.entry_price,
          stopLoss: post.stop_loss,
          takeProfit: post.take_profit,
          result: post.result,
          pnl: post.pnl,
          timestamp: post.timestamp,
          likes: post.likes,
          comments: post.comments,
          isLiked: post.is_liked || false,
        }));
        setPosts(mappedData);
      }
    } catch (error) {
      console.error('Failed to fetch feed:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleLike = async (postId: string) => {
    try {
      const response = await fetch(`/api/social/like/${postId}`, { method: 'POST' });
      if (response.ok) {
        setLikedPosts(prev => new Set(prev).add(postId));
        setPosts(prev => prev.map(post => 
          post.id === postId ? { ...post, likes: post.likes + 1 } : post
        ));
      }
    } catch (error) {
      console.error('Failed to like post:', error);
    }
  };

  const getTimeAgo = (timestamp: string) => {
    const date = new Date(timestamp);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    return `${diffDays}d ago`;
  };

  const getDirectionBadge = (direction: string) => {
    switch (direction) {
      case 'BUY':
        return (
          <span className="flex items-center gap-1 px-2 py-1 rounded bg-trading-buy/20 text-trading-buy text-sm font-medium">
            <TrendingUp className="w-3 h-3" />
            BUY
          </span>
        );
      case 'SELL':
        return (
          <span className="flex items-center gap-1 px-2 py-1 rounded bg-trading-sell/20 text-trading-sell text-sm font-medium">
            <TrendingDown className="w-3 h-3" />
            SELL
          </span>
        );
      default:
        return (
          <span className="flex items-center gap-1 px-2 py-1 rounded bg-trading-border text-trading-muted text-sm font-medium">
            <Minus className="w-3 h-3" />
            HOLD
          </span>
        );
    }
  };

  const getResultBadge = (result?: string, pnl?: number) => {
    if (!result || result === 'open') {
      return (
        <span className="flex items-center gap-1 px-2 py-1 rounded bg-blue-500/20 text-blue-400 text-xs font-medium">
          <Clock className="w-3 h-3" />
          Open
        </span>
      );
    }
    if (result === 'won') {
      return (
        <span className="flex items-center gap-1 px-2 py-1 rounded bg-trading-buy/20 text-trading-buy text-xs font-medium">
          <TrendingUp className="w-3 h-3" />
          Won +{pnl?.toFixed(2) || '0.00'}%
        </span>
      );
    }
    return (
      <span className="flex items-center gap-1 px-2 py-1 rounded bg-trading-sell/20 text-trading-sell text-xs font-medium">
        <TrendingDown className="w-3 h-3" />
        Lost {pnl?.toFixed(2) || '0.00'}%
      </span>
    );
  };

  const getConfidenceColor = (confidence: number) => {
    if (confidence >= 0.8) return 'bg-trading-buy';
    if (confidence >= 0.6) return 'bg-yellow-500';
    return 'bg-trading-sell';
  };

  const filteredPosts = posts.filter(post => {
    if (filter === 'all') return true;
    if (filter === 'buy') return post.direction === 'BUY';
    if (filter === 'sell') return post.direction === 'SELL';
    if (filter === 'following') return false; // Mock - no following data yet
    return true;
  });

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-trading-accent"></div>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {filteredPosts.map((post) => (
        <div
          key={post.id}
          className="bg-trading-card border border-trading-border rounded-lg p-4 hover:border-trading-border/80 transition-colors"
        >
          {/* Header */}
          <div className="flex items-start justify-between mb-3">
            <div className="flex items-center gap-3">
              <img
                src={post.avatar}
                alt={post.username}
                className="w-10 h-10 rounded-full bg-trading-border"
              />
              <div>
                <p className="font-medium text-trading-text">{post.username}</p>
                <p className="text-xs text-trading-muted">{getTimeAgo(post.timestamp)}</p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              {getDirectionBadge(post.direction)}
              {getResultBadge(post.result, post.pnl)}
            </div>
          </div>

          {/* Symbol & Confidence */}
          <div className="flex items-center justify-between mb-3">
            <span className="text-lg font-bold text-trading-text">{post.symbol}</span>
            <div className="flex items-center gap-2">
              <span className="text-sm text-trading-muted">Confidence</span>
              <div className="w-24 h-2 bg-trading-border rounded-full overflow-hidden">
                <div
                  className={`h-full ${getConfidenceColor(post.confidence)}`}
                  style={{ width: `${post.confidence * 100}%` }}
                />
              </div>
              <span className="text-sm font-medium text-trading-text">{Math.round(post.confidence * 100)}%</span>
            </div>
          </div>

          {/* Trade Details */}
          <div className="grid grid-cols-3 gap-4 mb-3 text-sm">
            <div>
              <p className="text-trading-muted text-xs">Entry</p>
              <p className="font-medium text-trading-text">{post.entryPrice.toFixed(4)}</p>
            </div>
            {post.stopLoss && (
              <div>
                <p className="text-trading-muted text-xs">Stop Loss</p>
                <p className="font-medium text-trading-sell">{post.stopLoss.toFixed(4)}</p>
              </div>
            )}
            {post.takeProfit && (
              <div>
                <p className="text-trading-muted text-xs">Take Profit</p>
                <p className="font-medium text-trading-buy">{post.takeProfit.toFixed(4)}</p>
              </div>
            )}
          </div>

          {/* P&L if closed */}
          {post.pnl !== undefined && post.pnl !== null && (
            <div className="mb-3 p-2 rounded bg-trading-border/30">
              <span className={`text-sm font-medium ${post.pnl >= 0 ? 'text-trading-buy' : 'text-trading-sell'}`}>
                P&L: {post.pnl >= 0 ? '+' : ''}${post.pnl.toFixed(2)}
              </span>
            </div>
          )}

          {/* Actions */}
          <div className="flex items-center gap-4 pt-3 border-t border-trading-border/50">
            <button
              onClick={() => handleLike(post.id)}
              className={`flex items-center gap-1.5 text-sm transition-colors ${
                likedPosts.has(post.id) || post.isLiked
                  ? 'text-red-400'
                  : 'text-trading-muted hover:text-red-400'
              }`}
            >
              <Heart className={`w-4 h-4 ${likedPosts.has(post.id) || post.isLiked ? 'fill-current' : ''}`} />
              {post.likes + (likedPosts.has(post.id) ? 1 : 0)}
            </button>
            <button className="flex items-center gap-1.5 text-sm text-trading-muted hover:text-trading-accent transition-colors">
              <MessageCircle className="w-4 h-4" />
              {post.comments}
            </button>
          </div>
        </div>
      ))}

      {filteredPosts.length === 0 && (
        <div className="text-center py-12 text-trading-muted">
          <p>No signals found for this filter.</p>
        </div>
      )}
    </div>
  );
}
