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

// Navigation items configuration
const navItems: NavItem[] = [
  { path: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { path: '/giveaways', label: 'Giveaways', icon: Gift, end: true },
  { path: '/giveaways/wishlist', label: 'Wishlist', icon: Heart },
  { path: '/giveaways/dlc', label: 'DLC', icon: Package },
  { path: '/giveaways/entered', label: 'Entered', icon: Ticket },
  { path: '/wins', label: 'Wins', icon: Trophy },
  { path: '/history', label: 'History', icon: History },
  { path: '/analytics', label: 'Analytics', icon: BarChart3 },
  { path: '/settings', label: 'Settings', icon: Settings },
  { path: '/logs', label: 'Logs', icon: FileText },
];

/**
 * Sidebar navigation component
 */
export function Sidebar() {
  return (
    <aside className="w-64 border-r border-gray-200 dark:border-gray-700 bg-surface-light dark:bg-surface-dark min-h-[calc(100vh-4rem)]">
      <nav className="p-4">
        <ul className="space-y-2">
          {navItems.map(({ path, label, icon: Icon, end }) => (
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
      </nav>
    </aside>
  );
}
