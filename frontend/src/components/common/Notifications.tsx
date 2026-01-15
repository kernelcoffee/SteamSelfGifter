import { X, CheckCircle, XCircle, Info, AlertTriangle } from 'lucide-react';
import { clsx } from 'clsx';
import { useUIStore, type Notification } from '@/stores/uiStore';

const icons = {
  success: CheckCircle,
  error: XCircle,
  info: Info,
  warning: AlertTriangle,
};

const styles = {
  success: 'bg-green-50 dark:bg-green-900/20 border-green-200 dark:border-green-800 text-green-800 dark:text-green-200',
  error: 'bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800 text-red-800 dark:text-red-200',
  info: 'bg-blue-50 dark:bg-blue-900/20 border-blue-200 dark:border-blue-800 text-blue-800 dark:text-blue-200',
  warning: 'bg-yellow-50 dark:bg-yellow-900/20 border-yellow-200 dark:border-yellow-800 text-yellow-800 dark:text-yellow-200',
};

interface NotificationItemProps {
  notification: Notification;
  onDismiss: () => void;
}

function NotificationItem({ notification, onDismiss }: NotificationItemProps) {
  const Icon = icons[notification.type];

  return (
    <div
      className={clsx(
        'flex items-start gap-3 p-4 rounded-lg border shadow-lg',
        styles[notification.type]
      )}
      role="alert"
    >
      <Icon size={20} className="flex-shrink-0 mt-0.5" />
      <p className="flex-1 text-sm">{notification.message}</p>
      <button
        onClick={onDismiss}
        className="flex-shrink-0 p-1 hover:opacity-70 transition-opacity"
        aria-label="Dismiss notification"
      >
        <X size={16} />
      </button>
    </div>
  );
}

/**
 * Toast notifications container
 * Displays notifications in the bottom-right corner
 */
export function Notifications() {
  const { notifications, removeNotification } = useUIStore();

  if (notifications.length === 0) {
    return null;
  }

  return (
    <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 max-w-sm">
      {notifications.map((notification) => (
        <NotificationItem
          key={notification.id}
          notification={notification}
          onDismiss={() => removeNotification(notification.id)}
        />
      ))}
    </div>
  );
}
