import { test, expect } from '@playwright/test';
import { mockApi, mockSettings, type ApiCall } from './mocks';

function listRequests(calls: ApiCall[]) {
  return calls.filter(
    (c) => c.method === 'GET' && /^\/api\/v1\/giveaways(\/(active|wishlist|dlc))?\?/.test(c.url)
  );
}

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
    await expect(page.getByText('Action, Indie', { exact: true }).first()).toBeVisible();
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

  test('auto-join line shows the stored label', async ({ page }) => {
    await expect(page.getByText('Review score 6 is below your minimum 7')).toBeVisible();
    await expect(page.getByText('Not evaluated yet; checked at the next cycle').first()).toBeVisible();
    // The entered giveaway has no Auto-join line: three cards, two lines.
    await expect(page.getByText('Auto-join:')).toHaveCount(2);
  });

  test('lens toggle sends lens=autojoin and shows decision labels', async ({ page }) => {
    await expect(page.getByText('Portal Reloaded')).toBeVisible();
    expect(listRequests(calls).every((c) => !c.url.includes('lens'))).toBe(true);

    const lens = page.getByRole('button', { name: 'Auto-join lens' });
    await expect(lens).toHaveAttribute('aria-pressed', 'false');
    // The explanation is the native tooltip, out of the layout.
    await expect(lens).toHaveAttribute(
      'title',
      'Show only what your saved policy would enter next cycle, in entry order'
    );
    await expect(page.getByText('Show only what your saved policy would enter')).toHaveCount(0);
    await lens.click();
    await expect(lens).toHaveAttribute('aria-pressed', 'true');

    await expect
      .poll(() => listRequests(calls).some((c) => c.url.includes('lens=autojoin')))
      .toBe(true);
    await expect(
      page.getByTitle('Joinable: Wishlist, filters skipped, 1st in your order').first()
    ).toBeVisible();
    await expect(page.getByText('Review score 6 is below your minimum 7')).toHaveCount(0);
    await expect(
      page.getByText('2 candidates in entry order; the points budget and per cycle cap apply at cycle time')
    ).toBeVisible();
    expect(calls.some((c) => c.method === 'PUT')).toBe(false);
  });

  test('lens is off after reload', async ({ page }) => {
    await page.getByRole('button', { name: 'Auto-join lens' }).click();
    await expect.poll(() => listRequests(calls).some((c) => c.url.includes('lens=autojoin'))).toBe(true);

    const before = calls.length;
    await page.reload();
    await expect(page.getByText('Portal Reloaded')).toBeVisible();

    await expect(page.getByRole('button', { name: 'Auto-join lens' })).toHaveAttribute(
      'aria-pressed',
      'false'
    );
    const firstAfter = listRequests(calls.slice(before))[0];
    expect(firstAfter.url).not.toContain('lens');
    const stored = await page.evaluate(() => window.localStorage.getItem('giveaway-filters'));
    expect(stored ?? '').not.toContain('lens');
  });
});

test.describe('Wishlist standing line', () => {
  test('wishlist first in the saved priority order', async ({ page }) => {
    await mockApi(page);
    await page.goto('/giveaways/wishlist');
    await expect(page.getByText('Wishlist giveaways skip the filters and are entered 1st')).toBeVisible();
  });

  test('wishlist absent from the saved priority order', async ({ page }) => {
    await mockApi(page);
    await page.route('**/api/v1/settings', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ success: true, data: { ...mockSettings, autojoin_priorities: [] } }),
      })
    );
    await page.goto('/giveaways/wishlist');
    await expect(
      page.getByText('Wishlist is not in your priority order: these giveaways obey the filters')
    ).toBeVisible();
  });
});
