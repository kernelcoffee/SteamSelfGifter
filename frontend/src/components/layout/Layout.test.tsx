import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, userEvent, within } from '@/test/utils';
import { Layout, MOBILE_MENU_ID } from './Layout';

vi.mock('@/services/api', () => ({
  api: {
    get: vi.fn().mockResolvedValue({ success: false, error: 'not mocked', data: undefined }),
  },
}));

function renderLayout() {
  window.history.pushState({}, '', '/dashboard');
  return render(
    <Layout>
      <p>Page content</p>
    </Layout>,
  );
}

describe('Layout: responsive shell', () => {
  beforeEach(() => {
    window.history.pushState({}, '', '/dashboard');
  });

  it('keeps the desktop sidebar from md up and a menu button below md', () => {
    renderLayout();

    const nav = screen.getAllByRole('navigation');
    expect(nav).toHaveLength(1);
    expect(nav[0].closest('aside')).toHaveClass('hidden', 'md:block');
    const menu = screen.getByRole('button', { name: 'Open menu' });
    expect(menu).toHaveClass('md:hidden');
    expect(menu).toHaveAttribute('aria-expanded', 'false');
    // aria-controls only points at the menu while the menu exists.
    expect(menu).not.toHaveAttribute('aria-controls');
    expect(screen.getByRole('main')).toHaveClass('p-4', 'md:p-6', 'min-w-0');
  });

  it('opens the menu as an overlay and closes it from the button', async () => {
    const user = userEvent.setup();
    renderLayout();

    await user.click(screen.getByRole('button', { name: 'Open menu' }));

    const overlay = screen.getByRole('complementary', { name: 'Main menu' });
    expect(overlay).toHaveAttribute('id', MOBILE_MENU_ID);
    expect(overlay).toHaveClass('fixed', 'md:hidden');
    const close = screen.getByRole('button', { name: 'Close menu' });
    expect(close).toHaveAttribute('aria-expanded', 'true');
    expect(close).toHaveAttribute('aria-controls', MOBILE_MENU_ID);

    await user.click(close);
    expect(screen.queryByRole('complementary', { name: 'Main menu' })).not.toBeInTheDocument();
  });

  it('keeps the header and its toggle above the overlay, which starts under the header', async () => {
    const user = userEvent.setup();
    renderLayout();

    await user.click(screen.getByRole('button', { name: 'Open menu' }));

    // Overlay z-40 and backdrop z-30 start at top-16, under the h-16 header,
    // which is sticky at z-50 below md, so the Close button is never covered.
    expect(screen.getByRole('banner')).toHaveClass('sticky', 'top-0', 'z-50', 'h-16', 'md:static');
    const overlay = screen.getByRole('complementary', { name: 'Main menu' });
    expect(overlay).toHaveClass('top-16', 'bottom-0', 'z-40');
    expect(overlay).not.toHaveClass('inset-y-0');
    expect(screen.getByTestId('menu-backdrop')).toHaveClass('top-16', 'bottom-0', 'z-30');
  });

  it('moves focus into the menu on open and back to the toggle on close', async () => {
    const user = userEvent.setup();
    renderLayout();

    await user.click(screen.getByRole('button', { name: 'Open menu' }));
    const overlay = screen.getByRole('complementary', { name: 'Main menu' });
    expect(within(overlay).getByRole('link', { name: 'Dashboard' })).toHaveFocus();

    await user.keyboard('{Escape}');
    expect(screen.getByRole('button', { name: 'Open menu' })).toHaveFocus();

    await user.click(screen.getByRole('button', { name: 'Open menu' }));
    await user.click(screen.getByTestId('menu-backdrop'));
    expect(screen.getByRole('button', { name: 'Open menu' })).toHaveFocus();
  });

  it('closes on Escape and on the backdrop', async () => {
    const user = userEvent.setup();
    renderLayout();

    await user.click(screen.getByRole('button', { name: 'Open menu' }));
    await user.keyboard('{Escape}');
    expect(screen.queryByRole('complementary', { name: 'Main menu' })).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Open menu' }));
    await user.click(screen.getByTestId('menu-backdrop'));
    expect(screen.queryByRole('complementary', { name: 'Main menu' })).not.toBeInTheDocument();
  });

  it('closes after following a link', async () => {
    const user = userEvent.setup();
    renderLayout();

    await user.click(screen.getByRole('button', { name: 'Open menu' }));
    const overlay = screen.getByRole('complementary', { name: 'Main menu' });
    await user.click(within(overlay).getByRole('link', { name: 'Settings' }));

    expect(window.location.pathname).toBe('/settings');
    expect(screen.queryByRole('complementary', { name: 'Main menu' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Open menu' })).toHaveAttribute('aria-expanded', 'false');
  });

  it('removes the Escape listener when the menu closes', async () => {
    const user = userEvent.setup();
    const remove = vi.spyOn(document, 'removeEventListener');
    renderLayout();

    await user.click(screen.getByRole('button', { name: 'Open menu' }));
    await user.click(screen.getByRole('button', { name: 'Close menu' }));

    expect(remove).toHaveBeenCalledWith('keydown', expect.any(Function));
    remove.mockRestore();
  });
});
