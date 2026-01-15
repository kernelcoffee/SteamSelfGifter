import { create } from 'zustand';

export interface Notification {
  id: string;
  type: 'success' | 'error' | 'info' | 'warning';
  message: string;
  duration?: number; // Auto-dismiss after ms (default: 5000)
}

interface UIState {
  // Sidebar state
  sidebarCollapsed: boolean;

  // Notifications
  notifications: Notification[];

  // Actions
  toggleSidebar: () => void;
  setSidebarCollapsed: (collapsed: boolean) => void;
  addNotification: (notification: Omit<Notification, 'id'>) => void;
  removeNotification: (id: string) => void;
  clearNotifications: () => void;
}

/**
 * UI state store
 *
 * Manages transient UI state:
 * - Sidebar collapsed/expanded
 * - Toast notifications
 */
export const useUIStore = create<UIState>((set, get) => ({
  // Initial state
  sidebarCollapsed: false,
  notifications: [],

  // Sidebar actions
  toggleSidebar: () => set((state) => ({
    sidebarCollapsed: !state.sidebarCollapsed,
  })),

  setSidebarCollapsed: (collapsed) => set({
    sidebarCollapsed: collapsed,
  }),

  // Notification actions
  addNotification: (notification) => {
    const id = crypto.randomUUID();
    const duration = notification.duration ?? 5000;

    set((state) => ({
      notifications: [...state.notifications, { ...notification, id }],
    }));

    // Auto-dismiss after duration
    if (duration > 0) {
      setTimeout(() => {
        get().removeNotification(id);
      }, duration);
    }
  },

  removeNotification: (id) => set((state) => ({
    notifications: state.notifications.filter((n) => n.id !== id),
  })),

  clearNotifications: () => set({
    notifications: [],
  }),
}));

/**
 * Helper to show a success notification
 */
export function showSuccess(message: string): void {
  useUIStore.getState().addNotification({ type: 'success', message });
}

/**
 * Helper to show an error notification
 */
export function showError(message: string): void {
  useUIStore.getState().addNotification({ type: 'error', message });
}

/**
 * Helper to show an info notification
 */
export function showInfo(message: string): void {
  useUIStore.getState().addNotification({ type: 'info', message });
}

/**
 * Helper to show a warning notification
 */
export function showWarning(message: string): void {
  useUIStore.getState().addNotification({ type: 'warning', message });
}
