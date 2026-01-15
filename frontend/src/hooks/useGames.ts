import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '@/services/api';
import type { Game } from '@/types';

/**
 * Query keys for games
 */
export const gameKeys = {
  all: ['games'] as const,
  lists: () => [...gameKeys.all, 'list'] as const,
  list: (filters: GameFilters) => [...gameKeys.lists(), filters] as const,
  details: () => [...gameKeys.all, 'detail'] as const,
  detail: (id: number) => [...gameKeys.details(), id] as const,
};

/**
 * Filter options for games
 */
export interface GameFilters {
  type?: 'game' | 'dlc' | 'bundle' | 'all';
  search?: string;
  stale?: boolean;
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
 * Backend response format for games
 */
interface GamesApiResponse {
  games: Game[];
  count: number;
}

/**
 * Fetch games with optional filters
 */
export function useGames(filters: GameFilters = {}) {
  return useQuery({
    queryKey: gameKeys.list(filters),
    queryFn: async () => {
      const params = new URLSearchParams();

      if (filters.type && filters.type !== 'all') {
        params.set('type', filters.type);
      }
      if (filters.search) {
        params.set('search', filters.search);
      }
      if (filters.stale !== undefined) {
        params.set('stale', String(filters.stale));
      }
      if (filters.limit) {
        params.set('limit', String(filters.limit));
      }

      const queryString = params.toString();
      const endpoint = `/api/v1/games${queryString ? `?${queryString}` : ''}`;

      const response = await api.get<GamesApiResponse>(endpoint);
      if (!response.success) {
        throw new Error(response.error || 'Failed to fetch games');
      }

      // Transform backend response to frontend format
      const page = filters.page || 1;
      const limit = filters.limit || 50;
      const total = response.data.count;

      return {
        items: response.data.games,
        total,
        page,
        limit,
        pages: Math.ceil(total / limit) || 1,
      } as PaginatedResponse<Game>;
    },
  });
}

/**
 * Fetch a single game by ID
 */
export function useGame(id: number) {
  return useQuery({
    queryKey: gameKeys.detail(id),
    queryFn: async () => {
      const response = await api.get<Game>(`/api/v1/games/${id}`);
      if (!response.success) {
        throw new Error(response.error || 'Failed to fetch game');
      }
      return response.data;
    },
    enabled: id > 0,
  });
}

/**
 * Refresh game data from Steam
 */
export function useRefreshGame() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (gameId: number) => {
      const response = await api.post<Game>(`/api/v1/games/${gameId}/refresh`);
      if (!response.success) {
        throw new Error(response.error || 'Failed to refresh game');
      }
      return response.data;
    },
    onSuccess: (_, gameId) => {
      queryClient.invalidateQueries({ queryKey: gameKeys.detail(gameId) });
      queryClient.invalidateQueries({ queryKey: gameKeys.lists() });
    },
  });
}

/**
 * Refresh all stale games
 */
export function useRefreshStaleGames() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async () => {
      const response = await api.post<{ refreshed: number }>('/api/v1/games/refresh-stale');
      if (!response.success) {
        throw new Error(response.error || 'Failed to refresh stale games');
      }
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: gameKeys.all });
    },
  });
}
