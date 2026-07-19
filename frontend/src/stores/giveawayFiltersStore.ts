import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { GiveawayFilters } from '@/hooks/useGiveaways';

// The status (active/wishlist/entered) comes from the route, not the store —
// each status is its own page in the sidebar.
type PersistedFilters = Omit<GiveawayFilters, 'page' | 'status'>;

interface GiveawayFiltersState {
  filters: PersistedFilters;
  setFilters: (update: Partial<PersistedFilters>) => void;
  resetFilters: () => void;
}

const DEFAULT_FILTERS: PersistedFilters = {
  limit: 20,
};

/**
 * Giveaways page filter store with localStorage persistence.
 *
 * Keeps the score/safety/chance/time filters across visits so they don't
 * have to be re-applied every time the page is opened. The search query is
 * deliberately NOT persisted (a stale search silently filtering the list is
 * more confusing than helpful).
 */
export const useGiveawayFiltersStore = create<GiveawayFiltersState>()(
  persist(
    (set) => ({
      filters: DEFAULT_FILTERS,
      setFilters: (update) =>
        set((state) => ({ filters: { ...state.filters, ...update } })),
      resetFilters: () => set({ filters: DEFAULT_FILTERS }),
    }),
    {
      name: 'giveaway-filters',
      // v1: the selected tab (status) moved out of the store and into the
      // route; strip it from state persisted by v0.
      version: 1,
      migrate: (persisted) => {
        const state = persisted as {
          filters?: PersistedFilters & { status?: string; search?: string };
        };
        if (state?.filters) {
          delete state.filters.status;
          delete state.filters.search;
        }
        return state as { filters: PersistedFilters & { search: undefined } };
      },
      partialize: (state) => ({
        filters: { ...state.filters, search: undefined },
      }),
    }
  )
);
