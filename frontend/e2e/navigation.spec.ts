import { test, expect } from '@playwright/test';
import { mockApi } from './mocks';

test.describe('Navigation', () => {
  test.beforeEach(async ({ page }) => {
    await mockApi(page);
    await page.goto('/dashboard');
  });

  test('sidebar links reach every page', async ({ page }) => {
    const pages: Array<[RegExp | string, RegExp]> = [
      ['Giveaways', /\/giveaways$/],
      ['Wins', /\/wins$/],
      ['History', /\/history$/],
      ['Analytics', /\/analytics$/],
      ['Logs', /\/logs$/],
      ['Settings', /\/settings$/],
      ['Dashboard', /\/dashboard$/],
    ];

    for (const [name, url] of pages) {
      await page.getByRole('link', { name }).first().click();
      await expect(page).toHaveURL(url);
    }
  });

  test('unknown routes fall back to the dashboard', async ({ page }) => {
    await page.goto('/definitely-not-a-page');
    await expect(page).toHaveURL(/\/dashboard$/);
  });
});
