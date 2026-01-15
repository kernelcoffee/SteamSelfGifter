import { Loader2 } from 'lucide-react';
import { clsx } from 'clsx';

type LoadingSize = 'sm' | 'md' | 'lg';

interface SpinnerProps {
  size?: LoadingSize;
  className?: string;
}

interface LoadingProps extends SpinnerProps {
  text?: string;
  fullScreen?: boolean;
}

const sizeStyles: Record<LoadingSize, number> = {
  sm: 16,
  md: 24,
  lg: 40,
};

const textSizes: Record<LoadingSize, string> = {
  sm: 'text-xs',
  md: 'text-sm',
  lg: 'text-base',
};

/**
 * Spinner component for inline loading states
 *
 * @example
 * <Spinner size="sm" />
 */
export function Spinner({ size = 'md', className }: SpinnerProps) {
  return (
    <Loader2
      size={sizeStyles[size]}
      className={clsx('animate-spin text-primary-light dark:text-primary-dark', className)}
    />
  );
}

/**
 * Loading component with optional text and full screen mode
 *
 * @example
 * <Loading text="Loading data..." />
 * <Loading fullScreen />
 */
export function Loading({ size = 'md', text, fullScreen = false, className }: LoadingProps) {
  const content = (
    <div
      className={clsx(
        'flex flex-col items-center justify-center gap-2',
        className
      )}
    >
      <Spinner size={size} />
      {text && (
        <p className={clsx('text-gray-500 dark:text-gray-400', textSizes[size])}>
          {text}
        </p>
      )}
    </div>
  );

  if (fullScreen) {
    return (
      <div className="fixed inset-0 flex items-center justify-center bg-background-light dark:bg-background-dark">
        {content}
      </div>
    );
  }

  return content;
}

/**
 * Skeleton component for content placeholders
 *
 * @example
 * <Skeleton className="h-4 w-32" />
 * <Skeleton className="h-10 w-full" />
 */
export function Skeleton({ className }: { className?: string }) {
  return (
    <div
      className={clsx(
        'animate-pulse rounded bg-gray-200 dark:bg-gray-700',
        className
      )}
    />
  );
}

/**
 * Card skeleton for loading card content
 */
export function CardSkeleton() {
  return (
    <div className="bg-white dark:bg-surface-dark rounded-lg border border-gray-200 dark:border-gray-700 p-4 space-y-3">
      <Skeleton className="h-4 w-1/3" />
      <Skeleton className="h-4 w-full" />
      <Skeleton className="h-4 w-2/3" />
    </div>
  );
}
