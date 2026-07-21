import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent } from '@/test/utils';
import { Header } from './Header';
import { useThemeStore } from '@/stores/themeStore';
import { api } from '@/services/api';

vi.mock('@/services/api', () => ({
  api: {
    get: vi.fn().mockResolvedValue({ success: false, error: 'not mocked', data: undefined }),
  },
}));

const mockApi = vi.mocked(api);

function mockSession(session: object) {
  mockApi.get.mockResolvedValue({
    success: true,
    data: { session },
  });
}

describe('Header', () => {
  beforeEach(() => {
    // Reset theme store
    useThemeStore.setState({ isDark: false });
    document.documentElement.classList.remove('dark');
    mockApi.get.mockResolvedValue({ success: false, error: 'not mocked', data: undefined });
  });

  it('should render the app title', () => {
    render(<Header />);

    expect(screen.getByText('SteamSelfGifter')).toBeInTheDocument();
  });

  describe('scheduler status', () => {
    it('should show Stopped when scheduler is not running', () => {
      render(<Header schedulerRunning={false} />);

      expect(screen.getByText('Stopped')).toBeInTheDocument();
    });

    it('should show Running when scheduler is running', () => {
      render(<Header schedulerRunning={true} />);

      expect(screen.getByText('Running')).toBeInTheDocument();
    });

    it('should show Paused when scheduler is paused', () => {
      render(<Header schedulerRunning={true} schedulerPaused={true} />);

      expect(screen.getByText('Paused')).toBeInTheDocument();
    });
  });

  describe('theme toggle', () => {
    it('should render theme toggle button', () => {
      render(<Header />);

      const button = screen.getByRole('button', { name: /switch to dark mode/i });
      expect(button).toBeInTheDocument();
    });

    it('should toggle theme when clicked', () => {
      render(<Header />);

      const button = screen.getByRole('button', { name: /switch to dark mode/i });
      fireEvent.click(button);

      expect(useThemeStore.getState().isDark).toBe(true);
    });

    it('should show sun icon in dark mode', () => {
      useThemeStore.setState({ isDark: true });
      render(<Header />);

      const button = screen.getByRole('button', { name: /switch to light mode/i });
      expect(button).toBeInTheDocument();
    });
  });

  describe('SteamGifts session indicator', () => {
    it('shows connected icon with username tooltip when session is valid', async () => {
      mockSession({ configured: true, valid: true, username: 'TestUser', error: null });
      render(<Header />);

      const icon = await screen.findByLabelText('Connected to SteamGifts as TestUser');
      expect(icon).toBeInTheDocument();
    });

    it('shows invalid-session icon when session expired', async () => {
      mockSession({ configured: true, valid: false, username: null, error: 'expired' });
      render(<Header />);

      const icon = await screen.findByLabelText(/session invalid or expired/i);
      expect(icon).toBeInTheDocument();
    });

    it('shows not-configured icon when no session is set', async () => {
      mockSession({ configured: false, valid: false, username: null, error: null });
      render(<Header />);

      const icon = await screen.findByLabelText(/session not configured/i);
      expect(icon).toBeInTheDocument();
    });

    it('renders no indicator while session status is unknown', () => {
      render(<Header />);

      expect(screen.queryByLabelText(/steamgifts/i)).not.toBeInTheDocument();
    });
  });
});
