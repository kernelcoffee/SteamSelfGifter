import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { GiveawayFilters } from '@/hooks/useGiveaways';

type PersistedFilters = Omit<GiveawayFilters, 'page'>;

interface GiveawayFiltersState {
  filters: PersistedFilters;
  setFilters: (update: Partial<PersistedFilters>) => void;
  resetFilters: () => void;
}

const DEFAULT_FILTERS: PersistedFilters = {
  status: 'active',
  limit: 20,
};

/**
 * Giveaways page filter store with localStorage persistence.
 *
 * Keeps the selected tab, score/safety/chance/time filters across visits so
 * they don't have to be re-applied every time the page is opened. The search
 * query is deliberately NOT persisted (a stale search silently filtering the
 * list is more confusing than helpful).
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
      partialize: (state) => ({
        filters: { ...state.filters, search: undefined },
      }),
    }
  )
);
