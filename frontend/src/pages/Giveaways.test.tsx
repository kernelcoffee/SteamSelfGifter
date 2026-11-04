import { describe, it, expect, vi, beforeEach } from 'vitest';
import { Link, Route, Routes } from 'react-router';
import { render, screen, within, userEvent, waitFor } from '@/test/utils';
import { Giveaways } from './Giveaways';
import { api } from '@/services/api';
import { useGiveawayFiltersStore } from '@/stores/giveawayFiltersStore';
import type { Giveaway, Settings } from '@/types';
import { makeGiveaway, testRegistry, testSettings } from '@/test/fixtures';

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

const baseGiveaway: Giveaway = makeGiveaway();

interface ServerOptions {
  giveaways?: Giveaway[];
  lensGiveaways?: Giveaway[];
  lensError?: string;
  settings?: Partial<Settings>;
  registryError?: boolean;
}

/** Dispatch GETs by URL: giveaway lists (with or without the lens), settings, registry. */
function mockServer({
  giveaways = [baseGiveaway],
  lensGiveaways = [],
  lensError,
  settings = {},
  registryError = false,
}: ServerOptions = {}) {
  mockApi.get.mockImplementation(async (url: string) => {
    if (url.startsWith('/api/v1/settings')) {
      return { success: true, data: { ...testSettings, ...settings } };
    }
    if (url.startsWith('/api/v1/giveaways/registry')) {
      return registryError
        ? { success: false, data: null, error: 'Registry down' }
        : { success: true, data: testRegistry };
    }
    if (url.includes('lens=autojoin')) {
      if (lensError) return { success: false, data: null, error: lensError };
      return {
        success: true,
        data: { giveaways: lensGiveaways, count: lensGiveaways.length, lens: 'autojoin', budget_applied: false },
      };
    }
    return { success: true, data: { giveaways, count: giveaways.length } };
  });
}

function listCalls(): string[] {
  return mockApi.get.mock.calls
    .map(([url]) => String(url))
    .filter((url) => /^\/api\/v1\/giveaways(\/(active|wishlist|dlc))?\?/.test(url));
}

async function renderWith(over: Partial<Giveaway>) {
  mockServer({ giveaways: [{ ...baseGiveaway, ...over }] });
  render(<Giveaways />);
  return screen.findByRole('heading', { name: 'Hollow Knight', level: 3 });
}

describe('Giveaways page: genre line on cards', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useGiveawayFiltersStore.getState().resetFilters();
  });

  it('shows the first three genres then +N, with the full list in the title', async () => {
    const heading = await renderWith({
      game_genres: ['Action', 'Indie', 'RPG', 'Strategy'],
    });

    const line = screen.getByTitle('Action, Indie, RPG, Strategy');
    expect(line).toHaveTextContent('Action, Indie, RPG +1');
    expect(heading.parentElement).toContainElement(line);
  });

  it('keeps the +N counter out of the truncated part so it stays visible', async () => {
    await renderWith({
      game_genres: ['Massively Multiplayer', 'Simulation', 'Strategy', 'Indie', 'RPG'],
    });

    const line = screen.getByTitle('Massively Multiplayer, Simulation, Strategy, Indie, RPG');
    const names = within(line).getByText('Massively Multiplayer, Simulation, Strategy');
    const counter = within(line).getByText('+2');
    expect(names).toHaveClass('truncate');
    expect(counter).toHaveClass('shrink-0');
    expect(counter).not.toHaveClass('truncate');
    expect(names).not.toContainElement(counter);
  });

  it('shows all genres without a counter when there are three or fewer', async () => {
    await renderWith({ game_genres: ['Animation & Modeling', 'Utilities'] });

    const line = screen.getByTitle('Animation & Modeling, Utilities');
    expect(line).toHaveTextContent(/^Animation & Modeling, Utilities$/);
  });

  it.each([
    ['null', null],
    ['an empty list', []],
    ['missing', undefined],
  ])('renders no genre line when game_genres is %s', async (_label, genres) => {
    const heading = await renderWith({ game_genres: genres });

    expect(heading.parentElement?.querySelector('p')).toBeNull();
  });
});

const candidate: Giveaway = makeGiveaway({
  id: 7,
  code: 'Cand7',
  game_name: 'Celeste',
  eligibility_reason: 'score_below_min',
  eligibility_label: 'Review score 6 is below your minimum 7',
  eligibility_kind: 'filter',
  decision: {
    code: 'eligible',
    label: 'Joinable',
    detail: { priority: 'wishlist', rank: 0, lifted_by: 'wishlist' },
    priority: 'wishlist',
    rank: 0,
    lifted_by: 'wishlist',
  },
});

describe('Giveaways page: auto-join line', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useGiveawayFiltersStore.getState().resetFilters();
  });

  it('shows "Not evaluated yet" when no decision is recorded', async () => {
    await renderWith({});
    expect(screen.getByText('Auto-join:')).toBeInTheDocument();
    expect(screen.getByText('Not evaluated yet; checked at the next cycle')).toBeInTheDocument();
  });

  it("shows the stored label with the server's wording for budget codes", async () => {
    await renderWith({
      eligibility_reason: 'budget_floor',
      eligibility_detail: { price: 50, points: 230, stop_at: 200 },
      eligibility_label: 'Not entered last cycle: 50P would leave 180P, below your 200P floor',
      eligibility_kind: 'budget',
    });
    expect(
      screen.getByText('Not entered last cycle: 50P would leave 180P, below your 200P floor'),
    ).toBeInTheDocument();
  });

  it('shows no Auto-join line on entered or expired giveaways', async () => {
    mockServer({
      giveaways: [
        makeGiveaway({ id: 1, game_name: 'Entered One', is_entered: true }),
        makeGiveaway({ id: 2, game_name: 'Old One', end_time: '2020-01-01T00:00:00Z' }),
      ],
    });
    render(<Giveaways />);
    await screen.findByRole('heading', { name: 'Entered One' });

    expect(screen.queryByText('Auto-join:')).not.toBeInTheDocument();
  });

  it('shows neither the lens toggle nor the line on the Entered tab', async () => {
    mockServer({ giveaways: [makeGiveaway({ is_entered: false })] });
    render(<Giveaways status="entered" />);
    await screen.findByRole('heading', { name: 'Hollow Knight', level: 3 });

    expect(screen.queryByRole('switch', { name: 'Auto-join lens' })).not.toBeInTheDocument();
    expect(screen.queryByText('Auto-join:')).not.toBeInTheDocument();
  });
});

describe('Giveaways page: auto-join lens', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useGiveawayFiltersStore.getState().resetFilters();
  });

  it('is off by default and sends lens=autojoin once turned on, showing live decisions', async () => {
    const user = userEvent.setup();
    mockServer({ giveaways: [candidate], lensGiveaways: [candidate] });
    render(<Giveaways />);
    await screen.findByText('Review score 6 is below your minimum 7');

    const toggle = screen.getByRole('switch', { name: 'Auto-join lens' });
    expect(toggle).toHaveAttribute('aria-checked', 'false');
    expect(listCalls().every((url) => !url.includes('lens'))).toBe(true);

    await user.click(toggle);

    await waitFor(() => expect(listCalls().some((url) => url.includes('lens=autojoin'))).toBe(true));
    expect(listCalls()[listCalls().length - 1]).toMatch(/^\/api\/v1\/giveaways\/active\?lens=autojoin/);
    expect(
      await screen.findByTitle('Joinable: Wishlist, filters skipped, 1st in your order'),
    ).toBeInTheDocument();
    expect(screen.queryByText('Review score 6 is below your minimum 7')).not.toBeInTheDocument();
    expect(
      screen.getByText('1 candidate in entry order; the points budget and per cycle cap apply at cycle time'),
    ).toBeInTheDocument();
    expect(mockApi.put).not.toHaveBeenCalled();
  });

  it('pauses stored view filters while the lens is on, so only the saved policy decides', async () => {
    const user = userEvent.setup();
    useGiveawayFiltersStore
      .getState()
      .setFilters({ minScore: 8, safetyFilter: 'safe', minChance: 50, endingWithin: 30 });
    mockServer({ lensGiveaways: [] });
    render(<Giveaways />);

    // Lens off: the stored view filters narrow the browse list.
    await waitFor(() =>
      expect(listCalls()).toContain(
        '/api/v1/giveaways/active?min_score=8&is_safe=true&min_chance=50&ending_within=30&limit=20',
      ),
    );
    await user.click(await screen.findByRole('switch', { name: 'Auto-join lens' }));

    // Lens on: none of them reaches the request, so an empty result really
    // means the saved policy enters nothing here.
    await waitFor(() => expect(listCalls()).toContain('/api/v1/giveaways/active?lens=autojoin&limit=20'));
    expect(listCalls().filter((url) => url.includes('lens=autojoin'))).toEqual([
      '/api/v1/giveaways/active?lens=autojoin&limit=20',
    ]);
    expect(
      await screen.findByText(/Nothing on this tab passes your saved auto-join policy/),
    ).toBeInTheDocument();

    // The controls say so: disabled, pointing at the visible reason.
    const reason = screen.getByText(
      'View filters are paused while the Auto-join lens is on: the list is your saved policy alone.',
    );
    for (const control of [
      screen.getByRole('slider', { name: 'Show score at least' }),
      screen.getByRole('slider', { name: 'Minimum win chance' }),
      screen.getByRole('slider', { name: 'Ending within' }),
      screen.getByRole('combobox', { name: 'Safety' }),
      screen.getByRole('textbox', { name: 'Search games' }),
    ]) {
      expect(control).toBeDisabled();
      expect(control).toHaveAttribute('aria-describedby', reason.id);
    }
    expect(screen.queryByTitle('Clear filter')).not.toBeInTheDocument();
    // The stored values are kept for when the lens goes off again.
    expect(useGiveawayFiltersStore.getState().filters).toMatchObject({ minScore: 8, minChance: 50 });

    await user.click(screen.getByRole('switch', { name: 'Auto-join lens' }));
    expect(screen.getByRole('slider', { name: 'Show score at least' })).toBeEnabled();
    expect(screen.getByText('View filters change only what you see; auto-join uses Settings.')).toBeInTheDocument();
  });

  it('keeps the search box showing the stored search after a tab switch', async () => {
    const user = userEvent.setup();
    mockServer();
    window.history.pushState({}, '', '/giveaways/entered');
    render(
      <>
        <Link to="/giveaways/entered">Entered tab</Link>
        <Link to="/giveaways">Active tab</Link>
        <Routes>
          <Route path="/giveaways" element={<Giveaways status="active" />} />
          <Route path="/giveaways/entered" element={<Giveaways status="entered" />} />
        </Routes>
      </>,
    );

    await user.type(await screen.findByRole('textbox', { name: 'Search games' }), 'portal');
    await user.click(screen.getByRole('button', { name: 'Search' }));
    await waitFor(() => expect(listCalls().some((url) => url.includes('search=portal'))).toBe(true));

    await user.click(screen.getByRole('link', { name: 'Active tab' }));
    await screen.findByRole('switch', { name: 'Auto-join lens' });
    await user.click(screen.getByRole('link', { name: 'Entered tab' }));

    // The list is still filtered by the stored term, and the box says so.
    expect(await screen.findByRole('textbox', { name: 'Search games' })).toHaveValue('portal');
    expect(listCalls()[listCalls().length - 1]).toContain('search=portal');
    window.history.pushState({}, '', '/');
  });

  it('never stores the lens in the persisted filter store', async () => {
    const user = userEvent.setup();
    mockServer({ lensGiveaways: [candidate] });
    render(<Giveaways />);

    await user.click(await screen.findByRole('switch', { name: 'Auto-join lens' }));

    expect(Object.keys(useGiveawayFiltersStore.getState().filters)).not.toContain('lens');
    const writes = vi.mocked(window.localStorage.setItem).mock.calls.map(([, value]) => String(value));
    expect(writes.every((value) => !value.includes('lens'))).toBe(true);
  });

  it('starts off again on every tab: switching tabs with the lens on sends no lens request', async () => {
    const user = userEvent.setup();
    mockServer({ lensGiveaways: [] });
    window.history.pushState({}, '', '/giveaways');
    // The same route table as App.tsx: one <Giveaways> element per tab.
    render(
      <>
        <Link to="/giveaways">Active tab</Link>
        <Link to="/giveaways/wishlist">Wishlist tab</Link>
        <Routes>
          <Route path="/giveaways" element={<Giveaways status="active" />} />
          <Route path="/giveaways/wishlist" element={<Giveaways status="wishlist" />} />
        </Routes>
      </>,
    );

    await user.click(await screen.findByRole('switch', { name: 'Auto-join lens' }));
    await waitFor(() => expect(listCalls().some((url) => url.startsWith('/api/v1/giveaways/active?lens=autojoin'))).toBe(true));

    await user.click(screen.getByRole('link', { name: 'Wishlist tab' }));
    await screen.findByText('Wishlist giveaways skip the filters and are entered 1st');
    expect(screen.getByRole('switch', { name: 'Auto-join lens' })).not.toBeChecked();
    await waitFor(() => expect(listCalls().some((url) => url.startsWith('/api/v1/giveaways/wishlist?'))).toBe(true));
    expect(listCalls().filter((url) => url.startsWith('/api/v1/giveaways/wishlist')).every((url) => !url.includes('lens'))).toBe(true);

    await user.click(screen.getByRole('link', { name: 'Active tab' }));
    expect(await screen.findByRole('switch', { name: 'Auto-join lens' })).not.toBeChecked();
    window.history.pushState({}, '', '/');
  });

  it('says nothing passes the saved policy when the lens list is empty', async () => {
    const user = userEvent.setup();
    mockServer({ lensGiveaways: [] });
    render(<Giveaways />);

    await user.click(await screen.findByRole('switch', { name: 'Auto-join lens' }));

    expect(
      await screen.findByText(/Nothing on this tab passes your saved auto-join policy\. The budget and cap apply at cycle time\./),
    ).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Adjust it in Settings' })).toHaveAttribute('href', '/settings');
  });

  it('shows the lens error with a retry, and the toggle stays reachable', async () => {
    const user = userEvent.setup();
    mockServer({ lensError: 'ConfigurationError: invalid autojoin_priorities' });
    render(<Giveaways />);

    await user.click(await screen.findByRole('switch', { name: 'Auto-join lens' }));

    expect(
      await screen.findByText('Could not load the auto-join lens: ConfigurationError: invalid autojoin_priorities'),
    ).toBeInTheDocument();
    const before = listCalls().length;
    await user.click(screen.getByRole('button', { name: 'Retry' }));
    await waitFor(() => expect(listCalls().length).toBe(before + 1));

    await user.click(screen.getByRole('switch', { name: 'Auto-join lens' }));
    expect(await screen.findByRole('heading', { name: 'Hollow Knight', level: 3 })).toBeInTheDocument();
  });

  it('tells the user when auto-join is off', async () => {
    mockServer({ settings: { autojoin_enabled: false } });
    render(<Giveaways />);
    expect(await screen.findByText('Auto-join is off: nothing is entered automatically.')).toBeInTheDocument();
  });

  it('separates view filters from the auto-join policy', async () => {
    mockServer();
    render(<Giveaways />);
    expect(await screen.findByText('Show score ≥')).toBeInTheDocument();
    expect(screen.getByText('View filters change only what you see; auto-join uses Settings.')).toBeInTheDocument();
  });
});

describe('Giveaways page: tab standing line', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useGiveawayFiltersStore.getState().resetFilters();
  });

  it('wishlist first in the saved list: skips the filters, entered 1st', async () => {
    mockServer({ settings: { autojoin_priorities: [{ type: 'wishlist' }] } });
    render(<Giveaways status="wishlist" />);
    expect(
      await screen.findByText('Wishlist giveaways skip the filters and are entered 1st'),
    ).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Change in Settings' })).toHaveAttribute('href', '/settings');
  });

  it('wishlist absent from the saved list: obeys the filters', async () => {
    mockServer({ settings: { autojoin_priorities: [] } });
    render(<Giveaways status="wishlist" />);
    expect(
      await screen.findByText('Wishlist is not in your priority order: these giveaways obey the filters'),
    ).toBeInTheDocument();
  });

  it('dlc second in the saved list: entered 2nd', async () => {
    mockServer({ settings: { autojoin_priorities: [{ type: 'wishlist' }, { type: 'dlc' }] } });
    render(<Giveaways status="dlc" />);
    expect(await screen.findByText('DLC giveaways skip the filters and are entered 2nd')).toBeInTheDocument();
  });

  it('reads the exemption from the registry, not a client copy', async () => {
    const registry = {
      ...testRegistry,
      priority_types: testRegistry.priority_types.map((t) =>
        t.type === 'dlc' ? { ...t, exempt_from_filters: false } : t,
      ),
    };
    mockServer({ settings: { autojoin_priorities: [{ type: 'dlc' }] } });
    const base = mockApi.get.getMockImplementation();
    mockApi.get.mockImplementation(async (url: string) =>
      url.startsWith('/api/v1/giveaways/registry')
        ? { success: true, data: registry }
        : base
          ? base(url)
          : { success: false, data: null },
    );
    render(<Giveaways status="dlc" />);
    expect(await screen.findByText('DLC giveaways obey the filters and are entered 1st')).toBeInTheDocument();
  });

  it('says it is loading, then reports a registry failure while the list still loads', async () => {
    mockServer({ registryError: true });
    render(<Giveaways status="wishlist" />);
    expect(screen.getByText('Loading your priority order…')).toBeInTheDocument();
    expect(await screen.findByText('Could not load the auto-join registry')).toBeInTheDocument();
    expect(await screen.findByRole('heading', { name: 'Hollow Knight', level: 3 })).toBeInTheDocument();
  });

  it('has no standing line on the active tab', async () => {
    mockServer();
    render(<Giveaways />);
    await screen.findByRole('heading', { name: 'Hollow Knight', level: 3 });
    expect(screen.queryByText(/priority order/)).not.toBeInTheDocument();
  });
});
