import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ReactNode } from 'react';
import {
  useDashboard,
  useEntryStats,
  useGiveawayStats,
  useGameStats,
  useEntryTrends,
} from './useAnalytics';
import { api } from '@/services/api';
import type { DashboardData, EntryStats, GiveawayStats, GameStats } from '@/types';

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

const mockDashboard: DashboardData = {
  session: {
    configured: true,
    valid: true,
    username: 'testuser',
    error: null,
  },
  points: { current: 500 },
  entries: { total: 100, today: 5, entered_30d: 80, wins_30d: 2, win_rate: 2.5 },
  giveaways: { active: 50, entered: 30, wins: 2 },
  safety: { checked: 40, safe: 35, unsafe: 5, unchecked: 10 },
  scheduler: {
    running: true,
    paused: false,
    last_scan: '2024-01-01T00:00:00Z',
    next_scan: '2024-01-01T00:30:00Z',
  },
};

const mockEntryStats: EntryStats = {
  total: 100,
  successful: 95,
  failed: 5,
  total_points_spent: 500,
  success_rate: 95.0,
  by_type: { manual: 20, auto: 70, wishlist: 10 },
};

const mockGiveawayStats: GiveawayStats = {
  total: 200,
  active: 50,
  entered: 30,
  hidden: 10,
  wins: 5,
  win_rate: 2.5,
};

const mockGameStats: GameStats = {
  total_games: 150,
  games: 100,
  dlc: 40,
  bundles: 10,
  stale_games: 5,
};

describe('useAnalytics', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('useDashboard hook', () => {
    it('should fetch dashboard data successfully', async () => {
      mockApi.get.mockResolvedValueOnce({
        success: true,
        data: mockDashboard,
      });

      const { result } = renderHook(() => useDashboard(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data).toEqual(mockDashboard);
      expect(mockApi.get).toHaveBeenCalledWith('/api/v1/analytics/dashboard');
    });

    it('should handle fetch error', async () => {
      mockApi.get.mockResolvedValueOnce({
        success: false,
        data: null,
        error: 'Failed to fetch dashboard',
      });

      const { result } = renderHook(() => useDashboard(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(result.current.isError).toBe(true);
      });

      expect(result.current.error?.message).toBe('Failed to fetch dashboard');
    });
  });

  describe('useEntryStats hook', () => {
    it('should fetch entry stats successfully', async () => {
      // Backend returns different field names that get transformed
      const backendResponse = {
        total_entries: 100,
        successful_entries: 95,
        failed_entries: 5,
        success_rate: 95.0,
        total_points_spent: 500,
        average_points_per_entry: 5,
        by_type: { manual: 20, auto: 70, wishlist: 10 },
      };

      mockApi.get.mockResolvedValueOnce({
        success: true,
        data: backendResponse,
      });

      const { result } = renderHook(() => useEntryStats(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      // Hook transforms backend response to frontend format
      expect(result.current.data).toEqual(mockEntryStats);
      expect(mockApi.get).toHaveBeenCalledWith('/api/v1/analytics/entries/summary');
    });

    it('should fetch with time range filter', async () => {
      const backendResponse = {
        total_entries: 100,
        successful_entries: 95,
        failed_entries: 5,
        success_rate: 95.0,
        total_points_spent: 500,
        average_points_per_entry: 5,
        by_type: { manual: 20, auto: 70, wishlist: 10 },
      };

      mockApi.get.mockResolvedValueOnce({
        success: true,
        data: backendResponse,
      });

      const { result } = renderHook(
        () => useEntryStats({ period: 'week' }),
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(mockApi.get).toHaveBeenCalledWith('/api/v1/analytics/entries/summary?period=week');
    });
  });

  describe('useGiveawayStats hook', () => {
    it('should fetch giveaway stats successfully', async () => {
      // Backend returns different field names that get transformed
      const backendResponse = {
        total_giveaways: 200,
        active_giveaways: 50,
        entered_giveaways: 30,
        hidden_giveaways: 10,
        expiring_24h: 5,
        wins: 5,
        win_rate: 2.5,
      };

      mockApi.get.mockResolvedValueOnce({
        success: true,
        data: backendResponse,
      });

      const { result } = renderHook(() => useGiveawayStats(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      // Hook transforms backend response to frontend format
      expect(result.current.data).toEqual(mockGiveawayStats);
      expect(mockApi.get).toHaveBeenCalledWith('/api/v1/analytics/giveaways/summary');
    });
  });

  describe('useGameStats hook', () => {
    it('should fetch game stats successfully', async () => {
      mockApi.get.mockResolvedValueOnce({
        success: true,
        data: mockGameStats,
      });

      const { result } = renderHook(() => useGameStats(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data).toEqual(mockGameStats);
      expect(mockApi.get).toHaveBeenCalledWith('/api/v1/analytics/games/summary');
    });
  });

  describe('useEntryTrends hook', () => {
    it('should fetch entry trends successfully', async () => {
      const mockTrends = [
        { date: '2024-01-01', entries: 10, points_spent: 50 },
        { date: '2024-01-02', entries: 15, points_spent: 75 },
      ];

      mockApi.get.mockResolvedValueOnce({
        success: true,
        data: mockTrends,
      });

      const { result } = renderHook(() => useEntryTrends('month'), {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data).toEqual(mockTrends);
      expect(mockApi.get).toHaveBeenCalledWith('/api/v1/analytics/entries/trends?period=month');
    });
  });
});
