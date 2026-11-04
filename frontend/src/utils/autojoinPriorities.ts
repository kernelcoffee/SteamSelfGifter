import type {
  AutojoinKind,
  AutojoinPriorityItem,
  AutojoinPriorityType,
  AutojoinPriorityTypeInfo,
  AutojoinRegistry,
  EligibilityDetail,
  Giveaway,
  RegistryParam,
} from '@/types';
import { ordinal } from './numbers';

/*
 * Helpers around the auto-join priority list and decisions. Labels, exemption
 * flags and bounds always come from the registry the backend serves
 * (GET /giveaways/registry); nothing here evaluates a rule.
 */

/** Name of the only parameter a priority type carries today. */
export const THRESHOLD_PARAM = 'threshold_minutes';

/** Bounds and default of the ending-soon threshold, from the registry. */
export function thresholdParam(types: AutojoinPriorityTypeInfo[]): RegistryParam | null {
  const info = types.find((t) => t.type === 'ending_soon');
  return info?.params.find((p) => p.name === THRESHOLD_PARAM) ?? null;
}

/** Move the item at `from` to position `to`; out-of-range indexes are a no-op. */
export function moveItem<T>(items: T[], from: number, to: number): T[] {
  if (from === to || from < 0 || to < 0 || from >= items.length || to >= items.length) {
    return items;
  }
  const next = [...items];
  const [moved] = next.splice(from, 1);
  next.splice(to, 0, moved);
  return next;
}

/** Registry types not in the list yet, in registry order. */
export function absentTypes(
  items: AutojoinPriorityItem[],
  types: AutojoinPriorityTypeInfo[],
): AutojoinPriorityTypeInfo[] {
  const present = new Set(items.map((item) => item.type));
  return types.filter((t) => !present.has(t.type));
}

/** A fresh list item; ending soon starts at the registry's default threshold. */
export function defaultItem(
  type: AutojoinPriorityType,
  thresholdDefault: number,
): AutojoinPriorityItem {
  switch (type) {
    case 'wishlist':
      return { type: 'wishlist' };
    case 'dlc':
      return { type: 'dlc' };
    case 'ending_soon':
      return { type: 'ending_soon', threshold_minutes: thresholdDefault };
  }
}

/**
 * The list as Save sends it: the displayed order, with the ending-soon item
 * carrying the parsed threshold draft.
 */
export function withThreshold(
  items: AutojoinPriorityItem[],
  threshold: number,
): AutojoinPriorityItem[] {
  return items.map((item) =>
    item.type === 'ending_soon' ? { type: 'ending_soon', threshold_minutes: threshold } : item,
  );
}

/** Registry label of a priority type, or the raw type when the registry lacks it. */
export function priorityLabel(
  type: string,
  types: AutojoinPriorityTypeInfo[] | undefined,
): string {
  return types?.find((t) => t.type === type)?.label ?? type;
}

/** code -> label over the registry's gates, filters and outcomes. */
export function registryLabels(registry: AutojoinRegistry): Record<string, string> {
  return Object.fromEntries(
    [...registry.gates, ...registry.filters, ...registry.outcomes].map((rule) => [
      rule.code,
      rule.label,
    ]),
  );
}

export const NOT_EVALUATED = 'Not evaluated yet; checked at the next cycle';

export interface AutojoinLine {
  text: string;
  kind: AutojoinKind | null;
  detail: EligibilityDetail | null;
  /** When the stored decision was recorded; null for live (lens) decisions. */
  checkedAt: string | null;
}

/**
 * What the card's Auto-join line shows. Lens mode shows the live decision
 * from the saved policy (always an enter outcome); otherwise the decision the
 * last cycle recorded. The text is the server's label, never re-worded.
 */
export function autojoinLineFor(giveaway: Giveaway, lens: boolean): AutojoinLine {
  if (lens) {
    const decision = giveaway.decision;
    if (!decision) return { text: NOT_EVALUATED, kind: null, detail: null, checkedAt: null };
    return {
      text: decision.label,
      kind: 'enter',
      detail: { ...decision.detail },
      checkedAt: null,
    };
  }
  if (giveaway.eligibility_label === null) {
    return { text: NOT_EVALUATED, kind: null, detail: null, checkedAt: null };
  }
  return {
    text: giveaway.eligibility_label,
    kind: giveaway.eligibility_kind,
    detail: giveaway.eligibility_detail,
    checkedAt: giveaway.eligibility_checked_at,
  };
}

function stringOrNull(value: EligibilityDetail[string] | undefined): string | null {
  return typeof value === 'string' ? value : null;
}

/**
 * Tooltip of an enter outcome: the server's one-word term followed by the
 * lift and position read from the decision detail, for example
 * "Joinable: Wishlist, filters skipped, 1st in your order".
 */
export function enterTooltip(
  term: string,
  detail: EligibilityDetail | null,
  types: AutojoinPriorityTypeInfo[] | undefined,
): string {
  if (!detail) return term;
  const priority = stringOrNull(detail.priority);
  const liftedBy = stringOrNull(detail.lifted_by);
  const rank = typeof detail.rank === 'number' ? detail.rank : null;
  if (priority === null) {
    return liftedBy === null
      ? `${term}: passes your filters, after the priority list`
      : `${term}: filters skipped (${priorityLabel(liftedBy, types)}), after the priority list`;
  }
  const position = rank === null ? 'in your order' : `${ordinal(rank + 1)} in your order`;
  const name = priorityLabel(priority, types);
  if (liftedBy === null) return `${term}: ${name}, ${position}`;
  if (liftedBy === priority) return `${term}: ${name}, filters skipped, ${position}`;
  return `${term}: ${name}, ${position}; filters skipped (${priorityLabel(liftedBy, types)})`;
}
