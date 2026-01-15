import { BrowserRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

// Create a fresh QueryClient for each test
function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: false, // Don't retry in tests
        gcTime: 0,    // Don't cache in tests
      },
    },
  });
}

interface TestProvidersProps {
  children: React.ReactNode;
}

export function TestProviders({ children }: TestProvidersProps) {
  const queryClient = createTestQueryClient();

  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        {children}
      </BrowserRouter>
    </QueryClientProvider>
  );
}