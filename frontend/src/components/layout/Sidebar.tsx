import type { Ref } from 'react';
import { NavLink } from 'react-router';
import {
  LayoutDashboard,
  Gift,
  Heart,
  Package,
  Ticket,
  Trophy,
  History,
  BarChart3,
  Settings,
  FileText,
  LucideIcon,
} from 'lucide-react';
import { clsx } from 'clsx';

interface NavItem {
  path: string;
  label: string;
  icon: LucideIcon;
  // Match the path exactly instead of as a prefix (needed for parent
  // routes like /giveaways that have sibling sub-pages).
  end?: boolean;
}

// Navigation items configuration. Settings goes last: pinning it to the
// column bottom scrolled it off-screen on pages taller than the viewport.
const navItems: NavItem[] = [
  { path: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { path: '/giveaways', label: 'Giveaways', icon: Gift, end: true },
  { path: '/giveaways/wishlist', label: 'Wishlist', icon: Heart },
  { path: '/giveaways/dlc', label: 'DLC', icon: Package },
  { path: '/giveaways/entered', label: 'Entered', icon: Ticket },
  { path: '/wins', label: 'Wins', icon: Trophy },
  { path: '/history', label: 'History', icon: History },
  { path: '/analytics', label: 'Analytics', icon: BarChart3 },
  { path: '/logs', label: 'Logs', icon: FileText },
  { path: '/settings', label: 'Settings', icon: Settings },
];

function NavList({ items }: { items: NavItem[] }) {
  return (
    <ul className="space-y-2">
      {items.map(({ path, label, icon: Icon, end }) => (
        <li key={path}>
          <NavLink
            to={path}
            end={end}
            className={({ isActive }) =>
              clsx(
                'flex items-center gap-3 px-4 py-2 rounded-lg transition-colors',
                isActive
                  ? 'bg-primary-light dark:bg-primary-dark text-white'
                  : 'text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700'
              )
            }
          >
            <Icon size={20} />
            <span>{label}</span>
          </NavLink>
        </li>
      ))}
    </ul>
  );
}

interface SidebarProps {
  /** Phone-width overlay variant, opened from the Header's menu button. */
  overlay?: boolean;
  id?: string;
  ref?: Ref<HTMLElement>;
  /** Called when a link is followed (closes the overlay). */
  onNavigate?: () => void;
}

/**
 * Sidebar navigation component. The column is shown from the md breakpoint
 * up; below it the same navigation opens as an overlay that starts under the
 * sticky h-16 header, so the header's menu toggle stays reachable.
 */
export function Sidebar({ overlay = false, id, ref, onNavigate }: SidebarProps = {}) {
  return (
    <aside
      ref={ref}
      id={id}
      aria-label={overlay ? 'Main menu' : undefined}
      className={clsx(
        'w-64 border-r border-gray-200 dark:border-gray-700 bg-surface-light dark:bg-surface-dark',
        overlay
          ? 'fixed top-16 bottom-0 left-0 z-40 overflow-y-auto shadow-xl md:hidden'
          : 'hidden md:block shrink-0 min-h-[calc(100vh-4rem)]'
      )}
    >
      <nav className="p-4" onClick={onNavigate}>
        <NavList items={navItems} />
      </nav>
    </aside>
  );
}
