import { test, expect } from '@playwright/test';
import { mockApi } from './mocks';

test.describe('Analytics page', () => {
  test('renders trend charts with legend and table view', async ({ page }) => {
    await mockApi(page);
    await page.goto('/analytics');

    await expect(page.getByRole('heading', { name: 'Analytics' })).toBeVisible();
    await expect(page.getByText('Entries per day')).toBeVisible();
    await expect(page.getByText('Points spent per day')).toBeVisible();
    await expect(page.getByText('Wins per day')).toBeVisible();

    // Legend carries series identity for the two-series chart
    const legend = page.locator('.recharts-legend-wrapper');
    await expect(legend.getByText('Successful')).toBeVisible();
    await expect(legend.getByText('Failed / skipped')).toBeVisible();

    // Charts actually painted bars/areas into the SVGs
    const barCount = await page.locator('.recharts-bar-rectangle').count();
    expect(barCount).toBeGreaterThan(10);

    // Accessible table alternative exists and opens
    await page.getByText('View trend data as table').click();
    await expect(page.getByRole('columnheader', { name: 'Points' })).toBeVisible();

    await page.screenshot({ path: 'test-results/analytics-light.png', fullPage: true });

    // Dark mode render
    await page.emulateMedia({ colorScheme: 'dark' });
    await page.evaluate(() => document.documentElement.classList.add('dark'));
    await page.screenshot({ path: 'test-results/analytics-dark.png', fullPage: true });
  });
});
