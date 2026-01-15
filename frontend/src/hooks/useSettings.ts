import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '@/services/api';
import type { Settings, ConfigValidation } from '@/types';

/**
 * Query key for settings
 */
export const settingsKeys = {
  all: ['settings'] as const,
  validation: ['settings', 'validation'] as const,
};

/**
 * Fetch current settings
 */
export function useSettings() {
  return useQuery({
    queryKey: settingsKeys.all,
    queryFn: async () => {
      const response = await api.get<Settings>('/api/v1/settings');
      if (!response.success) {
        throw new Error(response.error || 'Failed to fetch settings');
      }
      return response.data;
    },
  });
}

/**
 * Update settings
 */
export function useUpdateSettings() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (settings: Partial<Settings>) => {
      const response = await api.put<Settings>('/api/v1/settings', settings);
      if (!response.success) {
        throw new Error(response.error || 'Failed to update settings');
      }
      return response.data;
    },
    onSuccess: (newSettings) => {
      // Update the cached settings
      queryClient.setQueryData(settingsKeys.all, newSettings);
    },
  });
}

/**
 * Validate current configuration
 */
export function useValidateConfig() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async () => {
      const response = await api.post<ConfigValidation>('/api/v1/settings/validate');
      if (!response.success) {
        throw new Error(response.error || 'Failed to validate config');
      }
      return response.data;
    },
    onSuccess: (data) => {
      queryClient.setQueryData(settingsKeys.validation, data);
    },
  });
}

/**
 * Test Steam session (validate PHPSESSID)
 */
export function useTestSession() {
  return useMutation({
    mutationFn: async () => {
      const response = await api.post<{ valid: boolean; username?: string; points?: number; error?: string }>(
        '/api/v1/settings/test-session'
      );
      if (!response.success) {
        throw new Error(response.error || 'Failed to test session');
      }
      return response.data;
    },
  });
}
