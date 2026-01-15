import { ReactElement } from 'react';
import { render, RenderOptions } from '@testing-library/react';
import { TestProviders } from './TestProviders';

export function customRender(
  ui: ReactElement,
  options?: Omit<RenderOptions, 'wrapper'>
) {
  return render(ui, { wrapper: TestProviders, ...options });
}