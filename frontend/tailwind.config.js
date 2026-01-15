/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        // Custom colors from FUNCTIONAL_SPEC.md
        background: {
          light: '#ffffff',
          dark: '#1a1a2e',
        },
        surface: {
          light: '#f5f5f5',
          dark: '#16213e',
        },
        primary: {
          light: '#3b82f6',
          dark: '#60a5fa',
        },
        success: {
          light: '#22c55e',
          dark: '#4ade80',
        },
        warning: {
          light: '#eab308',
          dark: '#facc15',
        },
        error: {
          light: '#ef4444',
          dark: '#f87171',
        },
      },
    },
  },
  plugins: [
    require('@tailwindcss/forms'),
  ],
}
