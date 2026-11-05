import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { act, renderHook } from '@testing-library/react';
import { useDebouncedValue } from './useDebouncedValue';

describe('useDebouncedValue', () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it('starts with the initial value', () => {
    const { result } = renderHook(() => useDebouncedValue('a', 400));
    expect(result.current).toBe('a');
  });

  it('publishes a burst of changes once, 400 ms after the last one', () => {
    const { result, rerender } = renderHook(({ value }) => useDebouncedValue(value, 400), {
      initialProps: { value: '7' },
    });

    rerender({ value: '6' });
    act(() => vi.advanceTimersByTime(100));
    rerender({ value: '5' });
    act(() => vi.advanceTimersByTime(100));
    rerender({ value: '4' });

    act(() => vi.advanceTimersByTime(399));
    expect(result.current).toBe('7');
    act(() => vi.advanceTimersByTime(1));
    expect(result.current).toBe('4');
  });

  it('uses 400 ms by default', () => {
    const { result, rerender } = renderHook(({ value }) => useDebouncedValue(value), {
      initialProps: { value: 1 },
    });
    rerender({ value: 2 });
    act(() => vi.advanceTimersByTime(399));
    expect(result.current).toBe(1);
    act(() => vi.advanceTimersByTime(1));
    expect(result.current).toBe(2);
  });

  it('a new object with the same content neither restarts the timer nor changes identity', () => {
    const first = { min: 7, genres: ['Action'] };
    const { result, rerender } = renderHook(({ value }) => useDebouncedValue(value, 400), {
      initialProps: { value: first },
    });

    const changed = { min: 5, genres: ['Action'] };
    rerender({ value: changed });
    act(() => vi.advanceTimersByTime(300));
    // Same content, new identity: the pending timer keeps running.
    rerender({ value: { min: 5, genres: ['Action'] } });
    act(() => vi.advanceTimersByTime(100));
    expect(result.current).toEqual(changed);

    const published = result.current;
    rerender({ value: { min: 5, genres: ['Action'] } });
    act(() => vi.advanceTimersByTime(1000));
    expect(result.current).toBe(published);
  });

  it('clears the pending timer on unmount', () => {
    const { rerender, unmount } = renderHook(({ value }) => useDebouncedValue(value, 400), {
      initialProps: { value: 'a' },
    });
    rerender({ value: 'b' });
    expect(vi.getTimerCount()).toBe(1);
    unmount();
    expect(vi.getTimerCount()).toBe(0);
  });
});
