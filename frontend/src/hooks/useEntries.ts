import { useQuery } from '@tanstack/react-query';
import { api } from '@/services/api';
import type { EntryWithGiveaway } from '@/types';

/**
 * Query keys for entries
 */
export const entryKeys = {
  all: ['entries'] as const,
  lists: () => [...entryKeys.all, 'list'] as const,
  list: (filters: EntryFilters) => [...entryKeys.lists(), filters] as const,
  details: () => [...entryKeys.all, 'detail'] as const,
  detail: (id: number) => [...entryKeys.details(), id] as const,
};

/**
 * Filter options for entries
 */
export interface EntryFilters {
  status?: 'success' | 'failed' | 'pending' | 'all';
  type?: 'manual' | 'auto' | 'wishlist' | 'all';
  giveaway_id?: number;
  from_date?: string;
  to_date?: string;
  page?: number;
  limit?: number;
}

/**
 * Paginated response
 */
export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  limit: number;
  pages: number;
}

/**
 * Backend response format for entries
 */
interface EntriesApiResponse {
  entries: EntryWithGiveaway[];
  count: number;
}

/**
 * Fetch entries (history) with optional filters
 */
export function useEntries(filters: EntryFilters = {}) {
  return useQuery({
    queryKey: entryKeys.list(filters),
    queryFn: async () => {
      const params = new URLSearchParams();

      if (filters.status && filters.status !== 'all') {
        params.set('status', filters.status);
      }
      if (filters.type && filters.type !== 'all') {
        params.set('entry_type', filters.type);
      }
      if (filters.giveaway_id) {
        params.set('giveaway_id', String(filters.giveaway_id));
      }
      if (filters.from_date) {
        params.set('from_date', filters.from_date);
      }
      if (filters.to_date) {
        params.set('to_date', filters.to_date);
      }
      if (filters.limit) {
        params.set('limit', String(filters.limit));
      }

      const queryString = params.toString();
      const endpoint = `/api/v1/entries/${queryString ? `?${queryString}` : ''}`;

      const response = await api.get<EntriesApiResponse>(endpoint);
      if (!response.success) {
        throw new Error(response.error || 'Failed to fetch entries');
      }

      // Transform backend response to frontend format
      const page = filters.page || 1;
      const limit = filters.limit || 20;
      const total = response.data.count;

      return {
        items: response.data.entries,
        total,
        page,
        limit,
        pages: Math.ceil(total / limit) || 1,
      } as PaginatedResponse<EntryWithGiveaway>;
    },
  });
}

/**
 * Fetch a single entry by ID
 */
export function useEntry(id: number) {
  return useQuery({
    queryKey: entryKeys.detail(id),
    queryFn: async () => {
      const response = await api.get<EntryWithGiveaway>(`/api/v1/entries/${id}`);
      if (!response.success) {
        throw new Error(response.error || 'Failed to fetch entry');
      }
      return response.data;
    },
    enabled: id > 0,
  });
}

/**
 * Alias for useEntries - for semantic clarity when used in History page
 */
export const useHistory = useEntries;
