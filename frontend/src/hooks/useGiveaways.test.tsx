import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ReactNode } from 'react';
import {
  useGiveaways,
  useGiveaway,
  useEnterGiveaway,
  useHideGiveaway,
  useUnhideGiveaway,
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
  end_time: '2024-01-02T00:00:00Z',
  discovered_at: '2024-01-01T00:00:00Z',
  entered_at: null,
  is_hidden: false,
  is_entered: false,
  is_wishlist: false,
  is_won: false,
  won_at: null,
  is_safe: true,
  safety_score: 90,
  created_at: '2024-01-01T00:00:00Z',
  updated_at: '2024-01-01T00:00:00Z',
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
