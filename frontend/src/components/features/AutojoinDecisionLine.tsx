import { Ban, CircleCheck, CircleHelp, Funnel, Wallet, type LucideIcon } from 'lucide-react';
import { formatDistanceToNowStrict } from 'date-fns';
import type { AutojoinKind, AutojoinPriorityTypeInfo, Giveaway } from '@/types';
import { autojoinLineFor, enterTooltip } from '@/utils/autojoinPriorities';

const ICONS: Record<AutojoinKind, { icon: LucideIcon; className: string }> = {
  enter: { icon: CircleCheck, className: 'text-green-600 dark:text-green-400' },
  gate: { icon: Ban, className: 'text-gray-500 dark:text-gray-400' },
  filter: { icon: Funnel, className: 'text-amber-600 dark:text-amber-400' },
  budget: { icon: Wallet, className: 'text-blue-600 dark:text-blue-400' },
};

const UNKNOWN = { icon: CircleHelp, className: 'text-gray-500 dark:text-gray-400' };

interface AutojoinDecisionLineProps {
  giveaway: Giveaway;
  /** Lens mode: show the live decision instead of the last recorded one. */
  lens: boolean;
  /** Registry priority types, used to name the lift in the enter tooltip. */
  priorityTypes?: AutojoinPriorityTypeInfo[];
}

/**
 * "Auto-join:" line of a giveaway card. The icon comes from the decision's
 * kind and the text is always the server's label, so colour is never the
 * only signal. An enter outcome shows the one-word term with the lift and
 * position in its tooltip and accessible text.
 */
export function AutojoinDecisionLine({ giveaway, lens, priorityTypes }: AutojoinDecisionLineProps) {
  const line = autojoinLineFor(giveaway, lens);
  const { icon: Icon, className } = line.kind ? ICONS[line.kind] : UNKNOWN;
  const tooltip = line.kind === 'enter' ? enterTooltip(line.text, line.detail, priorityTypes) : null;
  const checkedAt = line.checkedAt ? new Date(line.checkedAt) : null;
  const checkedValid = checkedAt !== null && !Number.isNaN(checkedAt.getTime());

  return (
    <div className="space-y-0.5">
      <p className="flex min-w-0 items-start gap-1.5 text-sm text-gray-700 dark:text-gray-300">
        <Icon size={16} className={`mt-0.5 shrink-0 ${className}`} aria-hidden="true" />
        <span className="shrink-0 font-semibold">Auto-join:</span>
        {tooltip ? (
          <span className="min-w-0" title={tooltip}>
            {line.text}
            <span className="sr-only">{tooltip.slice(line.text.length)}</span>
          </span>
        ) : (
          <span className="min-w-0">{line.text}</span>
        )}
      </p>
      {checkedValid && (
        <p className="pl-6 text-xs text-gray-500 dark:text-gray-400" title={checkedAt.toUTCString()}>
          Checked {formatDistanceToNowStrict(checkedAt, { addSuffix: true })}
        </p>
      )}
    </div>
  );
}
