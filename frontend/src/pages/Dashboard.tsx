import { useState, useEffect } from 'react';
import { Play, Pause, Square, RefreshCw, Zap, Gift, Clock, ExternalLink, X, Trophy, RotateCw, AlertTriangle, Settings, CheckCircle, Shield, ShieldAlert, ShieldQuestion } from 'lucide-react';
import { SiSteam } from 'react-icons/si';
import { Card, Button, Badge, Loading, CardSkeleton } from '@/components/common';
import { useDashboard, useSchedulerStatus, useSchedulerControl, useGiveaways, useRemoveEntry } from '@/hooks';
import { showSuccess, showError } from '@/stores/uiStore';
import type { Giveaway, SchedulerJob } from '@/types';

/**
 * Dashboard page
 * Shows scheduler controls, current points, and activity overview
 */
export function Dashboard() {
  const { data: dashboard, isLoading: dashboardLoading, error: dashboardError } = useDashboard();
  const { data: scheduler, isLoading: schedulerLoading } = useSchedulerStatus();
  const { start, stop, pause, resume, scan, process, runCycle } = useSchedulerControl();
  const { data: enteredData, isLoading: enteredLoading } = useGiveaways({ status: 'entered', limit: 10 });
  const removeEntry = useRemoveEntry();

  const handleRemoveEntry = async (giveaway: Giveaway) => {
    try {
      await removeEntry.mutateAsync(giveaway.code);
      showSuccess(`Entry removed for ${giveaway.game_name}`);
    } catch (err) {
      showError(err instanceof Error ? err.message : 'Failed to remove entry');
    }
  };

  const handleStart = async () => {
    try {
      await start.mutateAsync();
      showSuccess('Scheduler started');
    } catch (err) {
      showError(err instanceof Error ? err.message : 'Failed to start scheduler');
    }
  };

  const handleStop = async () => {
    try {
      await stop.mutateAsync();
      showSuccess('Scheduler stopped');
    } catch (err) {
      showError(err instanceof Error ? err.message : 'Failed to stop scheduler');
    }
  };

  const handlePause = async () => {
    try {
      await pause.mutateAsync();
      showSuccess('Scheduler paused');
    } catch (err) {
      showError(err instanceof Error ? err.message : 'Failed to pause scheduler');
    }
  };

  const handleResume = async () => {
    try {
      await resume.mutateAsync();
      showSuccess('Scheduler resumed');
    } catch (err) {
      showError(err instanceof Error ? err.message : 'Failed to resume scheduler');
    }
  };

  const handleScan = async () => {
    try {
      const result = await scan.mutateAsync();
      showSuccess(`Scan complete: ${result.new} new, ${result.updated} updated`);
    } catch (err) {
      showError(err instanceof Error ? err.message : 'Failed to run scan');
    }
  };

  const handleProcess = async () => {
    try {
      const result = await process.mutateAsync();
      showSuccess(`Processed: ${result.entered} entries, ${result.points_spent} points spent`);
    } catch (err) {
      showError(err instanceof Error ? err.message : 'Failed to process entries');
    }
  };

  const handleRunCycle = async () => {
    try {
      const result = await runCycle.mutateAsync();
      const summary = [
        `Scan: ${result.scan.new} new`,
        `Wishlist: ${result.wishlist.new} new`,
        `Wins: ${result.wins.new_wins} new`,
        `Entries: ${result.entries.entered} entered`,
      ].join(' | ');
      showSuccess(`Cycle complete: ${summary}`);
    } catch (err) {
      showError(err instanceof Error ? err.message : 'Failed to run automation cycle');
    }
  };

  if (dashboardError) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Dashboard</h1>
        <Card>
          <div className="text-center py-8">
            <p className="text-red-500 dark:text-red-400">
              Failed to load dashboard data. Is the backend running?
            </p>
            <p className="text-sm text-gray-500 mt-2">
              {dashboardError instanceof Error ? dashboardError.message : 'Unknown error'}
            </p>
          </div>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Dashboard</h1>

      {/* Session Status Banner */}
      {!dashboardLoading && dashboard?.session && (
        <SessionStatusBanner session={dashboard.session} />
      )}

      {/* Scheduler Control Card */}
      <Card title="Scheduler" actions={
        <Badge variant={scheduler?.running ? (scheduler?.paused ? 'warning' : 'success') : 'default'}>
          {scheduler?.running ? (scheduler?.paused ? 'Paused' : 'Running') : 'Stopped'}
        </Badge>
      }>
        {schedulerLoading ? (
          <Loading text="Loading scheduler status..." />
        ) : (
          <div className="space-y-4">
            <div className="flex flex-wrap gap-3">
              {!scheduler?.running ? (
                <Button
                  onClick={handleStart}
                  isLoading={start.isPending}
                  icon={Play}
                >
                  Start
                </Button>
              ) : (
                <>
                  {scheduler.paused ? (
                    <Button
                      onClick={handleResume}
                      isLoading={resume.isPending}
                      icon={Play}
                    >
                      Resume
                    </Button>
                  ) : (
                    <Button
                      onClick={handlePause}
                      isLoading={pause.isPending}
                      icon={Pause}
                      variant="secondary"
                    >
                      Pause
                    </Button>
                  )}
                  <Button
                    onClick={handleStop}
                    isLoading={stop.isPending}
                    icon={Square}
                    variant="danger"
                  >
                    Stop
                  </Button>
                </>
              )}

              <div className="border-l border-gray-200 dark:border-gray-700 mx-2" />

              <Button
                onClick={handleRunCycle}
                isLoading={runCycle.isPending}
                icon={RotateCw}
              >
                Run Full Cycle
              </Button>

              <div className="border-l border-gray-200 dark:border-gray-700 mx-2" />

              <Button
                onClick={handleScan}
                isLoading={scan.isPending}
                icon={RefreshCw}
                variant="secondary"
              >
                Scan Now
              </Button>
              <Button
                onClick={handleProcess}
                isLoading={process.isPending}
                icon={Zap}
                variant="secondary"
              >
                Process Entries
              </Button>
            </div>

            {scheduler?.running && scheduler?.jobs && scheduler.jobs.length > 0 && (
              <div className="flex flex-wrap gap-4 text-sm text-gray-500 dark:text-gray-400">
                {scheduler.jobs.map((job) => (
                  <JobCountdown key={job.id} job={job} />
                ))}
              </div>
            )}
          </div>
        )}
      </Card>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {dashboardLoading ? (
          <>
            <CardSkeleton />
            <CardSkeleton />
            <CardSkeleton />
            <CardSkeleton />
          </>
        ) : (
          <>
            <StatCard
              label="Current Points"
              value={dashboard?.points?.current ?? 0}
              color="blue"
            />
            <StatCard
              label="Active Giveaways"
              value={dashboard?.giveaways?.active ?? 0}
              color="green"
            />
            <StatCard
              label="Today's Entries"
              value={dashboard?.entries?.today ?? 0}
              color="purple"
            />
            <StatCard
              label="Win Rate (30d)"
              value={`${(dashboard?.entries?.win_rate ?? 0).toFixed(1)}%`}
              subLabel={`${dashboard?.entries?.wins_30d ?? 0}/${dashboard?.entries?.entered_30d ?? 0}`}
              color="orange"
            />
          </>
        )}
      </div>

      {/* Additional Stats Row */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        {dashboardLoading ? (
          <>
            <CardSkeleton />
            <CardSkeleton />
            <CardSkeleton />
            <CardSkeleton />
          </>
        ) : (
          <>
            <StatCard
              label="Total Entries"
              value={dashboard?.entries?.total ?? 0}
              color="gray"
            />
            <StatCard
              label="Entered Giveaways"
              value={dashboard?.giveaways?.entered ?? 0}
              color="teal"
            />
            <StatCard
              label="Total Wins"
              value={dashboard?.giveaways?.wins ?? 0}
              color="yellow"
              href="/wins"
              icon={<Trophy size={24} />}
            />
            <Card>
              <p className="text-sm text-gray-500 dark:text-gray-400">Last Scan</p>
              <p className="text-lg font-semibold text-gray-900 dark:text-white">
                {dashboard?.scheduler?.last_scan
                  ? new Date(dashboard.scheduler.last_scan).toLocaleString()
                  : 'Never'}
              </p>
            </Card>
          </>
        )}
      </div>

      {/* Safety Stats Row */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        {dashboardLoading ? (
          <>
            <CardSkeleton />
            <CardSkeleton />
            <CardSkeleton />
            <CardSkeleton />
          </>
        ) : (
          <>
            <StatCard
              label="Safe Giveaways"
              value={dashboard?.safety?.safe ?? 0}
              color="green"
              icon={<Shield size={24} />}
            />
            <StatCard
              label="Unsafe Giveaways"
              value={dashboard?.safety?.unsafe ?? 0}
              color="orange"
              icon={<ShieldAlert size={24} />}
            />
            <StatCard
              label="Safety Checked"
              value={dashboard?.safety?.checked ?? 0}
              color="teal"
            />
            <StatCard
              label="Unchecked"
              value={dashboard?.safety?.unchecked ?? 0}
              color="gray"
              icon={<ShieldQuestion size={24} />}
            />
          </>
        )}
      </div>

      {/* Entered Giveaways List */}
      <Card title="Entered Giveaways" actions={
        <Badge variant="default">{enteredData?.total ?? 0} total</Badge>
      }>
        {enteredLoading ? (
          <Loading text="Loading entered giveaways..." />
        ) : !enteredData?.items?.length ? (
          <p className="text-gray-500 dark:text-gray-400 text-center py-4">
            No giveaways entered yet
          </p>
        ) : (
          <div className="space-y-3">
            {enteredData.items.map((giveaway) => (
              <EnteredGiveawayRow
                key={giveaway.id}
                giveaway={giveaway}
                onRemoveEntry={() => handleRemoveEntry(giveaway)}
                isRemoving={removeEntry.isPending}
              />
            ))}
            {(enteredData.total ?? 0) > 10 && (
              <p className="text-sm text-gray-500 dark:text-gray-400 text-center pt-2">
                <a href="/giveaways?status=entered" className="text-primary-light hover:underline">
                  View all {enteredData.total} entered giveaways →
                </a>
              </p>
            )}
          </div>
        )}
      </Card>
    </div>
  );
}

interface StatCardProps {
  label: string;
  value: number | string;
  subLabel?: string;
  color?: 'blue' | 'green' | 'purple' | 'orange' | 'gray' | 'teal' | 'yellow';
  href?: string;
  icon?: React.ReactNode;
}

function StatCard({ label, value, subLabel, color = 'gray', href, icon }: StatCardProps) {
  const colorClasses = {
    blue: 'text-blue-600 dark:text-blue-400',
    green: 'text-green-600 dark:text-green-400',
    purple: 'text-purple-600 dark:text-purple-400',
    orange: 'text-orange-600 dark:text-orange-400',
    gray: 'text-gray-900 dark:text-white',
    teal: 'text-teal-600 dark:text-teal-400',
    yellow: 'text-yellow-600 dark:text-yellow-400',
  };

  const content = (
    <Card className={href ? 'hover:ring-2 hover:ring-primary-light/50 transition-all cursor-pointer' : ''}>
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm text-gray-500 dark:text-gray-400">{label}</p>
          <p className={`text-3xl font-bold ${colorClasses[color]}`}>{value}</p>
          {subLabel && (
            <p className="text-xs text-gray-400 dark:text-gray-500">{subLabel}</p>
          )}
        </div>
        {icon && <div className={colorClasses[color]}>{icon}</div>}
      </div>
    </Card>
  );

  if (href) {
    return <a href={href}>{content}</a>;
  }

  return content;
}

interface EnteredGiveawayRowProps {
  giveaway: Giveaway;
  onRemoveEntry: () => void;
  isRemoving: boolean;
}

function EnteredGiveawayRow({ giveaway, onRemoveEntry, isRemoving }: EnteredGiveawayRowProps) {
  // Determine if giveaway has ended:
  // - If end_time is set and in the past, it's expired
  // - If end_time is null but it's a won giveaway, treat as ended (historical)
  const isExpired = giveaway.end_time
    ? new Date(giveaway.end_time) < new Date()
    : giveaway.is_won; // No end_time + won = historical giveaway
  const timeLeft = giveaway.end_time ? formatTimeLeft(new Date(giveaway.end_time)) : null;

  return (
    <div className="flex items-center gap-3 p-3 bg-gray-50 dark:bg-gray-800/50 rounded-lg">
      {/* Thumbnail */}
      {giveaway.game_thumbnail && (
        <img
          src={giveaway.game_thumbnail}
          alt={giveaway.game_name}
          className="w-16 h-10 object-cover rounded"
          onError={(e) => {
            e.currentTarget.style.display = 'none';
          }}
        />
      )}

      {/* Info */}
      <div className="flex-1 min-w-0">
        <h4 className="font-medium text-gray-900 dark:text-white truncate">
          {giveaway.game_name}
        </h4>
        <div className="flex items-center gap-3 text-sm text-gray-500 dark:text-gray-400">
          <span className="flex items-center gap-1">
            <Gift size={12} />
            {giveaway.price}P
          </span>
          {timeLeft && (
            <span className="flex items-center gap-1">
              <Clock size={12} />
              {isExpired ? 'Ended' : timeLeft}
            </span>
          )}
          {giveaway.game_review_summary && (
            <Badge
              variant={
                giveaway.game_review_summary.includes('Positive') ? 'success' :
                giveaway.game_review_summary.includes('Mixed') ? 'warning' : 'error'
              }
              size="sm"
            >
              {giveaway.game_review_summary}
            </Badge>
          )}
        </div>
      </div>

      {/* Remove Entry Button */}
      {!isExpired && !giveaway.is_won && (
        <Button
          size="sm"
          variant="danger"
          onClick={onRemoveEntry}
          isLoading={isRemoving}
          title="Remove Entry"
        >
          <X size={14} />
        </Button>
      )}

      {/* Status */}
      {giveaway.is_won ? (
        <Badge variant="default" size="sm" className="bg-yellow-100 text-yellow-600 dark:bg-yellow-900/30 dark:text-yellow-400">
          <Trophy size={10} className="mr-1" />
          Won
        </Badge>
      ) : isExpired ? (
        <Badge variant="error" size="sm">Ended</Badge>
      ) : (
        <Badge variant="success" size="sm">Active</Badge>
      )}

      {/* External Links */}
      <div className="flex items-center gap-1">
        {giveaway.game_id && (
          <a
            href={`https://store.steampowered.com/app/${giveaway.game_id}`}
            target="_blank"
            rel="noopener noreferrer"
            title="View on Steam"
            className="p-1.5 text-gray-400 hover:text-gray-600 dark:hover:text-gray-200"
          >
            <SiSteam size={16} />
          </a>
        )}
        <a
          href={giveaway.url}
          target="_blank"
          rel="noopener noreferrer"
          title="View on SteamGifts"
          className="p-1.5 text-gray-400 hover:text-gray-600 dark:hover:text-gray-200"
        >
          <ExternalLink size={16} />
        </a>
      </div>
    </div>
  );
}

interface JobCountdownProps {
  job: SchedulerJob;
}

function JobCountdown({ job }: JobCountdownProps) {
  const [countdown, setCountdown] = useState<string>('');

  useEffect(() => {
    if (!job.next_run) {
      setCountdown('Not scheduled');
      return;
    }

    const updateCountdown = () => {
      const now = new Date();
      const nextRun = new Date(job.next_run!);
      const diff = nextRun.getTime() - now.getTime();

      if (diff <= 0) {
        setCountdown('Running now...');
        return;
      }

      const hours = Math.floor(diff / (1000 * 60 * 60));
      const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));
      const seconds = Math.floor((diff % (1000 * 60)) / 1000);

      if (hours > 0) {
        setCountdown(`${hours}h ${minutes}m ${seconds}s`);
      } else if (minutes > 0) {
        setCountdown(`${minutes}m ${seconds}s`);
      } else {
        setCountdown(`${seconds}s`);
      }
    };

    updateCountdown();
    const interval = setInterval(updateCountdown, 1000);

    return () => clearInterval(interval);
  }, [job.next_run]);

  const jobLabel = job.name === 'scan_giveaways' ? 'Next scan' :
                   job.name === 'process_giveaways' ? 'Next process' : job.name;

  return (
    <span className="flex items-center gap-1">
      <Clock size={14} />
      {jobLabel}: <span className="font-medium text-gray-700 dark:text-gray-200">{countdown}</span>
    </span>
  );
}

function formatTimeLeft(endTime: Date): string {
  const now = new Date();
  const diff = endTime.getTime() - now.getTime();

  if (diff <= 0) return 'Ended';

  const hours = Math.floor(diff / (1000 * 60 * 60));
  const days = Math.floor(hours / 24);

  if (days > 0) return `${days}d ${hours % 24}h`;
  if (hours > 0) return `${hours}h`;

  const minutes = Math.floor(diff / (1000 * 60));
  return `${minutes}m`;
}

interface SessionStatusBannerProps {
  session: {
    configured: boolean;
    valid: boolean;
    username: string | null;
    error: string | null;
  };
}

function SessionStatusBanner({ session }: SessionStatusBannerProps) {
  // Session not configured - show setup prompt
  if (!session.configured) {
    return (
      <div className="rounded-lg bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 p-4">
        <div className="flex items-start gap-3">
          <AlertTriangle className="text-amber-500 flex-shrink-0 mt-0.5" size={20} />
          <div className="flex-1">
            <h3 className="font-semibold text-amber-800 dark:text-amber-200">
              Session Not Configured
            </h3>
            <p className="text-sm text-amber-700 dark:text-amber-300 mt-1">
              To start using SteamSelfGifter, you need to configure your SteamGifts session.
              Go to Settings and enter your PHPSESSID cookie from SteamGifts.com.
            </p>
            <a
              href="/settings"
              className="inline-flex items-center gap-2 mt-3 px-4 py-2 bg-amber-600 hover:bg-amber-700 text-white rounded-lg text-sm font-medium transition-colors"
            >
              <Settings size={16} />
              Configure Session
            </a>
          </div>
        </div>
      </div>
    );
  }

  // Session configured but invalid/expired
  if (!session.valid) {
    return (
      <div className="rounded-lg bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 p-4">
        <div className="flex items-start gap-3">
          <AlertTriangle className="text-red-500 flex-shrink-0 mt-0.5" size={20} />
          <div className="flex-1">
            <h3 className="font-semibold text-red-800 dark:text-red-200">
              Session Invalid or Expired
            </h3>
            <p className="text-sm text-red-700 dark:text-red-300 mt-1">
              {session.error || 'Your SteamGifts session has expired or become invalid.'}
              {' '}Please update your PHPSESSID cookie in Settings.
            </p>
            <a
              href="/settings"
              className="inline-flex items-center gap-2 mt-3 px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-lg text-sm font-medium transition-colors"
            >
              <Settings size={16} />
              Update Session
            </a>
          </div>
        </div>
      </div>
    );
  }

  // Session valid - show connected status (compact)
  return (
    <div className="rounded-lg bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 p-3">
      <div className="flex items-center gap-2">
        <CheckCircle className="text-green-500 flex-shrink-0" size={18} />
        <span className="text-sm text-green-700 dark:text-green-300">
          Connected to SteamGifts
          {session.username && (
            <span className="font-medium"> as {session.username}</span>
          )}
        </span>
      </div>
    </div>
  );
}
