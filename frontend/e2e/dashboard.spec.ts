import { test, expect } from '@playwright/test';
import { mockApi, type ApiCall } from './mocks';

test.describe('Dashboard', () => {
  let calls: ApiCall[];

  test.beforeEach(async ({ page }) => {
    calls = await mockApi(page);
    await page.goto('/dashboard');
  });

  test('renders the stats from the analytics endpoint', async ({ page }) => {
    await expect(page.getByText('Current Points')).toBeVisible();
    await expect(page.getByText('342', { exact: true })).toBeVisible();
    await expect(page.getByText('Active Giveaways')).toBeVisible();
    await expect(page.getByText('57', { exact: true })).toBeVisible();
    await expect(page.getByText('Win Rate (30d)')).toBeVisible();
  });

  test('root path redirects to the dashboard', async ({ page }) => {
    await page.goto('/');
    await expect(page).toHaveURL(/\/dashboard$/);
  });

  test('stopping the scheduler calls the stop endpoint', async ({ page }) => {
    // Scheduler is mocked as running, so a stop control must be available.
    await page.getByRole('button', { name: /stop/i }).first().click();

    await expect
      .poll(() => calls.some((c) => c.method === 'POST' && c.url === '/api/v1/scheduler/stop'))
      .toBe(true);
  });
});
