import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest';
import { useUIStore, showSuccess, showError, showInfo, showWarning } from './uiStore';

describe('uiStore', () => {
  beforeEach(() => {
    // Reset store state before each test
    useUIStore.setState({
      sidebarCollapsed: false,
      notifications: [],
    });
    // Use fake timers for auto-dismiss tests
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  describe('sidebar', () => {
    it('should start with sidebar expanded', () => {
      expect(useUIStore.getState().sidebarCollapsed).toBe(false);
    });

    it('should toggle sidebar', () => {
      useUIStore.getState().toggleSidebar();

      expect(useUIStore.getState().sidebarCollapsed).toBe(true);

      useUIStore.getState().toggleSidebar();

      expect(useUIStore.getState().sidebarCollapsed).toBe(false);
    });

    it('should set sidebar collapsed state directly', () => {
      useUIStore.getState().setSidebarCollapsed(true);

      expect(useUIStore.getState().sidebarCollapsed).toBe(true);

      useUIStore.getState().setSidebarCollapsed(false);

      expect(useUIStore.getState().sidebarCollapsed).toBe(false);
    });
  });

  describe('notifications', () => {
    it('should start with empty notifications', () => {
      expect(useUIStore.getState().notifications).toEqual([]);
    });

    it('should add a notification', () => {
      useUIStore.getState().addNotification({
        type: 'success',
        message: 'Test message',
      });

      const notifications = useUIStore.getState().notifications;
      expect(notifications).toHaveLength(1);
      expect(notifications[0].type).toBe('success');
      expect(notifications[0].message).toBe('Test message');
      expect(notifications[0].id).toBeDefined();
    });

    it('should add multiple notifications', () => {
      useUIStore.getState().addNotification({ type: 'success', message: 'First' });
      useUIStore.getState().addNotification({ type: 'error', message: 'Second' });
      useUIStore.getState().addNotification({ type: 'info', message: 'Third' });

      expect(useUIStore.getState().notifications).toHaveLength(3);
    });

    it('should remove a notification by id', () => {
      useUIStore.getState().addNotification({ type: 'success', message: 'Test' });

      const id = useUIStore.getState().notifications[0].id;
      useUIStore.getState().removeNotification(id);

      expect(useUIStore.getState().notifications).toHaveLength(0);
    });

    it('should clear all notifications', () => {
      useUIStore.getState().addNotification({ type: 'success', message: 'First' });
      useUIStore.getState().addNotification({ type: 'error', message: 'Second' });

      useUIStore.getState().clearNotifications();

      expect(useUIStore.getState().notifications).toHaveLength(0);
    });

    it('should auto-dismiss notification after default duration', () => {
      useUIStore.getState().addNotification({ type: 'success', message: 'Auto dismiss' });

      expect(useUIStore.getState().notifications).toHaveLength(1);

      // Fast-forward 5 seconds (default duration)
      vi.advanceTimersByTime(5000);

      expect(useUIStore.getState().notifications).toHaveLength(0);
    });

    it('should auto-dismiss notification after custom duration', () => {
      useUIStore.getState().addNotification({
        type: 'success',
        message: 'Custom duration',
        duration: 2000,
      });

      expect(useUIStore.getState().notifications).toHaveLength(1);

      vi.advanceTimersByTime(2000);

      expect(useUIStore.getState().notifications).toHaveLength(0);
    });

    it('should not auto-dismiss if duration is 0', () => {
      useUIStore.getState().addNotification({
        type: 'success',
        message: 'No auto dismiss',
        duration: 0,
      });

      vi.advanceTimersByTime(10000);

      expect(useUIStore.getState().notifications).toHaveLength(1);
    });
  });

  describe('helper functions', () => {
    it('showSuccess should add a success notification', () => {
      showSuccess('Success message');

      const notifications = useUIStore.getState().notifications;
      expect(notifications).toHaveLength(1);
      expect(notifications[0].type).toBe('success');
      expect(notifications[0].message).toBe('Success message');
    });

    it('showError should add an error notification', () => {
      showError('Error message');

      const notifications = useUIStore.getState().notifications;
      expect(notifications).toHaveLength(1);
      expect(notifications[0].type).toBe('error');
      expect(notifications[0].message).toBe('Error message');
    });

    it('showInfo should add an info notification', () => {
      showInfo('Info message');

      const notifications = useUIStore.getState().notifications;
      expect(notifications).toHaveLength(1);
      expect(notifications[0].type).toBe('info');
      expect(notifications[0].message).toBe('Info message');
    });

    it('showWarning should add a warning notification', () => {
      showWarning('Warning message');

      const notifications = useUIStore.getState().notifications;
      expect(notifications).toHaveLength(1);
      expect(notifications[0].type).toBe('warning');
      expect(notifications[0].message).toBe('Warning message');
    });
  });
});
