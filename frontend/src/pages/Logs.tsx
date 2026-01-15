import { useState } from 'react';
import { AlertCircle, Info, AlertTriangle, Download, Trash2, RefreshCw } from 'lucide-react';
import { Card, Button, Badge, Input, CardSkeleton } from '@/components/common';
import { useLogs, useClearLogs, useExportLogs, type LogFilters } from '@/hooks';
import { showSuccess, showError } from '@/stores/uiStore';
import type { ActivityLog } from '@/types';

/**
 * Logs page
 * Shows activity logs with level filtering
 */
export function Logs() {
  const [filters, setFilters] = useState<LogFilters>({
    level: 'all',
    event_type: 'all',
    page: 1,
    limit: 50,
  });
  const [searchInput, setSearchInput] = useState('');

  const { data, isLoading, error, refetch, isFetching } = useLogs(filters);
  const clearLogs = useClearLogs();
  const exportLogs = useExportLogs();

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    setFilters(prev => ({ ...prev, search: searchInput || undefined, page: 1 }));
  };

  const handleLevelFilter = (level: LogFilters['level']) => {
    setFilters(prev => ({ ...prev, level, page: 1 }));
  };

  const handleEventTypeFilter = (event_type: LogFilters['event_type']) => {
    setFilters(prev => ({ ...prev, event_type, page: 1 }));
  };

  const handlePageChange = (page: number) => {
    setFilters(prev => ({ ...prev, page }));
  };

  const handleClearLogs = async () => {
    if (!confirm('Are you sure you want to clear all logs? This action cannot be undone.')) {
      return;
    }

    try {
      const result = await clearLogs.mutateAsync();
      showSuccess(`Cleared ${result?.deleted ?? 0} logs`);
    } catch (err) {
      showError(err instanceof Error ? err.message : 'Failed to clear logs');
    }
  };

  const handleExport = async (format: 'csv' | 'json') => {
    try {
      await exportLogs.mutateAsync(format);
      showSuccess(`Logs exported as ${format.toUpperCase()}`);
    } catch (err) {
      showError(err instanceof Error ? err.message : 'Failed to export logs');
    }
  };

  if (error) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Activity Logs</h1>
        <Card>
          <div className="flex items-center gap-3 text-red-500">
            <AlertCircle size={24} />
            <span>Failed to load activity logs. Is the backend running?</span>
          </div>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Activity Logs</h1>

        {/* Actions */}
        <div className="flex flex-wrap gap-2">
          <Button
            variant="secondary"
            size="sm"
            icon={RefreshCw}
            onClick={() => refetch()}
            isLoading={isFetching}
          >
            Refresh
          </Button>
          <Button
            variant="secondary"
            size="sm"
            icon={Download}
            onClick={() => handleExport('csv')}
            isLoading={exportLogs.isPending}
          >
            Export CSV
          </Button>
          <Button
            variant="secondary"
            size="sm"
            icon={Download}
            onClick={() => handleExport('json')}
            isLoading={exportLogs.isPending}
          >
            Export JSON
          </Button>
          <Button
            variant="danger"
            size="sm"
            icon={Trash2}
            onClick={handleClearLogs}
            isLoading={clearLogs.isPending}
          >
            Clear All
          </Button>
        </div>
      </div>

      {/* Filters */}
      <Card>
        <div className="space-y-4">
          {/* Search */}
          <form onSubmit={handleSearch} className="flex gap-2">
            <Input
              placeholder="Search logs..."
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              className="flex-1"
            />
            <Button type="submit" variant="secondary">Search</Button>
          </form>

          {/* Level Filter */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              Log Level
            </label>
            <div className="flex flex-wrap gap-2">
              <FilterButton
                active={filters.level === 'all'}
                onClick={() => handleLevelFilter('all')}
              >
                All
              </FilterButton>
              <FilterButton
                active={filters.level === 'info'}
                onClick={() => handleLevelFilter('info')}
              >
                Info
              </FilterButton>
              <FilterButton
                active={filters.level === 'warning'}
                onClick={() => handleLevelFilter('warning')}
              >
                Warning
              </FilterButton>
              <FilterButton
                active={filters.level === 'error'}
                onClick={() => handleLevelFilter('error')}
              >
                Error
              </FilterButton>
            </div>
          </div>

          {/* Event Type Filter */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              Event Type
            </label>
            <div className="flex flex-wrap gap-2">
              <FilterButton
                active={filters.event_type === 'all'}
                onClick={() => handleEventTypeFilter('all')}
              >
                All
              </FilterButton>
              <FilterButton
                active={filters.event_type === 'scan'}
                onClick={() => handleEventTypeFilter('scan')}
              >
                Scan
              </FilterButton>
              <FilterButton
                active={filters.event_type === 'entry'}
                onClick={() => handleEventTypeFilter('entry')}
              >
                Entry
              </FilterButton>
              <FilterButton
                active={filters.event_type === 'scheduler'}
                onClick={() => handleEventTypeFilter('scheduler')}
              >
                Scheduler
              </FilterButton>
              <FilterButton
                active={filters.event_type === 'config'}
                onClick={() => handleEventTypeFilter('config')}
              >
                Config
              </FilterButton>
              <FilterButton
                active={filters.event_type === 'error'}
                onClick={() => handleEventTypeFilter('error')}
              >
                Error
              </FilterButton>
            </div>
          </div>
        </div>
      </Card>

      {/* Results count */}
      {data && (
        <p className="text-sm text-gray-500 dark:text-gray-400">
          Showing {data.items.length} of {data.total} logs
        </p>
      )}

      {/* Logs List */}
      {isLoading ? (
        <div className="space-y-2">
          {[...Array(10)].map((_, i) => (
            <CardSkeleton key={i} />
          ))}
        </div>
      ) : data?.items.length === 0 ? (
        <Card>
          <div className="text-center py-8 text-gray-500 dark:text-gray-400">
            No logs found matching your criteria.
          </div>
        </Card>
      ) : (
        <div className="space-y-2">
          {data?.items.map((log) => (
            <LogEntry key={log.id} log={log} />
          ))}
        </div>
      )}

      {/* Pagination */}
      {data && data.pages > 1 && (
        <div className="flex justify-center gap-2">
          <Button
            variant="secondary"
            disabled={data.page <= 1}
            onClick={() => handlePageChange(data.page - 1)}
          >
            Previous
          </Button>
          <span className="flex items-center px-4 text-gray-600 dark:text-gray-300">
            Page {data.page} of {data.pages}
          </span>
          <Button
            variant="secondary"
            disabled={data.page >= data.pages}
            onClick={() => handlePageChange(data.page + 1)}
          >
            Next
          </Button>
        </div>
      )}
    </div>
  );
}

interface FilterButtonProps {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}

function FilterButton({ active, onClick, children }: FilterButtonProps) {
  return (
    <button
      onClick={onClick}
      className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
        active
          ? 'bg-primary-light text-white'
          : 'bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700'
      }`}
    >
      {children}
    </button>
  );
}

interface LogEntryProps {
  log: ActivityLog;
}

function LogEntry({ log }: LogEntryProps) {
  const levelConfig = {
    info: {
      icon: Info,
      color: 'text-blue-500',
      bgColor: 'bg-blue-50 dark:bg-blue-900/20',
      badge: 'default' as const,
    },
    warning: {
      icon: AlertTriangle,
      color: 'text-yellow-500',
      bgColor: 'bg-yellow-50 dark:bg-yellow-900/20',
      badge: 'warning' as const,
    },
    error: {
      icon: AlertCircle,
      color: 'text-red-500',
      bgColor: 'bg-red-50 dark:bg-red-900/20',
      badge: 'error' as const,
    },
  };

  const eventTypeLabels = {
    scan: 'Scan',
    entry: 'Entry',
    error: 'Error',
    config: 'Config',
    scheduler: 'Scheduler',
  };

  const config = levelConfig[log.level];
  const LevelIcon = config.icon;

  return (
    <div className={`rounded-lg p-4 ${config.bgColor}`}>
      <div className="flex items-start gap-3">
        {/* Level Icon */}
        <div className={`mt-0.5 ${config.color}`}>
          <LevelIcon size={18} />
        </div>

        {/* Content */}
        <div className="flex-1 min-w-0">
          <div className="flex items-start justify-between gap-4">
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-gray-900 dark:text-white">
                {log.message}
              </p>
              {log.details && (
                <p className="mt-1 text-xs text-gray-600 dark:text-gray-400 font-mono break-all">
                  {log.details}
                </p>
              )}
            </div>
            <div className="flex gap-2 shrink-0">
              <Badge variant={config.badge} size="sm">
                {log.level.toUpperCase()}
              </Badge>
              <Badge variant="default" size="sm">
                {eventTypeLabels[log.event_type]}
              </Badge>
            </div>
          </div>
          <p className="mt-2 text-xs text-gray-500 dark:text-gray-400">
            {new Date(log.created_at).toLocaleString()}
          </p>
        </div>
      </div>
    </div>
  );
}
