// Type shim: @testing-library/jest-dom 7.0.x still augments Vitest's
// `Assertion<T>` with a single type parameter, which no longer merges with
// Vitest 5's `Assertion<R, T>` — so `toBeInTheDocument()` and friends type
// as missing even though they work at runtime. Vitest's documented extension
// point is `Matchers<R, T>`, so wire the jest-dom matchers in through that.
// The type parameters must match Vitest's declaration exactly for the
// interfaces to merge.
//
// Drop this file (and keep only the `/vitest` import in setup.ts) once
// jest-dom ships Vitest 5 support:
// https://github.com/testing-library/jest-dom/issues/738
import 'vitest';
import type { TestingLibraryMatchers } from '@testing-library/jest-dom/matchers';

declare module 'vitest' {
  // Declaration merging: the body is intentionally empty and `T` must be
  // declared (unused) to mirror Vitest's own type parameters.
  // eslint-disable-next-line @typescript-eslint/no-empty-object-type, @typescript-eslint/no-unused-vars
  interface Matchers<R extends void | Promise<void> = void | Promise<void>, T = unknown>
    extends TestingLibraryMatchers<unknown, R> {}
}
