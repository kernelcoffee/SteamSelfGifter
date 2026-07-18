import { describe, it, expect, beforeEach, vi, type Mock } from 'vitest';
import { useGiveawayFiltersStore } from './giveawayFiltersStore';

// localStorage is a vi.fn() mock (see test/setup.ts); read what the store
// last wrote through the mock's call log.
function lastPersistedState() {
  const calls = (localStorage.setItem as Mock).mock.calls.filter(
    ([key]) => key === 'giveaway-filters'
  );
  expect(calls.length).toBeGreaterThan(0);
  return JSON.parse(calls[calls.length - 1][1]).state;
}

describe('giveawayFiltersStore', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useGiveawayFiltersStore.getState().resetFilters();
  });

  it('starts with default filters', () => {
    const { filters } = useGiveawayFiltersStore.getState();
    expect(filters).toEqual({ status: 'active', limit: 20 });
  });

  it('merges partial updates', () => {
    useGiveawayFiltersStore.getState().setFilters({ minScore: 7 });
    useGiveawayFiltersStore.getState().setFilters({ minChance: 0.5, endingWithin: 6 });

    const { filters } = useGiveawayFiltersStore.getState();
    expect(filters.status).toBe('active');
    expect(filters.minScore).toBe(7);
    expect(filters.minChance).toBe(0.5);
    expect(filters.endingWithin).toBe(6);
  });

  it('persists filters to localStorage', () => {
    useGiveawayFiltersStore.getState().setFilters({ minScore: 8, status: 'wishlist' });

    const persisted = lastPersistedState();
    expect(persisted.filters.minScore).toBe(8);
    expect(persisted.filters.status).toBe('wishlist');
  });

  it('does not persist the search query', () => {
    useGiveawayFiltersStore.getState().setFilters({ search: 'portal', minScore: 5 });

    const persisted = lastPersistedState();
    expect(persisted.filters.search).toBeUndefined();
    expect(persisted.filters.minScore).toBe(5);
    // ...but it stays available in memory for the current session
    expect(useGiveawayFiltersStore.getState().filters.search).toBe('portal');
  });

  it('resetFilters restores defaults', () => {
    useGiveawayFiltersStore.getState().setFilters({ minScore: 9, minChance: 10 });
    useGiveawayFiltersStore.getState().resetFilters();

    expect(useGiveawayFiltersStore.getState().filters).toEqual({
      status: 'active',
      limit: 20,
    });
  });
});
