import { describe, it, expect } from 'vitest';

// Every source module (tests excluded), as text.
const sources = import.meta.glob(['/src/**/*.{ts,tsx}', '!/src/**/*.test.{ts,tsx}'], {
  query: '?raw',
  import: 'default',
  eager: true,
});

describe('frontend source: the auto-join registry is fetched, never mirrored', () => {
  it('reads the sources', () => {
    expect(Object.keys(sources).length).toBeGreaterThan(20);
    expect(Object.keys(sources)).toContain('/src/pages/Settings.tsx');
  });

  it.each([
    'PRIORITY_TYPE_META',
    'THRESHOLD_MIN',
    'THRESHOLD_MAX',
    'THRESHOLD_DEFAULT',
    'EXCLUDED_GENRES_MAX_ITEMS',
    'EXCLUDED_GENRE_MAX_LENGTH',
    'ENDING_SOON_THRESHOLD_',
  ])('no module defines %s', (name) => {
    const offenders = Object.entries(sources)
      .filter(([, text]) => typeof text === 'string' && text.includes(name))
      .map(([path]) => path);
    expect(offenders).toEqual([]);
  });

  it('has no candidates route, Sidebar entry or page status', () => {
    const text = (path: string) => {
      const value = sources[path];
      return typeof value === 'string' ? value : '';
    };
    const routeOffenders = Object.keys(sources).filter((path) => text(path).includes('/giveaways/candidates'));
    expect(routeOffenders).toEqual([]);
    expect(text('/src/components/layout/Sidebar.tsx')).not.toMatch(/candidates/i);
    const pageStatus = text('/src/pages/Giveaways.tsx').match(/export type GiveawayPageStatus = [^;]*;/);
    expect(pageStatus?.[0]).toBeDefined();
    expect(pageStatus?.[0]).not.toContain('candidates');
    const filterStatus = text('/src/hooks/useGiveaways.ts').match(/status\?: [^;]*;/);
    expect(filterStatus?.[0]).toBeDefined();
    expect(filterStatus?.[0]).not.toContain('candidates');
  });
});
