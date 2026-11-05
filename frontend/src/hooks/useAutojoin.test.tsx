import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { autojoinKeys, useAutojoinPreview, useAutojoinRegistry } from './useAutojoin';
import { api } from '@/services/api';
import type { PolicyPreviewRequest } from '@/types';
import { makePreview, testRegistry } from '@/test/fixtures';

vi.mock('@/services/api', () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
}));

const mockApi = vi.mocked(api);

function setup() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: Infinity } },
  });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  return { client, wrapper };
}

const policy: PolicyPreviewRequest = {
  autojoin_min_price: 10,
  autojoin_min_score: 7,
  autojoin_min_reviews: null,
  autojoin_max_game_age: null,
  excluded_genres: ['Sports'],
  included_genres: [],
  autojoin_priorities: [{ type: 'wishlist' }],
};

describe('useAutojoinRegistry', () => {
  beforeEach(() => vi.clearAllMocks());

  it('fetches the registry under a constant key and never marks it stale', async () => {
    mockApi.get.mockResolvedValue({ success: true, data: testRegistry });
    const { client, wrapper } = setup();

    const { result } = renderHook(() => useAutojoinRegistry(), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual(testRegistry);
    expect(mockApi.get).toHaveBeenCalledWith('/api/v1/giveaways/registry');
    expect(autojoinKeys.registry).toEqual(['autojoin', 'registry']);
    const query = client.getQueryCache().find({ queryKey: autojoinKeys.registry, exact: true });
    expect(query?.isStale()).toBe(false);
    expect(query?.options).toMatchObject({ staleTime: Infinity });
  });

  it('a second consumer reuses the cached registry without a new request', async () => {
    mockApi.get.mockResolvedValue({ success: true, data: testRegistry });
    const { wrapper } = setup();
    const first = renderHook(() => useAutojoinRegistry(), { wrapper });
    await waitFor(() => expect(first.result.current.isSuccess).toBe(true));

    const second = renderHook(() => useAutojoinRegistry(), { wrapper });
    expect(second.result.current.data).toEqual(testRegistry);
    expect(mockApi.get).toHaveBeenCalledTimes(1);
  });

  it('surfaces a failed envelope as an error with the backend message', async () => {
    mockApi.get.mockResolvedValue({ success: false, data: null, error: 'Registry exploded' });
    const { wrapper } = setup();

    const { result } = renderHook(() => useAutojoinRegistry(), { wrapper });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error?.message).toBe('Registry exploded');
    expect(result.current.data).toBeUndefined();
  });
});

describe('useAutojoinPreview', () => {
  beforeEach(() => vi.clearAllMocks());

  it('sends nothing while disabled', async () => {
    const { wrapper } = setup();
    const { result } = renderHook(() => useAutojoinPreview(policy, false), { wrapper });

    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(mockApi.post).not.toHaveBeenCalled();
    expect(result.current.fetchStatus).toBe('idle');
  });

  it('posts the policy body to the limit=1 preview URL', async () => {
    mockApi.post.mockResolvedValue({ success: true, data: makePreview() });
    const { wrapper } = setup();

    const { result } = renderHook(() => useAutojoinPreview(policy, true), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockApi.post).toHaveBeenCalledWith('/api/v1/giveaways/preview?limit=1', policy);
    expect(result.current.data?.count).toBe(3);
    expect(autojoinKeys.preview(policy)).toEqual(['autojoin', 'preview', policy]);
  });

  it('keeps the previous result as placeholder while a new policy loads', async () => {
    mockApi.post.mockResolvedValueOnce({ success: true, data: makePreview({ count: 3 }) });
    const { wrapper } = setup();
    const { result, rerender } = renderHook(
      ({ body }: { body: PolicyPreviewRequest }) => useAutojoinPreview(body, true),
      { wrapper, initialProps: { body: policy } },
    );
    await waitFor(() => expect(result.current.data?.count).toBe(3));

    let resolveNext: (value: Awaited<ReturnType<typeof api.post>>) => void = () => {};
    mockApi.post.mockReturnValueOnce(
      new Promise((resolve) => {
        resolveNext = resolve;
      }),
    );
    rerender({ body: { ...policy, autojoin_min_score: 3 } });

    await waitFor(() => expect(result.current.isPlaceholderData).toBe(true));
    expect(result.current.data?.count).toBe(3);

    resolveNext({ success: true, data: makePreview({ count: 5 }) });
    await waitFor(() => expect(result.current.data?.count).toBe(5));
    expect(result.current.isPlaceholderData).toBe(false);
  });

  it('surfaces a failed envelope as an error, never as data', async () => {
    mockApi.post.mockResolvedValue({ success: false, data: null, error: 'Pool unavailable' });
    const { wrapper } = setup();

    const { result } = renderHook(() => useAutojoinPreview(policy, true), { wrapper });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error?.message).toBe('Pool unavailable');
    expect(result.current.data).toBeUndefined();
  });

  it('two policies with the same content share one request', async () => {
    mockApi.post.mockResolvedValue({ success: true, data: makePreview() });
    const { wrapper } = setup();
    renderHook(() => useAutojoinPreview({ ...policy }, true), { wrapper });
    const second = renderHook(() => useAutojoinPreview({ ...policy }, true), { wrapper });

    await waitFor(() => expect(second.result.current.isSuccess).toBe(true));
    expect(mockApi.post).toHaveBeenCalledTimes(1);
  });
});
