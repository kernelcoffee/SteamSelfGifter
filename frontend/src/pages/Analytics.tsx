import { useState } from 'react';
import { TrendingUp, Target, Gift, Gamepad2, AlertCircle, CheckCircle, XCircle, Zap, type LucideIcon } from 'lucide-react';
import { Card, Badge, CardSkeleton } from '@/components/common';
import { useEntryStats, useGiveawayStats, useGameStats, type TimeRangeFilter } from '@/hooks';

/**
 * Analytics page
 * Shows entry statistics, success rates, and points tracking
 */
export function Analytics() {
  const [timeRange, setTimeRange] = useState<TimeRangeFilter>({ period: 'month' });

  const { data: entryStats, isLoading: entriesLoading, error: entriesError } = useEntryStats(timeRange);
  const { data: giveawayStats, isLoading: giveawaysLoading, error: giveawaysError } = useGiveawayStats(timeRange);
  const { data: gameStats, isLoading: gamesLoading, error: gamesError } = useGameStats();

  const isLoading = entriesLoading || giveawaysLoading || gamesLoading;
  const hasError = entriesError || giveawaysError || gamesError;

  const handlePeriodChange = (period: TimeRangeFilter['period']) => {
    setTimeRange({ period });
  };

  if (hasError) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Analytics</h1>
        <Card>
          <div className="flex items-center gap-3 text-red-500">
            <AlertCircle size={24} />
            <span>Failed to load analytics data. Is the backend running?</span>
          </div>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Analytics</h1>

        {/* Time Period Filter */}
        <div className="flex gap-2">
          <PeriodButton
            active={timeRange.period === 'day'}
            onClick={() => handlePeriodChange('day')}
          >
            Today
          </PeriodButton>
          <PeriodButton
            active={timeRange.period === 'week'}
            onClick={() => handlePeriodChange('week')}
          >
            Week
          </PeriodButton>
          <PeriodButton
            active={timeRange.period === 'month'}
            onClick={() => handlePeriodChange('month')}
          >
            Month
          </PeriodButton>
          <PeriodButton
            active={timeRange.period === 'year'}
            onClick={() => handlePeriodChange('year')}
          >
            Year
          </PeriodButton>
          <PeriodButton
            active={timeRange.period === 'all'}
            onClick={() => handlePeriodChange('all')}
          >
            All Time
          </PeriodButton>
        </div>
      </div>

      {/* Entry Statistics */}
      <section>
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
          <Target size={20} />
          Entry Statistics
        </h2>
        {isLoading ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            <CardSkeleton />
            <CardSkeleton />
            <CardSkeleton />
            <CardSkeleton />
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            <StatCard
              icon={Target}
              label="Total Entries"
              value={entryStats?.total ?? 0}
              color="blue"
            />
            <StatCard
              icon={CheckCircle}
              label="Submitted"
              value={entryStats?.successful ?? 0}
              subValue={`${(entryStats?.success_rate ?? 0).toFixed(1)}% submit rate`}
              color="green"
            />
            <StatCard
              icon={XCircle}
              label="Failed to Submit"
              value={entryStats?.failed ?? 0}
              color="red"
            />
            <StatCard
              icon={Zap}
              label="Points Spent"
              value={`${entryStats?.total_points_spent ?? 0}P`}
              color="purple"
            />
          </div>
        )}
      </section>

      {/* Entry Breakdown by Type */}
      {entryStats && (
        <section>
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
            <TrendingUp size={20} />
            Entries by Type
          </h2>
          <Card>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              <TypeBreakdownItem
                label="Automatic"
                value={entryStats.by_type.auto}
                total={entryStats.total}
                color="blue"
              />
              <TypeBreakdownItem
                label="Manual"
                value={entryStats.by_type.manual}
                total={entryStats.total}
                color="green"
              />
              <TypeBreakdownItem
                label="Wishlist"
                value={entryStats.by_type.wishlist}
                total={entryStats.total}
                color="purple"
              />
            </div>
          </Card>
        </section>
      )}

      {/* Giveaway Statistics */}
      <section>
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
          <Gift size={20} />
          Giveaway Statistics
        </h2>
        {isLoading ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            <CardSkeleton />
            <CardSkeleton />
            <CardSkeleton />
            <CardSkeleton />
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            <StatCard
              icon={Gift}
              label="Total Discovered"
              value={giveawayStats?.total ?? 0}
              color="blue"
            />
            <StatCard
              icon={TrendingUp}
              label="Active"
              value={giveawayStats?.active ?? 0}
              color="green"
            />
            <StatCard
              icon={CheckCircle}
              label="Entered"
              value={giveawayStats?.entered ?? 0}
              color="purple"
            />
            <StatCard
              icon={AlertCircle}
              label="Hidden"
              value={giveawayStats?.hidden ?? 0}
              color="gray"
            />
          </div>
        )}
      </section>

      {/* Game Statistics */}
      <section>
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
          <Gamepad2 size={20} />
          Game Database
        </h2>
        {isLoading ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            <CardSkeleton />
            <CardSkeleton />
            <CardSkeleton />
            <CardSkeleton />
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            <StatCard
              icon={Gamepad2}
              label="Total Items"
              value={gameStats?.total_games ?? 0}
              color="blue"
            />
            <StatCard
              icon={Gamepad2}
              label="Games"
              value={gameStats?.games ?? 0}
              color="green"
            />
            <StatCard
              icon={Gift}
              label="DLC"
              value={gameStats?.dlc ?? 0}
              color="purple"
            />
            <StatCard
              icon={AlertCircle}
              label="Stale Data"
              value={gameStats?.stale_games ?? 0}
              subValue="Need refresh"
              color="orange"
            />
          </div>
        )}
      </section>

      {/* Win Rate Overview */}
      {giveawayStats && giveawayStats.entered > 0 && (
        <section>
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
            Win Rate
          </h2>
          <Card>
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <span className="text-gray-600 dark:text-gray-400">Giveaway Win Rate</span>
                <Badge
                  variant={giveawayStats.win_rate >= 1 ? 'success' : giveawayStats.win_rate >= 0.5 ? 'warning' : 'default'}
                  size="md"
                >
                  {giveawayStats.win_rate.toFixed(2)}%
                </Badge>
              </div>
              <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-4 overflow-hidden">
                <div
                  className="h-full rounded-full transition-all duration-500 bg-green-500"
                  style={{ width: `${Math.min(giveawayStats.win_rate * 10, 100)}%` }}
                />
              </div>
              <div className="flex justify-between text-sm text-gray-500 dark:text-gray-400">
                <span>{giveawayStats.wins} wins</span>
                <span>{giveawayStats.entered} entered</span>
              </div>
            </div>
          </Card>
        </section>
      )}
    </div>
  );
}

interface PeriodButtonProps {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}

function PeriodButton({ active, onClick, children }: PeriodButtonProps) {
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

interface StatCardProps {
  icon: LucideIcon;
  label: string;
  value: number | string;
  subValue?: string;
  color?: 'blue' | 'green' | 'red' | 'purple' | 'orange' | 'gray';
}

function StatCard({ icon: Icon, label, value, subValue, color = 'gray' }: StatCardProps) {
  const colorClasses = {
    blue: 'text-blue-600 dark:text-blue-400',
    green: 'text-green-600 dark:text-green-400',
    red: 'text-red-600 dark:text-red-400',
    purple: 'text-purple-600 dark:text-purple-400',
    orange: 'text-orange-600 dark:text-orange-400',
    gray: 'text-gray-600 dark:text-gray-400',
  };

  const iconBgClasses = {
    blue: 'bg-blue-100 dark:bg-blue-900/30',
    green: 'bg-green-100 dark:bg-green-900/30',
    red: 'bg-red-100 dark:bg-red-900/30',
    purple: 'bg-purple-100 dark:bg-purple-900/30',
    orange: 'bg-orange-100 dark:bg-orange-900/30',
    gray: 'bg-gray-100 dark:bg-gray-800',
  };

  return (
    <Card>
      <div className="flex items-start gap-4">
        <div className={`p-3 rounded-lg ${iconBgClasses[color]}`}>
          <Icon size={24} />
        </div>
        <div>
          <p className="text-sm text-gray-500 dark:text-gray-400">{label}</p>
          <p className={`text-2xl font-bold ${colorClasses[color]}`}>{value}</p>
          {subValue && (
            <p className="text-xs text-gray-500 dark:text-gray-400">{subValue}</p>
          )}
        </div>
      </div>
    </Card>
  );
}

interface TypeBreakdownItemProps {
  label: string;
  value: number;
  total: number;
  color: 'blue' | 'green' | 'purple';
}

function TypeBreakdownItem({ label, value, total, color }: TypeBreakdownItemProps) {
  const percentage = total > 0 ? (value / total) * 100 : 0;

  const colorClasses = {
    blue: 'bg-blue-500',
    green: 'bg-green-500',
    purple: 'bg-purple-500',
  };

  return (
    <div className="space-y-2">
      <div className="flex justify-between items-center">
        <span className="text-gray-600 dark:text-gray-400">{label}</span>
        <span className="font-semibold text-gray-900 dark:text-white">{value}</span>
      </div>
      <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2 overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-500 ${colorClasses[color]}`}
          style={{ width: `${percentage}%` }}
        />
      </div>
      <p className="text-xs text-gray-500 dark:text-gray-400">
        {percentage.toFixed(1)}% of total
      </p>
    </div>
  );
}
