import { useMemo, useState } from 'react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { KeyRound, Loader2, PlayCircle } from 'lucide-react';
import * as api from '../services/api';
import type { AnalysisResult, LoginEvent } from '../types';
import { useApi } from '../hooks/useApi';
import PageHeader from '../components/common/PageHeader';
import DataTable, { type Column } from '../components/common/DataTable';
import SeverityBadge from '../components/common/SeverityBadge';
import IndicatorList from '../components/common/IndicatorList';
import ExplanationPanel from '../components/common/ExplanationPanel';
import RecommendedActionsPanel from '../components/common/RecommendedActionsPanel';
import ChartCard from '../components/common/ChartCard';
import { PanelSkeleton } from '../components/common/LoadingSkeleton';
import { useUiStore } from '../store/uiStore';
import { formatTime } from '../constants';

const SAMPLE_AUTH_LOG = JSON.stringify(
  [
    { user: 'john.doe', ip: '10.0.1.45', location: 'New York, US', device: 'Windows-Chrome', status: 'success', timestamp: '2024-01-15T09:30:00Z' },
    { user: 'john.doe', ip: '185.220.101.7', location: 'Moscow, RU', device: 'Linux-Firefox', status: 'failed', timestamp: '2024-01-15T09:35:00Z' },
    { user: 'john.doe', ip: '185.220.101.7', location: 'Moscow, RU', device: 'Linux-Firefox', status: 'failed', timestamp: '2024-01-15T09:35:30Z' },
    { user: 'john.doe', ip: '185.220.101.7', location: 'Moscow, RU', device: 'Linux-Firefox', status: 'success', timestamp: '2024-01-15T09:36:00Z' },
    { user: 'jane.smith', ip: '10.0.1.50', location: 'New York, US', device: 'MacOS-Safari', status: 'success', timestamp: '2024-01-15T10:00:00Z' },
  ],
  null,
  2
);

const tooltipStyle = {
  backgroundColor: '#0f172a',
  border: '1px solid #334155',
  borderRadius: '8px',
  fontSize: '12px',
  color: '#e2e8f0',
};

export default function AccountTakeover() {
  const addToast = useUiStore((s) => s.addToast);
  const { data: events, loading, refetch } = useApi(() => api.listLoginEvents(), []);
  const [jsonInput, setJsonInput] = useState(SAMPLE_AUTH_LOG);
  const [analyzing, setAnalyzing] = useState(false);
  const [result, setResult] = useState<AnalysisResult | null>(null);

  const failedPerHour = useMemo(() => {
    const buckets = Array.from({ length: 24 }, (_, i) => ({
      hour: `${String((new Date().getHours() - 23 + i + 48) % 24).padStart(2, '0')}:00`,
      failed: 0,
    }));
    for (const e of events ?? []) {
      if (e.status !== 'failed') continue;
      const ageHours = (Date.now() - new Date(e.timestamp).getTime()) / 3600_000;
      const idx = 23 - Math.floor(ageHours);
      if (idx >= 0 && idx < 24) buckets[idx].failed += 1;
    }
    return buckets;
  }, [events]);

  const columns: Column<LoginEvent>[] = [
    { key: 'user', header: 'User', render: (e) => <span className="font-mono text-xs text-slate-200">{e.username}</span>, sortValue: (e) => e.username },
    { key: 'ip', header: 'IP', render: (e) => <span className="font-mono text-xs text-slate-400">{e.sourceIp}</span>, sortValue: (e) => e.sourceIp },
    { key: 'loc', header: 'Location', render: (e) => <span className="text-xs text-slate-300">{e.location}</span>, sortValue: (e) => e.location },
    { key: 'dev', header: 'Device', render: (e) => <span className="font-mono text-xs text-slate-400">{e.device}</span>, sortValue: (e) => e.device },
    {
      key: 'status',
      header: 'Status',
      render: (e) =>
        e.status === 'success' ? (
          <span className="rounded-full bg-emerald-500/15 px-2 py-0.5 text-[11px] font-semibold text-emerald-400 ring-1 ring-emerald-500/40">SUCCESS</span>
        ) : (
          <span className="rounded-full bg-red-500/15 px-2 py-0.5 text-[11px] font-semibold text-red-400 ring-1 ring-red-500/40">FAILED</span>
        ),
      sortValue: (e) => e.status,
    },
    {
      key: 'risk',
      header: 'Risk',
      render: (e) => (
        <span
          className={`font-mono text-xs font-bold ${
            e.riskScore >= 80 ? 'text-red-500' : e.riskScore >= 60 ? 'text-orange-500' : e.riskScore >= 40 ? 'text-amber-500' : 'text-emerald-400'
          }`}
        >
          {e.riskScore}
        </span>
      ),
      sortValue: (e) => e.riskScore,
    },
    { key: 'time', header: 'Time', render: (e) => <span className="font-mono text-xs text-slate-500">{formatTime(e.timestamp)}</span>, sortValue: (e) => e.timestamp },
    {
      key: 'anom',
      header: 'Anomalies',
      render: (e) =>
        e.anomalies.length === 0 ? (
          <span className="text-xs text-slate-600">—</span>
        ) : (
          <div className="flex max-w-xs flex-wrap gap-1">
            {e.anomalies.map((a) => (
              <span key={a} className="rounded bg-amber-500/10 px-1.5 py-0.5 text-[10px] text-amber-500 ring-1 ring-amber-500/30">
                {a}
              </span>
            ))}
          </div>
        ),
    },
  ];

  const analyze = async () => {
    let parsed: unknown;
    try {
      parsed = JSON.parse(jsonInput);
    } catch {
      addToast('Invalid JSON: could not parse the auth log input', 'high');
      return;
    }
    if (!Array.isArray(parsed) || parsed.length === 0) {
      addToast('Auth log must be a non-empty JSON array of events', 'high');
      return;
    }
    setAnalyzing(true);
    try {
      const res = await api.analyzeAuthLog(
        (parsed as Record<string, string>[]).map((e) => ({
          user: String(e.user ?? ''),
          ip: String(e.ip ?? ''),
          location: String(e.location ?? ''),
          device: String(e.device ?? ''),
          status: String(e.status ?? ''),
          timestamp: String(e.timestamp ?? ''),
        }))
      );
      setResult(res);
      addToast(`Auth log analysis complete: risk ${res.riskScore}/100 (${res.severity})`, res.severity);
    } catch (err) {
      addToast(err instanceof Error ? err.message : 'Analysis failed. Please try again.', 'high');
    } finally {
      setAnalyzing(false);
    }
  };

  return (
    <div className="space-y-5">
      <PageHeader
        title="Credential Theft & Account Takeover Detection"
        description="Login anomaly detection: brute force, password spraying, impossible travel and MFA abuse."
      />

      {/* Recent login events */}
      <div>
        <div className="mb-2 flex items-center justify-between">
          <h3 className="text-sm font-semibold text-slate-200">Recent Login Events</h3>
          <button onClick={refetch} className="text-xs text-cyan-400 hover:text-cyan-300">
            Refresh
          </button>
        </div>
        {loading ? (
          <PanelSkeleton height="h-64" />
        ) : (
          <DataTable columns={columns} data={events ?? []} rowKey={(e) => e.id} emptyMessage="No login events recorded" />
        )}
      </div>

      {/* Failed logins chart */}
      <ChartCard title="Failed Logins per Hour — Last 24 Hours">
        <ResponsiveContainer width="100%" height={200}>
          <BarChart data={failedPerHour} margin={{ top: 4, right: 8, left: -22, bottom: 0 }}>
            <CartesianGrid stroke="#1e293b" strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="hour" tick={{ fill: '#94a3b8', fontSize: 10 }} interval={2} />
            <YAxis tick={{ fill: '#94a3b8', fontSize: 10 }} allowDecimals={false} />
            <Tooltip contentStyle={tooltipStyle} cursor={{ fill: '#1e293b55' }} />
            <Bar dataKey="failed" fill="#ef4444" radius={[3, 3, 0, 0]} name="Failed logins" />
          </BarChart>
        </ResponsiveContainer>
      </ChartCard>

      {/* Auth log analysis */}
      <div className="grid gap-5 lg:grid-cols-2">
        <div className="rounded-xl border border-slate-700/50 bg-slate-800/60 p-5 backdrop-blur">
          <div className="mb-3 flex items-center gap-2">
            <KeyRound className="h-4 w-4 text-cyan-400" />
            <h3 className="text-sm font-semibold text-slate-100">Analyze Authentication Log</h3>
          </div>
          <p className="mb-3 text-xs text-slate-500">
            Paste an array of auth events (user, ip, location, device, status, timestamp). The pre-filled sample contains a brute-force scenario.
          </p>
          <textarea
            value={jsonInput}
            onChange={(e) => setJsonInput(e.target.value)}
            rows={12}
            spellCheck={false}
            className="w-full resize-y rounded-lg border border-slate-700/60 bg-slate-900/80 p-3 font-mono text-[11px] leading-relaxed text-slate-200 outline-none focus:border-cyan-500/60"
          />
          <button
            onClick={analyze}
            disabled={analyzing}
            className="mt-3 flex items-center justify-center gap-2 rounded-lg bg-cyan-500 px-5 py-2.5 text-sm font-bold text-slate-950 hover:bg-cyan-400 disabled:opacity-60"
          >
            {analyzing ? <Loader2 className="h-4 w-4 animate-spin" /> : <PlayCircle className="h-4 w-4" />}
            {analyzing ? 'Analyzing...' : 'Analyze'}
          </button>
        </div>

        <div className="space-y-4">
          {analyzing && (
            <div className="rounded-xl border border-slate-700/50 bg-slate-800/60 p-5 backdrop-blur">
              <div className="mb-4 flex items-center gap-2 text-sm text-slate-400">
                <Loader2 className="h-4 w-4 animate-spin text-cyan-400" />
                Correlating login events...
              </div>
              <PanelSkeleton rows={5} />
            </div>
          )}
          {!analyzing && !result && (
            <div className="flex h-full min-h-56 items-center justify-center rounded-xl border border-dashed border-slate-700/60 bg-slate-800/20 p-8 text-center text-sm text-slate-500">
              Analysis results appear here — try the pre-filled brute-force sample
            </div>
          )}
          {!analyzing && result && (
            <>
              <div className="flex items-center gap-4 rounded-xl border border-slate-700/50 bg-slate-800/60 p-4 backdrop-blur">
                <span className="text-3xl font-bold" style={{ color: result.severity === 'critical' ? '#ef4444' : result.severity === 'high' ? '#f97316' : result.severity === 'medium' ? '#f59e0b' : '#10b981' }}>
                  {result.riskScore}
                </span>
                <div className="space-y-1">
                  <SeverityBadge severity={result.severity} />
                  <div className="text-xs text-slate-400">
                    {result.indicators.length} indicators — event <span className="font-mono text-slate-300">{result.eventId}</span>
                  </div>
                </div>
              </div>
              <IndicatorList indicators={result.indicators} />
              <ExplanationPanel explanation={result.explanation} confidence={result.confidence} />
              <RecommendedActionsPanel
                actions={result.recommendedActions}
                onExecute={(actionId) => {
                  const action = result.recommendedActions.find((a) => a.id === actionId);
                  addToast(`Response executed (simulated): ${action?.action ?? actionId}`, 'safe');
                }}
              />
            </>
          )}
        </div>
      </div>
    </div>
  );
}
