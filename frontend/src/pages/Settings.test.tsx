import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent, userEvent, within } from '@/test/utils';
import { Settings } from './Settings';
import { api } from '@/services/api';
import { useUIStore } from '@/stores/uiStore';
import type { GenreCount, Settings as SettingsType } from '@/types';

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

const TOGGLE_NAME = 'Enter giveaways ending soon first';
const INPUT_LABEL = 'Ending Soon Threshold (minutes)';

const mockSettings: SettingsType = {
  id: 1,
  phpsessid: 'test-session-id',
  user_agent: 'test-user-agent',
  xsrf_token: null,
  dlc_priority_enabled: false,
  safety_check_enabled: true,
  auto_hide_unsafe: true,
  autojoin_enabled: true,
  autojoin_start_at: 350,
  autojoin_stop_at: 200,
  autojoin_min_price: 10,
  autojoin_min_score: 7,
  autojoin_min_reviews: 1000,
  autojoin_max_game_age: null,
  wishlist_priority_enabled: true,
  ending_soon_priority_enabled: false,
  ending_soon_threshold_minutes: 60,
  excluded_genres: [],
  scan_interval_minutes: 30,
  max_entries_per_cycle: 10,
  automation_enabled: true,
  max_scan_pages: 3,
  entry_delay_min: 8,
  entry_delay_max: 12,
  log_retention_days: 30,
  last_synced_at: null,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
};

const mockGenres: GenreCount[] = [
  { name: 'Action', count: 12 },
  { name: 'Indie', count: 9 },
  { name: 'Sports', count: 2 },
];

function mockServer(initial: Partial<SettingsType> = {}) {
  const loaded = { ...mockSettings, ...initial };
  // Dispatch by URL: the page also fetches the genre list of the game cache.
  mockApi.get.mockImplementation(async (url: string) =>
    url.includes('/games/genres')
      ? { success: true, data: { genres: mockGenres } }
      : { success: true, data: loaded },
  );
  mockApi.getGameGenres.mockImplementation(() => mockApi.get('/api/v1/games/genres'));
  mockApi.put.mockImplementation(async (_url, body) => ({
    success: true,
    data: { ...loaded, ...(body as Partial<SettingsType>), updated_at: '2026-01-02T00:00:00Z' },
  }));
}

function saveButtons() {
  return screen.getAllByRole('button', { name: /save changes/i });
}

async function renderPage(initial: Partial<SettingsType> = {}) {
  mockServer(initial);
  render(<Settings />);
  return screen.findByRole('switch', { name: TOGGLE_NAME });
}

describe('Settings page: ending soon priority', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useUIStore.setState({ notifications: [] });
  });

  it('shows the toggle unchecked and hides the threshold input when disabled', async () => {
    const toggle = await renderPage();

    expect(toggle).toHaveAttribute('aria-checked', 'false');
    expect(screen.queryByLabelText(INPUT_LABEL)).not.toBeInTheDocument();
    expect(saveButtons()[0]).toBeDisabled();
  });

  it('reveals the threshold input prefilled with 60 and enables Save when toggled on', async () => {
    const user = userEvent.setup();
    const toggle = await renderPage();

    await user.click(toggle);

    expect(toggle).toHaveAttribute('aria-checked', 'true');
    const input = screen.getByLabelText(INPUT_LABEL);
    expect(input).toHaveValue(60);
    expect(input).toHaveAttribute('min', '5');
    expect(input).toHaveAttribute('max', '10080');
    expect(saveButtons()[0]).toBeEnabled();
  });

  it('PUTs both fields on save and reports success', async () => {
    const user = userEvent.setup();
    const toggle = await renderPage();

    await user.click(toggle);
    fireEvent.change(screen.getByLabelText(INPUT_LABEL), { target: { value: '120' } });
    await user.click(saveButtons()[0]);

    await waitFor(() => {
      expect(mockApi.put).toHaveBeenCalledWith(
        '/api/v1/settings',
        expect.objectContaining({
          ending_soon_priority_enabled: true,
          ending_soon_threshold_minutes: 120,
        }),
      );
    });
    await waitFor(() => {
      expect(useUIStore.getState().notifications.map((n) => n.message)).toContain(
        'Settings saved successfully',
      );
    });
  });

  it('round-trips server values: checked toggle and stored threshold', async () => {
    const toggle = await renderPage({
      ending_soon_priority_enabled: true,
      ending_soon_threshold_minutes: 120,
    });

    expect(toggle).toHaveAttribute('aria-checked', 'true');
    expect(screen.getByLabelText(INPUT_LABEL)).toHaveValue(120);
  });

  it.each([4, 10081])('rejects %i inline and blocks saving', async (value) => {
    const user = userEvent.setup();
    const toggle = await renderPage();

    await user.click(toggle);
    fireEvent.change(screen.getByLabelText(INPUT_LABEL), { target: { value: String(value) } });

    expect(screen.getByRole('alert')).toHaveTextContent('Must be between 5 and 10080 minutes');
    expect(screen.getByLabelText(INPUT_LABEL)).toHaveAttribute('aria-invalid', 'true');
    for (const button of saveButtons()) {
      expect(button).toBeDisabled();
      await user.click(button);
    }
    expect(mockApi.put).not.toHaveBeenCalled();
  });

  it.each([5, 10080])('accepts the boundary value %i', async (value) => {
    const user = userEvent.setup();
    const toggle = await renderPage();

    await user.click(toggle);
    fireEvent.change(screen.getByLabelText(INPUT_LABEL), { target: { value: String(value) } });

    expect(screen.getByLabelText(INPUT_LABEL)).toHaveValue(value);
    expect(screen.queryByText('Must be between 5 and 10080 minutes')).not.toBeInTheDocument();
    for (const button of saveButtons()) {
      expect(button).toBeEnabled();
    }
  });

  it('sends an explicit false when the toggle is turned off', async () => {
    const user = userEvent.setup();
    const toggle = await renderPage({
      ending_soon_priority_enabled: true,
      ending_soon_threshold_minutes: 120,
    });

    await user.click(toggle);
    expect(toggle).toHaveAttribute('aria-checked', 'false');
    expect(screen.queryByLabelText(INPUT_LABEL)).not.toBeInTheDocument();

    await user.click(saveButtons()[0]);

    await waitFor(() => {
      expect(mockApi.put).toHaveBeenCalledWith(
        '/api/v1/settings',
        expect.objectContaining({ ending_soon_priority_enabled: false }),
      );
    });
  });

  it('restores the saved threshold when toggled off with an out-of-range draft', async () => {
    const user = userEvent.setup();
    const toggle = await renderPage();

    await user.click(toggle);
    fireEvent.change(screen.getByLabelText(INPUT_LABEL), { target: { value: '4' } });
    expect(saveButtons()[0]).toBeDisabled();

    await user.click(toggle);
    expect(saveButtons()[0]).toBeEnabled();
    await user.click(saveButtons()[0]);

    await waitFor(() => {
      expect(mockApi.put).toHaveBeenCalledWith(
        '/api/v1/settings',
        expect.objectContaining({
          ending_soon_priority_enabled: false,
          ending_soon_threshold_minutes: 60,
        }),
      );
    });
  });
});

describe('Settings page: ending soon threshold typing and toggle-off rule', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useUIStore.setState({ notifications: [] });
  });

  it('clearing the threshold shows the error and blocks saving instead of snapping back to 60', async () => {
    const user = userEvent.setup();
    const toggle = await renderPage();

    await user.click(toggle);
    const input = screen.getByLabelText(INPUT_LABEL);
    await user.clear(input);

    expect(input).toHaveValue(null);
    expect(screen.getByRole('alert')).toHaveTextContent('Must be between 5 and 10080 minutes');
    for (const button of saveButtons()) {
      expect(button).toBeDisabled();
    }
  });

  it('typing 0 shows the error rather than being replaced by 60', async () => {
    const user = userEvent.setup();
    const toggle = await renderPage();

    await user.click(toggle);
    const input = screen.getByLabelText(INPUT_LABEL);
    await user.clear(input);
    await user.type(input, '0');

    expect(input).toHaveValue(0);
    expect(screen.getByRole('alert')).toHaveTextContent('Must be between 5 and 10080 minutes');
    expect(saveButtons()[0]).toBeDisabled();
  });

  it('saves a threshold typed after clearing the field', async () => {
    const user = userEvent.setup();
    const toggle = await renderPage();

    await user.click(toggle);
    const input = screen.getByLabelText(INPUT_LABEL);
    await user.clear(input);
    await user.type(input, '240');
    await user.click(saveButtons()[0]);

    await waitFor(() => {
      expect(mockApi.put).toHaveBeenCalledWith(
        '/api/v1/settings',
        expect.objectContaining({
          ending_soon_priority_enabled: true,
          ending_soon_threshold_minutes: 240,
        }),
      );
    });
  });

  it('discards a valid draft threshold when toggled off and sends the saved value', async () => {
    const user = userEvent.setup();
    const toggle = await renderPage({
      ending_soon_priority_enabled: true,
      ending_soon_threshold_minutes: 90,
    });

    const input = screen.getByLabelText(INPUT_LABEL);
    await user.clear(input);
    await user.type(input, '120');
    await user.click(toggle);
    await user.click(saveButtons()[0]);

    await waitFor(() => {
      expect(mockApi.put).toHaveBeenCalledWith(
        '/api/v1/settings',
        expect.objectContaining({
          ending_soon_priority_enabled: false,
          ending_soon_threshold_minutes: 90,
        }),
      );
    });
  });

  it('shows the saved threshold, not the discarded valid draft, when toggled back on', async () => {
    const user = userEvent.setup();
    const toggle = await renderPage();

    await user.click(toggle);
    const input = screen.getByLabelText(INPUT_LABEL);
    await user.clear(input);
    await user.type(input, '120');
    await user.click(toggle);
    await user.click(toggle);

    expect(screen.getByLabelText(INPUT_LABEL)).toHaveValue(60);
  });
});

describe('Settings page: ending soon priority (challenger)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useUIStore.setState({ notifications: [] });
  });

  it('places the ending-soon switch directly after the Prioritize DLC switch', async () => {
    await renderPage();

    const switches = screen.getAllByRole('switch');
    const dlcIndex = switches.indexOf(screen.getByRole('switch', { name: /Prioritize DLC/ }));
    const soonIndex = switches.indexOf(screen.getByRole('switch', { name: TOGGLE_NAME }));
    expect(dlcIndex).toBeGreaterThanOrEqual(0);
    expect(soonIndex).toBe(dlcIndex + 1);
  });

  it('lets the user clear the threshold and type a new value without a spurious error', async () => {
    const user = userEvent.setup();
    const toggle = await renderPage();

    await user.click(toggle);
    const input = screen.getByLabelText(INPUT_LABEL);
    await user.clear(input);
    await user.type(input, '120');

    expect(input).toHaveValue(120);
    expect(screen.queryByText('Must be between 5 and 10080 minutes')).not.toBeInTheDocument();
  });

  it('shows the saved threshold, not the rejected draft, when toggled back on', async () => {
    const user = userEvent.setup();
    const toggle = await renderPage();

    await user.click(toggle);
    fireEvent.change(screen.getByLabelText(INPUT_LABEL), { target: { value: '4' } });
    await user.click(toggle);
    await user.click(toggle);

    expect(screen.getByLabelText(INPUT_LABEL)).toHaveValue(60);
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('reports a rejected save and keeps the draft instead of claiming success', async () => {
    const user = userEvent.setup();
    const toggle = await renderPage();
    mockApi.put.mockResolvedValue({ success: false, data: null, error: 'Validation failed' });

    await user.click(toggle);
    fireEvent.change(screen.getByLabelText(INPUT_LABEL), { target: { value: '120' } });
    await user.click(saveButtons()[0]);

    await waitFor(() => {
      expect(useUIStore.getState().notifications.map((n) => n.message)).toContain(
        'Validation failed',
      );
    });
    expect(useUIStore.getState().notifications.map((n) => n.message)).not.toContain(
      'Settings saved successfully',
    );
    expect(toggle).toHaveAttribute('aria-checked', 'true');
    expect(screen.getByLabelText(INPUT_LABEL)).toHaveValue(120);
    expect(saveButtons()[0]).toBeEnabled();
  });
});

describe('Settings page: ending soon review findings', () => {
  const BLOCKED_REASON = 'Fix the ending soon threshold (5 to 10080 minutes) to save';

  beforeEach(() => {
    vi.clearAllMocks();
    useUIStore.setState({ notifications: [] });
  });

  it('tells the user that ending-soon giveaways must still pass the filters', async () => {
    await renderPage();

    expect(
      screen.getByText(
        'Giveaways that pass the filters below and end within the threshold are entered after wishlist and DLC ones but before the rest, soonest first'
      )
    ).toBeInTheDocument();
  });

  it('explains next to the disabled Save buttons why saving is blocked', async () => {
    const user = userEvent.setup();
    const toggle = await renderPage();

    await user.click(toggle);
    await user.clear(screen.getByLabelText(INPUT_LABEL));

    expect(screen.getByText(BLOCKED_REASON)).toBeInTheDocument();
    expect(screen.queryByText('You have unsaved changes')).not.toBeInTheDocument();
    for (const button of saveButtons()) {
      expect(button).toBeDisabled();
      expect(button).toHaveAttribute('title', BLOCKED_REASON);
    }
  });

  it('restores the normal banner and drops the title once the threshold is valid again', async () => {
    const user = userEvent.setup();
    const toggle = await renderPage();

    await user.click(toggle);
    const input = screen.getByLabelText(INPUT_LABEL);
    await user.clear(input);
    await user.type(input, '120');

    expect(screen.getByText('You have unsaved changes')).toBeInTheDocument();
    expect(screen.queryByText(BLOCKED_REASON)).not.toBeInTheDocument();
    for (const button of saveButtons()) {
      expect(button).toBeEnabled();
      expect(button).not.toHaveAttribute('title');
    }
  });
});

describe('Settings page: excluded genres', () => {
  const ADD_INPUT = 'Add a genre';

  beforeEach(() => {
    vi.clearAllMocks();
    useUIStore.setState({ notifications: [] });
  });

  function chips() {
    return screen.getByRole('group', { name: 'Excluded genres' });
  }

  async function lastPutGenres() {
    await waitFor(() => expect(mockApi.put).toHaveBeenCalled());
    const calls = mockApi.put.mock.calls;
    const body = calls[calls.length - 1][1] as Partial<SettingsType>;
    return body.excluded_genres;
  }

  it('shows no exclusions and the cached genres with their counts', async () => {
    await renderPage();

    expect(within(chips()).getByText('No genres excluded')).toBeInTheDocument();
    const action = await screen.findByRole('button', { name: 'Action (12 games)' });
    expect(action).toHaveAttribute('aria-pressed', 'false');
    expect(screen.getByRole('button', { name: 'Sports (2 games)' })).toBeInTheDocument();
    expect(
      screen.getByText(
        'Auto-join skips giveaways whose game has one of these genres. Wishlist giveaways (when Prioritize Wishlist is on) and DLC (when Prioritize DLC is on) are still entered. Games cached before this update pick up their genres over the next refreshes.',
      ),
    ).toBeInTheDocument();
  });

  it('adds a genre from the picker and PUTs it on save', async () => {
    const user = userEvent.setup();
    await renderPage();

    const action = await screen.findByRole('button', { name: 'Action (12 games)' });
    await user.click(action);

    expect(action).toHaveAttribute('aria-pressed', 'true');
    expect(within(chips()).getByText('Action')).toBeInTheDocument();
    await user.click(saveButtons()[0]);

    expect(await lastPutGenres()).toEqual(['Action']);
  });

  it('removes an excluded genre when its picker toggle is pressed again', async () => {
    const user = userEvent.setup();
    await renderPage({ excluded_genres: ['Action', 'Indie'] });

    const action = await screen.findByRole('button', { name: 'Action (12 games)' });
    expect(action).toHaveAttribute('aria-pressed', 'true');
    await user.click(action);

    expect(action).toHaveAttribute('aria-pressed', 'false');
    await user.click(saveButtons()[0]);
    expect(await lastPutGenres()).toEqual(['Indie']);
  });

  it('adds a typed genre with the Add button and clears the input', async () => {
    const user = userEvent.setup();
    await renderPage();

    const input = screen.getByLabelText(ADD_INPUT);
    await user.type(input, '  Racing ');
    await user.click(screen.getByRole('button', { name: 'Add genre' }));

    expect(within(chips()).getByText('Racing')).toBeInTheDocument();
    expect(input).toHaveValue('');
  });

  it('adds a typed genre on Enter without saving the form', async () => {
    const user = userEvent.setup();
    await renderPage();

    const input = screen.getByLabelText(ADD_INPUT);
    await user.type(input, 'Racing{Enter}');

    expect(within(chips()).getByText('Racing')).toBeInTheDocument();
    expect(input).toHaveValue('');
    expect(mockApi.put).not.toHaveBeenCalled();
  });

  it('removes a chip and leaves it out of the PUT payload', async () => {
    const user = userEvent.setup();
    await renderPage();

    await user.click(await screen.findByRole('button', { name: 'Action (12 games)' }));
    await user.type(screen.getByLabelText(ADD_INPUT), 'Racing{Enter}');
    await user.type(screen.getByLabelText(ADD_INPUT), 'Gore{Enter}');
    await user.click(screen.getByRole('button', { name: 'Remove Racing' }));

    expect(within(chips()).queryByText('Racing')).not.toBeInTheDocument();
    await user.click(saveButtons()[0]);
    expect(await lastPutGenres()).toEqual(['Action', 'Gore']);
  });

  it('keeps a case-insensitive duplicate in the field with an error and adds nothing', async () => {
    const user = userEvent.setup();
    await renderPage({ excluded_genres: ['Action'] });

    const input = screen.getByLabelText(ADD_INPUT);
    await user.type(input, 'action{Enter}');

    expect(input).toHaveValue('action');
    expect(input).toHaveAttribute('aria-invalid', 'true');
    expect(screen.getByText('Action is already excluded')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Add genre' })).toBeDisabled();
    expect(within(chips()).getAllByRole('button', { name: /^Remove / })).toHaveLength(1);
  });

  it('keeps Add disabled for a blank draft', async () => {
    const user = userEvent.setup();
    await renderPage();

    const add = screen.getByRole('button', { name: 'Add genre' });
    expect(add).toBeDisabled();
    await user.type(screen.getByLabelText(ADD_INPUT), '   ');
    expect(add).toBeDisabled();
  });

  it('round-trips server values into chips and pressed toggles', async () => {
    await renderPage({ excluded_genres: ['Sports', 'Animation & Modeling'] });

    expect(within(chips()).getByText('Sports')).toBeInTheDocument();
    expect(within(chips()).getByText('Animation & Modeling')).toBeInTheDocument();
    expect(
      await screen.findByRole('button', { name: 'Sports (2 games)' }),
    ).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('button', { name: 'Action (12 games)' })).toHaveAttribute(
      'aria-pressed',
      'false',
    );
  });

  it('shows the loading text while the genre list is pending', async () => {
    mockServer();
    mockApi.getGameGenres.mockReturnValue(new Promise(() => {}));
    render(<Settings />);

    expect(await screen.findByText('Loading genres…')).toBeInTheDocument();
  });

  it('shows the empty-cache message and still allows a manual add', async () => {
    const user = userEvent.setup();
    mockServer();
    mockApi.getGameGenres.mockResolvedValue({ success: true, data: { genres: [] } });
    render(<Settings />);

    expect(
      await screen.findByText(
        'No genres cached yet, genres appear as games are fetched from Steam',
      ),
    ).toBeInTheDocument();
    await user.type(screen.getByLabelText(ADD_INPUT), 'Racing{Enter}');
    expect(within(chips()).getByText('Racing')).toBeInTheDocument();
  });

  it('shows the error message and still allows a manual add', async () => {
    const user = userEvent.setup();
    mockServer();
    mockApi.getGameGenres.mockResolvedValue({
      success: false,
      data: { genres: [] },
      error: 'boom',
    });
    render(<Settings />);

    expect(
      await screen.findByText(
        'Could not load the genre list; you can still type a genre below',
      ),
    ).toBeInTheDocument();
    await user.type(screen.getByLabelText(ADD_INPUT), 'Racing{Enter}');
    expect(within(chips()).getByText('Racing')).toBeInTheDocument();
  });

  it('caps the list at 50 genres', async () => {
    const full = Array.from({ length: 50 }, (_, i) => `Genre ${i + 1}`);
    await renderPage({ excluded_genres: full });

    expect(screen.getByText('Maximum 50 genres')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Add genre' })).toBeDisabled();
    expect(
      await screen.findByRole('button', { name: 'Action (12 games)' }),
    ).toBeDisabled();
  });

  it('allows removing a genre at the cap, which re-enables adding', async () => {
    const user = userEvent.setup();
    const full = [...Array.from({ length: 49 }, (_, i) => `Genre ${i + 1}`), 'Sports'];
    await renderPage({ excluded_genres: full });

    const sports = await screen.findByRole('button', { name: 'Sports (2 games)' });
    expect(sports).toBeEnabled();
    await user.click(sports);

    expect(screen.queryByText('Maximum 50 genres')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Action (12 games)' })).toBeEnabled();
  });
  it('accepts a 64-character name typed with surrounding spaces', async () => {
    const user = userEvent.setup();
    await renderPage();
    const name = 'G'.repeat(64);

    const input = screen.getByLabelText(ADD_INPUT);
    await user.type(input, `  ${name}  `);
    expect(input).toHaveValue(`  ${name}  `);
    await user.click(screen.getByRole('button', { name: 'Add genre' }));
    await user.click(saveButtons()[0]);

    expect(await lastPutGenres()).toEqual([name]);
  });

  it('counts code points, not UTF-16 units: 33 emoji are accepted', async () => {
    const user = userEvent.setup();
    await renderPage();
    const name = '\u{1F3AE}'.repeat(33);
    expect(name.length).toBe(66);

    const input = screen.getByLabelText(ADD_INPUT);
    await user.click(input);
    await user.paste(name);
    await user.click(screen.getByRole('button', { name: 'Add genre' }));
    await user.click(saveButtons()[0]);

    expect(await lastPutGenres()).toEqual([name]);
  });

  it('rejects a 65-character name with an error and adds nothing', async () => {
    const user = userEvent.setup();
    await renderPage();

    const input = screen.getByLabelText(ADD_INPUT);
    await user.type(input, `${'G'.repeat(65)}{Enter}`);

    expect(
      screen.getByText('Genre names are limited to 64 characters'),
    ).toBeInTheDocument();
    expect(input).toHaveAttribute('aria-invalid', 'true');
    expect(input).toHaveValue('G'.repeat(65));
    expect(screen.getByRole('button', { name: 'Add genre' })).toBeDisabled();
    expect(screen.getByText('No genres excluded')).toBeInTheDocument();
  });

  it('shows a toggle as excluded for an ASCII case variant, like the backend match', async () => {
    await renderPage({ excluded_genres: ['ACTION'] });

    expect(
      await screen.findByRole('button', { name: 'Action (12 games)' }),
    ).toHaveAttribute('aria-pressed', 'true');
  });

  it('keeps a non-ASCII case variant as a separate genre, like the backend', async () => {
    const user = userEvent.setup();
    mockServer({ excluded_genres: ['éducation'] });
    mockApi.getGameGenres.mockResolvedValue({
      success: true,
      data: { genres: [{ name: 'Éducation', count: 3 }] },
    });
    render(<Settings />);

    // The backend's ASCII-only key treats "É" and "é" as different letters:
    // the stored "éducation" does not exclude the cached "Éducation".
    const toggle = await screen.findByRole('button', { name: 'Éducation (3 games)' });
    expect(toggle).toHaveAttribute('aria-pressed', 'false');

    await user.click(toggle);
    expect(toggle).toHaveAttribute('aria-pressed', 'true');
    expect(within(chips()).getByText('éducation')).toBeInTheDocument();
    expect(within(chips()).getByText('Éducation')).toBeInTheDocument();
    await user.click(saveButtons()[0]);
    expect(await lastPutGenres()).toEqual(['éducation', 'Éducation']);
  });

  it('accepts a typed non-ASCII case variant of an excluded genre', async () => {
    const user = userEvent.setup();
    await renderPage({ excluded_genres: ['éducation'] });

    await user.type(screen.getByLabelText(ADD_INPUT), 'Éducation{Enter}');

    expect(within(chips()).getByText('Éducation')).toBeInTheDocument();
    await user.click(saveButtons()[0]);
    expect(await lastPutGenres()).toEqual(['éducation', 'Éducation']);
  });

  it('disables a non-ASCII case variant toggle at the 50-genre cap', async () => {
    const full = [...Array.from({ length: 49 }, (_, i) => `Genre ${i + 1}`), 'éducation'];
    mockServer({ excluded_genres: full });
    mockApi.getGameGenres.mockResolvedValue({
      success: true,
      data: { genres: [{ name: 'Éducation', count: 3 }, { name: 'Action', count: 12 }] },
    });
    render(<Settings />);

    expect(
      await screen.findByRole('button', { name: 'Éducation (3 games)' }),
    ).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Action (12 games)' })).toBeDisabled();
  });
});

describe('Settings page: excluded genres review findings', () => {
  const ADD_INPUT = 'Add a genre';

  beforeEach(() => {
    vi.clearAllMocks();
    useUIStore.setState({ notifications: [] });
  });

  it('blocks saving while a typed genre has not been added, and says why', async () => {
    const user = userEvent.setup();
    await renderPage();

    await user.clear(screen.getByLabelText('Min Game Price ($)'));
    await user.type(screen.getByLabelText('Min Game Price ($)'), '20');
    await user.type(screen.getByLabelText(ADD_INPUT), 'Sports');

    const reason =
      'Press Add to include "Sports" in the excluded genres, or clear the field, to save';
    expect(screen.getByText(reason)).toBeInTheDocument();
    for (const button of saveButtons()) {
      expect(button).toBeDisabled();
      expect(button).toHaveAttribute('title', reason);
    }
    await user.click(saveButtons()[0]);
    expect(mockApi.put).not.toHaveBeenCalled();

    await user.click(screen.getByRole('button', { name: 'Add genre' }));
    expect(saveButtons()[0]).toBeEnabled();
    await user.click(saveButtons()[0]);
    await waitFor(() => expect(mockApi.put).toHaveBeenCalledTimes(1));
    const body = mockApi.put.mock.calls[0][1] as Partial<SettingsType>;
    expect(body.excluded_genres).toEqual(['Sports']);
    expect(body.autojoin_min_price).toBe(20);
  });

  it('lets the user save again after clearing an unconfirmed genre', async () => {
    const user = userEvent.setup();
    await renderPage();

    await user.clear(screen.getByLabelText('Min Game Price ($)'));
    await user.type(screen.getByLabelText('Min Game Price ($)'), '20');
    const input = screen.getByLabelText(ADD_INPUT);
    await user.type(input, 'Sports');
    expect(saveButtons()[0]).toBeDisabled();
    await user.clear(input);

    expect(saveButtons()[0]).toBeEnabled();
    expect(screen.getByText('You have unsaved changes')).toBeInTheDocument();
  });

  it('reports no unsaved changes once a typed genre is cleared with nothing else edited', async () => {
    const user = userEvent.setup();
    await renderPage();

    const input = screen.getByLabelText(ADD_INPUT);
    await user.type(input, 'Spo');
    expect(screen.getByText(/Press Add to include "Spo"/)).toBeInTheDocument();
    await user.clear(input);

    expect(screen.queryByText('You have unsaved changes')).not.toBeInTheDocument();
    expect(screen.queryByText(/Press Add to include/)).not.toBeInTheDocument();
    expect(saveButtons()).toHaveLength(1);
    expect(saveButtons()[0]).toBeDisabled();
    await user.click(saveButtons()[0]);
    expect(mockApi.put).not.toHaveBeenCalled();
  });

  it('does not count a whitespace-only draft as a change', async () => {
    const user = userEvent.setup();
    await renderPage();

    await user.type(screen.getByLabelText(ADD_INPUT), '   ');

    expect(screen.queryByText('You have unsaved changes')).not.toBeInTheDocument();
    expect(saveButtons()[0]).toBeDisabled();
  });

  it('names the existing exclusion when the typed duplicate blocks saving', async () => {
    const user = userEvent.setup();
    await renderPage({ excluded_genres: ['Action'] });

    await user.type(screen.getByLabelText(ADD_INPUT), 'ACTION');

    expect(
      screen.getByText('"Action" is already excluded; clear the Add a genre field to save'),
    ).toBeInTheDocument();
    expect(saveButtons()[0]).toBeDisabled();
  });

  it('uses the singular in the toggle name for a genre carried by one game', async () => {
    mockServer();
    mockApi.getGameGenres.mockResolvedValue({
      success: true,
      data: { genres: [{ name: 'RPG', count: 1 }, { name: 'Indie', count: 2 }] },
    });
    render(<Settings />);

    expect(await screen.findByRole('button', { name: 'RPG (1 game)' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Indie (2 games)' })).toBeInTheDocument();
  });

  it('truncates a long chip name and keeps its full text in the title', async () => {
    const name = 'G'.repeat(64);
    await renderPage({ excluded_genres: [name] });

    const label = within(screen.getByRole('group', { name: 'Excluded genres' })).getByText(name);
    expect(label).toHaveClass('truncate');
    expect(label).toHaveAttribute('title', name);
    expect(screen.getByRole('button', { name: `Remove ${name}` })).toHaveClass('shrink-0');
  });
});

describe('Settings page: excluded genres (challenger)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useUIStore.setState({ notifications: [] });
  });

  // The page has no <form>, so "Enter does not PUT" holds with or without
  // preventDefault. This pins the preventDefault itself, so the input stays
  // safe if the settings are ever wrapped in a form.
  it('prevents the default action of Enter in the add input', async () => {
    await renderPage();

    const input = screen.getByLabelText('Add a genre');
    fireEvent.change(input, { target: { value: 'Racing' } });
    const notPrevented = fireEvent.keyDown(input, { key: 'Enter' });

    expect(notPrevented).toBe(false);
    expect(
      within(screen.getByRole('group', { name: 'Excluded genres' })).getByText('Racing'),
    ).toBeInTheDocument();
  });

  // text-gray-500 on the pressed bg-red-100 is about 4.3:1, under AA for
  // text-xs; the count takes the red palette when the toggle is pressed.
  it('colours the count from the pressed state for contrast', async () => {
    await renderPage({ excluded_genres: ['Sports'] });

    const pressed = await screen.findByRole('button', { name: 'Sports (2 games)' });
    const unpressed = screen.getByRole('button', { name: 'Action (12 games)' });

    expect(within(pressed).getByText('2')).toHaveClass('text-red-700');
    expect(within(pressed).getByText('2')).not.toHaveClass('text-gray-500');
    expect(within(unpressed).getByText('12')).toHaveClass('text-gray-500');
  });

  it('shows the server-normalized list after save (form remounts on updated_at)', async () => {
    const user = userEvent.setup();
    await renderPage();
    // Server echoes a different spelling than was sent: the chips must follow it.
    mockApi.put.mockImplementationOnce(async (_url, body) => ({
      success: true,
      data: {
        ...mockSettings,
        ...(body as Partial<SettingsType>),
        excluded_genres: ['Racing (server)'],
        updated_at: '2026-01-03T00:00:00Z',
      },
    }));

    await user.type(screen.getByLabelText('Add a genre'), 'Racing{Enter}');
    await user.click(saveButtons()[0]);

    expect(
      await within(screen.getByRole('group', { name: 'Excluded genres' })).findByText(
        'Racing (server)',
      ),
    ).toBeInTheDocument();
  });
});
