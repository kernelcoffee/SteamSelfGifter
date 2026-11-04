import { test, expect, type Locator, type Page } from '@playwright/test';
import { mockApi, mockSettings, type ApiCall } from './mocks';

const SAVED_TOAST = 'Settings saved. Auto-join uses them from the next cycle.';

function puts(calls: ApiCall[]) {
  return calls.filter((c) => c.method === 'PUT' && c.url === '/api/v1/settings');
}

function previews(calls: ApiCall[]) {
  return calls.filter((c) => c.method === 'POST' && c.url.startsWith('/api/v1/giveaways/preview'));
}

function lastPut(calls: ApiCall[]) {
  const all = puts(calls);
  expect(all).toHaveLength(1);
  return JSON.parse(all[0].postData ?? '{}');
}

async function save(page: Page) {
  await page.getByRole('button', { name: 'Save Changes' }).first().click();
  await expect(page.getByText(SAVED_TOAST)).toBeVisible();
}

test.describe('Settings', () => {
  let calls: ApiCall[];

  test.beforeEach(async ({ page }) => {
    calls = await mockApi(page);
    await page.goto('/settings');
    await expect(page.getByRole('heading', { name: 'Filters: what auto-join skips' })).toBeVisible();
  });

  test('loads current settings into the form', async ({ page }) => {
    await expect(page.getByLabel('PHPSESSID', { exact: true })).toHaveValue('e2e-session-cookie');
    // The page renders a save button in the header and one in the save bar.
    await expect(page.getByRole('button', { name: 'Save Changes' }).first()).toBeDisabled();
  });

  test('editing PHPSESSID enables save and PUTs the new value', async ({ page }) => {
    await page.getByLabel('PHPSESSID', { exact: true }).fill('new-cookie-value');
    await expect(page.getByText('Saving changes what auto-join enters from the next cycle.')).toBeVisible();
    await save(page);

    expect(lastPut(calls)).toMatchObject({ phpsessid: 'new-cookie-value' });
  });

  test('test session reports the mocked user', async ({ page }) => {
    await page.getByRole('button', { name: /test session/i }).click();
    await expect(page.getByText(/session valid.*e2e-user/i)).toBeVisible();
  });

  test('excluding a cached genre and typing a new one PUTs the full list', async ({ page }) => {
    const action = page.getByRole('group', { name: 'Action (12 games)' });
    const exclude = action.getByRole('button', { name: 'Excluded', exact: true });
    await expect(exclude).toHaveAttribute('aria-pressed', 'false');
    await exclude.click();
    await expect(exclude).toHaveAttribute('aria-pressed', 'true');

    const input = page.getByLabel('Add a genre');
    await input.fill('Racing');
    await input.press('Enter');
    await expect(input).toHaveValue('');
    await expect(
      page.getByRole('group', { name: 'Racing (not cached)' }).getByRole('button', { name: 'Excluded', exact: true })
    ).toHaveAttribute('aria-pressed', 'true');

    await save(page);
    const body = lastPut(calls);
    expect(body.excluded_genres).toEqual(['Action', 'Racing']);
    expect(body.included_genres).toEqual([]);
  });

  test('marks a cached genre Included and saves', async ({ page }) => {
    const action = page.getByRole('group', { name: 'Action (12 games)' });
    const include = action.getByRole('button', { name: 'Included', exact: true });
    await include.click();
    await expect(include).toHaveAttribute('aria-pressed', 'true');

    await save(page);
    const body = lastPut(calls);
    expect(body.included_genres).toEqual(['Action']);
    expect(body.excluded_genres).toEqual([]);
  });

  test('moves a genre from Included to Excluded', async ({ page }) => {
    const action = page.getByRole('group', { name: 'Action (12 games)' });
    await action.getByRole('button', { name: 'Included', exact: true }).click();
    await action.getByRole('button', { name: 'Excluded', exact: true }).click();
    await expect(action.getByRole('button', { name: 'Included', exact: true })).toHaveAttribute(
      'aria-pressed',
      'false'
    );

    await save(page);
    const body = lastPut(calls);
    expect(body.excluded_genres).toEqual(['Action']);
    expect(body.included_genres).toEqual([]);
  });

  test('manual add to the included list and the both-lists note', async ({ page }) => {
    await page
      .getByRole('group', { name: 'Action (12 games)' })
      .getByRole('button', { name: 'Excluded', exact: true })
      .click();
    await page.getByRole('combobox', { name: 'Add to list' }).selectOption('included');
    await page.getByLabel('Add a genre').fill('Action');
    await page.getByRole('button', { name: 'Add genre' }).click();

    await expect(
      page.getByText('Action is in both lists: exclusion wins, so it is never entered.')
    ).toBeVisible();
    await save(page);
    const body = lastPut(calls);
    expect(body.excluded_genres).toEqual(['Action']);
    expect(body.included_genres).toEqual(['Action']);
  });

  test('preview line updates after an edit', async ({ page }) => {
    const line = page.getByText('3 of 12 active giveaways would be entered next cycle').first();
    await expect(line).toBeVisible();
    await expect.poll(() => previews(calls).length).toBe(1);

    await page.getByLabel('Minimum review score', { exact: true }).fill('5');

    await expect(
      page.getByText('5 of 12 active giveaways would be entered next cycle (saved: 3)').first()
    ).toBeVisible();
    // One debounced request for the edit, on top of the initial one.
    expect(previews(calls)).toHaveLength(2);
    expect(JSON.parse(previews(calls)[1].postData ?? '{}').autojoin_min_score).toBe(5);
    expect(puts(calls)).toHaveLength(0);
  });

  test('reorders priorities by buttons and saves the displayed order', async ({ page }) => {
    const add = page.getByRole('combobox', { name: 'Add priority' });
    await add.selectOption('dlc');
    await page.getByRole('button', { name: 'Add the selected priority' }).click();
    await add.selectOption('ending_soon');
    await page.getByRole('button', { name: 'Add the selected priority' }).click();
    await page.getByRole('button', { name: 'Move DLC up' }).click();

    const rows = page.getByRole('list', { name: 'Priority order' }).getByRole('listitem');
    await expect(rows.nth(0)).toContainText('DLC');
    await expect(rows.nth(1)).toContainText('Wishlist');
    await expect(rows.nth(2)).toContainText('Ending soon');
    await expect(page.getByText('All priority types are in the list')).toBeVisible();

    await save(page);
    expect(lastPut(calls).autojoin_priorities).toEqual([
      { type: 'dlc' },
      { type: 'wishlist' },
      { type: 'ending_soon', threshold_minutes: 60 },
    ]);
  });

  test('removing then re-adding a priority sends the new order; removing all sends []', async ({
    page,
  }) => {
    await page.getByRole('button', { name: 'Remove Wishlist' }).click();
    await expect(page.getByText('Wishlist giveaways will obey your filters after saving.')).toBeVisible();
    await expect(page.getByText(/^No priorities:/)).toBeVisible();

    await save(page);
    expect(lastPut(calls).autojoin_priorities).toEqual([]);
  });

  test('ending soon threshold out of range blocks save with the range message and sends no PUT', async ({
    page,
  }) => {
    await page.getByRole('combobox', { name: 'Add priority' }).selectOption('ending_soon');
    await page.getByRole('button', { name: 'Add the selected priority' }).click();
    await page.getByLabel('Ending soon threshold (minutes)').fill('4');

    await expect(page.getByText('Must be between 5 and 10080 minutes')).toBeVisible();
    await expect(
      page.getByText('Enter an ending soon threshold between 5 and 10080 minutes to save', {
        exact: true,
      })
    ).toBeVisible();
    await expect(
      page.getByText('Preview paused: Enter an ending soon threshold between 5 and 10080 minutes to save').first()
    ).toBeVisible();
    for (const button of await page.getByRole('button', { name: 'Save Changes' }).all()) {
      await expect(button).toBeDisabled();
    }
    expect(puts(calls)).toHaveLength(0);
  });

  test('No minimum sends null for min score', async ({ page }) => {
    await page.getByRole('checkbox', { name: 'No minimum review score' }).check();
    await expect(page.getByLabel('Minimum review score', { exact: true })).toBeDisabled();
    await save(page);

    const body = lastPut(calls);
    expect(body.autojoin_min_score).toBeNull();
    expect(body.autojoin_min_reviews).toBe(mockSettings.autojoin_min_reviews);
  });

  test('clearing the score field without No minimum blocks save', async ({ page }) => {
    await page.getByLabel('Minimum review score', { exact: true }).fill('');

    await expect(
      page.getByText('Enter a minimum review score from 0 to 10, or choose No minimum').first()
    ).toBeVisible();
    for (const button of await page.getByRole('button', { name: 'Save Changes' }).all()) {
      await expect(button).toBeDisabled();
    }
    expect(puts(calls)).toHaveLength(0);
  });
});

test.describe('Phone width', () => {
  test.use({ viewport: { width: 360, height: 780 } });

  for (const path of ['/settings', '/giveaways']) {
    test(`${path} has no horizontal overflow at 360 px and the menu reaches the sidebar`, async ({
      page,
    }) => {
      await mockApi(page);
      await page.goto(path);
      await expect(page.getByRole('main')).toContainText(path === '/settings' ? 'Priority order' : 'Portal Reloaded');

      const overflow = await page.evaluate(
        () => document.documentElement.scrollWidth - window.innerWidth
      );
      expect(overflow).toBeLessThanOrEqual(0);

      await page.getByRole('button', { name: 'Open menu' }).click();
      const menu = page.getByRole('complementary', { name: 'Main menu' });
      await menu.getByRole('link', { name: 'Logs' }).click();
      await expect(page).toHaveURL(/\/logs$/);
      await expect(menu).toHaveCount(0);
    });
  }
});

test.describe('Genre names at phone width', () => {
  test.use({ viewport: { width: 360, height: 780 } });

  test('every genre name is shown in full, with its toggles wrapped under it', async ({ page }) => {
    await mockApi(page);
    await page.goto('/settings');
    const grid = page.getByRole('group', { name: 'Genres' });
    const longest = grid.getByRole('group', { name: 'Massively Multiplayer (3 games)' });
    await expect(longest).toBeVisible();

    const names = grid.getByTestId('genre-name');
    expect(await names.count()).toBeGreaterThanOrEqual(3);
    for (const name of await names.all()) {
      const cut = await name.evaluate((el) => el.scrollWidth > el.clientWidth);
      expect(cut, `${await name.textContent()} is truncated`).toBe(false);
    }
    // The toggles sit on the line below the name.
    const nameBox = await longest.getByTestId('genre-name').boundingBox();
    const toggleBox = await longest.getByRole('button', { name: 'Excluded' }).boundingBox();
    // A missing box compares against Infinity, so it fails instead of passing.
    const nameBottom = nameBox === null ? Infinity : nameBox.y + nameBox.height;
    expect(toggleBox?.y ?? -Infinity).toBeGreaterThanOrEqual(nameBottom);
  });
});

test.describe('Phone width with unsaved changes', () => {
  test.use({ viewport: { width: 360, height: 640 } });

  /** True when the element is the topmost hit at its own centre. */
  async function isOnTop(locator: Locator): Promise<boolean> {
    const box = await locator.boundingBox();
    if (box === null) return false;
    const point = { x: box.x + box.width / 2, y: box.y + box.height / 2 };
    return locator.evaluate((el, { x, y }) => {
      const hit = document.elementFromPoint(x, y);
      return hit !== null && el.contains(hit);
    }, point);
  }

  test('the open menu sits above the sticky save bar, and toasts above both', async ({ page }) => {
    await mockApi(page);
    await page.route('**/api/v1/settings', (route) =>
      route.request().method() === 'PUT'
        ? route.fulfill({
            status: 400,
            contentType: 'application/json',
            body: JSON.stringify({ detail: 'user_agent cannot be null' }),
          })
        : route.fallback(),
    );
    await page.goto('/settings');
    await expect(page.getByRole('main')).toContainText('Priority order');

    // Removing an exempt type gives the tallest bar: consequence, warning, reason, Save.
    await page.getByRole('button', { name: 'Remove Wishlist' }).click();
    const consequence = page.getByText('Saving changes what auto-join enters from the next cycle.');
    await expect(consequence).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0);

    // Scrolled down, as when Save is reached on a phone: the header must still
    // hold the toggle, and the open menu must not cover it.
    await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight));
    expect(await page.evaluate(() => window.scrollY)).toBeGreaterThan(0);
    const openButton = page.getByRole('button', { name: 'Open menu' });
    expect(await isOnTop(openButton), 'Open menu scrolled out of reach').toBe(true);
    await openButton.click();
    const menu = page.getByRole('complementary', { name: 'Main menu' });
    const closeButton = page.getByRole('button', { name: 'Close menu' });
    expect(await isOnTop(closeButton), 'Close menu is covered').toBe(true);
    for (const name of ['Dashboard', 'Giveaways', 'Logs', 'Settings']) {
      expect(await isOnTop(menu.getByRole('link', { name, exact: true })), `${name} link is covered`).toBe(true);
    }
    // The backdrop covers the bar, so the bar cannot be used while the menu is open.
    expect(await isOnTop(consequence)).toBe(false);
    await page.getByTestId('menu-backdrop').click({ position: { x: 340, y: 500 } });
    await expect(menu).toHaveCount(0);
    expect(await isOnTop(consequence)).toBe(true);

    // Tapping the X closes the menu and stays on Settings with the edit kept.
    await page.getByRole('button', { name: 'Open menu' }).click();
    await expect(menu).toBeVisible();
    await closeButton.click();
    await expect(menu).toHaveCount(0);
    await expect(page).toHaveURL(/\/settings$/);
    await expect(consequence).toBeVisible();

    // A toast stays above the bar.
    await page.getByRole('button', { name: 'Save Changes' }).last().click();
    const toast = page.getByText('user_agent cannot be null');
    await expect(toast).toBeVisible();
    expect(await isOnTop(toast)).toBe(true);
  });
});
