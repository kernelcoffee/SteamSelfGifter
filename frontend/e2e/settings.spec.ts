import { test, expect } from '@playwright/test';
import { mockApi, type ApiCall } from './mocks';

test.describe('Settings', () => {
  let calls: ApiCall[];

  test.beforeEach(async ({ page }) => {
    calls = await mockApi(page);
    await page.goto('/settings');
  });

  test('loads current settings into the form', async ({ page }) => {
    await expect(page.getByLabel('PHPSESSID', { exact: true })).toHaveValue('e2e-session-cookie');
    // The page renders a save button in the header and one at the bottom.
    await expect(page.getByRole('button', { name: 'Save Changes' }).first()).toBeDisabled();
  });

  test('editing PHPSESSID enables save and PUTs the new value', async ({ page }) => {
    const field = page.getByLabel('PHPSESSID', { exact: true });
    await field.fill('new-cookie-value');

    const save = page.getByRole('button', { name: 'Save Changes' }).first();
    await expect(save).toBeEnabled();
    await save.click();

    await expect(page.getByText('Settings saved successfully')).toBeVisible();

    const put = calls.find((c) => c.method === 'PUT' && c.url === '/api/v1/settings');
    expect(put).toBeTruthy();
    expect(JSON.parse(put!.postData!)).toMatchObject({ phpsessid: 'new-cookie-value' });
  });

  test('test session reports the mocked user', async ({ page }) => {
    await page.getByRole('button', { name: /test session/i }).click();
    await expect(page.getByText(/session valid.*e2e-user/i)).toBeVisible();
  });
  test('excluding a cached genre and typing a new one PUTs the full list', async ({ page }) => {
    const action = page.getByRole('button', { name: 'Action (12 games)' });
    await expect(action).toHaveAttribute('aria-pressed', 'false');
    await action.click();
    await expect(action).toHaveAttribute('aria-pressed', 'true');

    const input = page.getByLabel('Add a genre');
    await input.fill('Racing');
    await input.press('Enter');
    await expect(input).toHaveValue('');
    const chips = page.getByRole('group', { name: 'Excluded genres' });
    await expect(chips.getByText('Racing', { exact: true })).toBeVisible();

    await page.getByRole('button', { name: 'Save Changes' }).first().click();
    await expect(page.getByText('Settings saved successfully')).toBeVisible();

    const puts = calls.filter((c) => c.method === 'PUT' && c.url === '/api/v1/settings');
    expect(puts).toHaveLength(1);
    expect(JSON.parse(puts[0].postData!).excluded_genres).toEqual(['Action', 'Racing']);
  });
});
