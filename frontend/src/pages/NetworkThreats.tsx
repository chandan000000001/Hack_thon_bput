import { useMemo, useState } from 'react';
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { Network } from 'lucide-react';
import * as api from '../services/api';
import type { ApiLogEntry, NetworkFlow } from '../types';
import { useApi } from '../hooks/useApi';
import PageHeader from '../components/common/PageHeader';
import DataTable, { type Column } from '../components/common/DataTable';
import ChartCard from '../components/common/ChartCard';
import SeverityBadge from '../components/common/SeverityBadge';
import { PanelSkeleton } from '../components/common/LoadingSkeleton';
import { formatBytes, formatTime } from '../constants';

const tooltipStyle = {
  backgroundColor: '#0f172a',
  border: '1px solid #334155',
  borderRadius: '8px',
  fontSize: '12px',
  color: '#e2e8f0',
};

function scoreColor(score: number): string {
  if (score >= 0.8) return 'text-red-500';
  if (score >= 0.6) return 'text-orange-500';
  if (score >= 0.4) return 'text-amber-500';
  return 'text-emerald-400';
}

function flagSeverity(flags: string[]): 'critical' | 'high' | 'medium' | 'low' | 'safe' {
  if (flags.length === 0) return 'safe';
  if (flags.length >= 3) return 'critical';
  if (flags.length === 2) return 'high';
  return 'medium';
}

export default function NetworkThreats() {
  const [tab, setTab] = useState<'flows' | 'api'>('flows');
  const [flowSearch, setFlowSearch] = useState('');
  const [apiSearch, setApiSearch] = useState('');
  const [expandedFlow, setExpandedFlow] = useState<NetworkFlow | null>(null);
  const [expandedApi, setExpandedApi] = useState<ApiLogEntry | null>(null);

  const { data: flows, loading: flowsLoading } = useApi(() => api.listNetworkFlows(), []);
  const { data: apiLogs, loading: apiLoading } = useApi(() => api.listApiLogs(), []);

  const outboundChart = useMemo(() => {
    return (flows ?? [])
      .slice(0, 14)
      .map((f) => ({
        time: formatTime(f.timestamp),
        mbOut: Number((f.bytesOut / 1024 / 1024).toFixed(2)),
      }));
  }, [flows]);

  const filteredFlows = useMemo(() => {
    const q = flowSearch.toLowerCase();
    if (!q) return flows ?? [];
    return (flows ?? []).filter(
      (f) =>
        f.sourceIp.includes(q) ||
        f.destIp.includes(q) ||
        f.destDomain.toLowerCase().includes(q) ||
        f.flags.some((fl) => fl.toLowerCase().includes(q))
    );
  }, [flows, flowSearch]);

  const filteredApi = useMemo(() => {
    const q = apiSearch.toLowerCase();
    if (!q) return apiLogs ?? [];
    return (apiLogs ?? []).filter(
      (l) =>
        l.endpoint.toLowerCase().includes(q) ||
        l.sourceIp.includes(q) ||
        l.userAgent.toLowerCase().includes(q) ||
        l.flags.some((fl) => fl.toLowerCase().includes(q))
    );
  }, [apiLogs, apiSearch]);

  const flowColumns: Column<NetworkFlow>[] = [
    { key: 'src', header: 'Source IP', render: (f) => <span className="font-mono text-xs text-slate-300">{f.sourceIp}</span>, sortValue: (f) => f.sourceIp },
    { key: 'dst', header: 'Dest IP', render: (f) => <span className="font-mono text-xs text-slate-300">{f.destIp}</span>, sortValue: (f) => f.destIp },
    { key: 'dom', header: 'Domain', render: (f) => <span className="font-mono text-xs text-cyan-400">{f.destDomain}</span>, sortValue: (f) => f.destDomain },
    { key: 'port', header: 'Port', render: (f) => <span className={`font-mono text-xs ${[4444, 8888, 1337, 31337, 6667, 9001].includes(f.port) ? 'font-bold text-red-400' : 'text-slate-400'}`}>{f.port}</span>, sortValue: (f) => f.port },
    { key: 'proto', header: 'Proto', render: (f) => <span className="text-xs text-slate-400">{f.protocol}</span>, sortValue: (f) => f.protocol },
    { key: 'out', header: 'Bytes Out', render: (f) => <span className={`font-mono text-xs ${f.bytesOut > 1024 ** 3 ? 'font-bold text-red-400' : 'text-slate-300'}`}>{formatBytes(f.bytesOut)}</span>, sortValue: (f) => f.bytesOut },
    { key: 'anom', header: 'Anomaly', render: (f) => <span className={`font-mono text-xs font-bold ${scoreColor(f.anomalyScore)}`}>{f.anomalyScore.toFixed(2)}</span>, sortValue: (f) => f.anomalyScore },
    {
      key: 'flags',
      header: 'Flags',
      render: (f) =>
        f.flags.length === 0 ? (
          <span className="text-xs text-slate-600">—</span>
        ) : (
          <div className="flex max-w-56 flex-wrap gap-1">
            {f.flags.map((fl) => (
              <span key={fl} className="rounded bg-amber-500/10 px-1.5 py-0.5 text-[10px] text-amber-500 ring-1 ring-amber-500/30">
                {fl}
              </span>
            ))}
          </div>
        ),
    },
    { key: 'time', header: 'Time', render: (f) => <span className="font-mono text-xs text-slate-500">{formatTime(f.timestamp)}</span>, sortValue: (f) => f.timestamp },
  ];

  const apiColumns: Column<ApiLogEntry>[] = [
    { key: 'ep', header: 'Endpoint', render: (l) => <span className="font-mono text-xs text-cyan-400">{l.endpoint}</span>, sortValue: (l) => l.endpoint },
    { key: 'm', header: 'Method', render: (l) => <span className="rounded bg-slate-700/60 px-1.5 py-0.5 font-mono text-[10px] font-bold text-slate-300">{l.method}</span>, sortValue: (l) => l.method },
    { key: 'ip', header: 'Source IP', render: (l) => <span className="font-mono text-xs text-slate-300">{l.sourceIp}</span>, sortValue: (l) => l.sourceIp },
    {
      key: 'code',
      header: 'Status',
      render: (l) => (
        <span className={`font-mono text-xs font-bold ${l.statusCode >= 500 ? 'text-red-400' : l.statusCode >= 400 ? 'text-orange-400' : 'text-emerald-400'}`}>
          {l.statusCode}
        </span>
      ),
      sortValue: (l) => l.statusCode,
    },
    { key: 'rt', header: 'Response', render: (l) => <span className="font-mono text-xs text-slate-400">{l.responseTime}ms</span>, sortValue: (l) => l.responseTime },
    { key: 'anom', header: 'Anomaly', render: (l) => <span className={`font-mono text-xs font-bold ${scoreColor(l.anomalyScore)}`}>{l.anomalyScore.toFixed(2)}</span>, sortValue: (l) => l.anomalyScore },
    {
      key: 'flags',
      header: 'Flags',
      render: (l) =>
        l.flags.length === 0 ? (
          <span className="text-xs text-slate-600">—</span>
        ) : (
          <div className="flex max-w-56 flex-wrap gap-1">
            {l.flags.map((fl) => (
              <span key={fl} className="rounded bg-amber-500/10 px-1.5 py-0.5 text-[10px] text-amber-500 ring-1 ring-amber-500/30">
                {fl}
              </span>
            ))}
          </div>
        ),
    },
    { key: 'ua', header: 'User Agent', render: (l) => <span className="block max-w-40 truncate font-mono text-[11px] text-slate-500">{l.userAgent}</span> },
    { key: 'time', header: 'Time', render: (l) => <span className="font-mono text-xs text-slate-500">{formatTime(l.timestamp)}</span>, sortValue: (l) => l.timestamp },
  ];

  return (
    <div className="space-y-5">
      <PageHeader
        title="Network & API Threat Detection"
        description="Traffic anomalies, C2 beaconing, exfiltration, API rate abuse and credential stuffing."
      />

      {/* Tabs */}
      <div className="flex gap-1 rounded-xl border border-slate-700/50 bg-slate-800/60 p-1 backdrop-blur">
        {(
          [
            ['flows', `Network Flows (${flows?.length ?? 0})`],
            ['api', `API Logs (${apiLogs?.length ?? 0})`],
          ] as const
        ).map(([key, label]) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={`flex-1 rounded-lg px-4 py-2 text-sm font-medium ${
              tab === key ? 'bg-cyan-500/15 text-cyan-300 ring-1 ring-cyan-500/40' : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === 'flows' && (
        <div className="space-y-4">
          <ChartCard title="Outbound Traffic Volume" subtitle="Most recent flows (MB)">
            <ResponsiveContainer width="100%" height={180}>
              <AreaChart data={outboundChart} margin={{ top: 4, right: 8, left: -18, bottom: 0 }}>
                <defs>
                  <linearGradient id="gOut" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#06b6d4" stopOpacity={0.4} />
                    <stop offset="100%" stopColor="#06b6d4" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke="#1e293b" strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="time" tick={{ fill: '#94a3b8', fontSize: 9 }} interval={2} />
                <YAxis tick={{ fill: '#94a3b8', fontSize: 10 }} />
                <Tooltip contentStyle={tooltipStyle} />
                <Area type="monotone" dataKey="mbOut" stroke="#06b6d4" fill="url(#gOut)" strokeWidth={2} name="MB out" />
              </AreaChart>
            </ResponsiveContainer>
          </ChartCard>

          <input
            value={flowSearch}
            onChange={(e) => setFlowSearch(e.target.value)}
            placeholder="Filter by IP, domain or flag..."
            className="w-full rounded-lg border border-slate-700/60 bg-slate-800/60 px-3.5 py-2 text-sm text-slate-100 placeholder-slate-600 outline-none focus:border-cyan-500/60"
          />

          {flowsLoading ? (
            <PanelSkeleton height="h-64" />
          ) : (
            <DataTable
              columns={flowColumns}
              data={filteredFlows}
              rowKey={(f) => f.id}
              emptyMessage="No network flows match the filter"
              onRowClick={(f) => setExpandedFlow(expandedFlow?.id === f.id ? null : f)}
            />
          )}

          {expandedFlow && (
            <div className="rounded-xl border border-cyan-500/30 bg-slate-800/60 p-4 backdrop-blur">
              <div className="mb-3 flex items-center justify-between">
                <h3 className="flex items-center gap-2 text-sm font-semibold text-slate-100">
                  <Network className="h-4 w-4 text-cyan-400" />
                  Flow Detail — {expandedFlow.id}
                </h3>
                <SeverityBadge severity={flagSeverity(expandedFlow.flags)} />
              </div>
              <div className="grid gap-2 text-xs sm:grid-cols-2 lg:grid-cols-4">
                {(
                  [
                    ['Source', expandedFlow.sourceIp],
                    ['Destination', `${expandedFlow.destIp} (${expandedFlow.destDomain})`],
                    ['Port / Protocol', `${expandedFlow.port} / ${expandedFlow.protocol}`],
                    ['Volume', `${formatBytes(expandedFlow.bytesOut)} out / ${formatBytes(expandedFlow.bytesIn)} in`],
                  ] as const
                ).map(([label, value]) => (
                  <div key={label} className="rounded-lg bg-slate-900/60 p-2.5">
                    <div className="text-[10px] uppercase tracking-wider text-slate-500">{label}</div>
                    <div className="mt-0.5 break-all font-mono text-slate-200">{value}</div>
                  </div>
                ))}
              </div>
              <p className="mt-3 text-xs leading-relaxed text-slate-400">
                {expandedFlow.flags.length > 0
                  ? `This flow was flagged: ${expandedFlow.flags.join('; ')}. Anomaly score ${expandedFlow.anomalyScore.toFixed(2)} indicates ${
                      expandedFlow.anomalyScore >= 0.8
                        ? 'high-confidence malicious traffic warranting isolation and C2 blocking.'
                        : 'suspicious activity recommended for monitoring and correlation with other events.'
                    }`
                  : 'No anomaly flags on this flow. Traffic pattern matches expected behavior for this service profile.'}
              </p>
            </div>
          )}
        </div>
      )}

      {tab === 'api' && (
        <div className="space-y-4">
          <input
            value={apiSearch}
            onChange={(e) => setApiSearch(e.target.value)}
            placeholder="Filter by endpoint, IP, user agent or flag..."
            className="w-full rounded-lg border border-slate-700/60 bg-slate-800/60 px-3.5 py-2 text-sm text-slate-100 placeholder-slate-600 outline-none focus:border-cyan-500/60"
          />

          {apiLoading ? (
            <PanelSkeleton height="h-64" />
          ) : (
            <DataTable
              columns={apiColumns}
              data={filteredApi}
              rowKey={(l) => l.id}
              emptyMessage="No API logs match the filter"
              onRowClick={(l) => setExpandedApi(expandedApi?.id === l.id ? null : l)}
            />
          )}

          {expandedApi && (
            <div className="rounded-xl border border-cyan-500/30 bg-slate-800/60 p-4 backdrop-blur">
              <div className="mb-3 flex items-center justify-between">
                <h3 className="flex items-center gap-2 text-sm font-semibold text-slate-100">
                  <Network className="h-4 w-4 text-cyan-400" />
                  API Log Detail — {expandedApi.id}
                </h3>
                <SeverityBadge severity={flagSeverity(expandedApi.flags)} />
              </div>
              <div className="grid gap-2 text-xs sm:grid-cols-2 lg:grid-cols-4">
                {(
                  [
                    ['Endpoint', `${expandedApi.method} ${expandedApi.endpoint}`],
                    ['Source', `${expandedApi.sourceIp}`],
                    ['User Agent', expandedApi.userAgent],
                    ['Result', `${expandedApi.statusCode} in ${expandedApi.responseTime}ms`],
                  ] as const
                ).map(([label, value]) => (
                  <div key={label} className="rounded-lg bg-slate-900/60 p-2.5">
                    <div className="text-[10px] uppercase tracking-wider text-slate-500">{label}</div>
                    <div className="mt-0.5 break-all font-mono text-slate-200">{value}</div>
                  </div>
                ))}
              </div>
              <p className="mt-3 text-xs leading-relaxed text-slate-400">
                {expandedApi.flags.length > 0
                  ? `Flagged for: ${expandedApi.flags.join('; ')}. Anomaly score ${expandedApi.anomalyScore.toFixed(2)} — ${
                      expandedApi.anomalyScore >= 0.8
                        ? 'consistent with automated abuse tooling; rate limiting and token revocation recommended.'
                        : 'borderline activity; correlate with other logs from this source before acting.'
                    }`
                  : 'No flags. Request pattern matches legitimate application traffic.'}
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
