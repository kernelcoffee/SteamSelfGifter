import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ReactNode } from 'react';
import {
  useSchedulerStatus,
  useStartScheduler,
  useStopScheduler,
  usePauseScheduler,
  useResumeScheduler,
  useTriggerScan,
  useTriggerProcess,
  useSchedulerControl,
} from './useScheduler';
import { api } from '@/services/api';
import type { SchedulerStatus, ScanResult, ProcessResult } from '@/types';

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

const mockSchedulerStatus: SchedulerStatus = {
  running: true,
  paused: false,
  job_count: 2,
  jobs: [
    { id: 'scan', name: 'Scan Giveaways', next_run: '2024-01-01T01:00:00Z', pending: false },
    { id: 'process', name: 'Process Entries', next_run: '2024-01-01T01:05:00Z', pending: false },
  ],
};

describe('useScheduler', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('useSchedulerStatus hook', () => {
    it('should fetch scheduler status successfully', async () => {
      mockApi.get.mockResolvedValueOnce({
        success: true,
        data: mockSchedulerStatus,
      });

      const { result } = renderHook(() => useSchedulerStatus(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data).toEqual(mockSchedulerStatus);
      expect(mockApi.get).toHaveBeenCalledWith('/api/v1/scheduler/status');
    });

    it('should handle fetch error', async () => {
      mockApi.get.mockResolvedValueOnce({
        success: false,
        data: null,
        error: 'Failed to fetch status',
      });

      const { result } = renderHook(() => useSchedulerStatus(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(result.current.isError).toBe(true);
      });

      expect(result.current.error?.message).toBe('Failed to fetch status');
    });
  });

  describe('useStartScheduler hook', () => {
    it('should start scheduler successfully', async () => {
      mockApi.post.mockResolvedValueOnce({
        success: true,
        data: { ...mockSchedulerStatus, running: true },
      });

      const { result } = renderHook(() => useStartScheduler(), {
        wrapper: createWrapper(),
      });

      result.current.mutate();

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(mockApi.post).toHaveBeenCalledWith('/api/v1/scheduler/start');
    });

    it('should handle start error', async () => {
      mockApi.post.mockResolvedValueOnce({
        success: false,
        data: null,
        error: 'Already running',
      });

      const { result } = renderHook(() => useStartScheduler(), {
        wrapper: createWrapper(),
      });

      result.current.mutate();

      await waitFor(() => {
        expect(result.current.isError).toBe(true);
      });

      expect(result.current.error?.message).toBe('Already running');
    });
  });

  describe('useStopScheduler hook', () => {
    it('should stop scheduler successfully', async () => {
      mockApi.post.mockResolvedValueOnce({
        success: true,
        data: { ...mockSchedulerStatus, running: false },
      });

      const { result } = renderHook(() => useStopScheduler(), {
        wrapper: createWrapper(),
      });

      result.current.mutate();

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(mockApi.post).toHaveBeenCalledWith('/api/v1/scheduler/stop');
    });
  });

  describe('usePauseScheduler hook', () => {
    it('should pause scheduler successfully', async () => {
      mockApi.post.mockResolvedValueOnce({
        success: true,
        data: { ...mockSchedulerStatus, paused: true },
      });

      const { result } = renderHook(() => usePauseScheduler(), {
        wrapper: createWrapper(),
      });

      result.current.mutate();

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(mockApi.post).toHaveBeenCalledWith('/api/v1/scheduler/pause');
    });
  });

  describe('useResumeScheduler hook', () => {
    it('should resume scheduler successfully', async () => {
      mockApi.post.mockResolvedValueOnce({
        success: true,
        data: { ...mockSchedulerStatus, paused: false },
      });

      const { result } = renderHook(() => useResumeScheduler(), {
        wrapper: createWrapper(),
      });

      result.current.mutate();

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(mockApi.post).toHaveBeenCalledWith('/api/v1/scheduler/resume');
    });
  });

  describe('useTriggerScan hook', () => {
    it('should trigger scan successfully', async () => {
      const scanResult: ScanResult = {
        new: 5,
        updated: 3,
        pages_scanned: 3,
        scan_time: 2.5,
      };

      mockApi.post.mockResolvedValueOnce({
        success: true,
        data: scanResult,
      });

      const { result } = renderHook(() => useTriggerScan(), {
        wrapper: createWrapper(),
      });

      result.current.mutate();

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data).toEqual(scanResult);
      expect(mockApi.post).toHaveBeenCalledWith('/api/v1/scheduler/scan');
    });
  });

  describe('useTriggerProcess hook', () => {
    it('should trigger process successfully', async () => {
      const processResult: ProcessResult = {
        eligible: 10,
        entered: 5,
        failed: 0,
        points_spent: 25,
      };

      mockApi.post.mockResolvedValueOnce({
        success: true,
        data: processResult,
      });

      const { result } = renderHook(() => useTriggerProcess(), {
        wrapper: createWrapper(),
      });

      result.current.mutate();

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data).toEqual(processResult);
      expect(mockApi.post).toHaveBeenCalledWith('/api/v1/scheduler/process');
    });
  });

  describe('useSchedulerControl hook', () => {
    it('should provide all scheduler control methods', () => {
      const { result } = renderHook(() => useSchedulerControl(), {
        wrapper: createWrapper(),
      });

      expect(result.current.start).toBeDefined();
      expect(result.current.stop).toBeDefined();
      expect(result.current.pause).toBeDefined();
      expect(result.current.resume).toBeDefined();
      expect(result.current.scan).toBeDefined();
      expect(result.current.process).toBeDefined();
    });
  });
});
