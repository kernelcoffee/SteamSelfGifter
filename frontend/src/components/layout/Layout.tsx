import { ReactNode } from 'react';
import { Header } from './Header';
import { Sidebar } from './Sidebar';
import { Notifications } from '@/components/common/Notifications';

interface LayoutProps {
  children: ReactNode;
  schedulerRunning?: boolean;
  schedulerPaused?: boolean;
}

/**
 * Main application layout with header, sidebar, and content area
 */
export function Layout({ children, schedulerRunning, schedulerPaused }: LayoutProps) {
  return (
    <div className="min-h-screen bg-background-light dark:bg-background-dark transition-colors">
      <Header
        schedulerRunning={schedulerRunning}
        schedulerPaused={schedulerPaused}
      />

      <div className="flex">
        <Sidebar />

        {/* Main content area */}
        <main className="flex-1 p-6">
          {children}
        </main>
      </div>

      {/* Toast notifications */}
      <Notifications />
    </div>
  );
}
