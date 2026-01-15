import { ReactNode } from 'react';
import { clsx } from 'clsx';

interface CardProps {
  title?: string;
  children: ReactNode;
  className?: string;
  padding?: 'none' | 'sm' | 'md' | 'lg';
  actions?: ReactNode;
}

const paddingStyles = {
  none: '',
  sm: 'p-3',
  md: 'p-4',
  lg: 'p-6',
};

/**
 * Card component for grouping content
 *
 * @example
 * <Card title="Settings">
 *   <p>Content here</p>
 * </Card>
 *
 * <Card title="Actions" actions={<Button>Save</Button>}>
 *   <p>Content with action button</p>
 * </Card>
 */
export function Card({
  title,
  children,
  className,
  padding = 'md',
  actions,
}: CardProps) {
  return (
    <div
      className={clsx(
        'bg-white dark:bg-surface-dark rounded-lg border border-gray-200 dark:border-gray-700 shadow-sm',
        className
      )}
    >
      {/* Header with title and actions */}
      {(title || actions) && (
        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200 dark:border-gray-700">
          {title && (
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
              {title}
            </h3>
          )}
          {actions && <div className="flex items-center gap-2">{actions}</div>}
        </div>
      )}

      {/* Content */}
      <div className={paddingStyles[padding]}>{children}</div>
    </div>
  );
}
