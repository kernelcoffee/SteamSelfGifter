import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ReactNode } from 'react';
import { useGameGenres, useRefreshGame, gameKeys } from './useGames';
import { api } from '@/services/api';
import type { GenreList } from '@/types';

vi.mock('@/services/api', () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
    getGameGenres: vi.fn(),
  },
}));

const mockApi = vi.mocked(api);

function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
}

function createWrapper(queryClient = createTestQueryClient()) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  };
}

describe('useGameGenres', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('returns the genre list from the genres endpoint', async () => {
    const genres = [
      { name: 'Action', count: 12 },
      { name: 'Indie', count: 9 },
      { name: 'Animation & Modeling', count: 1 },
    ];
    mockApi.getGameGenres.mockResolvedValue({ success: true, data: { genres } });

    const { result } = renderHook(() => useGameGenres(), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual(genres);
    expect(mockApi.getGameGenres).toHaveBeenCalledTimes(1);
  });

  it('surfaces the API error message', async () => {
    mockApi.getGameGenres.mockResolvedValue({
      success: false,
      data: null as unknown as GenreList,
      error: 'boom',
    });

    const { result } = renderHook(() => useGameGenres(), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error?.message).toBe('boom');
  });

  it('falls back to a generic message when the API gives none', async () => {
    mockApi.getGameGenres.mockResolvedValue({
      success: false,
      data: null as unknown as GenreList,
    });

    const { result } = renderHook(() => useGameGenres(), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error?.message).toBe('Failed to fetch game genres');
  });

  it('resolves to an empty list when the response has no genres key', async () => {
    mockApi.getGameGenres.mockResolvedValue({
      success: true,
      data: {} as GenreList,
    });

    const { result } = renderHook(() => useGameGenres(), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual([]);
  });
});

describe('useRefreshGame', () => {
  it('invalidates the genre list, since a refresh can change a game\'s genres', async () => {
    mockApi.post.mockResolvedValue({ success: true, data: { id: 10 } });
    const queryClient = createTestQueryClient();
    const invalidate = vi.spyOn(queryClient, 'invalidateQueries');

    const { result } = renderHook(() => useRefreshGame(), {
      wrapper: createWrapper(queryClient),
    });
    await result.current.mutateAsync(10);

    expect(mockApi.post).toHaveBeenCalledWith('/api/v1/games/10/refresh');
    expect(invalidate).toHaveBeenCalledWith({ queryKey: gameKeys.genres() });
  });
});
