import { useQuery, useMutation, useQueryClient, useInfiniteQuery } from '@tanstack/react-query';
import { api } from '@/services/api';
import type { Giveaway, SafetyCheckResult } from '@/types';

/**
 * Query keys for giveaways
 */
export const giveawayKeys = {
  all: ['giveaways'] as const,
  lists: () => [...giveawayKeys.all, 'list'] as const,
  list: (filters: GiveawayFilters) => [...giveawayKeys.lists(), filters] as const,
  details: () => [...giveawayKeys.all, 'detail'] as const,
  detail: (id: number) => [...giveawayKeys.details(), id] as const,
};

/**
 * Filter options for giveaways
 */
export interface GiveawayFilters {
  status?: 'active' | 'entered' | 'wishlist' | 'won';
  type?: 'game' | 'dlc' | 'bundle' | 'all';
  search?: string;
  sort?: 'end_time' | 'price' | 'discovered_at';
  order?: 'asc' | 'desc';
  page?: number;
  limit?: number;
  minScore?: number; // Minimum review score (0-10)
  safetyFilter?: 'all' | 'safe' | 'unsafe'; // Filter by safety status
  minChance?: number; // Minimum win chance in percent (0.01-100)
  endingWithin?: number; // Only giveaways ending within this many minutes
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
 * Backend response format for giveaways
 */
interface GiveawaysApiResponse {
  giveaways: Giveaway[];
  count: number;
}

/**
 * Build the endpoint URL (path + query string) for a giveaways request.
 * Shared by useGiveaways and useInfiniteGiveaways so the filter mapping
 * stays in one place.
 */
function buildGiveawaysEndpoint(
  filters: Omit<GiveawayFilters, 'page'>,
  limit: number,
  offset: number
): string {
  const params = new URLSearchParams();

  // Determine which endpoint to use based on status filter
  let endpointPath = '/api/v1/giveaways';
  if (filters.status === 'active') {
    endpointPath = '/api/v1/giveaways/active';
  } else if (filters.status === 'wishlist') {
    endpointPath = '/api/v1/giveaways/wishlist';
  } else if (filters.status === 'won') {
    endpointPath = '/api/v1/giveaways/won';
  }

  // Add filter parameters
  if (filters.status === 'entered') {
    params.set('is_entered', 'true');
    params.set('active_only', 'true'); // Only show active entered giveaways
  }
  if (filters.type && filters.type !== 'all') {
    params.set('type', filters.type);
  }
  if (filters.search) {
    params.set('search', filters.search);
  }
  if (filters.sort) {
    params.set('sort', filters.sort);
  }
  if (filters.order) {
    params.set('order', filters.order);
  }
  if (filters.minScore !== undefined && filters.minScore > 0) {
    params.set('min_score', String(filters.minScore));
  }
  if (filters.safetyFilter && filters.safetyFilter !== 'all') {
    params.set('is_safe', filters.safetyFilter === 'safe' ? 'true' : 'false');
  }
  if (filters.minChance !== undefined && filters.minChance > 0) {
    params.set('min_chance', String(filters.minChance));
  }
  if (filters.endingWithin !== undefined && filters.endingWithin > 0) {
    params.set('ending_within', String(filters.endingWithin));
  }

  params.set('limit', String(limit));
  if (offset > 0) {
    params.set('offset', String(offset));
  }

  const queryString = params.toString();
  return `${endpointPath}${queryString ? `?${queryString}` : ''}`;
}

/**
 * Fetch giveaways with optional filters
 */
export function useGiveaways(filters: GiveawayFilters = {}) {
  return useQuery({
    queryKey: giveawayKeys.list(filters),
    queryFn: async () => {
      const limit = filters.limit || 20;
      const page = filters.page || 1;
      const offset = (page - 1) * limit;

      const endpoint = buildGiveawaysEndpoint(filters, limit, offset);

      const response = await api.get<GiveawaysApiResponse>(endpoint);
      if (!response.success) {
        throw new Error(response.error || 'Failed to fetch giveaways');
      }

      // Transform backend response to frontend format
      const total = response.data.count;

      return {
        items: response.data.giveaways,
        total,
        page,
        limit,
        pages: Math.ceil(total / limit) || 1,
      } as PaginatedResponse<Giveaway>;
    },
  });
}

/**
 * Fetch giveaways with infinite scrolling
 */
export function useInfiniteGiveaways(filters: Omit<GiveawayFilters, 'page'> = {}) {
  return useInfiniteQuery({
    queryKey: [...giveawayKeys.lists(), 'infinite', filters],
    queryFn: async ({ pageParam = 0 }) => {
      const limit = filters.limit || 20;

      const endpoint = buildGiveawaysEndpoint(filters, limit, pageParam);

      const response = await api.get<GiveawaysApiResponse>(endpoint);
      if (!response.success) {
        throw new Error(response.error || 'Failed to fetch giveaways');
      }

      return {
        giveaways: response.data.giveaways,
        nextOffset: response.data.giveaways.length === limit ? pageParam + limit : undefined,
      };
    },
    getNextPageParam: (lastPage) => lastPage.nextOffset,
    initialPageParam: 0,
  });
}

/**
 * Fetch a single giveaway by ID
 */
export function useGiveaway(id: number) {
  return useQuery({
    queryKey: giveawayKeys.detail(id),
    queryFn: async () => {
      const response = await api.get<Giveaway>(`/api/v1/giveaways/${id}`);
      if (!response.success) {
        throw new Error(response.error || 'Failed to fetch giveaway');
      }
      return response.data;
    },
    enabled: id > 0,
  });
}

/**
 * Enter a giveaway manually
 */
export function useEnterGiveaway() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (giveawayCode: string) => {
      const response = await api.post<{ success: boolean; entry_id: number }>(
        `/api/v1/giveaways/${giveawayCode}/enter`
      );
      if (!response.success) {
        throw new Error(response.error || 'Failed to enter giveaway');
      }
      return response.data;
    },
    onSuccess: () => {
      // Refresh giveaways list and entries
      queryClient.invalidateQueries({ queryKey: giveawayKeys.all });
      queryClient.invalidateQueries({ queryKey: ['entries'] });
    },
  });
}

/**
 * Hide a giveaway from auto-entry
 */
export function useHideGiveaway() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (giveawayCode: string) => {
      const response = await api.post<{ message: string; code: string }>(
        `/api/v1/giveaways/${giveawayCode}/hide`
      );
      if (!response.success) {
        throw new Error(response.error || 'Failed to hide giveaway');
      }
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: giveawayKeys.all });
    },
  });
}

/**
 * Unhide a giveaway
 */
export function useUnhideGiveaway() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (giveawayCode: string) => {
      const response = await api.post<{ message: string; code: string }>(
        `/api/v1/giveaways/${giveawayCode}/unhide`
      );
      if (!response.success) {
        throw new Error(response.error || 'Failed to unhide giveaway');
      }
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: giveawayKeys.all });
    },
  });
}

/**
 * Remove entry from a giveaway
 */
export function useRemoveEntry() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (giveawayCode: string) => {
      const response = await api.post<{ message: string; code: string }>(
        `/api/v1/giveaways/${giveawayCode}/remove-entry`
      );
      if (!response.success) {
        throw new Error(response.error || 'Failed to remove entry');
      }
      return response.data;
    },
    onSuccess: () => {
      // Refresh giveaways list and entries
      queryClient.invalidateQueries({ queryKey: giveawayKeys.all });
      queryClient.invalidateQueries({ queryKey: ['entries'] });
    },
  });
}

/**
 * Refresh giveaway game data from Steam
 */
export function useRefreshGiveawayGame() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (giveawayId: number) => {
      const response = await api.post<Giveaway>(`/api/v1/giveaways/${giveawayId}/refresh`);
      if (!response.success) {
        throw new Error(response.error || 'Failed to refresh game data');
      }
      return response.data;
    },
    onSuccess: (_, giveawayId) => {
      queryClient.invalidateQueries({ queryKey: giveawayKeys.detail(giveawayId) });
      queryClient.invalidateQueries({ queryKey: giveawayKeys.lists() });
    },
  });
}

/**
 * Check giveaway safety (trap detection)
 */
export function useCheckGiveawaySafety() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (giveawayCode: string) => {
      const response = await api.post<SafetyCheckResult>(
        `/api/v1/giveaways/${giveawayCode}/check-safety`
      );
      if (!response.success) {
        throw new Error(response.error || 'Failed to check giveaway safety');
      }
      return response.data;
    },
    onSuccess: () => {
      // Refresh giveaways to show updated safety info
      queryClient.invalidateQueries({ queryKey: giveawayKeys.all });
    },
  });
}

/**
 * Hide giveaway on SteamGifts (permanent hide for the game)
 */
export function useHideOnSteamGifts() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (giveawayCode: string) => {
      const response = await api.post<{ message: string; code: string }>(
        `/api/v1/giveaways/${giveawayCode}/hide-on-steamgifts`
      );
      if (!response.success) {
        throw new Error(response.error || 'Failed to hide on SteamGifts');
      }
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: giveawayKeys.all });
    },
  });
}

/**
 * Post a comment on a giveaway
 */
export function usePostComment() {
  return useMutation({
    mutationFn: async ({ giveawayCode, comment = 'Thanks!' }: { giveawayCode: string; comment?: string }) => {
      const response = await api.post<{ message: string; code: string; comment: string }>(
        `/api/v1/giveaways/${giveawayCode}/comment?comment=${encodeURIComponent(comment)}`
      );
      if (!response.success) {
        throw new Error(response.error || 'Failed to post comment');
      }
      return response.data;
    },
  });
}
