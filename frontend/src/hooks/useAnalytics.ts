import { useQuery } from '@tanstack/react-query';
import { api } from '@/services/api';
import type { DashboardData, EntryStats, GiveawayStats, GameStats } from '@/types';

/**
 * Query keys for analytics
 */
export const analyticsKeys = {
  all: ['analytics'] as const,
  dashboard: ['analytics', 'dashboard'] as const,
  entries: ['analytics', 'entries'] as const,
  giveaways: ['analytics', 'giveaways'] as const,
  games: ['analytics', 'games'] as const,
};

/**
 * Time range filter
 */
export interface TimeRangeFilter {
  period?: 'day' | 'week' | 'month' | 'year' | 'all';
  from_date?: string;
  to_date?: string;
}

/**
 * Fetch dashboard overview data
 */
export function useDashboard() {
  return useQuery({
    queryKey: analyticsKeys.dashboard,
    queryFn: async () => {
      const response = await api.get<DashboardData>('/api/v1/analytics/dashboard');
      if (!response.success) {
        throw new Error(response.error || 'Failed to fetch dashboard data');
      }
      return response.data;
    },
    // Dashboard refreshes every 30 seconds
    refetchInterval: 30_000,
  });
}

/** Backend response for entries/summary */
interface EntrySummaryResponse {
  total_entries: number;
  successful_entries: number;
  failed_entries: number;
  success_rate: number;
  total_points_spent: number;
  average_points_per_entry: number;
  by_type: { manual: number; auto: number; wishlist: number };
}

/**
 * Fetch entry statistics
 */
export function useEntryStats(timeRange: TimeRangeFilter = {}) {
  return useQuery({
    queryKey: [...analyticsKeys.entries, timeRange],
    queryFn: async () => {
      const params = new URLSearchParams();

      if (timeRange.period) {
        params.set('period', timeRange.period);
      }
      if (timeRange.from_date) {
        params.set('from_date', timeRange.from_date);
      }
      if (timeRange.to_date) {
        params.set('to_date', timeRange.to_date);
      }

      const queryString = params.toString();
      const endpoint = `/api/v1/analytics/entries/summary${queryString ? `?${queryString}` : ''}`;

      const response = await api.get<EntrySummaryResponse>(endpoint);
      if (!response.success) {
        throw new Error(response.error || 'Failed to fetch entry stats');
      }
      // Transform backend response to frontend format
      const data = response.data;
      return {
        total: data.total_entries,
        successful: data.successful_entries,
        failed: data.failed_entries,
        success_rate: data.success_rate,
        total_points_spent: data.total_points_spent,
        by_type: data.by_type,
      } as EntryStats;
    },
  });
}

/** Backend response for giveaways/summary */
interface GiveawaySummaryResponse {
  total_giveaways: number;
  active_giveaways: number;
  entered_giveaways: number;
  hidden_giveaways: number;
  expiring_24h: number;
  wins: number;
  win_rate: number;
}

/**
 * Fetch giveaway statistics
 */
export function useGiveawayStats(timeRange: TimeRangeFilter = {}) {
  return useQuery({
    queryKey: [...analyticsKeys.giveaways, timeRange],
    queryFn: async () => {
      const params = new URLSearchParams();

      if (timeRange.period) {
        params.set('period', timeRange.period);
      }
      if (timeRange.from_date) {
        params.set('from_date', timeRange.from_date);
      }
      if (timeRange.to_date) {
        params.set('to_date', timeRange.to_date);
      }

      const queryString = params.toString();
      const endpoint = `/api/v1/analytics/giveaways/summary${queryString ? `?${queryString}` : ''}`;

      const response = await api.get<GiveawaySummaryResponse>(endpoint);
      if (!response.success) {
        throw new Error(response.error || 'Failed to fetch giveaway stats');
      }
      // Transform backend response to frontend format
      const data = response.data;
      return {
        total: data.total_giveaways,
        active: data.active_giveaways,
        entered: data.entered_giveaways,
        hidden: data.hidden_giveaways,
        wins: data.wins,
        win_rate: data.win_rate,
      } as GiveawayStats;
    },
  });
}

/**
 * Fetch game statistics
 */
export function useGameStats() {
  return useQuery({
    queryKey: analyticsKeys.games,
    queryFn: async () => {
      const response = await api.get<GameStats>('/api/v1/analytics/games/summary');
      if (!response.success) {
        throw new Error(response.error || 'Failed to fetch game stats');
      }
      return response.data;
    },
  });
}

/**
 * Entry trend data point
 */
export interface TrendDataPoint {
  date: string;
  entries: number;
  points_spent: number;
}

/**
 * Fetch entry trends over time
 */
export function useEntryTrends(period: 'week' | 'month' | 'year' = 'month') {
  return useQuery({
    queryKey: [...analyticsKeys.entries, 'trends', period],
    queryFn: async () => {
      const response = await api.get<TrendDataPoint[]>(
        `/api/v1/analytics/entries/trends?period=${period}`
      );
      if (!response.success) {
        throw new Error(response.error || 'Failed to fetch entry trends');
      }
      return response.data;
    },
  });
}
