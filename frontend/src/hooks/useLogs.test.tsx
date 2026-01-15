import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ReactNode } from 'react';
import { useLogs, useClearLogs } from './useLogs';
import { api } from '@/services/api';
import type { ActivityLog } from '@/types';

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

const mockLog: ActivityLog = {
  id: 1,
  level: 'info',
  event_type: 'scan',
  message: 'Scan completed successfully',
  details: 'Found 5 new giveaways',
  created_at: '2024-01-01T00:00:00Z',
};

describe('useLogs', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('useLogs hook', () => {
    it('should fetch logs successfully', async () => {
      // Backend returns { logs, count, limit } which gets transformed
      const backendResponse = {
        logs: [mockLog],
        count: 1,
        limit: 50,
      };

      mockApi.get.mockResolvedValueOnce({
        success: true,
        data: backendResponse,
      });

      const { result } = renderHook(() => useLogs(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      // Hook transforms backend response to frontend format
      expect(result.current.data).toEqual({
        items: [mockLog],
        total: 1,
        page: 1,
        limit: 50,
        pages: 1,
      });
      expect(mockApi.get).toHaveBeenCalledWith('/api/v1/system/logs');
    });

    it('should fetch with filters', async () => {
      // Backend format
      mockApi.get.mockResolvedValueOnce({
        success: true,
        data: { logs: [], count: 0, limit: 50 },
      });

      const { result } = renderHook(
        () => useLogs({ level: 'error', event_type: 'entry', search: 'failed' }),
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(mockApi.get).toHaveBeenCalledWith(
        '/api/v1/system/logs?level=error&event_type=entry&search=failed'
      );
    });

    it('should handle fetch error', async () => {
      mockApi.get.mockResolvedValueOnce({
        success: false,
        data: null,
        error: 'Failed to fetch logs',
      });

      const { result } = renderHook(() => useLogs(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(result.current.isError).toBe(true);
      });

      expect(result.current.error?.message).toBe('Failed to fetch logs');
    });
  });

  describe('useClearLogs hook', () => {
    it('should clear logs successfully', async () => {
      mockApi.delete.mockResolvedValueOnce({
        success: true,
        data: { deleted: 100 },
      });

      const { result } = renderHook(() => useClearLogs(), {
        wrapper: createWrapper(),
      });

      result.current.mutate();

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data).toEqual({ deleted: 100 });
      expect(mockApi.delete).toHaveBeenCalledWith('/api/v1/system/logs');
    });

    it('should handle clear error', async () => {
      mockApi.delete.mockResolvedValueOnce({
        success: false,
        data: null,
        error: 'Permission denied',
      });

      const { result } = renderHook(() => useClearLogs(), {
        wrapper: createWrapper(),
      });

      result.current.mutate();

      await waitFor(() => {
        expect(result.current.isError).toBe(true);
      });

      expect(result.current.error?.message).toBe('Permission denied');
    });
  });
});
