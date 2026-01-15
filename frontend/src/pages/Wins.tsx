import { useState, useEffect, useRef } from 'react';
import { ExternalLink, Trophy, Clock, Gift, AlertCircle, Loader2, RefreshCw } from 'lucide-react';
import { SiSteam } from 'react-icons/si';
import { Card, Button, Badge, CardSkeleton } from '@/components/common';
import { useInfiniteGiveaways, type GiveawayFilters } from '@/hooks';
import { useSyncWins } from '@/hooks/useScheduler';
import { showSuccess, showError } from '@/stores/uiStore';
import type { Giveaway } from '@/types';

/**
 * Wins page
 * Display won giveaways and sync wins from SteamGifts
 */
export function Wins() {
  const [filters] = useState<Omit<GiveawayFilters, 'page'>>({
    status: 'won',
    limit: 20,
  });

  const {
    data,
    isLoading,
    error,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
    refetch
  } = useInfiniteGiveaways(filters);

  const syncWins = useSyncWins();

  // Flatten all pages into a single array
  const allWins = data?.pages.flatMap(page => page.giveaways) ?? [];
  const totalWins = allWins.length;

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
      { threshold: 0.1 }
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

  const handleSyncWins = async () => {
    try {
      const result = await syncWins.mutateAsync();
      if (result.new_wins > 0) {
        showSuccess(`Found ${result.new_wins} new win(s)!`);
      } else {
        showSuccess('Win sync complete. No new wins found.');
      }
      refetch();
    } catch (err) {
      showError(err instanceof Error ? err.message : 'Failed to sync wins');
    }
  };

  if (error) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Wins</h1>
        <Card>
          <div className="flex items-center gap-3 text-red-500">
            <AlertCircle size={24} />
            <span>Failed to load wins. Is the backend running?</span>
          </div>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div className="flex items-center gap-3">
          <Trophy className="text-yellow-500" size={28} />
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Wins</h1>
          {totalWins > 0 && (
            <Badge variant="success" size="md">
              {totalWins} total
            </Badge>
          )}
        </div>

        <Button
          onClick={handleSyncWins}
          isLoading={syncWins.isPending}
          icon={RefreshCw}
          variant="secondary"
        >
          Sync Wins
        </Button>
      </div>

      {/* Summary Card */}
      <Card className="bg-gradient-to-r from-yellow-50 to-amber-50 dark:from-yellow-900/20 dark:to-amber-900/20 border-yellow-200 dark:border-yellow-800">
        <div className="flex items-center gap-4">
          <div className="p-3 bg-yellow-100 dark:bg-yellow-900/50 rounded-full">
            <Trophy className="text-yellow-600 dark:text-yellow-400" size={24} />
          </div>
          <div>
            <h3 className="font-semibold text-gray-900 dark:text-white">
              {totalWins > 0 ? `Congratulations! You've won ${totalWins} giveaway${totalWins !== 1 ? 's' : ''}!` : 'No wins yet'}
            </h3>
            <p className="text-sm text-gray-600 dark:text-gray-400">
              {totalWins > 0
                ? 'Click "Sync Wins" to check for new wins from SteamGifts.'
                : 'Keep entering giveaways and check back later. Good luck!'}
            </p>
          </div>
        </div>
      </Card>

      {/* Wins Grid */}
      {isLoading ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4">
          {[...Array(10)].map((_, i) => (
            <CardSkeleton key={i} />
          ))}
        </div>
      ) : allWins.length === 0 ? (
        <Card>
          <div className="text-center py-12 text-gray-500 dark:text-gray-400">
            <Trophy className="mx-auto mb-4 text-gray-300 dark:text-gray-600" size={48} />
            <p className="text-lg font-medium">No wins yet</p>
            <p className="text-sm mt-2">Keep entering giveaways and your wins will appear here.</p>
          </div>
        </Card>
      ) : (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4">
            {allWins.map((giveaway) => (
              <WinCard key={giveaway.id} giveaway={giveaway} />
            ))}
          </div>

          {/* Infinite Scroll Trigger */}
          {hasNextPage && (
            <div ref={loadMoreRef} className="flex justify-center mt-6 py-4">
              {isFetchingNextPage && (
                <div className="flex items-center gap-2 text-gray-500 dark:text-gray-400">
                  <Loader2 className="animate-spin" size={20} />
                  <span>Loading more wins...</span>
                </div>
              )}
            </div>
          )}

          {!hasNextPage && allWins.length > 0 && (
            <div className="flex justify-center mt-6 py-4">
              <p className="text-sm text-gray-500 dark:text-gray-400">
                All wins loaded
              </p>
            </div>
          )}
        </>
      )}
    </div>
  );
}

interface WinCardProps {
  giveaway: Giveaway;
}

function WinCard({ giveaway }: WinCardProps) {
  const wonDate = giveaway.won_at ? new Date(giveaway.won_at) : null;

  return (
    <Card className="border-yellow-200 dark:border-yellow-800/50 bg-gradient-to-b from-yellow-50/50 to-transparent dark:from-yellow-900/10">
      <div className="space-y-3">
        {/* Game Thumbnail */}
        {giveaway.game_thumbnail && (
          <div className="w-full h-32 overflow-hidden rounded-lg bg-gray-100 dark:bg-gray-800 -mx-4 -mt-4 mb-1 relative">
            <img
              src={giveaway.game_thumbnail}
              alt={giveaway.game_name}
              className="w-full h-full object-cover"
              onError={(e) => {
                const parent = e.currentTarget.parentElement;
                if (parent) parent.style.display = 'none';
              }}
            />
            <div className="absolute top-2 right-2">
              <Badge variant="success" size="sm" className="bg-yellow-500 text-white">
                <Trophy size={12} className="mr-1" />
                Won!
              </Badge>
            </div>
          </div>
        )}

        {/* Header */}
        <div className="flex items-start justify-between gap-2">
          <h3 className="font-semibold text-gray-900 dark:text-white line-clamp-2">
            {giveaway.game_name}
          </h3>
          {!giveaway.game_thumbnail && (
            <Badge variant="success" size="sm" className="bg-yellow-500 text-white shrink-0">
              <Trophy size={12} className="mr-1" />
              Won!
            </Badge>
          )}
        </div>

        {/* Win Info */}
        <div className="flex flex-wrap gap-2 text-sm text-gray-500 dark:text-gray-400">
          <span className="flex items-center gap-1">
            <Gift size={14} />
            {giveaway.price}P
          </span>
          {wonDate && (
            <span className="flex items-center gap-1">
              <Clock size={14} />
              Won {formatWonDate(wonDate)}
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
          </div>
        )}

        {/* Actions */}
        <div className="flex gap-2 pt-2 border-t border-gray-100 dark:border-gray-800">
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

function formatWonDate(date: Date): string {
  const now = new Date();
  const diff = now.getTime() - date.getTime();
  const days = Math.floor(diff / (1000 * 60 * 60 * 24));

  if (days === 0) return 'today';
  if (days === 1) return 'yesterday';
  if (days < 7) return `${days} days ago`;
  if (days < 30) return `${Math.floor(days / 7)} week${Math.floor(days / 7) !== 1 ? 's' : ''} ago`;

  return date.toLocaleDateString();
}
