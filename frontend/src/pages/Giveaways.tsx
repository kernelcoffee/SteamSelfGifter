import { useState, useEffect, useRef } from 'react';
import { Link } from 'react-router';
import { ExternalLink, Eye, EyeOff, Gift, Clock, AlertCircle, Loader2, X, Heart, Trophy, Star, Shield, ShieldAlert, EyeOff as HideIcon, MessageSquare, Percent, Users, Package, Info, RotateCw, ScanEye, Check } from 'lucide-react';
import { SiSteam } from 'react-icons/si';
import { Card, Button, Badge, Input, CardSkeleton } from '@/components/common';
import { AutojoinDecisionLine } from '@/components/features/AutojoinDecisionLine';
import { useInfiniteGiveaways, useEnterGiveaway, useHideGiveaway, useUnhideGiveaway, useRemoveEntry, useCheckGiveawaySafety, useHideOnSteamGifts, usePostComment, useSettings, useAutojoinRegistry } from '@/hooks';
import { showSuccess, showError } from '@/stores/uiStore';
import { useGiveawayFiltersStore } from '@/stores/giveawayFiltersStore';
import type { AutojoinPriorityType, AutojoinPriorityTypeInfo, Giveaway } from '@/types';
import { ordinal } from '@/utils/numbers';

// Stepped slider stops. Chance: first notch = Any, then 0.01% up to 100%.
const CHANCE_STOPS = [0, 0.01, 0.1, 0.25, 0.5, 1, 2, 5, 10, 25, 50, 100];
// Time remaining (minutes): 5min up to 24h, last notch = Any.
const ENDING_STOPS = [5, 15, 30, 60, 120, 180, 360, 720, 1440, 0];

const formatChanceStop = (v: number) => (v === 0 ? 'Any' : `≥${v}%`);
const formatEndingStop = (v: number) =>
  v === 0 ? 'Any' : v < 60 ? `${v}min` : `${v / 60}h`;

// Map a stored filter value back to its slider notch (fallback: Any).
const stopIndex = (stops: number[], value: number | undefined, fallback: number) => {
  const idx = stops.indexOf(value ?? 0);
  return idx === -1 ? fallback : idx;
};

/** Id of the line that says why the view filters are disabled in lens mode. */
const VIEW_FILTERS_PAUSED_ID = 'view-filters-note';

export type GiveawayPageStatus = 'active' | 'wishlist' | 'dlc' | 'entered';

const PAGE_TITLES: Record<GiveawayPageStatus, string> = {
  active: 'Giveaways',
  wishlist: 'Wishlist',
  dlc: 'DLC',
  entered: 'Entered',
};

/** Tabs whose giveaways auto-join may still enter: lens and decision line. */
function isAutojoinTab(status: GiveawayPageStatus): boolean {
  return status === 'active' || status === 'wishlist' || status === 'dlc';
}

/** Priority type a tab lists, for the tab's standing line. */
const TAB_PRIORITY_TYPE: Partial<Record<GiveawayPageStatus, AutojoinPriorityType>> = {
  wishlist: 'wishlist',
  dlc: 'dlc',
};

/**
 * Where this tab's giveaways stand in the saved priority order: whether they
 * skip the filters (from the registry) and at which position (from the
 * saved list).
 */
function StandingLine({ type }: { type: AutojoinPriorityType }) {
  const settings = useSettings();
  const registry = useAutojoinRegistry();

  let text: string;
  if (registry.isError) {
    text = 'Could not load the auto-join registry';
  } else if (settings.isError) {
    text = 'Could not load your priority order';
  } else if (!registry.data || !settings.data) {
    text = 'Loading your priority order…';
  } else {
    const info = registry.data.priority_types.find((t) => t.type === type);
    const label = info?.label ?? type;
    const index = settings.data.autojoin_priorities.findIndex((item) => item.type === type);
    if (index === -1) {
      text = `${label} is not in your priority order: these giveaways obey the filters`;
    } else {
      const verb = info?.exempt_from_filters ? 'skip' : 'obey';
      text = `${label} giveaways ${verb} the filters and are entered ${ordinal(index + 1)}`;
    }
  }

  return (
    <p className="flex flex-wrap items-center gap-x-2 text-sm text-gray-600 dark:text-gray-300">
      <Info size={16} className="shrink-0" aria-hidden="true" />
      <span>{text}</span>
      <Link to="/settings" className="text-primary-light dark:text-primary-dark underline">
        Change in Settings
      </Link>
    </p>
  );
}

/**
 * Giveaways page
 * Browse, filter, and enter giveaways. The status (active/wishlist/entered)
 * comes from the route — each has its own sidebar entry; won giveaways live
 * on the dedicated Wins page.
 */
export function Giveaways({ status = 'active' }: { status?: GiveawayPageStatus }) {
  // The tab routes render this same component, so React Router keeps one
  // instance across tab switches; the key gives each tab visit its own page
  // state, so the auto-join lens starts off on every tab.
  return <GiveawaysTab key={status} status={status} />;
}

function GiveawaysTab({ status }: { status: GiveawayPageStatus }) {
  const title = PAGE_TITLES[status];
  // Filters persist across visits (localStorage-backed store)
  const filters = useGiveawayFiltersStore((s) => s.filters);
  const setFilters = useGiveawayFiltersStore((s) => s.setFilters);
  // The draft starts from the store's search so the box always shows the term
  // the list is filtered by, including after a tab switch remounts the page.
  const [searchInput, setSearchInput] = useState(() => filters.search ?? '');
  // The auto-join lens is page state: off on every tab visit, never persisted.
  const [lensOn, setLensOn] = useState(false);
  const autojoinTab = isAutojoinTab(status);
  const lens = autojoinTab && lensOn;
  const standingType = TAB_PRIORITY_TYPE[status];
  const settings = useSettings();
  const registry = useAutojoinRegistry();
  const priorityTypes: AutojoinPriorityTypeInfo[] | undefined = registry.data?.priority_types;

  const {
    data,
    isLoading,
    error,
    refetch,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage
  } = useInfiniteGiveaways({ ...filters, status, lens: lens ? 'autojoin' : undefined });
  const enterGiveaway = useEnterGiveaway();
  const hideGiveaway = useHideGiveaway();
  const unhideGiveaway = useUnhideGiveaway();
  const removeEntry = useRemoveEntry();
  const checkSafety = useCheckGiveawaySafety();
  const hideOnSteamGifts = useHideOnSteamGifts();
  const postComment = usePostComment();

  // Flatten all pages into a single array
  const allGiveaways = data?.pages.flatMap(page => page.giveaways) ?? [];
  // With the lens, count is the total number of candidates on the tab.
  const lensCount = data?.pages[0]?.count ?? 0;

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
    setFilters({ search: searchInput });
  };

  const handleScoreFilter = (score: number) => {
    setFilters({ minScore: score });
  };

  const handleChanceFilter = (minChance: number) => {
    setFilters({ minChance });
  };

  const handleEndingWithinFilter = (endingWithin: number) => {
    setFilters({ endingWithin });
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
    setFilters({ safetyFilter });
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div className="space-y-1">
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">{title}</h1>
          {standingType && <StandingLine type={standingType} />}
        </div>

        {/* Search */}
        <form onSubmit={handleSearch} className="flex gap-2">
          <Input
            placeholder="Search games..."
            aria-label="Search games"
            value={searchInput}
            disabled={lens}
            aria-describedby={lens ? VIEW_FILTERS_PAUSED_ID : undefined}
            onChange={(e) => setSearchInput(e.target.value)}
            className="w-full sm:w-64"
          />
          <Button type="submit" variant="secondary" disabled={lens}>Search</Button>
        </form>
      </div>

      {autojoinTab && settings.data && !settings.data.autojoin_enabled && (
        <p className="flex items-start gap-2 rounded-lg bg-yellow-50 dark:bg-yellow-900/20 p-3 text-sm text-yellow-800 dark:text-yellow-200">
          <Info size={16} className="mt-0.5 shrink-0" aria-hidden="true" />
          Auto-join is off: nothing is entered automatically.
        </p>
      )}

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-4">
        {autojoinTab && (
          // A pressed button with its explanation in the native tooltip,
          // like the page's other controls, so it takes one slot in the row.
          // The icon changes with the state so it shows without relying on
          // colour.
          <Button
            type="button"
            variant={lensOn ? 'primary' : 'secondary'}
            size="sm"
            icon={lensOn ? Check : ScanEye}
            aria-pressed={lensOn}
            title="Show only what your saved policy would enter next cycle, in entry order"
            onClick={() => setLensOn((on) => !on)}
          >
            Auto-join lens
          </Button>
        )}

        {/* Score Filter - only show for active status */}
        {status === 'active' && (
          <div className="flex items-center gap-3 px-3 py-1.5 bg-gray-100 dark:bg-gray-800 rounded-lg">
            <Star size={16} className="text-yellow-500" />
            <span className="text-sm text-gray-600 dark:text-gray-400 whitespace-nowrap">
              Show score ≥
            </span>
            <input
              type="range"
              aria-label="Show score at least"
              min="0"
              max="10"
              value={filters.minScore || 0}
              disabled={lens}
              aria-describedby={lens ? VIEW_FILTERS_PAUSED_ID : undefined}
              onChange={(e) => handleScoreFilter(Number(e.target.value))}
              className="w-24 h-2 bg-gray-300 dark:bg-gray-600 rounded-lg appearance-none cursor-pointer accent-primary-light disabled:cursor-not-allowed disabled:opacity-50"
            />
            <span className="text-sm font-medium text-gray-700 dark:text-gray-300 w-6 text-center">
              {filters.minScore || 0}
            </span>
            {!lens && (filters.minScore ?? 0) > 0 && (
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

        {/* Win Chance Filter (slider: Any, then 0.01% .. 100%) */}
        {(status === 'active' || status === 'wishlist' || status === 'dlc') && (
          <div className="flex items-center gap-3 px-3 py-1.5 bg-gray-100 dark:bg-gray-800 rounded-lg">
            <Percent size={16} className="text-blue-500" />
            <span className="text-sm text-gray-600 dark:text-gray-400 whitespace-nowrap">
              Min Chance:
            </span>
            <input
              type="range"
              min="0"
              max={CHANCE_STOPS.length - 1}
              step="1"
              aria-label="Minimum win chance"
              value={stopIndex(CHANCE_STOPS, filters.minChance, 0)}
              disabled={lens}
              aria-describedby={lens ? VIEW_FILTERS_PAUSED_ID : undefined}
              onChange={(e) => handleChanceFilter(CHANCE_STOPS[Number(e.target.value)])}
              className="w-24 h-2 bg-gray-300 dark:bg-gray-600 rounded-lg appearance-none cursor-pointer accent-primary-light disabled:cursor-not-allowed disabled:opacity-50"
            />
            <span className="text-sm font-medium text-gray-700 dark:text-gray-300 w-14 text-center">
              {formatChanceStop(filters.minChance ?? 0)}
            </span>
            {!lens && (filters.minChance ?? 0) > 0 && (
              <button
                onClick={() => handleChanceFilter(0)}
                className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-200"
                title="Clear filter"
              >
                <X size={14} />
              </button>
            )}
          </div>
        )}

        {/* Time Remaining Filter (slider: 5min .. 24h, last notch = Any) */}
        {(status === 'active' || status === 'wishlist' || status === 'dlc') && (
          <div className="flex items-center gap-3 px-3 py-1.5 bg-gray-100 dark:bg-gray-800 rounded-lg">
            <Clock size={16} className="text-orange-500" />
            <span className="text-sm text-gray-600 dark:text-gray-400 whitespace-nowrap">
              Ending in:
            </span>
            <input
              type="range"
              min="0"
              max={ENDING_STOPS.length - 1}
              step="1"
              aria-label="Ending within"
              value={stopIndex(ENDING_STOPS, filters.endingWithin, ENDING_STOPS.length - 1)}
              disabled={lens}
              aria-describedby={lens ? VIEW_FILTERS_PAUSED_ID : undefined}
              onChange={(e) => handleEndingWithinFilter(ENDING_STOPS[Number(e.target.value)])}
              className="w-24 h-2 bg-gray-300 dark:bg-gray-600 rounded-lg appearance-none cursor-pointer accent-primary-light disabled:cursor-not-allowed disabled:opacity-50"
            />
            <span className="text-sm font-medium text-gray-700 dark:text-gray-300 w-12 text-center">
              {formatEndingStop(filters.endingWithin ?? 0)}
            </span>
            {!lens && (filters.endingWithin ?? 0) > 0 && (
              <button
                onClick={() => handleEndingWithinFilter(0)}
                className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-200"
                title="Clear filter"
              >
                <X size={14} />
              </button>
            )}
          </div>
        )}

        {/* Safety Filter */}
        {status === 'active' && (
          <div className="flex items-center gap-2 px-3 py-1.5 bg-gray-100 dark:bg-gray-800 rounded-lg">
            <Shield size={16} className="text-green-500" />
            <span className="text-sm text-gray-600 dark:text-gray-400">Safety:</span>
            <select
              aria-label="Safety"
              value={filters.safetyFilter || 'all'}
              disabled={lens}
              aria-describedby={lens ? VIEW_FILTERS_PAUSED_ID : undefined}
              onChange={(e) => handleSafetyFilter(e.target.value as 'all' | 'safe' | 'unsafe')}
              className="text-sm bg-transparent border-none focus:ring-0 text-gray-700 dark:text-gray-300 cursor-pointer disabled:cursor-not-allowed disabled:opacity-50"
            >
              <option value="all">All</option>
              <option value="safe">Safe Only</option>
              <option value="unsafe">Unsafe Only</option>
            </select>
          </div>
        )}
      </div>

      {autojoinTab && (
        <p id={VIEW_FILTERS_PAUSED_ID} className="text-xs text-gray-500 dark:text-gray-400">
          {lens
            ? 'View filters are paused while the Auto-join lens is on: the list is your saved policy alone.'
            : 'View filters change only what you see; auto-join uses Settings.'}
        </p>
      )}

      {/* Results count */}
      {!error && allGiveaways.length > 0 && (
        <p className="text-sm text-gray-500 dark:text-gray-400">
          {lens
            ? `${lensCount} ${lensCount === 1 ? 'candidate' : 'candidates'} in entry order; the points budget and per cycle cap apply at cycle time`
            : `Showing ${allGiveaways.length} giveaway${allGiveaways.length !== 1 ? 's' : ''}`}
        </p>
      )}

      {/* Giveaways Grid */}
      {error ? (
        <Card>
          <div className="flex flex-wrap items-center gap-3 text-red-500">
            <AlertCircle size={24} className="shrink-0" />
            <span>
              {lens
                ? `Could not load the auto-join lens: ${error.message}`
                : 'Failed to load giveaways. Is the backend running?'}
            </span>
            {lens && (
              <Button
                variant="ghost"
                size="sm"
                icon={RotateCw}
                onClick={() => {
                  void refetch();
                }}
              >
                Retry
              </Button>
            )}
          </div>
        </Card>
      ) : isLoading ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4">
          {[...Array(10)].map((_, i) => (
            <CardSkeleton key={i} />
          ))}
        </div>
      ) : allGiveaways.length === 0 ? (
        <Card>
          <div className="text-center py-8 text-gray-500 dark:text-gray-400">
            {lens ? (
              <>
                Nothing on this tab passes your saved auto-join policy. The budget and cap apply at
                cycle time.{' '}
                <Link to="/settings" className="text-primary-light dark:text-primary-dark underline">
                  Adjust it in Settings
                </Link>
              </>
            ) : (
              'No giveaways found matching your criteria.'
            )}
          </div>
        </Card>
      ) : (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4">
            {allGiveaways.map((giveaway) => (
              <GiveawayCard
                key={giveaway.id}
                giveaway={giveaway}
                lens={lens}
                showAutojoin={autojoinTab}
                priorityTypes={priorityTypes}
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

interface GiveawayCardProps {
  giveaway: Giveaway;
  /** Lens mode: the card shows its live decision. */
  lens: boolean;
  /** Whether this tab shows the Auto-join line at all. */
  showAutojoin: boolean;
  priorityTypes?: AutojoinPriorityTypeInfo[];
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

const GENRES_SHOWN_ON_CARD = 3;

function GenreLine({ genres }: { genres: string[] }) {
  const shown = genres.slice(0, GENRES_SHOWN_ON_CARD).join(', ');
  const rest = genres.length - GENRES_SHOWN_ON_CARD;
  // The names truncate on their own, so the "+N" counter is never the part
  // cut off on a narrow card.
  return (
    <p
      className="flex min-w-0 text-xs text-gray-500 dark:text-gray-400"
      title={genres.join(', ')}
    >
      <span className="truncate">{shown}</span>
      {rest > 0 && <span className="shrink-0 whitespace-pre">{` +${rest}`}</span>}
    </p>
  );
}

function GiveawayCard({ giveaway, lens, showAutojoin, priorityTypes, onEnter, onHide, onUnhide, onRemoveEntry, onCheckSafety, onHideOnSteamGifts, onComment, isEntering, isRemovingEntry, isCheckingSafety, isHidingOnSteamGifts, isCommenting }: GiveawayCardProps) {
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
          <div className="min-w-0">
            <h3 className="font-semibold text-gray-900 dark:text-white line-clamp-2">
              {giveaway.game_name}
            </h3>
            {giveaway.game_genres && giveaway.game_genres.length > 0 && (
              <GenreLine genres={giveaway.game_genres} />
            )}
          </div>
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
            {giveaway.is_dlc && (
              <Badge variant="default" size="sm" className="bg-purple-100 text-purple-600 dark:bg-purple-900/30 dark:text-purple-400">
                <Package size={10} className="mr-1" />
                DLC
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
          {!isExpired && (
            <span
              className="flex items-center gap-1"
              title={
                giveaway.entries > 0
                  ? `${giveaway.entries} entries for ${giveaway.copies} ${giveaway.copies > 1 ? 'copies' : 'copy'} (as of last scan)`
                  : 'No entries recorded yet'
              }
            >
              <Percent size={14} />
              {giveaway.win_chance}%
            </span>
          )}
        </div>

        {/* Auto-join decision */}
        {showAutojoin && !giveaway.is_entered && !isExpired && (
          <AutojoinDecisionLine giveaway={giveaway} lens={lens} priorityTypes={priorityTypes} />
        )}

        {/* Entries */}
        {!isExpired && (
          <div className="flex items-center gap-1.5 text-sm text-gray-500 dark:text-gray-400">
            <Users size={14} />
            {giveaway.entries > 0 ? (
              <span>
                {giveaway.entries.toLocaleString()} {giveaway.entries === 1 ? 'entry' : 'entries'}
                {giveaway.copies > 1 && ` · ${giveaway.copies} copies`}
              </span>
            ) : (
              <span>No entries recorded yet</span>
            )}
          </div>
        )}

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
            ) : (giveaway.safety_score ?? 0) >= 50 ? (
              <Badge variant="warning" size="sm">
                <ShieldAlert size={10} className="mr-1" />
                Borderline
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
