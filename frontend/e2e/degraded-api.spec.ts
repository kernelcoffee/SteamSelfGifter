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
