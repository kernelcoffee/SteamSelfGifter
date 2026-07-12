import { test, expect } from '@playwright/test';
import { mockApi, type ApiCall } from './mocks';

test.describe('Giveaways', () => {
  let calls: ApiCall[];

  test.beforeEach(async ({ page }) => {
    calls = await mockApi(page);
    await page.goto('/giveaways');
  });

  test('lists the mocked giveaways', async ({ page }) => {
    await expect(page.getByText('Portal Reloaded')).toBeVisible();
    await expect(page.getByText('Half-Life 3')).toBeVisible();
    await expect(page.getByText('Stardew Galaxy')).toBeVisible();
  });

  test('entering a giveaway posts to the enter endpoint', async ({ page }) => {
    // The first non-entered card exposes an Enter button.
    await page.getByRole('button', { name: 'Enter', exact: true }).first().click();

    await expect
      .poll(() =>
        calls.some((c) => c.method === 'POST' && /\/giveaways\/Code\d+\/enter$/.test(c.url))
      )
      .toBe(true);
  });

  test('searching narrows the list', async ({ page }) => {
    const search = page.getByPlaceholder(/search/i);
    await search.fill('Portal');
    await search.press('Enter');

    await expect(page.getByText('Portal Reloaded')).toBeVisible();
    await expect(page.getByText('Half-Life 3')).not.toBeVisible();
  });
});
