import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { api } from '@/services/api';
import type { AutojoinRegistry, PolicyPreviewRequest, PolicyPreviewResponse } from '@/types';

/**
 * Query keys for the auto-join engine endpoints. The registry key is a
 * constant (the registry never changes while the backend runs); the preview
 * key carries the whole policy body so two policies never share a result.
 */
export const autojoinKeys = {
  all: ['autojoin'] as const,
  registry: ['autojoin', 'registry'] as const,
  preview: (policy: PolicyPreviewRequest) => ['autojoin', 'preview', policy] as const,
};

/** Only the summary is rendered while editing, so one candidate is enough. */
export const PREVIEW_LIMIT = 1;

/**
 * The engine's rules as data: gates, filters, outcomes, priority types and
 * limits (GET /giveaways/registry). Fetched once per session.
 */
export function useAutojoinRegistry() {
  return useQuery({
    queryKey: autojoinKeys.registry,
    queryFn: async () => {
      const response = await api.get<AutojoinRegistry>('/api/v1/giveaways/registry');
      if (!response.success) {
        throw new Error(response.error || 'Failed to load the auto-join registry');
      }
      return response.data;
    },
    staleTime: Infinity,
  });
}

/**
 * Dry run of an unsaved policy over the active pool (POST /giveaways/preview).
 * Persists nothing and sends nothing to SteamGifts. While a new policy loads
 * the previous result stays as placeholder data (isPlaceholderData true).
 */
export function useAutojoinPreview(policy: PolicyPreviewRequest, enabled: boolean) {
  return useQuery({
    queryKey: autojoinKeys.preview(policy),
    queryFn: async () => {
      const response = await api.post<PolicyPreviewResponse>(
        `/api/v1/giveaways/preview?limit=${PREVIEW_LIMIT}`,
        policy,
      );
      if (!response.success) {
        throw new Error(response.error || 'Failed to compute the auto-join preview');
      }
      return response.data;
    },
    enabled,
    placeholderData: keepPreviousData,
  });
}
