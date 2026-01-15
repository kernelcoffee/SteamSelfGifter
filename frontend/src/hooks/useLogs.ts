import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '@/services/api';
import type { ActivityLog } from '@/types';

/**
 * Query keys for logs
 */
export const logKeys = {
  all: ['logs'] as const,
  lists: () => [...logKeys.all, 'list'] as const,
  list: (filters: LogFilters) => [...logKeys.lists(), filters] as const,
};

/**
 * Filter options for logs
 */
export interface LogFilters {
  level?: 'info' | 'warning' | 'error' | 'all';
  event_type?: 'scan' | 'entry' | 'error' | 'config' | 'scheduler' | 'all';
  from_date?: string;
  to_date?: string;
  search?: string;
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
 * Backend response format for logs
 */
interface LogsApiResponse {
  logs: ActivityLog[];
  count: number;
  limit: number;
}

/**
 * Fetch activity logs with optional filters
 */
export function useLogs(filters: LogFilters = {}) {
  return useQuery({
    queryKey: logKeys.list(filters),
    queryFn: async () => {
      const params = new URLSearchParams();

      if (filters.level && filters.level !== 'all') {
        params.set('level', filters.level);
      }
      if (filters.event_type && filters.event_type !== 'all') {
        params.set('event_type', filters.event_type);
      }
      if (filters.from_date) {
        params.set('from_date', filters.from_date);
      }
      if (filters.to_date) {
        params.set('to_date', filters.to_date);
      }
      if (filters.search) {
        params.set('search', filters.search);
      }
      if (filters.limit) {
        params.set('limit', String(filters.limit));
      }

      const queryString = params.toString();
      const endpoint = `/api/v1/system/logs${queryString ? `?${queryString}` : ''}`;

      const response = await api.get<LogsApiResponse>(endpoint);
      if (!response.success) {
        throw new Error(response.error || 'Failed to fetch logs');
      }

      // Transform backend response to frontend format
      const page = filters.page || 1;
      const limit = filters.limit || 50;
      const total = response.data.count;

      return {
        items: response.data.logs,
        total,
        page,
        limit,
        pages: Math.ceil(total / limit) || 1,
      } as PaginatedResponse<ActivityLog>;
    },
    // Logs refresh every 15 seconds when viewing
    refetchInterval: 15_000,
  });
}

/**
 * Clear all logs
 */
export function useClearLogs() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async () => {
      const response = await api.delete<{ deleted: number }>('/api/v1/system/logs');
      if (!response.success) {
        throw new Error(response.error || 'Failed to clear logs');
      }
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: logKeys.all });
    },
  });
}

/**
 * Export logs as CSV or JSON
 */
export function useExportLogs() {
  return useMutation({
    mutationFn: async (format: 'csv' | 'json') => {
      // This endpoint returns a file download, not JSON
      const response = await fetch(`/api/v1/system/logs/export?format=${format}`);
      if (!response.ok) {
        throw new Error('Failed to export logs');
      }
      const blob = await response.blob();
      return { blob, format };
    },
    onSuccess: ({ blob, format }) => {
      // Trigger browser download
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `logs_${new Date().toISOString().split('T')[0]}.${format}`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    },
  });
}
