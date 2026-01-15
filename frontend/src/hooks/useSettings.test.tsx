import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ReactNode } from 'react';
import { useSettings, useUpdateSettings, useValidateConfig, useTestSession } from './useSettings';
import { api } from '@/services/api';
import type { Settings } from '@/types';

// Mock the API module
vi.mock('@/services/api', () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
}));

const mockApi = vi.mocked(api);

// Create a fresh QueryClient for each test
function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        gcTime: 0,
      },
      mutations: {
        retry: false,
      },
    },
  });
}

function createWrapper() {
  const queryClient = createTestQueryClient();
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>
        {children}
      </QueryClientProvider>
    );
  };
}

const mockSettings: Settings = {
  id: 1,
  phpsessid: 'test-session-id',
  user_agent: 'test-user-agent',
  xsrf_token: 'test-token',
  dlc_enabled: true,
  safety_check_enabled: true,
  auto_hide_unsafe: true,
  autojoin_enabled: true,
  autojoin_start_at: 100,
  autojoin_stop_at: 10,
  autojoin_min_price: 5,
  autojoin_min_score: 70,
  autojoin_min_reviews: 100,
  autojoin_max_game_age: null,
  scan_interval_minutes: 30,
  max_entries_per_cycle: 10,
  automation_enabled: true,
  max_scan_pages: 5,
  entry_delay_min: 1000,
  entry_delay_max: 3000,
  last_synced_at: '2024-01-01T00:00:00Z',
  created_at: '2024-01-01T00:00:00Z',
  updated_at: '2024-01-01T00:00:00Z',
};

describe('useSettings', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('useSettings hook', () => {
    it('should fetch settings successfully', async () => {
      mockApi.get.mockResolvedValueOnce({
        success: true,
        data: mockSettings,
      });

      const { result } = renderHook(() => useSettings(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data).toEqual(mockSettings);
      expect(mockApi.get).toHaveBeenCalledWith('/api/v1/settings');
    });

    it('should handle fetch error', async () => {
      mockApi.get.mockResolvedValueOnce({
        success: false,
        data: null,
        error: 'Failed to fetch settings',
      });

      const { result } = renderHook(() => useSettings(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(result.current.isError).toBe(true);
      });

      expect(result.current.error?.message).toBe('Failed to fetch settings');
    });
  });

  describe('useUpdateSettings hook', () => {
    it('should update settings successfully', async () => {
      const updatedSettings = { ...mockSettings, dlc_enabled: false };

      mockApi.put.mockResolvedValueOnce({
        success: true,
        data: updatedSettings,
      });

      const { result } = renderHook(() => useUpdateSettings(), {
        wrapper: createWrapper(),
      });

      result.current.mutate({ dlc_enabled: false });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data).toEqual(updatedSettings);
      expect(mockApi.put).toHaveBeenCalledWith('/api/v1/settings', { dlc_enabled: false });
    });

    it('should handle update error', async () => {
      mockApi.put.mockResolvedValueOnce({
        success: false,
        data: null,
        error: 'Failed to update settings',
      });

      const { result } = renderHook(() => useUpdateSettings(), {
        wrapper: createWrapper(),
      });

      result.current.mutate({ dlc_enabled: false });

      await waitFor(() => {
        expect(result.current.isError).toBe(true);
      });

      expect(result.current.error?.message).toBe('Failed to update settings');
    });
  });

  describe('useValidateConfig hook', () => {
    it('should not call API automatically (mutation)', () => {
      const { result } = renderHook(() => useValidateConfig(), {
        wrapper: createWrapper(),
      });

      // Mutations don't call automatically
      expect(result.current.isPending).toBe(false);
      expect(mockApi.post).not.toHaveBeenCalled();
    });

    it('should validate config when mutate is called', async () => {
      const validationResult = { is_valid: true, errors: [], warnings: [] };

      mockApi.post.mockResolvedValueOnce({
        success: true,
        data: validationResult,
      });

      const { result } = renderHook(() => useValidateConfig(), {
        wrapper: createWrapper(),
      });

      // The hook should have a mutate function available
      expect(typeof result.current.mutate).toBe('function');

      result.current.mutate();

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data).toEqual(validationResult);
      expect(mockApi.post).toHaveBeenCalledWith('/api/v1/settings/validate');
    });
  });

  describe('useTestSession hook', () => {
    it('should test session successfully', async () => {
      const sessionData = { valid: true, username: 'testuser', points: 500 };

      mockApi.post.mockResolvedValueOnce({
        success: true,
        data: sessionData,
      });

      const { result } = renderHook(() => useTestSession(), {
        wrapper: createWrapper(),
      });

      result.current.mutate();

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data).toEqual(sessionData);
      expect(mockApi.post).toHaveBeenCalledWith('/api/v1/settings/test-session');
    });

    it('should handle invalid session', async () => {
      mockApi.post.mockResolvedValueOnce({
        success: false,
        data: null,
        error: 'Invalid session',
      });

      const { result } = renderHook(() => useTestSession(), {
        wrapper: createWrapper(),
      });

      result.current.mutate();

      await waitFor(() => {
        expect(result.current.isError).toBe(true);
      });

      expect(result.current.error?.message).toBe('Invalid session');
    });
  });
});
