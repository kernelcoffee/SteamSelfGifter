import { useQuery } from '@tanstack/react-query';
import { api } from '@/services/api';
import type { SystemInfo, HealthCheck } from '@/types';

/**
 * Query keys for system
 */
export const systemKeys = {
  all: ['system'] as const,
  health: ['system', 'health'] as const,
  info: ['system', 'info'] as const,
};

/**
 * Health check endpoint
 */
export function useHealthCheck() {
  return useQuery({
    queryKey: systemKeys.health,
    queryFn: async () => {
      const response = await api.get<HealthCheck>('/api/v1/system/health');
      if (!response.success) {
        throw new Error(response.error || 'Health check failed');
      }
      return response.data;
    },
    // Health check every 30 seconds
    refetchInterval: 30_000,
    // Retry on failure
    retry: 3,
    retryDelay: 1000,
  });
}

/**
 * System info (app name, version, etc.)
 */
export function useSystemInfo() {
  return useQuery({
    queryKey: systemKeys.info,
    queryFn: async () => {
      const response = await api.get<SystemInfo>('/api/v1/system/info');
      if (!response.success) {
        throw new Error(response.error || 'Failed to fetch system info');
      }
      return response.data;
    },
    // System info rarely changes, cache for longer
    staleTime: 5 * 60 * 1000, // 5 minutes
  });
}
