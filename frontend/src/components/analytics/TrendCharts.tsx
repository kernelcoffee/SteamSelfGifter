import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { Card, CardSkeleton } from '@/components/common';
import type { TrendDataPoint } from '@/hooks';

/**
 * Per-day trend charts for the Analytics page.
 *
 * Colors come from the validated chart palette in index.css. The entries
 * chart uses the "emphasis" form: successful entries carry the accent hue,
 * failed ones the de-emphasis gray, with a legend carrying identity.
 */

const formatDay = (iso: string) =>
  new Date(`${iso}T00:00:00`).toLocaleDateString(undefined, { month: 'short', day: 'numeric' });

// Tooltip labels arrive typed as ReactNode; only format the string case
const formatDayLabel = (label: React.ReactNode) =>
  typeof label === 'string' ? formatDay(label) : label;

const axisTick = { fill: 'var(--chart-ink-muted)', fontSize: 12 } as const;

const tooltipStyle = {
  backgroundColor: 'var(--chart-surface)',
  border: '1px solid var(--chart-grid)',
  borderRadius: '8px',
  fontSize: '12px',
} as const;

const tooltipLabelStyle = { color: 'var(--chart-ink-muted)' } as const;

function legendText(value: string) {
  return <span className="text-sm text-gray-600 dark:text-gray-300">{value}</span>;
}

interface ChartFrameProps {
  title: string;
  children: React.ReactElement;
}

function ChartFrame({ title, children }: ChartFrameProps) {
  return (
    <Card>
      <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">{title}</h3>
      <div className="h-56">
        <ResponsiveContainer width="100%" height="100%">
          {children}
        </ResponsiveContainer>
      </div>
    </Card>
  );
}

interface TrendChartsProps {
  trends: TrendDataPoint[] | undefined;
  isLoading: boolean;
}

export function TrendCharts({ trends, isLoading }: TrendChartsProps) {
  if (isLoading) {
    return (
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <CardSkeleton />
        <CardSkeleton />
      </div>
    );
  }

  if (!trends || trends.length === 0) {
    return null;
  }

  const hasWins = trends.some((t) => t.wins > 0);

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <ChartFrame title="Entries per day">
          <BarChart data={trends} margin={{ top: 4, right: 8, left: -16, bottom: 0 }}>
            <CartesianGrid vertical={false} stroke="var(--chart-grid)" />
            <XAxis
              dataKey="date"
              tickFormatter={formatDay}
              tick={axisTick}
              tickLine={false}
              axisLine={{ stroke: 'var(--chart-grid)' }}
              minTickGap={24}
            />
            <YAxis tick={axisTick} tickLine={false} axisLine={false} allowDecimals={false} />
            <Tooltip
              labelFormatter={formatDayLabel}
              contentStyle={tooltipStyle}
              labelStyle={tooltipLabelStyle}
              cursor={{ fill: 'var(--chart-grid)', fillOpacity: 0.35 }}
            />
            <Legend formatter={legendText} iconSize={10} />
            <Bar
              dataKey="successful"
              name="Successful"
              stackId="entries"
              fill="var(--chart-series-1)"
              stroke="var(--chart-surface)"
              strokeWidth={1}
            />
            <Bar
              dataKey="failed"
              name="Failed / skipped"
              stackId="entries"
              fill="var(--chart-emphasis)"
              stroke="var(--chart-surface)"
              strokeWidth={1}
              radius={[4, 4, 0, 0]}
            />
          </BarChart>
        </ChartFrame>

        <ChartFrame title="Points spent per day">
          <AreaChart data={trends} margin={{ top: 4, right: 8, left: -16, bottom: 0 }}>
            <CartesianGrid vertical={false} stroke="var(--chart-grid)" />
            <XAxis
              dataKey="date"
              tickFormatter={formatDay}
              tick={axisTick}
              tickLine={false}
              axisLine={{ stroke: 'var(--chart-grid)' }}
              minTickGap={24}
            />
            <YAxis tick={axisTick} tickLine={false} axisLine={false} allowDecimals={false} />
            <Tooltip
              labelFormatter={formatDayLabel}
              formatter={(value) => [`${value}P`, 'Points spent']}
              contentStyle={tooltipStyle}
              labelStyle={tooltipLabelStyle}
            />
            <Area
              type="monotone"
              dataKey="points_spent"
              stroke="var(--chart-series-1)"
              strokeWidth={2}
              fill="var(--chart-series-1)"
              fillOpacity={0.15}
            />
          </AreaChart>
        </ChartFrame>
      </div>

      {hasWins && (
        <ChartFrame title="Wins per day">
          <BarChart data={trends} margin={{ top: 4, right: 8, left: -16, bottom: 0 }}>
            <CartesianGrid vertical={false} stroke="var(--chart-grid)" />
            <XAxis
              dataKey="date"
              tickFormatter={formatDay}
              tick={axisTick}
              tickLine={false}
              axisLine={{ stroke: 'var(--chart-grid)' }}
              minTickGap={24}
            />
            <YAxis tick={axisTick} tickLine={false} axisLine={false} allowDecimals={false} />
            <Tooltip
              labelFormatter={formatDayLabel}
              formatter={(value) => [value, 'Wins']}
              contentStyle={tooltipStyle}
              labelStyle={tooltipLabelStyle}
              cursor={{ fill: 'var(--chart-grid)', fillOpacity: 0.35 }}
            />
            <Bar dataKey="wins" name="Wins" fill="var(--chart-series-2)" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ChartFrame>
      )}

      {/* Accessible alternative: the same data as a table */}
      <details className="text-sm">
        <summary className="cursor-pointer text-gray-500 dark:text-gray-400 select-none">
          View trend data as table
        </summary>
        <div className="mt-2 overflow-x-auto">
          <table className="min-w-full text-left text-gray-700 dark:text-gray-300">
            <thead>
              <tr className="border-b border-gray-200 dark:border-gray-700 text-xs uppercase text-gray-500">
                <th className="py-1 pr-4">Date</th>
                <th className="py-1 pr-4">Entries</th>
                <th className="py-1 pr-4">Successful</th>
                <th className="py-1 pr-4">Failed</th>
                <th className="py-1 pr-4">Points</th>
                <th className="py-1">Wins</th>
              </tr>
            </thead>
            <tbody className="tabular-nums">
              {trends.map((t) => (
                <tr key={t.date} className="border-b border-gray-100 dark:border-gray-800">
                  <td className="py-1 pr-4">{t.date}</td>
                  <td className="py-1 pr-4">{t.entries}</td>
                  <td className="py-1 pr-4">{t.successful}</td>
                  <td className="py-1 pr-4">{t.failed}</td>
                  <td className="py-1 pr-4">{t.points_spent}</td>
                  <td className="py-1">{t.wins}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </div>
  );
}
