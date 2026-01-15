import { useState } from 'react';
import { ExternalLink, CheckCircle, XCircle, Clock, AlertCircle, Gift } from 'lucide-react';
import { Card, Button, Badge, Input, CardSkeleton } from '@/components/common';
import { useEntries, type EntryFilters } from '@/hooks';
import type { EntryWithGiveaway } from '@/types';

/**
 * History page
 * Shows entry history with success/failure status
 */
export function History() {
  const [filters, setFilters] = useState<EntryFilters>({
    status: 'all',
    type: 'all',
    page: 1,
    limit: 20,
  });
  const [dateRange, setDateRange] = useState({ from: '', to: '' });

  const { data, isLoading, error } = useEntries(filters);

  const handleStatusFilter = (status: EntryFilters['status']) => {
    setFilters(prev => ({ ...prev, status, page: 1 }));
  };

  const handleTypeFilter = (type: EntryFilters['type']) => {
    setFilters(prev => ({ ...prev, type, page: 1 }));
  };

  const handleDateFilter = () => {
    setFilters(prev => ({
      ...prev,
      from_date: dateRange.from || undefined,
      to_date: dateRange.to || undefined,
      page: 1,
    }));
  };

  const handleClearDates = () => {
    setDateRange({ from: '', to: '' });
    setFilters(prev => ({
      ...prev,
      from_date: undefined,
      to_date: undefined,
      page: 1,
    }));
  };

  const handlePageChange = (page: number) => {
    setFilters(prev => ({ ...prev, page }));
  };

  if (error) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Entry History</h1>
        <Card>
          <div className="flex items-center gap-3 text-red-500">
            <AlertCircle size={24} />
            <span>Failed to load entry history. Is the backend running?</span>
          </div>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Entry History</h1>

      {/* Filters */}
      <Card>
        <div className="space-y-4">
          {/* Status Filter */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              Status
            </label>
            <div className="flex flex-wrap gap-2">
              <FilterButton
                active={filters.status === 'all'}
                onClick={() => handleStatusFilter('all')}
              >
                All
              </FilterButton>
              <FilterButton
                active={filters.status === 'success'}
                onClick={() => handleStatusFilter('success')}
              >
                Success
              </FilterButton>
              <FilterButton
                active={filters.status === 'failed'}
                onClick={() => handleStatusFilter('failed')}
              >
                Failed
              </FilterButton>
              <FilterButton
                active={filters.status === 'pending'}
                onClick={() => handleStatusFilter('pending')}
              >
                Pending
              </FilterButton>
            </div>
          </div>

          {/* Type Filter */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              Entry Type
            </label>
            <div className="flex flex-wrap gap-2">
              <FilterButton
                active={filters.type === 'all'}
                onClick={() => handleTypeFilter('all')}
              >
                All
              </FilterButton>
              <FilterButton
                active={filters.type === 'auto'}
                onClick={() => handleTypeFilter('auto')}
              >
                Automatic
              </FilterButton>
              <FilterButton
                active={filters.type === 'manual'}
                onClick={() => handleTypeFilter('manual')}
              >
                Manual
              </FilterButton>
              <FilterButton
                active={filters.type === 'wishlist'}
                onClick={() => handleTypeFilter('wishlist')}
              >
                Wishlist
              </FilterButton>
            </div>
          </div>

          {/* Date Range */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              Date Range
            </label>
            <div className="flex flex-wrap gap-2 items-center">
              <Input
                type="date"
                value={dateRange.from}
                onChange={(e) => setDateRange(prev => ({ ...prev, from: e.target.value }))}
                className="w-40"
              />
              <span className="text-gray-500">to</span>
              <Input
                type="date"
                value={dateRange.to}
                onChange={(e) => setDateRange(prev => ({ ...prev, to: e.target.value }))}
                className="w-40"
              />
              <Button variant="secondary" size="sm" onClick={handleDateFilter}>
                Apply
              </Button>
              {(filters.from_date || filters.to_date) && (
                <Button variant="ghost" size="sm" onClick={handleClearDates}>
                  Clear
                </Button>
              )}
            </div>
          </div>
        </div>
      </Card>

      {/* Results count */}
      {data && (
        <p className="text-sm text-gray-500 dark:text-gray-400">
          Showing {data.items.length} of {data.total} entries
        </p>
      )}

      {/* Entries List */}
      {isLoading ? (
        <div className="space-y-4">
          {[...Array(5)].map((_, i) => (
            <CardSkeleton key={i} />
          ))}
        </div>
      ) : data?.items.length === 0 ? (
        <Card>
          <div className="text-center py-8 text-gray-500 dark:text-gray-400">
            No entries found matching your criteria.
          </div>
        </Card>
      ) : (
        <div className="space-y-4">
          {data?.items.map((entry) => (
            <EntryCard key={entry.id} entry={entry} />
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

interface EntryCardProps {
  entry: EntryWithGiveaway;
}

function EntryCard({ entry }: EntryCardProps) {
  const statusConfig = {
    success: {
      icon: CheckCircle,
      color: 'text-green-500',
      badge: 'success' as const,
      label: 'Success',
    },
    failed: {
      icon: XCircle,
      color: 'text-red-500',
      badge: 'error' as const,
      label: 'Failed',
    },
    pending: {
      icon: Clock,
      color: 'text-yellow-500',
      badge: 'warning' as const,
      label: 'Pending',
    },
  };

  const typeLabels = {
    auto: 'Automatic',
    manual: 'Manual',
    wishlist: 'Wishlist',
  };

  const config = statusConfig[entry.status];
  const StatusIcon = config.icon;

  return (
    <Card>
      <div className="flex items-start gap-4">
        {/* Status Icon */}
        <div className={`mt-1 ${config.color}`}>
          <StatusIcon size={24} />
        </div>

        {/* Main Content */}
        <div className="flex-1 min-w-0">
          <div className="flex items-start justify-between gap-4">
            <div>
              <h3 className="font-semibold text-gray-900 dark:text-white truncate">
                {entry.giveaway.game_name}
              </h3>
              <p className="text-sm text-gray-500 dark:text-gray-400">
                {new Date(entry.entered_at).toLocaleString()}
              </p>
            </div>
            <div className="flex gap-2 shrink-0">
              <Badge variant={config.badge} size="sm">{config.label}</Badge>
              <Badge variant="default" size="sm">{typeLabels[entry.entry_type]}</Badge>
            </div>
          </div>

          {/* Details */}
          <div className="mt-2 flex flex-wrap gap-4 text-sm text-gray-500 dark:text-gray-400">
            <span className="flex items-center gap-1">
              <Gift size={14} />
              {entry.points_spent}P spent
            </span>
            {entry.giveaway.copies > 1 && (
              <span>{entry.giveaway.copies} copies</span>
            )}
          </div>

          {/* Error message if failed */}
          {entry.status === 'failed' && entry.error_message && (
            <div className="mt-2 p-2 bg-red-50 dark:bg-red-900/20 rounded text-sm text-red-600 dark:text-red-400">
              {entry.error_message}
            </div>
          )}

          {/* Actions */}
          <div className="mt-3 pt-3 border-t border-gray-100 dark:border-gray-800">
            <a
              href={entry.giveaway.url}
              target="_blank"
              rel="noopener noreferrer"
            >
              <Button size="sm" variant="ghost" icon={ExternalLink}>
                View Giveaway
              </Button>
            </a>
          </div>
        </div>
      </div>
    </Card>
  );
}
