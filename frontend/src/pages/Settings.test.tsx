import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { act, render, screen, waitFor, fireEvent, userEvent, within } from '@/test/utils';
import { Settings } from './Settings';
import { api } from '@/services/api';
import { useUIStore } from '@/stores/uiStore';
import type {
  ApiResponse,
  AutojoinRegistry,
  GenreCount,
  PolicyPreviewRequest,
  PolicyPreviewResponse,
  Settings as SettingsType,
} from '@/types';
import { makePreview, testRegistry, testSettings } from '@/test/fixtures';

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

const THRESHOLD_LABEL = 'Ending soon threshold (minutes)';

const mockGenres: GenreCount[] = [
  { name: 'Action', count: 12 },
  { name: 'Indie', count: 9 },
];

type PreviewHandler = (
  body: PolicyPreviewRequest,
) => Promise<ApiResponse<PolicyPreviewResponse | null>>;

/** Preview count that follows the body, so tests can see which policy was sent. */
const defaultPreview: PreviewHandler = async (body) => ({
  success: true,
  data: makePreview({ count: body.autojoin_min_score !== null && body.autojoin_min_score <= 5 ? 5 : 3 }),
});

interface ServerOptions {
  settings?: Partial<SettingsType>;
  registry?: () => Promise<ApiResponse<AutojoinRegistry | null>>;
  preview?: PreviewHandler;
}

function mockServer({ settings = {}, registry, preview = defaultPreview }: ServerOptions = {}) {
  const loaded = { ...testSettings, ...settings };
  mockApi.get.mockImplementation(async (url: string) => {
    if (url.includes('/games/genres')) return { success: true, data: { genres: mockGenres } };
    if (url.includes('/giveaways/registry')) {
      return registry ? registry() : { success: true, data: testRegistry };
    }
    return { success: true, data: loaded };
  });
  mockApi.getGameGenres.mockImplementation(() => mockApi.get('/api/v1/games/genres'));
  mockApi.post.mockImplementation(async (url: string, body?: unknown) => {
    if (url.startsWith('/api/v1/giveaways/preview')) return preview(body as PolicyPreviewRequest);
    return { success: true, data: {} };
  });
  mockApi.put.mockImplementation(async (_url, body) => ({
    success: true,
    data: { ...loaded, ...(body as Partial<SettingsType>), updated_at: '2026-01-02T00:00:00Z' },
  }));
}

function previewCalls(): PolicyPreviewRequest[] {
  return mockApi.post.mock.calls
    .filter(([url]) => String(url).startsWith('/api/v1/giveaways/preview'))
    .map(([, body]) => body as PolicyPreviewRequest);
}

function saveButtons() {
  return screen.getAllByRole('button', { name: /save changes/i });
}

async function renderPage(options: ServerOptions = {}) {
  mockServer(options);
  render(<Settings />);
  await screen.findByRole('heading', { name: 'Filters: what auto-join skips' });
}

/** Body of the only PUT /settings call. */
async function savedBody(): Promise<Partial<SettingsType>> {
  await waitFor(() => expect(mockApi.put).toHaveBeenCalledTimes(1));
  return mockApi.put.mock.calls[0][1] as Partial<SettingsType>;
}

function cardOf(title: string): HTMLElement {
  const heading = screen.getByRole('heading', { name: title });
  const card = heading.closest('div.rounded-lg');
  if (!(card instanceof HTMLElement)) throw new Error(`No card for ${title}`);
  return card;
}

/** True when `a` comes before `b` in document order. */
function precedes(a: Element, b: Element): boolean {
  return Boolean(a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING);
}

beforeEach(() => {
  vi.clearAllMocks();
  useUIStore.setState({ notifications: [] });
});

describe('Settings page: loading the registry', () => {
  it('shows the loading state, and no form, while the registry is pending', async () => {
    mockServer({ registry: () => new Promise(() => {}) });
    render(<Settings />);

    expect(await screen.findByText('Loading settings...')).toBeInTheDocument();
    await waitFor(() => expect(mockApi.get).toHaveBeenCalledWith('/api/v1/settings'));
    expect(screen.queryByRole('heading', { name: 'Filters: what auto-join skips' })).not.toBeInTheDocument();
  });

  it('shows an error naming the registry and what to do, with no form and no PUT', async () => {
    mockServer({ registry: async () => ({ success: false, data: null, error: 'Internal Server Error' }) });
    render(<Settings />);

    expect(
      await screen.findByText(
        'Could not load the auto-join registry (GET /giveaways/registry). Reload the page; if it keeps failing check the backend logs.',
      ),
    ).toBeInTheDocument();
    expect(screen.getByText('Internal Server Error')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /save changes/i })).not.toBeInTheDocument();
    expect(screen.queryByLabelText('PHPSESSID')).not.toBeInTheDocument();
    expect(mockApi.put).not.toHaveBeenCalled();
  });

  it('treats a registry without threshold bounds as a registry error', async () => {
    const broken = {
      ...testRegistry,
      priority_types: testRegistry.priority_types.map((t) => ({ ...t, params: [] })),
    };
    mockServer({ registry: async () => ({ success: true, data: broken }) });
    render(<Settings />);

    expect(await screen.findByText('The registry has no ending soon threshold bounds')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /save changes/i })).not.toBeInTheDocument();
  });

  it('shows the backend message when settings fail to load, and Retry asks again', async () => {
    mockServer();
    let fail = true;
    const message =
      "Auto-join priorities setting is invalid: unknown priority type 'bogus'; replace it with PUT /api/v1/settings";
    mockApi.get.mockImplementation(async (url: string) => {
      if (url.includes('/giveaways/registry')) return { success: true, data: testRegistry };
      if (url.includes('/games/genres')) return { success: true, data: { genres: mockGenres } };
      return fail ? { success: false, data: null, error: message } : { success: true, data: testSettings };
    });
    render(<Settings />);

    expect(await screen.findByRole('alert')).toHaveTextContent(`Failed to load settings: ${message}`);
    expect(screen.queryByText(/Is the backend running/)).not.toBeInTheDocument();

    fail = false;
    await userEvent.setup().click(screen.getByRole('button', { name: 'Retry' }));
    expect(await screen.findByLabelText('Per cycle cap')).toBeInTheDocument();
  });
});

describe('Settings page: structure', () => {
  it('renders the cards in stage order', async () => {
    await renderPage();

    const titles = screen.getAllByRole('heading', { level: 3 }).map((h) => h.textContent);
    expect(titles).toEqual([
      'SteamGifts Credentials',
      'Automation',
      'Filters: what auto-join skips',
      'Priority order',
      'Points budget and pacing',
      'Safety',
      'Scheduler',
    ]);
  });

  it('orders the Filters card: price, genre lists, score, reviews, age, Steam-data note, preview', async () => {
    await renderPage();
    const card = cardOf('Filters: what auto-join skips');
    const c = within(card);

    const sequence = [
      c.getByLabelText('Minimum price (points)'),
      await c.findByRole('group', { name: 'Genres' }),
      c.getByLabelText('Minimum review score'),
      c.getByLabelText('Minimum review count'),
      c.getByLabelText('Maximum game age (years)'),
      c.getByText(/Giveaways without cached Steam data are skipped while a minimum score/),
      await c.findByText('3 of 12 active giveaways would be entered next cycle'),
    ];
    for (let i = 1; i < sequence.length; i += 1) {
      expect(precedes(sequence[i - 1], sequence[i])).toBe(true);
    }
    expect(c.getByText(/a non-empty included-genres list skips them/)).toBeInTheDocument();
    expect(screen.queryByText(/\$/)).not.toBeInTheDocument();
  });

  it('names the exempt types from the registry in the Filters description', async () => {
    await renderPage();
    expect(
      screen.getByText(
        'Auto-join skips any giveaway that fails one of these. Wishlist and DLC giveaways skip them only while Wishlist or DLC is in your priority order.',
      ),
    ).toBeInTheDocument();
  });

  it('shows the preview line in both the Filters and the Priority order cards', async () => {
    await renderPage();

    expect(
      await within(cardOf('Filters: what auto-join skips')).findByText(
        '3 of 12 active giveaways would be entered next cycle',
      ),
    ).toBeInTheDocument();
    expect(
      within(cardOf('Priority order')).getByText('3 of 12 active giveaways would be entered next cycle'),
    ).toBeInTheDocument();
    expect(within(cardOf('Priority order')).getAllByText('Review score below minimum: 8')).toHaveLength(1);
  });

  it('says the rules are unused while auto-join is off', async () => {
    await renderPage({ settings: { autojoin_enabled: false } });
    expect(
      screen.getAllByText('Auto-join is off: these rules are used once you turn it on in Automation.'),
    ).toHaveLength(2);
  });

  it('relabels the per cycle cap and the SteamGifts hide toggle', async () => {
    await renderPage();
    const cap = screen.getByLabelText('Per cycle cap');
    expect(cap).toHaveValue(10);
    expect(cap).toHaveAttribute('min', '1');
    expect(cap).toBeRequired();
    expect(screen.getByRole('switch', { name: 'Hide unsafe giveaways on SteamGifts' })).toBeInTheDocument();
    expect(
      screen.getByText('Off: detected traps are hidden in this app only and never hidden on SteamGifts'),
    ).toBeInTheDocument();
  });
});

describe('Settings page: live preview', () => {
  it('previews the saved policy once on load (shared with the saved baseline)', async () => {
    await renderPage({ settings: { excluded_genres: ['Sports'] } });
    await screen.findAllByText('3 of 12 active giveaways would be entered next cycle');

    expect(previewCalls()).toHaveLength(1);
    expect(mockApi.post.mock.calls[0][0]).toBe('/api/v1/giveaways/preview?limit=1');
    expect(previewCalls()[0]).toEqual({
      autojoin_min_price: 10,
      autojoin_min_score: 7,
      autojoin_min_reviews: 1000,
      autojoin_max_game_age: null,
      excluded_genres: ['Sports'],
      included_genres: [],
      autojoin_priorities: [{ type: 'wishlist' }],
    });
  });

  describe('debounce', () => {
    afterEach(() => vi.useRealTimers());

    it('sends one POST about 400 ms after three quick edits, with the edited policy', async () => {
      await renderPage();
      await screen.findAllByText('3 of 12 active giveaways would be entered next cycle');
      expect(previewCalls()).toHaveLength(1);

      vi.useFakeTimers();
      const score = screen.getByLabelText('Minimum review score');
      fireEvent.change(score, { target: { value: '6' } });
      await act(() => vi.advanceTimersByTimeAsync(80));
      fireEvent.change(score, { target: { value: '5' } });
      await act(() => vi.advanceTimersByTimeAsync(80));
      fireEvent.change(score, { target: { value: '4' } });

      await act(() => vi.advanceTimersByTimeAsync(399));
      expect(previewCalls()).toHaveLength(1);
      await act(() => vi.advanceTimersByTimeAsync(1));
      expect(previewCalls()).toHaveLength(2);
      expect(previewCalls()[1].autojoin_min_score).toBe(4);

      await act(() => vi.advanceTimersByTimeAsync(2000));
      expect(previewCalls()).toHaveLength(2);
      vi.useRealTimers();

      expect(
        (await screen.findAllByText('5 of 12 active giveaways would be entered next cycle (saved: 3)'))
          .length,
      ).toBe(2);
    });

    it('sends no new request for budget, cap or scheduler edits', async () => {
      await renderPage();
      await screen.findAllByText('3 of 12 active giveaways would be entered next cycle');

      vi.useFakeTimers();
      fireEvent.change(screen.getByLabelText('Per cycle cap'), { target: { value: '5' } });
      fireEvent.change(screen.getByLabelText('Start at (points)'), { target: { value: '400' } });
      fireEvent.change(screen.getByLabelText('PHPSESSID'), { target: { value: 'other' } });
      await act(() => vi.advanceTimersByTimeAsync(1000));

      expect(previewCalls()).toHaveLength(1);
    });
  });

  it.each([
    [
      'a cleared score without No minimum',
      () => fireEvent.change(screen.getByLabelText('Minimum review score'), { target: { value: '' } }),
      'Preview paused: Enter a minimum review score from 0 to 10, or choose No minimum',
    ],
    [
      'an out-of-range ending soon threshold',
      async () => {
        const user = userEvent.setup();
        await user.selectOptions(screen.getByRole('combobox', { name: 'Add priority' }), 'ending_soon');
        await user.click(screen.getByRole('button', { name: 'Add the selected priority' }));
        fireEvent.change(screen.getByLabelText(THRESHOLD_LABEL), { target: { value: '4' } });
      },
      'Preview paused: Enter an ending soon threshold between 5 and 10080 minutes to save',
    ],
    [
      'a pending genre draft',
      () => fireEvent.change(screen.getByLabelText('Add a genre'), { target: { value: 'Racing' } }),
      'Preview paused: Press Add to put "Racing" on the excluded list, or clear the field, to save',
    ],
  ])('pauses on %s, says why and sends nothing', async (_name, edit, text) => {
    await renderPage();
    await screen.findAllByText('3 of 12 active giveaways would be entered next cycle');
    const before = previewCalls().length;

    await edit();

    expect(await screen.findAllByText(text)).toHaveLength(2);
    await new Promise((resolve) => setTimeout(resolve, 600));
    expect(previewCalls()).toHaveLength(before);
  });

  it('after a pause, never shows the saved numbers as the new policy', async () => {
    await renderPage();
    await screen.findAllByText('3 of 12 active giveaways would be entered next cycle');

    const score = screen.getByLabelText('Minimum review score');
    fireEvent.change(score, { target: { value: '' } });
    await screen.findAllByText(/^Preview paused:/);
    await new Promise((resolve) => setTimeout(resolve, 500));
    fireEvent.change(score, { target: { value: '5' } });

    expect(screen.getAllByText('Computing the preview…')).toHaveLength(2);
    expect(screen.queryByText(/^3 of 12/)).not.toBeInTheDocument();
    expect(
      await screen.findAllByText('5 of 12 active giveaways would be entered next cycle (saved: 3)'),
    ).toHaveLength(2);
  });

  it('shows the backend message and a Retry that asks again', async () => {
    let fail = true;
    await renderPage({
      preview: async (body) =>
        fail
          ? { success: false, data: null, error: 'Database is locked' }
          : defaultPreview(body),
    });

    const errors = await screen.findAllByText(
      'Preview unavailable: Database is locked. Your changes can still be saved.',
    );
    expect(errors).toHaveLength(2);
    // Save is not blocked by a preview failure.
    fireEvent.change(screen.getByLabelText('Per cycle cap'), { target: { value: '5' } });
    expect(saveButtons()[0]).toBeEnabled();

    fail = false;
    await userEvent.setup().click(screen.getAllByRole('button', { name: 'Retry' })[0]);
    expect(await screen.findAllByText('3 of 12 active giveaways would be entered next cycle')).toHaveLength(2);
  });

  it('keeps the previous result visible, marked Updating…, while a new one loads', async () => {
    let release: () => void = () => {};
    let first = true;
    await renderPage({
      preview: (body) => {
        if (first) {
          first = false;
          return defaultPreview(body);
        }
        return new Promise((resolve) => {
          release = () => resolve({ success: true, data: makePreview({ count: 5 }) });
        });
      },
    });
    await screen.findAllByText('3 of 12 active giveaways would be entered next cycle');

    fireEvent.change(screen.getByLabelText('Minimum review score'), { target: { value: '5' } });
    expect(await screen.findAllByText('Updating…')).toHaveLength(2);
    expect(screen.getAllByText('3 of 12 active giveaways would be entered next cycle')).toHaveLength(2);

    await waitFor(() => expect(previewCalls()).toHaveLength(2));
    act(() => release());
    expect(await screen.findAllByText('5 of 12 active giveaways would be entered next cycle (saved: 3)')).toHaveLength(2);
    expect(screen.queryByText('Updating…')).not.toBeInTheDocument();
  });
});

describe('Settings page: nullable thresholds', () => {
  it('No minimum sends null for the score and disables the input', async () => {
    const user = userEvent.setup();
    await renderPage();

    await user.click(screen.getByRole('checkbox', { name: 'No minimum review score' }));
    const score = screen.getByLabelText('Minimum review score');
    expect(score).toBeDisabled();
    expect(score).toHaveAttribute('placeholder', 'No minimum');
    expect(screen.getByText('Off: review score is not checked')).toBeInTheDocument();
    await user.click(saveButtons()[0]);

    const body = await savedBody();
    expect(body.autojoin_min_score).toBeNull();
    expect(body.autojoin_min_reviews).toBe(1000);
  });

  it('a cleared score without No minimum blocks Save and never sends 0', async () => {
    const user = userEvent.setup();
    await renderPage();

    await user.clear(screen.getByLabelText('Minimum review score'));

    expect(screen.getByRole('alert')).toHaveTextContent(
      'Enter a minimum review score from 0 to 10, or choose No minimum',
    );
    for (const button of saveButtons()) {
      expect(button).toBeDisabled();
      await user.click(button);
    }
    expect(mockApi.put).not.toHaveBeenCalled();
    // The header Save button points at the visible reason in the save bar.
    const describedBy = saveButtons()[0].getAttribute('aria-describedby');
    expect(describedBy).not.toBeNull();
    expect(document.getElementById(describedBy ?? '')).toHaveTextContent(
      'Enter a minimum review score from 0 to 10, or choose No minimum',
    );
  });

  it('typing 0 sends 0', async () => {
    const user = userEvent.setup();
    await renderPage();

    const score = screen.getByLabelText('Minimum review score');
    await user.clear(score);
    await user.type(score, '0');
    await user.click(saveButtons()[0]);

    expect((await savedBody()).autojoin_min_score).toBe(0);
  });

  it.each(['11', '-1'])('rejects a score of %s', async (value) => {
    await renderPage();
    fireEvent.change(screen.getByLabelText('Minimum review score'), { target: { value } });
    expect(saveButtons()[0]).toBeDisabled();
  });

  it('a saved null loads as No minimum checked with the input disabled', async () => {
    await renderPage({ settings: { autojoin_min_reviews: null, autojoin_min_score: null } });

    expect(screen.getByRole('checkbox', { name: 'No minimum review count' })).toBeChecked();
    expect(screen.getByLabelText('Minimum review count')).toBeDisabled();
    expect(screen.getByLabelText('Minimum review count')).toHaveValue(null);
    expect(screen.getByRole('checkbox', { name: 'No minimum review score' })).toBeChecked();
  });

  it('turning No minimum off restores the backend default for a saved null', async () => {
    const user = userEvent.setup();
    await renderPage({ settings: { autojoin_min_reviews: null } });

    await user.click(screen.getByRole('checkbox', { name: 'No minimum review count' }));
    expect(screen.getByLabelText('Minimum review count')).toHaveValue(1000);
    await user.click(saveButtons()[0]);
    expect((await savedBody()).autojoin_min_reviews).toBe(1000);
  });

  it('turning No minimum off restores the last draft', async () => {
    const user = userEvent.setup();
    await renderPage();

    fireEvent.change(screen.getByLabelText('Minimum review score'), { target: { value: '4' } });
    await user.click(screen.getByRole('checkbox', { name: 'No minimum review score' }));
    await user.click(screen.getByRole('checkbox', { name: 'No minimum review score' }));
    expect(screen.getByLabelText('Minimum review score')).toHaveValue(4);
  });

  it('No limit sends null for the game age; a cleared age without it blocks Save', async () => {
    const user = userEvent.setup();
    await renderPage({ settings: { autojoin_max_game_age: 5 } });

    await user.clear(screen.getByLabelText('Maximum game age (years)'));
    expect(screen.getByRole('alert')).toHaveTextContent(
      'Enter a maximum age of 1 year or more, or choose No limit',
    );
    expect(saveButtons()[0]).toBeDisabled();

    await user.click(screen.getByRole('checkbox', { name: 'No age limit' }));
    await user.click(saveButtons()[0]);
    expect((await savedBody()).autojoin_max_game_age).toBeNull();
  });

  it('the No minimum controls have distinct accessible names and ids', async () => {
    await renderPage();
    const boxes = screen.getAllByRole('checkbox');
    const ids = boxes.map((b) => b.id);
    expect(new Set(ids).size).toBe(ids.length);
    expect(boxes.map((b) => b.getAttribute('aria-label'))).toEqual([
      'No minimum review score',
      'No minimum review count',
      'No age limit',
    ]);
  });
});

describe('Settings page: number fields', () => {
  it.each([
    ['Per cycle cap', '', 'Enter a per cycle cap of 1 or more'],
    ['Per cycle cap', '0', 'Enter a per cycle cap of 1 or more'],
    ['Minimum price (points)', '', 'Enter a minimum price of 0 points or more'],
    ['Start at (points)', '', 'Enter a start threshold of 0 points or more'],
    ['Min entry delay (seconds)', '', 'Enter a minimum delay of 0 seconds or more'],
    ['Scan interval (minutes)', '0', 'Enter a scan interval of 1 minute or more'],
  ])('%s %j blocks Save with a reason naming the field', async (label, value, message) => {
    await renderPage();

    fireEvent.change(screen.getByLabelText(label), { target: { value } });

    expect(screen.getByRole('alert')).toHaveTextContent(message);
    expect(saveButtons()[0]).toBeDisabled();
    expect(screen.getAllByText(message).length).toBeGreaterThanOrEqual(2);
  });

  it('checks Stop at against Start at and the delays against each other', async () => {
    await renderPage();

    fireEvent.change(screen.getByLabelText('Stop at (points)'), { target: { value: '400' } });
    expect(screen.getAllByText('Stop at must not be above Start at').length).toBeGreaterThanOrEqual(1);
    expect(saveButtons()[0]).toBeDisabled();
    fireEvent.change(screen.getByLabelText('Stop at (points)'), { target: { value: '350' } });
    expect(screen.queryByText('Stop at must not be above Start at')).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Max entry delay (seconds)'), { target: { value: '7' } });
    expect(screen.getAllByText('Max delay must not be below Min delay').length).toBeGreaterThanOrEqual(1);
    expect(saveButtons()[0]).toBeDisabled();
  });

  it('sends every number as typed, with 0 kept as 0', async () => {
    const user = userEvent.setup();
    await renderPage();

    fireEvent.change(screen.getByLabelText('Minimum price (points)'), { target: { value: '0' } });
    fireEvent.change(screen.getByLabelText('Per cycle cap'), { target: { value: '3' } });
    fireEvent.change(screen.getByLabelText('Log retention (days)'), { target: { value: '0' } });
    fireEvent.change(screen.getByLabelText('Stop at (points)'), { target: { value: '0' } });
    await user.click(saveButtons()[0]);

    expect(await savedBody()).toMatchObject({
      autojoin_min_price: 0,
      max_entries_per_cycle: 3,
      log_retention_days: 0,
      autojoin_stop_at: 0,
      autojoin_start_at: 350,
      entry_delay_min: 8,
      entry_delay_max: 12,
      scan_interval_minutes: 30,
      max_scan_pages: 3,
    });
  });
});

describe('Settings page: priority order', () => {
  it('reorders by buttons and saves the displayed order with the threshold', async () => {
    const user = userEvent.setup();
    await renderPage();

    await user.selectOptions(screen.getByRole('combobox', { name: 'Add priority' }), 'dlc');
    await user.click(screen.getByRole('button', { name: 'Add the selected priority' }));
    await user.click(screen.getByRole('button', { name: 'Add the selected priority' }));
    await user.click(screen.getByRole('button', { name: 'Move DLC up' }));
    fireEvent.change(screen.getByLabelText(THRESHOLD_LABEL), { target: { value: '120' } });
    await user.click(saveButtons()[0]);

    expect((await savedBody()).autojoin_priorities).toEqual([
      { type: 'dlc' },
      { type: 'wishlist' },
      { type: 'ending_soon', threshold_minutes: 120 },
    ]);
  });

  it('round-trips a saved list and its threshold', async () => {
    await renderPage({
      settings: {
        autojoin_priorities: [
          { type: 'ending_soon', threshold_minutes: 90 },
          { type: 'dlc' },
        ],
      },
    });

    const rows = within(screen.getByRole('list', { name: 'Priority order' })).getAllByRole('listitem');
    expect(rows[0]).toHaveTextContent('Ending soon');
    expect(rows[1]).toHaveTextContent('DLC');
    expect(screen.getByLabelText(THRESHOLD_LABEL)).toHaveValue(90);
  });

  it('removing every priority sends [] and warns about the lost exemption', async () => {
    const user = userEvent.setup();
    await renderPage();

    await user.click(screen.getByRole('button', { name: 'Remove Wishlist' }));
    expect(screen.getByText('Wishlist giveaways will obey your filters after saving.')).toBeInTheDocument();
    await user.click(saveButtons()[0]);

    expect((await savedBody()).autojoin_priorities).toEqual([]);
  });

  it.each(['4', '10081', ''])('a threshold of %j blocks Save naming the range, no PUT', async (value) => {
    const user = userEvent.setup();
    await renderPage();

    await user.selectOptions(screen.getByRole('combobox', { name: 'Add priority' }), 'ending_soon');
    await user.click(screen.getByRole('button', { name: 'Add the selected priority' }));
    expect(screen.getByLabelText(THRESHOLD_LABEL)).toHaveValue(60);
    fireEvent.change(screen.getByLabelText(THRESHOLD_LABEL), { target: { value } });

    expect(screen.getByRole('alert')).toHaveTextContent('Must be between 5 and 10080 minutes');
    expect(
      screen.getByText('Enter an ending soon threshold between 5 and 10080 minutes to save'),
    ).toBeInTheDocument();
    for (const button of saveButtons()) {
      expect(button).toBeDisabled();
      await user.click(button);
    }
    expect(mockApi.put).not.toHaveBeenCalled();
  });

  it('an invalid threshold stops blocking once ending soon is removed', async () => {
    const user = userEvent.setup();
    await renderPage();

    await user.selectOptions(screen.getByRole('combobox', { name: 'Add priority' }), 'ending_soon');
    await user.click(screen.getByRole('button', { name: 'Add the selected priority' }));
    fireEvent.change(screen.getByLabelText(THRESHOLD_LABEL), { target: { value: '4' } });
    await user.click(screen.getByRole('button', { name: 'Remove Ending soon' }));

    expect(saveButtons()[0]).toBeEnabled();
    await user.click(saveButtons()[0]);
    expect((await savedBody()).autojoin_priorities).toEqual([{ type: 'wishlist' }]);
  });
});

describe('Settings page: genre lists', () => {
  it('marks a cached genre Included and PUTs both lists as displayed', async () => {
    const user = userEvent.setup();
    await renderPage({ settings: { excluded_genres: ['Action'] } });

    const action = await screen.findByRole('group', { name: 'Action (12 games)' });
    await user.click(within(action).getByRole('button', { name: 'Included' }));
    await user.click(saveButtons()[0]);

    const body = await savedBody();
    expect(body.excluded_genres).toEqual([]);
    expect(body.included_genres).toEqual(['Action']);
  });

  it('blocks saving while a typed genre has not been added, and says why', async () => {
    const user = userEvent.setup();
    await renderPage();

    await user.selectOptions(screen.getByRole('combobox', { name: 'Add to list' }), 'included');
    await user.type(screen.getByLabelText('Add a genre'), 'RPG');

    const reason = 'Press Add to put "RPG" on the included list, or clear the field, to save';
    expect(screen.getAllByText(reason).length).toBeGreaterThanOrEqual(1);
    expect(saveButtons()[0]).toBeDisabled();

    await user.keyboard('{Enter}');
    expect(saveButtons()[0]).toBeEnabled();
    await user.click(saveButtons()[0]);
    expect((await savedBody()).included_genres).toEqual(['RPG']);
  });

  it('shows the server-normalised lists after save (form remounts on updated_at)', async () => {
    const user = userEvent.setup();
    await renderPage();
    mockApi.put.mockImplementationOnce(async (_url, body) => ({
      success: true,
      data: {
        ...testSettings,
        ...(body as Partial<SettingsType>),
        included_genres: ['RPG (server)'],
        updated_at: '2026-01-03T00:00:00Z',
      },
    }));

    await user.selectOptions(screen.getByRole('combobox', { name: 'Add to list' }), 'included');
    await user.type(screen.getByLabelText('Add a genre'), 'RPG{Enter}');
    await user.click(saveButtons()[0]);

    const rpg = await screen.findByRole('group', { name: 'RPG (server) (not cached)' });
    expect(within(rpg).getByRole('button', { name: 'Included' })).toHaveAttribute('aria-pressed', 'true');
  });
});

describe('Settings page: saving', () => {
  it('reports success in terms of the next cycle and sends the whole form', async () => {
    const user = userEvent.setup();
    await renderPage();

    await user.clear(screen.getByLabelText('PHPSESSID'));
    await user.type(screen.getByLabelText('PHPSESSID'), 'new-cookie');
    expect(screen.getByText('Saving changes what auto-join enters from the next cycle.')).toBeInTheDocument();
    await user.click(saveButtons()[0]);

    const body = await savedBody();
    expect(body).toEqual({
      phpsessid: 'new-cookie',
      user_agent: 'test-user-agent',
      automation_enabled: true,
      autojoin_enabled: true,
      safety_check_enabled: true,
      auto_hide_unsafe: true,
      autojoin_min_price: 10,
      autojoin_min_score: 7,
      autojoin_min_reviews: 1000,
      autojoin_max_game_age: null,
      excluded_genres: [],
      included_genres: [],
      autojoin_priorities: [{ type: 'wishlist' }],
      autojoin_start_at: 350,
      autojoin_stop_at: 200,
      max_entries_per_cycle: 10,
      entry_delay_min: 8,
      entry_delay_max: 12,
      scan_interval_minutes: 30,
      max_scan_pages: 3,
      log_retention_days: 30,
    });
    await waitFor(() =>
      expect(useUIStore.getState().notifications.map((n) => n.message)).toContain(
        'Settings saved. Auto-join uses them from the next cycle.',
      ),
    );
  });

  it('shows the backend error and keeps the edits', async () => {
    const user = userEvent.setup();
    await renderPage();
    mockApi.put.mockResolvedValue({ success: false, data: null, error: 'max_entries_per_cycle: too small' });

    fireEvent.change(screen.getByLabelText('Per cycle cap'), { target: { value: '4' } });
    await user.click(saveButtons()[0]);

    await waitFor(() =>
      expect(useUIStore.getState().notifications.map((n) => n.message)).toContain(
        'max_entries_per_cycle: too small',
      ),
    );
    expect(screen.getByLabelText('Per cycle cap')).toHaveValue(4);
    expect(saveButtons()[0]).toBeEnabled();
  });

  it('disables Save with nothing to save', async () => {
    await renderPage();
    for (const button of saveButtons()) expect(button).toBeDisabled();
    expect(screen.queryByText('Saving changes what auto-join enters from the next cycle.')).not.toBeInTheDocument();
  });
});
