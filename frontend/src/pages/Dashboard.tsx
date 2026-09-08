import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Area,
  AreaChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { KeyRound, LayoutDashboard, Mail, ShieldAlert, UserX, Video } from 'lucide-react';
import * as api from '../services/api';
import { useApi } from '../hooks/useApi';
import { useRealtimeAlerts } from '../hooks/useRealtimeAlerts';
import { useUiStore } from '../store/uiStore';
import type { Alert } from '../types';
import PageHeader from '../components/common/PageHeader';
import StatCard from '../components/common/StatCard';
import ChartCard from '../components/common/ChartCard';
import SeverityBadge from '../components/common/SeverityBadge';
import StatusPill from '../components/common/StatusPill';
import DataTable, { type Column } from '../components/common/DataTable';
import { PanelSkeleton } from '../components/common/LoadingSkeleton';
import { MODULE_LABELS } from '../constants';

const tooltipStyle = {
  backgroundColor: '#101010',
  border: '1px solid #262626',
  borderRadius: '8px',
  fontSize: '12px',
  color: '#fafafa',
};

export default function Dashboard() {
  const navigate = useNavigate();
  const addToast = useUiStore((s) => s.addToast);
  const { data, loading, error, refetch } = useApi(() => api.getDashboardSummary(), []);
  const liveAlerts = useUiStore((s) => s.liveSimulation);
  useRealtimeAlerts(liveAlerts, refetch);

  // Auto-refresh every 30 seconds
  useEffect(() => {
    const interval = setInterval(refetch, 30000);
    return () => clearInterval(interval);
  }, [refetch]);

  useEffect(() => {
    if (error) addToast(`Failed to load dashboard: ${error}`, 'high');
  }, [error, addToast]);

  const recentColumns: Column<Alert>[] = [
    { key: 'id', header: 'ID', render: (a) => <span className="font-mono text-xs text-red-400">{a.id}</span>, sortValue: (a) => a.id },
    { key: 'title', header: 'Title', render: (a) => <span className="line-clamp-1 max-w-xs text-zinc-200">{a.title}</span>, sortValue: (a) => a.title },
    { key: 'module', header: 'Module', render: (a) => <span className="text-xs text-zinc-400">{MODULE_LABELS[a.module]}</span>, sortValue: (a) => a.module },
    { key: 'severity', header: 'Severity', render: (a) => <SeverityBadge severity={a.severity} />, sortValue: (a) => a.severity },
    { key: 'risk', header: 'Risk', render: (a) => <span className="font-mono font-semibold text-zinc-100">{a.riskScore}</span>, sortValue: (a) => a.riskScore },
    { key: 'status', header: 'Status', render: (a) => <StatusPill status={a.status} />, sortValue: (a) => a.status },
  ];

  return (
    <div className="space-y-5">
      <PageHeader
        title="Security Operations Center"
        description="Real-time threat monitoring, detection and response overview. Auto-refreshes every 30 seconds."
      />

      {loading || !data ? (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-4 xl:grid-cols-6">
            {Array.from({ length: 6 }).map((_, i) => (
              <PanelSkeleton key={i} height="h-28" />
            ))}
          </div>
          <div className="grid gap-4 lg:grid-cols-3">
            <PanelSkeleton className="lg:col-span-2" height="h-80" />
            <PanelSkeleton height="h-80" />
          </div>
        </div>
      ) : (
        <>
          {/* Stat cards */}
          <div className="grid grid-cols-2 gap-4 xl:grid-cols-6">
            <StatCard title="Events Analyzed" value={data.totalEventsAnalyzed} icon={LayoutDashboard} trend="up" trendValue="+12%" color="#dc2626" />
            <StatCard title="Threats Detected" value={data.threatsDetected} icon={ShieldAlert} trend="up" trendValue="+8%" color="#ef4444" />
            <StatCard title="Phishing Attempts" value={data.phishingAttempts} icon={Mail} trend="up" trendValue="+15%" color="#ef4444" />
            <StatCard title="Impersonation Attempts" value={data.impersonationAttempts} icon={UserX} trend="neutral" trendValue="stable" color="#a3a3a3" />
            <StatCard title="Suspected Deepfakes" value={data.suspectedDeepfakes} icon={Video} trend="up" trendValue="+5%" color="#fafafa" />
            <StatCard title="Account Takeover Attempts" value={data.accountTakeoverAttempts} icon={KeyRound} trend="down" trendValue="-3%" color="#7f1d1d" />
          </div>

          {/* Charts + right column */}
          <div className="grid gap-4 lg:grid-cols-3">
            <div className="space-y-4 lg:col-span-2">
              <ChartCard title="Risk Distribution" subtitle="Alerts by severity band">
                <ResponsiveContainer width="100%" height={220}>
                  <PieChart>
                    <Pie data={data.riskDistribution} dataKey="value" nameKey="name" innerRadius={60} outerRadius={85} paddingAngle={3} stroke="#101010">
                      {data.riskDistribution.map((entry) => (
                        <Cell key={entry.name} fill={entry.color} />
                      ))}
                    </Pie>
                    <Tooltip contentStyle={tooltipStyle} />
                  </PieChart>
                </ResponsiveContainer>
                <div className="mt-1 flex flex-wrap justify-center gap-3">
                  {data.riskDistribution.map((entry) => (
                    <div key={entry.name} className="flex items-center gap-1.5 text-xs text-zinc-400">
                      <span className="h-2 w-2 rounded-full" style={{ backgroundColor: entry.color }} />
                      {entry.name} ({entry.value})
                    </div>
                  ))}
                </div>
              </ChartCard>

              <ChartCard title="Threat Categories" subtitle="Alert count per module">
                <ResponsiveContainer width="100%" height={220}>
                  <BarChart data={data.threatCategories} margin={{ top: 4, right: 8, left: -18, bottom: 0 }}>
                    <CartesianGrid stroke="#262626" strokeDasharray="3 3" vertical={false} />
                    <XAxis dataKey="name" tick={{ fill: '#a3a3a3', fontSize: 10 }} interval={0} angle={-18} textAnchor="end" height={50} />
                    <YAxis tick={{ fill: '#a3a3a3', fontSize: 10 }} allowDecimals={false} />
                    <Tooltip contentStyle={tooltipStyle} cursor={{ fill: '#26262655' }} />
                    <Bar dataKey="count" fill="#dc2626" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </ChartCard>

              <ChartCard title="Attack Timeline — Last 24 Hours" subtitle="Events analyzed vs threats detected">
                <ResponsiveContainer width="100%" height={220}>
                  <AreaChart data={data.attackTimeline} margin={{ top: 4, right: 8, left: -18, bottom: 0 }}>
                    <defs>
                      <linearGradient id="gEvents" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="#dc2626" stopOpacity={0.35} />
                        <stop offset="100%" stopColor="#dc2626" stopOpacity={0} />
                      </linearGradient>
                      <linearGradient id="gThreats" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="#ef4444" stopOpacity={0.35} />
                        <stop offset="100%" stopColor="#ef4444" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid stroke="#262626" strokeDasharray="3 3" vertical={false} />
                    <XAxis dataKey="hour" tick={{ fill: '#a3a3a3', fontSize: 10 }} interval={3} />
                    <YAxis tick={{ fill: '#a3a3a3', fontSize: 10 }} />
                    <Tooltip contentStyle={tooltipStyle} />
                    <Area type="monotone" dataKey="events" stroke="#dc2626" fill="url(#gEvents)" strokeWidth={2} name="Events" />
                    <Area type="monotone" dataKey="threats" stroke="#ef4444" fill="url(#gThreats)" strokeWidth={2} name="Threats" />
                  </AreaChart>
                </ResponsiveContainer>
              </ChartCard>
            </div>

            {/* Right column */}
            <div className="space-y-4">
              <div className="rounded-xl border border-zinc-700/50 bg-zinc-800/60 p-4 backdrop-blur">
                <h3 className="mb-3 text-sm font-semibold text-zinc-100">Incident Summary</h3>
                <div className="space-y-2.5">
                  {(
                    [
                      ['open', data.incidentSummary.open],
                      ['investigating', data.incidentSummary.investigating],
                      ['contained', data.incidentSummary.contained],
                      ['closed', data.incidentSummary.closed],
                    ] as const
                  ).map(([status, count]) => (
                    <div key={status} className="flex items-center justify-between">
                      <StatusPill status={status} />
                      <span className="font-mono text-lg font-bold text-zinc-100">{count}</span>
                    </div>
                  ))}
                </div>
              </div>

              <div className="rounded-xl border border-zinc-700/50 bg-zinc-800/60 p-4 backdrop-blur">
                <h3 className="mb-3 text-sm font-semibold text-zinc-100">Top Targeted Users</h3>
                <div className="space-y-2">
                  {data.topTargetedUsers.map((u) => (
                    <div key={u.user} className="flex items-center justify-between gap-2">
                      <span className="truncate font-mono text-xs text-zinc-300">{u.user}</span>
                      <span className="shrink-0 rounded bg-red-500/15 px-1.5 py-0.5 font-mono text-[11px] font-bold text-red-400">{u.attacks}</span>
                    </div>
                  ))}
                  {data.topTargetedUsers.length === 0 && <p className="text-xs text-zinc-500">No targeted users recorded</p>}
                </div>
              </div>

              <div className="rounded-xl border border-zinc-700/50 bg-zinc-800/60 p-4 backdrop-blur">
                <h3 className="mb-3 text-sm font-semibold text-zinc-100">Top Targeted Services</h3>
                <div className="space-y-2.5">
                  {data.topTargetedServices.map((s) => (
                    <div key={s.service} className="flex items-center justify-between gap-2">
                      <span className="truncate text-xs text-zinc-300">{s.service}</span>
                      <div className="flex shrink-0 items-center gap-1.5">
                        <span className="font-mono text-[11px] text-zinc-500">{s.attacks}x</span>
                        <SeverityBadge severity={s.riskLevel} />
                      </div>
                    </div>
                  ))}
                  {data.topTargetedServices.length === 0 && <p className="text-xs text-zinc-500">No targeted services recorded</p>}
                </div>
              </div>
            </div>
          </div>

          {/* Recent alerts */}
          <div>
            <h3 className="mb-2 text-sm font-semibold text-zinc-200">Recent Alerts</h3>
            <DataTable
              columns={recentColumns}
              data={data.recentAlerts}
              rowKey={(a) => a.id}
              onRowClick={(a) => navigate(`/alerts/${a.id}`)}
              emptyMessage="No recent alerts"
            />
          </div>
        </>
      )}
    </div>
  );
}
