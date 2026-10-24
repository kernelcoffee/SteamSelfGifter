import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent, userEvent } from '@/test/utils';
import { Settings } from './Settings';
import { api } from '@/services/api';
import { useUIStore } from '@/stores/uiStore';
import type { Settings as SettingsType } from '@/types';

vi.mock('@/services/api', () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
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

function mockServer(initial: Partial<SettingsType> = {}) {
  const loaded = { ...mockSettings, ...initial };
  mockApi.get.mockResolvedValue({ success: true, data: loaded });
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
