import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@/test/utils';
import { Header } from './Header';
import { useThemeStore } from '@/stores/themeStore';

describe('Header', () => {
  beforeEach(() => {
    // Reset theme store
    useThemeStore.setState({ isDark: false });
    document.documentElement.classList.remove('dark');
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
});
