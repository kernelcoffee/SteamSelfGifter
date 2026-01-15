// Re-export everything from testing-library
export * from '@testing-library/react';
export { userEvent } from '@testing-library/user-event';

// Override render with custom render that includes providers
export { customRender as render } from './render';

// Export TestProviders for direct use if needed
export { TestProviders } from './TestProviders';