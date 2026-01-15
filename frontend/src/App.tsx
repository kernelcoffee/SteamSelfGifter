import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useEffect } from 'react';

import { Layout } from '@/components/layout/Layout';
import { WebSocketProvider } from '@/components/providers';
import { initializeTheme } from '@/stores/themeStore';
import { useSchedulerStatus } from '@/hooks';

// Pages
import { Dashboard } from '@/pages/Dashboard';
import { Giveaways } from '@/pages/Giveaways';
import { Wins } from '@/pages/Wins';
import { History } from '@/pages/History';
import { Analytics } from '@/pages/Analytics';
import { Settings } from '@/pages/Settings';
import { Logs } from '@/pages/Logs';

// Create React Query client
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000, // Data is fresh for 30 seconds
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
});

/**
 * Inner app component that has access to React Query context
 */
function AppContent() {
  const { data: scheduler } = useSchedulerStatus();

  return (
    <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <Layout
        schedulerRunning={scheduler?.running ?? false}
        schedulerPaused={scheduler?.paused ?? false}
      >
        <Routes>
          {/* Redirect root to dashboard */}
          <Route path="/" element={<Navigate to="/dashboard" replace />} />

          {/* Main pages */}
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/giveaways" element={<Giveaways />} />
          <Route path="/wins" element={<Wins />} />
          <Route path="/history" element={<History />} />
          <Route path="/analytics" element={<Analytics />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="/logs" element={<Logs />} />

          {/* 404 fallback */}
          <Route path="*" element={<Navigate to="/dashboard" replace />} />
        </Routes>
      </Layout>
    </BrowserRouter>
  );
}

/**
 * Main application component
 */
function App() {
  // Initialize theme on mount
  useEffect(() => {
    initializeTheme();
  }, []);

  return (
    <QueryClientProvider client={queryClient}>
      <WebSocketProvider>
        <AppContent />
      </WebSocketProvider>
    </QueryClientProvider>
  );
}

export default App;
