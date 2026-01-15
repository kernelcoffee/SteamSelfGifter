import { useState, useEffect, useRef } from 'react';
import { ExternalLink, Eye, EyeOff, Gift, Clock, AlertCircle, Loader2, X, Heart, Trophy, Star, Shield, ShieldAlert, EyeOff as HideIcon, MessageSquare } from 'lucide-react';
import { SiSteam } from 'react-icons/si';
import { Card, Button, Badge, Input, CardSkeleton } from '@/components/common';
import { useInfiniteGiveaways, useEnterGiveaway, useHideGiveaway, useUnhideGiveaway, useRemoveEntry, useCheckGiveawaySafety, useHideOnSteamGifts, usePostComment, type GiveawayFilters } from '@/hooks';
import { showSuccess, showError } from '@/stores/uiStore';
import type { Giveaway } from '@/types';

/**
 * Giveaways page
 * Browse, filter, and enter giveaways
 */
export function Giveaways() {
  const [filters, setFilters] = useState<Omit<GiveawayFilters, 'page'>>({
    status: 'active',
    limit: 20,
  });
  const [searchInput, setSearchInput] = useState('');

  const {
    data,
    isLoading,
    error,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage
  } = useInfiniteGiveaways(filters);
  const enterGiveaway = useEnterGiveaway();
  const hideGiveaway = useHideGiveaway();
  const unhideGiveaway = useUnhideGiveaway();
  const removeEntry = useRemoveEntry();
  const checkSafety = useCheckGiveawaySafety();
  const hideOnSteamGifts = useHideOnSteamGifts();
  const postComment = usePostComment();

  // Flatten all pages into a single array
  const allGiveaways = data?.pages.flatMap(page => page.giveaways) ?? [];

  // Ref for intersection observer
  const loadMoreRef = useRef<HTMLDivElement>(null);

  // Set up intersection observer for infinite scroll
  useEffect(() => {
    if (!hasNextPage || isFetchingNextPage) return;

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting) {
          fetchNextPage();
        }
      },
      { threshold: 0.1 } // Trigger when 10% of the element is visible
    );

    const currentRef = loadMoreRef.current;
    if (currentRef) {
      observer.observe(currentRef);
    }

    return () => {
      if (currentRef) {
        observer.unobserve(currentRef);
      }
    };
  }, [hasNextPage, isFetchingNextPage, fetchNextPage]);

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    setFilters(prev => ({ ...prev, search: searchInput }));
  };

  const handleStatusFilter = (status: GiveawayFilters['status']) => {
    setFilters(prev => ({ ...prev, status }));
  };

  const handleScoreFilter = (score: number) => {
    setFilters(prev => ({ ...prev, minScore: score }));
  };

  const handleEnter = async (giveaway: Giveaway) => {
    try {
      await enterGiveaway.mutateAsync(giveaway.code);
      showSuccess(`Entered giveaway for ${giveaway.game_name}`);
    } catch (err) {
      showError(err instanceof Error ? err.message : 'Failed to enter giveaway');
    }
  };

  const handleHide = async (giveaway: Giveaway) => {
    try {
      await hideGiveaway.mutateAsync(giveaway.code);
      showSuccess(`Hidden: ${giveaway.game_name}`);
    } catch (err) {
      showError(err instanceof Error ? err.message : 'Failed to hide giveaway');
    }
  };

  const handleUnhide = async (giveaway: Giveaway) => {
    try {
      await unhideGiveaway.mutateAsync(giveaway.code);
      showSuccess(`Unhidden: ${giveaway.game_name}`);
    } catch (err) {
      showError(err instanceof Error ? err.message : 'Failed to unhide giveaway');
    }
  };

  const handleRemoveEntry = async (giveaway: Giveaway) => {
    try {
      await removeEntry.mutateAsync(giveaway.code);
      showSuccess(`Entry removed for ${giveaway.game_name}`);
    } catch (err) {
      showError(err instanceof Error ? err.message : 'Failed to remove entry');
    }
  };

  const handleCheckSafety = async (giveaway: Giveaway) => {
    try {
      const result = await checkSafety.mutateAsync(giveaway.code);
      if (result.is_safe) {
        showSuccess(`${giveaway.game_name} appears safe (score: ${result.safety_score}%)`);
      } else {
        showError(`${giveaway.game_name} flagged as unsafe! Score: ${result.safety_score}%. Issues: ${result.details.join(', ')}`);
      }
    } catch (err) {
      showError(err instanceof Error ? err.message : 'Failed to check safety');
    }
  };

  const handleHideOnSteamGifts = async (giveaway: Giveaway) => {
    try {
      await hideOnSteamGifts.mutateAsync(giveaway.code);
      showSuccess(`Hidden ${giveaway.game_name} on SteamGifts`);
    } catch (err) {
      showError(err instanceof Error ? err.message : 'Failed to hide on SteamGifts');
    }
  };

  const handleComment = async (giveaway: Giveaway) => {
    try {
      await postComment.mutateAsync({ giveawayCode: giveaway.code });
      showSuccess(`Comment posted on ${giveaway.game_name}`);
    } catch (err) {
      showError(err instanceof Error ? err.message : 'Failed to post comment');
    }
  };

  const handleSafetyFilter = (safetyFilter: 'all' | 'safe' | 'unsafe') => {
    setFilters(prev => ({ ...prev, safetyFilter }));
  };

  if (error) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Giveaways</h1>
        <Card>
          <div className="flex items-center gap-3 text-red-500">
            <AlertCircle size={24} />
            <span>Failed to load giveaways. Is the backend running?</span>
          </div>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Giveaways</h1>

        {/* Search */}
        <form onSubmit={handleSearch} className="flex gap-2">
          <Input
            placeholder="Search games..."
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            className="w-64"
          />
          <Button type="submit" variant="secondary">Search</Button>
        </form>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-4">
        <div className="flex flex-wrap gap-2">
          <FilterButton
            active={filters.status === 'active'}
            onClick={() => handleStatusFilter('active')}
          >
            Active
          </FilterButton>
          <FilterButton
            active={filters.status === 'wishlist'}
            onClick={() => handleStatusFilter('wishlist')}
          >
            <Heart size={12} className="mr-1 fill-current text-pink-500" />
            Wishlist
          </FilterButton>
          <FilterButton
            active={filters.status === 'entered'}
            onClick={() => handleStatusFilter('entered')}
          >
            Entered
          </FilterButton>
          <FilterButton
            active={filters.status === 'won'}
            onClick={() => handleStatusFilter('won')}
          >
            <Trophy size={12} className="mr-1 text-yellow-500" />
            Won
          </FilterButton>
        </div>

        {/* Score Filter - only show for active status */}
        {filters.status === 'active' && (
          <div className="flex items-center gap-3 px-3 py-1.5 bg-gray-100 dark:bg-gray-800 rounded-lg">
            <Star size={16} className="text-yellow-500" />
            <span className="text-sm text-gray-600 dark:text-gray-400 whitespace-nowrap">
              Min Score:
            </span>
            <input
              type="range"
              min="0"
              max="10"
              value={filters.minScore || 0}
              onChange={(e) => handleScoreFilter(Number(e.target.value))}
              className="w-24 h-2 bg-gray-300 dark:bg-gray-600 rounded-lg appearance-none cursor-pointer accent-primary-light"
            />
            <span className="text-sm font-medium text-gray-700 dark:text-gray-300 w-6 text-center">
              {filters.minScore || 0}
            </span>
            {(filters.minScore ?? 0) > 0 && (
              <button
                onClick={() => handleScoreFilter(0)}
                className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-200"
                title="Clear filter"
              >
                <X size={14} />
              </button>
            )}
          </div>
        )}

        {/* Safety Filter */}
        {filters.status === 'active' && (
          <div className="flex items-center gap-2 px-3 py-1.5 bg-gray-100 dark:bg-gray-800 rounded-lg">
            <Shield size={16} className="text-green-500" />
            <span className="text-sm text-gray-600 dark:text-gray-400">Safety:</span>
            <select
              value={filters.safetyFilter || 'all'}
              onChange={(e) => handleSafetyFilter(e.target.value as 'all' | 'safe' | 'unsafe')}
              className="text-sm bg-transparent border-none focus:ring-0 text-gray-700 dark:text-gray-300 cursor-pointer"
            >
              <option value="all">All</option>
              <option value="safe">Safe Only</option>
              <option value="unsafe">Unsafe Only</option>
            </select>
          </div>
        )}
      </div>

      {/* Results count */}
      {allGiveaways.length > 0 && (
        <p className="text-sm text-gray-500 dark:text-gray-400">
          Showing {allGiveaways.length} giveaway{allGiveaways.length !== 1 ? 's' : ''}
        </p>
      )}

      {/* Giveaways Grid */}
      {isLoading ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4">
          {[...Array(10)].map((_, i) => (
            <CardSkeleton key={i} />
          ))}
        </div>
      ) : allGiveaways.length === 0 ? (
        <Card>
          <div className="text-center py-8 text-gray-500 dark:text-gray-400">
            No giveaways found matching your criteria.
          </div>
        </Card>
      ) : (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4">
            {allGiveaways.map((giveaway) => (
              <GiveawayCard
                key={giveaway.id}
                giveaway={giveaway}
                onEnter={() => handleEnter(giveaway)}
                onHide={() => handleHide(giveaway)}
                onUnhide={() => handleUnhide(giveaway)}
                onRemoveEntry={() => handleRemoveEntry(giveaway)}
                onCheckSafety={() => handleCheckSafety(giveaway)}
                onHideOnSteamGifts={() => handleHideOnSteamGifts(giveaway)}
                onComment={() => handleComment(giveaway)}
                isEntering={enterGiveaway.isPending}
                isRemovingEntry={removeEntry.isPending}
                isCheckingSafety={checkSafety.isPending}
                isHidingOnSteamGifts={hideOnSteamGifts.isPending}
                isCommenting={postComment.isPending}
              />
            ))}
          </div>

          {/* Infinite Scroll Trigger & Loading State */}
          {hasNextPage && (
            <div ref={loadMoreRef} className="flex justify-center mt-6 py-4">
              {isFetchingNextPage && (
                <div className="flex items-center gap-2 text-gray-500 dark:text-gray-400">
                  <Loader2 className="animate-spin" size={20} />
                  <span>Loading more giveaways...</span>
                </div>
              )}
            </div>
          )}

          {/* End of results indicator */}
          {!hasNextPage && allGiveaways.length > 0 && (
            <div className="flex justify-center mt-6 py-4">
              <p className="text-sm text-gray-500 dark:text-gray-400">
                No more giveaways to load
              </p>
            </div>
          )}
        </>
      )}

    </div>
  );
}

interface FilterButtonProps {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}

function FilterButton({ active, onClick, children }: FilterButtonProps) {
  return (
    <button
      onClick={onClick}
      className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
        active
          ? 'bg-primary-light text-white'
          : 'bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700'
      }`}
    >
      {children}
    </button>
  );
}

interface GiveawayCardProps {
  giveaway: Giveaway;
  onEnter: () => void;
  onHide: () => void;
  onUnhide: () => void;
  onRemoveEntry: () => void;
  onCheckSafety: () => void;
  onHideOnSteamGifts: () => void;
  onComment: () => void;
  isEntering: boolean;
  isRemovingEntry: boolean;
  isCheckingSafety: boolean;
  isHidingOnSteamGifts: boolean;
  isCommenting: boolean;
}

function GiveawayCard({ giveaway, onEnter, onHide, onUnhide, onRemoveEntry, onCheckSafety, onHideOnSteamGifts, onComment, isEntering, isRemovingEntry, isCheckingSafety, isHidingOnSteamGifts, isCommenting }: GiveawayCardProps) {
  // Determine if giveaway has ended:
  // - If end_time is set and in the past, it's expired
  // - If end_time is null but it's a won giveaway, treat as ended (historical)
  const isExpired = giveaway.end_time
    ? new Date(giveaway.end_time) < new Date()
    : giveaway.is_won; // No end_time + won = historical giveaway
  const timeLeft = giveaway.end_time
    ? formatTimeLeft(new Date(giveaway.end_time))
    : null;

  return (
    <Card className={giveaway.is_hidden ? 'opacity-60' : ''}>
      <div className="space-y-3">
        {/* Game Thumbnail */}
        {giveaway.game_thumbnail && (
          <div className="w-full h-32 overflow-hidden rounded-lg bg-gray-100 dark:bg-gray-800 -mx-4 -mt-4 mb-1">
            <img
              src={giveaway.game_thumbnail}
              alt={giveaway.game_name}
              className="w-full h-full object-cover"
              onError={(e) => {
                // Hide image container if it fails to load
                const parent = e.currentTarget.parentElement;
                if (parent) parent.style.display = 'none';
              }}
            />
          </div>
        )}

        {/* Header */}
        <div className="flex items-start justify-between gap-2">
          <h3 className="font-semibold text-gray-900 dark:text-white line-clamp-2">
            {giveaway.game_name}
          </h3>
          <div className="flex gap-1 shrink-0 flex-wrap">
            {giveaway.is_won && (
              <Badge variant="default" size="sm" className="bg-yellow-100 text-yellow-600 dark:bg-yellow-900/30 dark:text-yellow-400">
                <Trophy size={10} className="mr-1" />
                Won
              </Badge>
            )}
            {giveaway.is_wishlist && (
              <Badge variant="default" size="sm" className="bg-pink-100 text-pink-600 dark:bg-pink-900/30 dark:text-pink-400">
                <Heart size={10} className="mr-1 fill-current" />
                Wishlist
              </Badge>
            )}
            {giveaway.is_entered && !giveaway.is_won && <Badge variant="success" size="sm">Entered</Badge>}
            {giveaway.is_hidden && <Badge variant="warning" size="sm">Hidden</Badge>}
            {isExpired && !giveaway.is_won && <Badge variant="error" size="sm">Expired</Badge>}
          </div>
        </div>

        {/* Info */}
        <div className="flex flex-wrap gap-2 text-sm text-gray-500 dark:text-gray-400">
          <span className="flex items-center gap-1">
            <Gift size={14} />
            {giveaway.price}P
          </span>
          {giveaway.copies > 1 && (
            <span>{giveaway.copies} copies</span>
          )}
          {timeLeft && !isExpired && (
            <span className="flex items-center gap-1">
              <Clock size={14} />
              {timeLeft}
            </span>
          )}
        </div>

        {/* Steam Reviews */}
        {giveaway.game_review_summary && (
          <div className="flex items-center gap-2">
            <span className="text-sm text-gray-500 dark:text-gray-400">Reviews:</span>
            <Badge
              variant={
                giveaway.game_review_summary.includes('Positive') ? 'success' :
                giveaway.game_review_summary.includes('Mixed') ? 'warning' : 'error'
              }
              size="sm"
            >
              {giveaway.game_review_summary}
            </Badge>
            {giveaway.game_total_reviews && (
              <span className="text-xs text-gray-400">({giveaway.game_total_reviews.toLocaleString()})</span>
            )}
          </div>
        )}

        {/* Safety Score */}
        {giveaway.is_safe !== null && (
          <div className="flex items-center gap-2">
            <span className="text-sm text-gray-500 dark:text-gray-400">Safety:</span>
            {giveaway.is_safe ? (
              <Badge variant="success" size="sm">
                <Shield size={10} className="mr-1" />
                Safe
              </Badge>
            ) : (
              <Badge variant="error" size="sm">
                <ShieldAlert size={10} className="mr-1" />
                Unsafe
              </Badge>
            )}
            {giveaway.safety_score !== null && (
              <span className="text-xs text-gray-400">({giveaway.safety_score}%)</span>
            )}
          </div>
        )}

        {/* Actions */}
        <div className="flex flex-wrap gap-2 pt-2 border-t border-gray-100 dark:border-gray-800">
          {!giveaway.is_entered && !isExpired && (
            <Button
              size="sm"
              onClick={onEnter}
              isLoading={isEntering}
              icon={Gift}
            >
              Enter
            </Button>
          )}

          {giveaway.is_entered && !giveaway.is_won && !isExpired && (
            <Button
              size="sm"
              variant="danger"
              onClick={onRemoveEntry}
              isLoading={isRemovingEntry}
              icon={X}
            >
              Remove Entry
            </Button>
          )}

          {giveaway.is_hidden ? (
            <Button size="sm" variant="ghost" onClick={onUnhide} icon={Eye}>
              Unhide
            </Button>
          ) : (
            <Button size="sm" variant="ghost" onClick={onHide} icon={EyeOff}>
              Hide
            </Button>
          )}

          {/* Safety Actions */}
          {giveaway.is_safe === null && !isExpired && (
            <Button
              size="sm"
              variant="ghost"
              onClick={onCheckSafety}
              isLoading={isCheckingSafety}
              icon={Shield}
              title="Check if this giveaway is safe"
            >
              Check
            </Button>
          )}

          {giveaway.is_safe === false && (
            <Button
              size="sm"
              variant="ghost"
              onClick={onHideOnSteamGifts}
              isLoading={isHidingOnSteamGifts}
              icon={HideIcon}
              title="Permanently hide this game on SteamGifts"
              className="text-red-500 hover:text-red-600"
            >
              Hide on SG
            </Button>
          )}

          {/* Comment button - show on entered giveaways */}
          {giveaway.is_entered && !isExpired && (
            <Button
              size="sm"
              variant="ghost"
              onClick={onComment}
              isLoading={isCommenting}
              icon={MessageSquare}
              title="Post 'Thanks!' comment"
            >
              Thanks
            </Button>
          )}

          <div className="flex gap-1 ml-auto">
            {giveaway.game_id && (
              <a
                href={`https://store.steampowered.com/app/${giveaway.game_id}`}
                target="_blank"
                rel="noopener noreferrer"
                title="View on Steam"
              >
                <Button size="sm" variant="ghost">
                  <SiSteam size={16} />
                </Button>
              </a>
            )}
            <a
              href={giveaway.url}
              target="_blank"
              rel="noopener noreferrer"
              title="View on SteamGifts"
            >
              <Button size="sm" variant="ghost" icon={ExternalLink}>
                View
              </Button>
            </a>
          </div>
        </div>
      </div>
    </Card>
  );
}

function formatTimeLeft(endTime: Date): string {
  const now = new Date();
  const diff = endTime.getTime() - now.getTime();

  if (diff <= 0) return 'Expired';

  const hours = Math.floor(diff / (1000 * 60 * 60));
  const days = Math.floor(hours / 24);

  if (days > 0) return `${days}d ${hours % 24}h`;
  if (hours > 0) return `${hours}h`;

  const minutes = Math.floor(diff / (1000 * 60));
  return `${minutes}m`;
}
