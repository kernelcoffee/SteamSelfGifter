import { ReactNode, useEffect, useRef, useState } from 'react';
import { useLocation } from 'react-router';
import { Header } from './Header';
import { Sidebar } from './Sidebar';
import { Notifications } from '@/components/common/Notifications';

interface LayoutProps {
  children: ReactNode;
  schedulerRunning?: boolean;
  schedulerPaused?: boolean;
}

export const MOBILE_MENU_ID = 'mobile-menu';

/**
 * Main application layout with header, sidebar, and content area. Below the
 * md breakpoint the sidebar is hidden and opens as an overlay from the
 * Header's menu button. The header stays on top of the overlay (it is sticky
 * at phone width and the overlay starts under it), so the button that opened
 * the menu is the one that closes it.
 */
export function Layout({ children, schedulerRunning, schedulerPaused }: LayoutProps) {
  const { pathname } = useLocation();
  // The overlay is open for the route it was opened on, so following a link
  // closes it without syncing state in an effect.
  const [openOn, setOpenOn] = useState<string | null>(null);
  const menuOpen = openOn === pathname;
  const closeMenu = () => setOpenOn(null);
  const menuButtonRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLElement>(null);
  const wasOpenRef = useRef(false);

  // Focus moves into the menu when it opens and back to its button when it
  // closes, whichever way it was closed. Only focus moves here, no state.
  useEffect(() => {
    if (menuOpen) {
      menuRef.current?.querySelector('a')?.focus();
    } else if (wasOpenRef.current) {
      menuButtonRef.current?.focus();
    }
    wasOpenRef.current = menuOpen;
  }, [menuOpen]);

  useEffect(() => {
    if (!menuOpen) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpenOn(null);
    };
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [menuOpen]);

  return (
    <div className="min-h-screen bg-background-light dark:bg-background-dark transition-colors">
      <Header
        schedulerRunning={schedulerRunning}
        schedulerPaused={schedulerPaused}
        menuOpen={menuOpen}
        menuId={MOBILE_MENU_ID}
        menuButtonRef={menuButtonRef}
        onMenuToggle={() => setOpenOn(menuOpen ? null : pathname)}
      />

      <div className="flex">
        <Sidebar />

        {menuOpen && (
          <>
            <div
              className="fixed inset-x-0 top-16 bottom-0 z-30 bg-black/40 md:hidden"
              aria-hidden="true"
              data-testid="menu-backdrop"
              onClick={closeMenu}
            />
            <Sidebar overlay id={MOBILE_MENU_ID} ref={menuRef} onNavigate={closeMenu} />
          </>
        )}

        {/* Main content area */}
        <main className="flex-1 min-w-0 p-4 md:p-6">
          {children}
        </main>
      </div>

      {/* Toast notifications */}
      <Notifications />
    </div>
  );
}
