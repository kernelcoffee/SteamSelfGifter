import { create } from 'zustand';
import { persist } from 'zustand/middleware';

interface ThemeState {
  // State
  isDark: boolean;

  // Actions
  toggle: () => void;
  setDark: (isDark: boolean) => void;
}

/**
 * Theme store with localStorage persistence
 *
 * Manages dark/light mode preference:
 * - Detects system preference on first visit
 * - Persists user preference to localStorage
 * - Applies theme class to document
 */
export const useThemeStore = create<ThemeState>()(
  persist(
    (set) => ({
      // Initial state: check system preference
      isDark: typeof window !== 'undefined'
        ? window.matchMedia('(prefers-color-scheme: dark)').matches
        : false,

      // Toggle between dark and light
      toggle: () => set((state) => {
        const newIsDark = !state.isDark;
        applyTheme(newIsDark);
        return { isDark: newIsDark };
      }),

      // Set specific theme
      setDark: (isDark) => set(() => {
        applyTheme(isDark);
        return { isDark };
      }),
    }),
    {
      name: 'theme-storage', // localStorage key
      onRehydrateStorage: () => (state) => {
        // Apply theme after rehydration from localStorage
        if (state) {
          applyTheme(state.isDark);
        }
      },
    }
  )
);

/**
 * Apply theme to document by toggling 'dark' class
 */
export function applyTheme(isDark: boolean): void {
  if (typeof document !== 'undefined') {
    if (isDark) {
      document.documentElement.classList.add('dark');
    } else {
      document.documentElement.classList.remove('dark');
    }
  }
}

/**
 * Initialize theme on app load
 * Call this in main.tsx or App.tsx
 */
export function initializeTheme(): void {
  const state = useThemeStore.getState();
  applyTheme(state.isDark);
}
