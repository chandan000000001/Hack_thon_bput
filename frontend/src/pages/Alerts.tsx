import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Bell } from 'lucide-react';
import * as api from '../services/api';
import type { Alert, Severity, ThreatModule } from '../types';
import { useApi } from '../hooks/useApi';
import { useRealtimeAlerts } from '../hooks/useRealtimeAlerts';
import { useUiStore } from '../store/uiStore';
import PageHeader from '../components/common/PageHeader';
import DataTable, { type Column } from '../components/common/DataTable';
import SeverityBadge from '../components/common/SeverityBadge';
import StatusPill from '../components/common/StatusPill';
import { PanelSkeleton } from '../components/common/LoadingSkeleton';
import { MODULE_LABELS, MODULE_OPTIONS, SEVERITY_OPTIONS, formatTime } from '../constants';

const PAGE_SIZE = 20;

export default function Alerts() {
  const navigate = useNavigate();
  const [severity, setSeverity] = useState<Severity | ''>('');
  const [module, setModule] = useState<ThreatModule | ''>('');
  const [status, setStatus] = useState('');
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);

  const { data, loading, refetch } = useApi(
    () =>
      api.listAlerts({
        severity: severity || undefined,
        module: module || undefined,
        status: status || undefined,
        search: search || undefined,
        limit: 200,
      }),
    [severity, module, status, search]
  );
  const liveAlerts = useUiStore((s) => s.liveSimulation);
  useRealtimeAlerts(liveAlerts, refetch);

  const alertColumns: Column<Alert>[] = useMemo(
    () => [
      { key: 'id', header: 'ID', render: (a) => <span className="font-mono text-xs text-red-400">{a.id}</span>, sortValue: (a) => a.id },
      { key: 'title', header: 'Title', render: (a) => <span className="block max-w-xs truncate text-zinc-200">{a.title}</span>, sortValue: (a) => a.title },
      { key: 'module', header: 'Module', render: (a) => <span className="text-xs text-zinc-400">{MODULE_LABELS[a.module]}</span>, sortValue: (a) => a.module },
      { key: 'severity', header: 'Severity', render: (a) => <SeverityBadge severity={a.severity} />, sortValue: (a) => a.severity },
      { key: 'risk', header: 'Risk', render: (a) => <span className="font-mono text-sm font-semibold text-zinc-100">{a.riskScore}</span>, sortValue: (a) => a.riskScore },
      { key: 'status', header: 'Status', render: (a) => <StatusPill status={a.status} />, sortValue: (a) => a.status },
      { key: 'target', header: 'Target', render: (a) => <span className="block max-w-40 truncate font-mono text-xs text-zinc-400">{a.targetUser ?? a.targetService ?? '—'}</span> },
      { key: 'time', header: 'Timestamp', render: (a) => <span className="font-mono text-xs text-zinc-500">{formatTime(a.timestamp)}</span>, sortValue: (a) => a.timestamp },
    ],
    []
  );

  const total = data?.length ?? 0;
  const paged = (data ?? []).slice(0, page * PAGE_SIZE);

  return (
    <div className="space-y-4">
      <PageHeader title="Security Alerts" description="All detected threats across every detection module." />

      {/* Filter bar */}
      <div className="grid gap-2 rounded-xl border border-zinc-700/50 bg-zinc-800/60 p-3 backdrop-blur sm:grid-cols-2 lg:grid-cols-4">
        <select
          value={severity}
          onChange={(e) => {
            setSeverity(e.target.value as Severity | '');
            setPage(1);
          }}
          className="rounded-lg border border-zinc-700/60 bg-zinc-800 px-3 py-2 text-sm text-zinc-200 outline-none focus:border-red-500/60"
        >
          <option value="">All severities</option>
          {SEVERITY_OPTIONS.map((s) => (
            <option key={s} value={s}>
              {s.toUpperCase()}
            </option>
          ))}
        </select>
        <select
          value={module}
          onChange={(e) => {
            setModule(e.target.value as ThreatModule | '');
            setPage(1);
          }}
          className="rounded-lg border border-zinc-700/60 bg-zinc-800 px-3 py-2 text-sm text-zinc-200 outline-none focus:border-red-500/60"
        >
          <option value="">All modules</option>
          {MODULE_OPTIONS.map((m) => (
            <option key={m} value={m}>
              {MODULE_LABELS[m]}
            </option>
          ))}
        </select>
        <select
          value={status}
          onChange={(e) => {
            setStatus(e.target.value);
            setPage(1);
          }}
          className="rounded-lg border border-zinc-700/60 bg-zinc-800 px-3 py-2 text-sm text-zinc-200 outline-none focus:border-red-500/60"
        >
          <option value="">All statuses</option>
          {['new', 'acknowledged', 'resolved', 'dismissed'].map((s) => (
            <option key={s} value={s}>
              {s.toUpperCase()}
            </option>
          ))}
        </select>
        <input
          value={search}
          onChange={(e) => {
            setSearch(e.target.value);
            setPage(1);
          }}
          placeholder="Search title, summary, ID or target..."
          className="rounded-lg border border-zinc-700/60 bg-zinc-800 px-3 py-2 text-sm text-zinc-100 placeholder-zinc-600 outline-none focus:border-red-500/60"
        />
      </div>

      {loading ? (
        <PanelSkeleton height="h-72" />
      ) : (
        <>
          <DataTable
            columns={alertColumns}
            data={paged}
            rowKey={(a) => a.id}
            onRowClick={(a) => navigate(`/alerts/${a.id}`)}
            emptyMessage="No alerts match the current filters"
          />
          {total > paged.length && (
            <div className="text-center">
              <button
                onClick={() => setPage((p) => p + 1)}
                className="rounded-lg bg-zinc-800 px-5 py-2 text-xs font-semibold text-red-300 ring-1 ring-zinc-700 hover:bg-zinc-700"
              >
                Show more ({total - paged.length} remaining)
              </button>
            </div>
          )}
          <p className="text-center text-[11px] text-zinc-600">
            Showing {paged.length} of {total} alerts
          </p>
        </>
      )}

      {!loading && total === 0 && (
        <div className="flex flex-col items-center rounded-xl border border-zinc-700/50 bg-zinc-800/30 py-10 text-center">
          <Bell className="h-6 w-6 text-zinc-600" />
          <p className="mt-2 text-sm text-zinc-400">No alerts match the current filters</p>
        </div>
      )}
    </div>
  );
}
