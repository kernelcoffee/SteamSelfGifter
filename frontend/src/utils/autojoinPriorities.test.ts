import { describe, it, expect } from 'vitest';
import type { AutojoinPriorityItem } from '@/types';
import { makeGiveaway, testRegistry } from '@/test/fixtures';
import * as priorities from './autojoinPriorities';
import {
  NOT_EVALUATED,
  absentTypes,
  autojoinLineFor,
  defaultItem,
  enterTooltip,
  moveItem,
  priorityLabel,
  registryLabels,
  thresholdParam,
  withThreshold,
} from './autojoinPriorities';

const types = testRegistry.priority_types;

describe('autojoinPriorities: no mirrored metadata', () => {
  it('exports no type metadata or bound constants (they come from the registry)', () => {
    const names = Object.keys(priorities);
    for (const banned of [
      'PRIORITY_TYPE_META',
      'THRESHOLD_MIN',
      'THRESHOLD_MAX',
      'THRESHOLD_DEFAULT',
    ]) {
      expect(names).not.toContain(banned);
    }
  });
});

describe('thresholdParam', () => {
  it('reads the ending-soon threshold bounds from the registry', () => {
    expect(thresholdParam(types)).toEqual({
      name: 'threshold_minutes',
      min: 5,
      max: 10080,
      default: 60,
    });
  });

  it('is null when the registry has no such parameter', () => {
    expect(thresholdParam(types.filter((t) => t.type !== 'ending_soon'))).toBeNull();
  });
});

describe('moveItem', () => {
  const list = ['a', 'b', 'c'];

  it('moves an item down and up', () => {
    expect(moveItem(list, 0, 2)).toEqual(['b', 'c', 'a']);
    expect(moveItem(list, 2, 0)).toEqual(['c', 'a', 'b']);
    expect(moveItem(list, 1, 0)).toEqual(['b', 'a', 'c']);
  });

  it('does not mutate the input', () => {
    const copy = [...list];
    moveItem(list, 0, 1);
    expect(list).toEqual(copy);
  });

  it('returns the same list for a no-op or an out-of-range index', () => {
    expect(moveItem(list, 1, 1)).toBe(list);
    expect(moveItem(list, -1, 0)).toBe(list);
    expect(moveItem(list, 0, 3)).toBe(list);
  });
});

describe('absentTypes', () => {
  it('lists registry types not in the list, in registry order', () => {
    expect(absentTypes([{ type: 'dlc' }], types).map((t) => t.type)).toEqual([
      'wishlist',
      'ending_soon',
    ]);
  });

  it('is empty when every type is present', () => {
    const all: AutojoinPriorityItem[] = [
      { type: 'ending_soon', threshold_minutes: 60 },
      { type: 'wishlist' },
      { type: 'dlc' },
    ];
    expect(absentTypes(all, types)).toEqual([]);
  });
});

describe('defaultItem', () => {
  it('builds plain items and an ending-soon item with the given default', () => {
    expect(defaultItem('wishlist', 60)).toEqual({ type: 'wishlist' });
    expect(defaultItem('dlc', 60)).toEqual({ type: 'dlc' });
    expect(defaultItem('ending_soon', 90)).toEqual({ type: 'ending_soon', threshold_minutes: 90 });
  });
});

describe('withThreshold', () => {
  it('replaces the ending-soon threshold and keeps the order', () => {
    const items: AutojoinPriorityItem[] = [
      { type: 'dlc' },
      { type: 'ending_soon', threshold_minutes: 60 },
      { type: 'wishlist' },
    ];
    expect(withThreshold(items, 120)).toEqual([
      { type: 'dlc' },
      { type: 'ending_soon', threshold_minutes: 120 },
      { type: 'wishlist' },
    ]);
  });
});

describe('priorityLabel and registryLabels', () => {
  it('names a type from the registry, or falls back to the raw type', () => {
    expect(priorityLabel('ending_soon', types)).toBe('Ending soon');
    expect(priorityLabel('dlc', undefined)).toBe('dlc');
    expect(priorityLabel('bogus', types)).toBe('bogus');
  });

  it('maps every gate, filter and outcome code to its label', () => {
    const labels = registryLabels(testRegistry);
    expect(labels.hidden).toBe('Hidden');
    expect(labels.genre_not_included).toBe('No genre on your included list');
    expect(labels.cycle_cap).toBe('Not entered last cycle: per cycle cap');
    expect(Object.keys(labels)).toHaveLength(15);
  });
});

describe('autojoinLineFor', () => {
  it('falls back to "Not evaluated yet" with no kind when nothing is recorded', () => {
    expect(autojoinLineFor(makeGiveaway(), false)).toEqual({
      text: NOT_EVALUATED,
      kind: null,
      detail: null,
      checkedAt: null,
    });
    expect(NOT_EVALUATED).toMatch(/^Not evaluated yet/);
  });

  it('shows the stored label, kind, detail and check time outside the lens', () => {
    const giveaway = makeGiveaway({
      eligibility_reason: 'score_below_min',
      eligibility_detail: { score: 6, min_score: 7 },
      eligibility_label: 'Review score 6 is below your minimum 7',
      eligibility_kind: 'filter',
      eligibility_checked_at: '2026-11-04T10:00:00Z',
    });
    expect(autojoinLineFor(giveaway, false)).toEqual({
      text: 'Review score 6 is below your minimum 7',
      kind: 'filter',
      detail: { score: 6, min_score: 7 },
      checkedAt: '2026-11-04T10:00:00Z',
    });
  });

  it('shows the live decision in lens mode, ignoring the stored one', () => {
    const giveaway = makeGiveaway({
      eligibility_label: 'Review score 6 is below your minimum 7',
      eligibility_kind: 'filter',
      decision: {
        code: 'eligible',
        label: 'Joinable',
        detail: { priority: 'wishlist', rank: 0, lifted_by: 'wishlist' },
        priority: 'wishlist',
        rank: 0,
        lifted_by: 'wishlist',
      },
    });
    expect(autojoinLineFor(giveaway, true)).toEqual({
      text: 'Joinable',
      kind: 'enter',
      detail: { priority: 'wishlist', rank: 0, lifted_by: 'wishlist' },
      checkedAt: null,
    });
  });

  it('falls back in lens mode when an item carries no decision', () => {
    expect(autojoinLineFor(makeGiveaway({ eligibility_label: 'Hidden' }), true).text).toBe(
      NOT_EVALUATED,
    );
  });
});

describe('enterTooltip', () => {
  it('names the lift and the position', () => {
    expect(enterTooltip('Joinable', { priority: 'wishlist', rank: 0, lifted_by: 'wishlist' }, types)).toBe(
      'Joinable: Wishlist, filters skipped, 1st in your order',
    );
  });

  it('names a priority that obeys the filters without a lift', () => {
    expect(enterTooltip('Joinable', { priority: 'ending_soon', rank: 1, lifted_by: null }, types)).toBe(
      'Joinable: Ending soon, 2nd in your order',
    );
  });

  it('names a lift by another type than the matched priority', () => {
    expect(
      enterTooltip('Joinable', { priority: 'ending_soon', rank: 0, lifted_by: 'wishlist' }, types),
    ).toBe('Joinable: Ending soon, 1st in your order; filters skipped (Wishlist)');
  });

  it('describes an unmatched candidate', () => {
    expect(enterTooltip('Joinable', { priority: null, rank: 3, lifted_by: null }, types)).toBe(
      'Joinable: passes your filters, after the priority list',
    );
    expect(enterTooltip('Joinable', { priority: null, rank: 3, lifted_by: 'dlc' }, types)).toBe(
      'Joinable: filters skipped (DLC), after the priority list',
    );
  });

  it('is the bare term without detail, and tolerates a missing rank', () => {
    expect(enterTooltip('Joinable', null, types)).toBe('Joinable');
    expect(enterTooltip('Joinable', { priority: 'dlc', lifted_by: 'dlc' }, undefined)).toBe(
      'Joinable: dlc, filters skipped, in your order',
    );
  });
});
