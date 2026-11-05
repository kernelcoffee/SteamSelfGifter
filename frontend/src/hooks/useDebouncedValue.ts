import { useEffect, useRef, useState } from 'react';

/**
 * The value as it was `delayMs` after its content last changed. Each change
 * restarts the timer, so a burst of edits publishes once. Changes are
 * detected by content (JSON serialisation), so a new object with the same
 * content neither restarts the timer nor changes the returned value; the
 * value must therefore be JSON-serialisable.
 *
 * State is only set from the timer callback; the timer is cleared on change
 * and on unmount.
 */
export function useDebouncedValue<T>(value: T, delayMs = 400): T {
  const [debounced, setDebounced] = useState(value);
  const key = JSON.stringify(value);
  // Latest value for the timer callback, updated after every commit.
  const latest = useRef(value);

  useEffect(() => {
    latest.current = value;
  });

  useEffect(() => {
    const timer = setTimeout(() => setDebounced(latest.current), delayMs);
    return () => clearTimeout(timer);
  }, [key, delayMs]);

  return debounced;
}
