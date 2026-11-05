import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ReactNode } from 'react';
import {
  useInfiniteGiveaways,
  useGiveaways,
  useGiveaway,
  useEnterGiveaway,
  useHideGiveaway,
  useUnhideGiveaway,
  requestFilters,
} from './useGiveaways';
import { api } from '@/services/api';
import type { Giveaway } from '@/types';

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

const mockGiveaway: Giveaway = {
  id: 1,
  code: 'abc123',
  url: 'https://steamgifts.com/giveaway/abc123/',
  game_name: 'Test Game',
  game_id: 12345,
  price: 5,
  copies: 1,
  entries: 100,
  win_chance: 1.0,
  end_time: '2024-01-02T00:00:00Z',
  discovered_at: '2024-01-01T00:00:00Z',
  entered_at: null,
  is_hidden: false,
  is_entered: false,
  is_wishlist: false,
  is_dlc: false,
  is_won: false,
  won_at: null,
  is_safe: true,
  safety_score: 90,
  created_at: '2024-01-01T00:00:00Z',
  updated_at: '2024-01-01T00:00:00Z',
  eligibility_reason: null,
  eligibility_detail: null,
  eligibility_checked_at: null,
  eligibility_label: null,
  eligibility_kind: null,
};

describe('useGiveaways', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('useGiveaways hook', () => {
    it('should fetch giveaways successfully', async () => {
      // Backend returns { giveaways, count } which gets transformed to PaginatedResponse
      const backendResponse = {
        giveaways: [mockGiveaway],
        count: 1,
      };

      mockApi.get.mockResolvedValueOnce({
        success: true,
        data: backendResponse,
      });

      const { result } = renderHook(() => useGiveaways(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data).toEqual({
        items: [mockGiveaway],
        total: 1,
        page: 1,
        limit: 20,
        pages: 1,
      });
      expect(mockApi.get).toHaveBeenCalledWith('/api/v1/giveaways?limit=20');
    });

    it('should fetch with filters', async () => {
      const backendResponse = {
        giveaways: [],
        count: 0,
      };

      mockApi.get.mockResolvedValueOnce({
        success: true,
        data: backendResponse,
      });

      const { result } = renderHook(
        () => useGiveaways({ status: 'active', type: 'game', search: 'test' }),
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      // Active status uses /active endpoint, type and search are params
      expect(mockApi.get).toHaveBeenCalledWith(
        '/api/v1/giveaways/active?type=game&search=test&limit=20'
      );
    });

    it('should map chance and time-remaining filters to query params', async () => {
      mockApi.get.mockResolvedValueOnce({
        success: true,
        data: { giveaways: [], count: 0 },
      });

      const { result } = renderHook(
        () => useGiveaways({ status: 'active', minChance: 0.5, endingWithin: 360 }),
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(mockApi.get).toHaveBeenCalledWith(
        '/api/v1/giveaways/active?min_chance=0.5&ending_within=360&limit=20'
      );
    });

    it('should omit chance and time filters when zero/unset', async () => {
      mockApi.get.mockResolvedValueOnce({
        success: true,
        data: { giveaways: [], count: 0 },
      });

      const { result } = renderHook(
        () => useGiveaways({ status: 'wishlist', minChance: 0, endingWithin: 0 }),
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(mockApi.get).toHaveBeenCalledWith('/api/v1/giveaways/wishlist?limit=20');
    });

    it('should send lens=autojoin without the paused view filters when the lens is on', async () => {
      mockApi.get.mockResolvedValueOnce({
        success: true,
        data: { giveaways: [], count: 0, lens: 'autojoin', budget_applied: false },
      });

      const { result } = renderHook(
        () =>
          useGiveaways({
            status: 'wishlist',
            minChance: 50,
            minScore: 8,
            safetyFilter: 'safe',
            endingWithin: 30,
            search: 'portal',
            lens: 'autojoin',
          }),
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      // The lens answers 'what would my saved policy enter', so no view filter
      // may narrow it behind the policy's back.
      expect(mockApi.get).toHaveBeenCalledWith('/api/v1/giveaways/wishlist?lens=autojoin&limit=20');
    });

    it('should send no lens parameter when the lens is off', async () => {
      mockApi.get.mockResolvedValueOnce({ success: true, data: { giveaways: [], count: 0 } });

      const { result } = renderHook(
        () => useGiveaways({ status: 'active', lens: undefined }),
        { wrapper: createWrapper() }
      );

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      const url = String(mockApi.get.mock.calls[0][0]);
      expect(url).toBe('/api/v1/giveaways/active?limit=20');
      expect(url).not.toContain('lens');
    });

    it('should handle fetch error', async () => {
      mockApi.get.mockResolvedValueOnce({
        success: false,
        data: null,
        error: 'Failed to fetch giveaways',
      });

      const { result } = renderHook(() => useGiveaways(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(result.current.isError).toBe(true);
      });

      expect(result.current.error?.message).toBe('Failed to fetch giveaways');
    });
  });

  describe('requestFilters', () => {
    it('keeps every filter when the lens is off', () => {
      const filters = { status: 'active' as const, minScore: 8, endingWithin: 30, search: 'x', limit: 20 };
      expect(requestFilters(filters)).toEqual(filters);
    });

    it('keeps only the tab, the page size and the lens when the lens is on', () => {
      expect(
        requestFilters({
          status: 'dlc',
          limit: 40,
          minScore: 8,
          safetyFilter: 'unsafe',
          minChance: 5,
          endingWithin: 60,
          search: 'x',
          sort: 'price',
          order: 'asc',
          type: 'game',
          lens: 'autojoin',
        })
      ).toEqual({ status: 'dlc', limit: 40, lens: 'autojoin' });
    });
  });

  describe('useInfiniteGiveaways hook', () => {
    it('drops the view filters from the lens request and its query key', async () => {
      mockApi.get.mockResolvedValue({
        success: true,
        data: { giveaways: [], count: 0, lens: 'autojoin', budget_applied: false },
      });

      const { result, rerender } = renderHook(
        ({ minScore }: { minScore: number }) =>
          useInfiniteGiveaways({ status: 'active', limit: 20, minScore, endingWithin: 30, lens: 'autojoin' }),
        { wrapper: createWrapper(), initialProps: { minScore: 8 } }
      );
      await waitFor(() => expect(result.current.isSuccess).toBe(true));
      expect(mockApi.get).toHaveBeenLastCalledWith('/api/v1/giveaways/active?lens=autojoin&limit=20');

      // A different stored view filter is the same lens query: no new request.
      rerender({ minScore: 3 });
      expect(result.current.isSuccess).toBe(true);
      expect(mockApi.get).toHaveBeenCalledTimes(1);
    });

    it('keys the lens into the query and pages the candidates by offset with their total', async () => {
      const candidate = {
        ...mockGiveaway,
        decision: {
          code: 'eligible',
          label: 'Joinable',
          detail: { priority: 'wishlist' as const, rank: 0, lifted_by: 'wishlist' as const },
          priority: 'wishlist' as const,
          rank: 0,
          lifted_by: 'wishlist' as const,
        },
      };
      mockApi.get
        .mockResolvedValueOnce({
          success: true,
          data: { giveaways: [candidate, { ...candidate, id: 2 }], count: 3, lens: 'autojoin', budget_applied: false },
        })
        .mockResolvedValueOnce({
          success: true,
          data: { giveaways: [{ ...candidate, id: 3 }], count: 3, lens: 'autojoin', budget_applied: false },
        })
        .mockResolvedValueOnce({ success: true, data: { giveaways: [mockGiveaway], count: 1 } });

      const { result, rerender } = renderHook(
        ({ lens }: { lens?: 'autojoin' }) => useInfiniteGiveaways({ status: 'active', limit: 2, lens }),
        { wrapper: createWrapper(), initialProps: { lens: 'autojoin' } }
      );

      await waitFor(() => expect(result.current.isSuccess).toBe(true));
      expect(mockApi.get).toHaveBeenLastCalledWith('/api/v1/giveaways/active?lens=autojoin&limit=2');
      expect(result.current.data?.pages[0].count).toBe(3);
      expect(result.current.data?.pages[0].giveaways[0].decision?.label).toBe('Joinable');
      expect(result.current.hasNextPage).toBe(true);

      await result.current.fetchNextPage();
      await waitFor(() => expect(result.current.data?.pages).toHaveLength(2));
      expect(mockApi.get).toHaveBeenLastCalledWith('/api/v1/giveaways/active?lens=autojoin&limit=2&offset=2');
      expect(result.current.hasNextPage).toBe(false);

      // Turning the lens off is a different query (key includes the lens).
      rerender({ lens: undefined });
      await waitFor(() => expect(mockApi.get).toHaveBeenCalledTimes(3));
      expect(mockApi.get).toHaveBeenLastCalledWith('/api/v1/giveaways/active?limit=2');
    });
  });

  describe('useGiveaway hook', () => {
    it('should fetch single giveaway successfully', async () => {
      mockApi.get.mockResolvedValueOnce({
        success: true,
        data: mockGiveaway,
      });

      const { result } = renderHook(() => useGiveaway(1), {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data).toEqual(mockGiveaway);
      expect(mockApi.get).toHaveBeenCalledWith('/api/v1/giveaways/1');
    });

    it('should not fetch if id is 0', () => {
      const { result } = renderHook(() => useGiveaway(0), {
        wrapper: createWrapper(),
      });

      expect(result.current.isFetching).toBe(false);
      expect(mockApi.get).not.toHaveBeenCalled();
    });
  });

  describe('useEnterGiveaway hook', () => {
    it('should enter giveaway successfully', async () => {
      mockApi.post.mockResolvedValueOnce({
        success: true,
        data: { success: true, entry_id: 123 },
      });

      const { result } = renderHook(() => useEnterGiveaway(), {
        wrapper: createWrapper(),
      });

      // Mutation takes giveaway code as string
      result.current.mutate('abc123');

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data).toEqual({ success: true, entry_id: 123 });
      expect(mockApi.post).toHaveBeenCalledWith('/api/v1/giveaways/abc123/enter');
    });

    it('should handle enter error', async () => {
      mockApi.post.mockResolvedValueOnce({
        success: false,
        data: null,
        error: 'Already entered',
      });

      const { result } = renderHook(() => useEnterGiveaway(), {
        wrapper: createWrapper(),
      });

      result.current.mutate('abc123');

      await waitFor(() => {
        expect(result.current.isError).toBe(true);
      });

      expect(result.current.error?.message).toBe('Already entered');
    });
  });

  describe('useHideGiveaway hook', () => {
    it('should hide giveaway successfully', async () => {
      // API returns { message, code } not the full giveaway
      const hideResponse = { message: 'Giveaway hidden', code: 'abc123' };

      mockApi.post.mockResolvedValueOnce({
        success: true,
        data: hideResponse,
      });

      const { result } = renderHook(() => useHideGiveaway(), {
        wrapper: createWrapper(),
      });

      // Mutation takes giveaway code as string
      result.current.mutate('abc123');

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data).toEqual(hideResponse);
      expect(mockApi.post).toHaveBeenCalledWith('/api/v1/giveaways/abc123/hide');
    });
  });

  describe('useUnhideGiveaway hook', () => {
    it('should unhide giveaway successfully', async () => {
      // API returns { message, code } not the full giveaway
      const unhideResponse = { message: 'Giveaway unhidden', code: 'abc123' };

      mockApi.post.mockResolvedValueOnce({
        success: true,
        data: unhideResponse,
      });

      const { result } = renderHook(() => useUnhideGiveaway(), {
        wrapper: createWrapper(),
      });

      // Mutation takes giveaway code as string
      result.current.mutate('abc123');

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data).toEqual(unhideResponse);
      expect(mockApi.post).toHaveBeenCalledWith('/api/v1/giveaways/abc123/unhide');
    });
  });
});
