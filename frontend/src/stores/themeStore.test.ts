import { describe, it, expect, beforeEach } from 'vitest';
import { useThemeStore, applyTheme } from './themeStore';

describe('themeStore', () => {
  beforeEach(() => {
    // Reset store state before each test
    useThemeStore.setState({ isDark: false });
    // Clear document class
    document.documentElement.classList.remove('dark');
  });

  describe('initial state', () => {
    it('should have isDark as false by default in tests', () => {
      const { isDark } = useThemeStore.getState();
      expect(isDark).toBe(false);
    });
  });

  describe('toggle', () => {
    it('should toggle from light to dark', () => {
      useThemeStore.setState({ isDark: false });

      useThemeStore.getState().toggle();

      expect(useThemeStore.getState().isDark).toBe(true);
    });

    it('should toggle from dark to light', () => {
      useThemeStore.setState({ isDark: true });

      useThemeStore.getState().toggle();

      expect(useThemeStore.getState().isDark).toBe(false);
    });

    it('should apply theme to document when toggling', () => {
      useThemeStore.setState({ isDark: false });

      useThemeStore.getState().toggle();

      expect(document.documentElement.classList.contains('dark')).toBe(true);
    });
  });

  describe('setDark', () => {
    it('should set theme to dark', () => {
      useThemeStore.getState().setDark(true);

      expect(useThemeStore.getState().isDark).toBe(true);
    });

    it('should set theme to light', () => {
      useThemeStore.setState({ isDark: true });

      useThemeStore.getState().setDark(false);

      expect(useThemeStore.getState().isDark).toBe(false);
    });

    it('should apply theme to document', () => {
      useThemeStore.getState().setDark(true);

      expect(document.documentElement.classList.contains('dark')).toBe(true);

      useThemeStore.getState().setDark(false);

      expect(document.documentElement.classList.contains('dark')).toBe(false);
    });
  });
});

describe('applyTheme', () => {
  beforeEach(() => {
    document.documentElement.classList.remove('dark');
  });

  it('should add dark class when isDark is true', () => {
    applyTheme(true);

    expect(document.documentElement.classList.contains('dark')).toBe(true);
  });

  it('should remove dark class when isDark is false', () => {
    document.documentElement.classList.add('dark');

    applyTheme(false);

    expect(document.documentElement.classList.contains('dark')).toBe(false);
  });
});
