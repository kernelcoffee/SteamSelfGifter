import { test, expect } from '@playwright/test';
import { mockApi } from './mocks';

/**
 * Regression: partial/unexpected API payloads must degrade gracefully, not
 * blank the page with an unhandled TypeError (History and Analytics did
 * exactly that before the defensive guards).
 *
 * Routes registered after mockApi() take precedence, so each test overrides
 * just the endpoint it degrades.
 */
function ok(data: unknown) {
  return {
    status: 200,
    contentType: 'application/json' as const,
    body: JSON.stringify({ success: true, data }),
  };
}

test('History survives an empty entries payload', async ({ page }) => {
  await mockApi(page);
  await page.route('**/api/v1/entries/**', (route) => route.fulfill(ok({})));

  await page.goto('/history');

  await expect(page.getByRole('heading', { name: /history/i })).toBeVisible();
  await expect(page.getByText(/showing 0 of 0 entries/i)).toBeVisible();
});

test('Analytics survives summaries without by_type or win_rate', async ({ page }) => {
  await mockApi(page);
  await page.route('**/api/v1/analytics/entries/summary**', (route) =>
    route.fulfill(ok({ total: 5, successful: 5, failed: 0, total_points_spent: 100, success_rate: 100 }))
  );
  await page.route('**/api/v1/analytics/giveaways/summary**', (route) =>
    route.fulfill(ok({ total: 10, active: 3, entered: 2, hidden: 0, wins: 1 }))
  );

  await page.goto('/analytics');

  await expect(page.getByRole('heading', { name: /analytics/i })).toBeVisible();
  // The by_type breakdown renders with zeroed values instead of crashing.
  await expect(page.getByText('Automatic')).toBeVisible();
});

test('Settings shows the registry error and no form when the registry fails', async ({ page }) => {
  await mockApi(page);
  await page.route('**/api/v1/giveaways/registry', (route) =>
    route.fulfill({
      status: 500,
      contentType: 'application/json',
      body: JSON.stringify({
        error: { message: 'Internal server error', code: 'SYS_001', details: {} },
      }),
    })
  );

  await page.goto('/settings');

  await expect(
    page.getByText(
      'Could not load the auto-join registry (GET /giveaways/registry). Reload the page; if it keeps failing check the backend logs.'
    )
  ).toBeVisible();
  await expect(page.getByText('Internal server error')).toBeVisible();
  await expect(page.getByLabel('PHPSESSID', { exact: true })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Save Changes' })).toHaveCount(0);
});
