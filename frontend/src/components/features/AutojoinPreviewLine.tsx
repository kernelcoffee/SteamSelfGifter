import { CircleAlert, RotateCw, TriangleAlert } from 'lucide-react';
import { clsx } from 'clsx';
import { Button, Spinner } from '@/components/common';
import type { PolicyPreviewResponse } from '@/types';

export type PreviewStatus = 'paused' | 'loading' | 'error' | 'ready';

interface AutojoinPreviewLineProps {
  status: PreviewStatus;
  /** Why the form cannot be previewed (the Save-blocked reason). */
  pausedReason?: string;
  /** Backend message of a failed preview. */
  error?: string;
  onRetry?: () => void;
  data?: PolicyPreviewResponse;
  /** Candidates under the saved policy, shown while the form differs from it. */
  savedCount?: number;
  /** code -> registry label for the breakdown. */
  labels: Record<string, string>;
  /** Previous result shown while a newer one loads. */
  isStale: boolean;
  /** Announce updates to screen readers (one line per page should). */
  live?: boolean;
}

function plural(n: number, one: string, many: string): string {
  return n === 1 ? one : many;
}

/**
 * One line summarising what the edited policy would enter next cycle, from
 * the server's dry run (POST /giveaways/preview). Presentational only.
 */
export function AutojoinPreviewLine({
  status,
  pausedReason,
  error,
  onRetry,
  data,
  savedCount,
  labels,
  isStale,
  live = false,
}: AutojoinPreviewLineProps) {
  const body = (() => {
    if (status === 'paused') {
      return (
        <p className="text-sm text-gray-600 dark:text-gray-300">
          Preview paused: {pausedReason ?? 'fix the highlighted fields to update it'}
        </p>
      );
    }
    if (status === 'error') {
      return (
        <div className="flex flex-wrap items-center gap-2 text-sm text-red-600 dark:text-red-400">
          <CircleAlert size={16} className="shrink-0" aria-hidden="true" />
          <span>Preview unavailable: {error ?? 'unknown error'}. Your changes can still be saved.</span>
          {onRetry && (
            <Button type="button" variant="ghost" size="sm" icon={RotateCw} onClick={onRetry}>
              Retry
            </Button>
          )}
        </div>
      );
    }
    if (!data) {
      return (
        <p className="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-300">
          <Spinner size="sm" />
          Computing the preview…
        </p>
      );
    }
    const breakdown = Object.entries(data.counts)
      .filter(([, n]) => n > 0)
      .sort((a, b) => b[1] - a[1]);
    return (
      <div className={clsx('space-y-1', isStale && 'opacity-60')}>
        <p className="flex flex-wrap items-center gap-x-2 text-sm font-medium text-gray-900 dark:text-white">
          <span>
            {data.count} of {data.pool} active {plural(data.pool, 'giveaway', 'giveaways')} would be
            entered next cycle
            {savedCount !== undefined && savedCount !== data.count && ` (saved: ${savedCount})`}
          </span>
          {isStale && (
            <span className="inline-flex items-center gap-1 font-normal text-gray-500 dark:text-gray-400">
              <Spinner size="sm" />
              Updating…
            </span>
          )}
        </p>
        {data.count === 0 && (
          <p className="flex items-center gap-2 text-sm text-yellow-700 dark:text-yellow-400">
            <TriangleAlert size={16} className="shrink-0" aria-hidden="true" />
            Auto-join would enter nothing next cycle.
          </p>
        )}
        {breakdown.length > 0 && (
          <ul aria-label="Decisions by reason" className="flex flex-wrap gap-x-4 gap-y-1 text-sm text-gray-600 dark:text-gray-300">
            {breakdown.map(([code, n]) => (
              <li key={code}>
                {labels[code] ?? code}: {n}
              </li>
            ))}
          </ul>
        )}
      </div>
    );
  })();

  return (
    <div
      className="space-y-1 rounded-lg border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800/50 p-3"
      aria-live={live ? 'polite' : undefined}
    >
      {body}
      <p className="text-xs text-gray-500 dark:text-gray-400">
        Preview only: nothing is entered. The points budget and the per cycle cap apply at cycle time.
      </p>
    </div>
  );
}
