import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import path from 'path';

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  test: {
    // Use jsdom for DOM testing
    environment: 'jsdom',

    // Enable globals (describe, it, expect, etc.)
    globals: true,

    // Setup file for test utilities
    setupFiles: ['./src/test/setup.ts'],

    // Include patterns
    include: ['src/**/*.{test,spec}.{ts,tsx}'],

    // Coverage configuration
    coverage: {
      provider: 'v8',
      reporter: ['text', 'html', 'lcov'],
      exclude: [
        'node_modules/',
        'src/test/',
        '**/*.d.ts',
        'src/main.tsx',
        'src/vite-env.d.ts',
      ],
    },

    // Global test timeout
    testTimeout: 10000,
  },
});
