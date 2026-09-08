import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import * as api from '../services/api';
import type { Incident, IncidentStatus } from '../types';
import { useApi } from '../hooks/useApi';
import PageHeader from '../components/common/PageHeader';
import { useAuthStore } from '../store/authStore';
import DataTable, { type Column } from '../components/common/DataTable';
import SeverityBadge from '../components/common/SeverityBadge';
import StatusPill from '../components/common/StatusPill';
import { PanelSkeleton } from '../components/common/LoadingSkeleton';
import { formatTime } from '../constants';

const STATUS_OPTIONS: IncidentStatus[] = ['open', 'investigating', 'contained', 'closed'];

export default function Incidents() {
  const navigate = useNavigate();
  const [statusFilter, setStatusFilter] = useState<IncidentStatus | ''>('');
  const readOnly = !useAuthStore((s) => s.can('analyze'));

  const { data, loading } = useApi(() => api.listIncidents(), []);

  const filtered = useMemo(
    () => (data ?? []).filter((i) => !statusFilter || i.status === statusFilter),
    [data, statusFilter]
  );

  const columns: Column<Incident>[] = useMemo(
    () => [
      { key: 'id', header: 'ID', render: (i) => <span className="font-mono text-xs text-red-400">{i.id}</span>, sortValue: (i) => i.id },
      { key: 'title', header: 'Title', render: (i) => <span className="block max-w-sm truncate text-zinc-200">{i.title}</span>, sortValue: (i) => i.title },
      { key: 'severity', header: 'Severity', render: (i) => <SeverityBadge severity={i.severity} />, sortValue: (i) => i.severity },
      { key: 'status', header: 'Status', render: (i) => <StatusPill status={i.status} />, sortValue: (i) => i.status },
      { key: 'assigned', header: 'Assigned To', render: (i) => <span className="text-xs text-zinc-300">{i.assignedTo ?? 'Unassigned'}</span> },
      { key: 'alerts', header: 'Linked Alerts', render: (i) => <span className="font-mono text-xs text-zinc-300">{i.linkedAlertIds.length}</span>, sortValue: (i) => i.linkedAlertIds.length },
      { key: 'created', header: 'Created', render: (i) => <span className="font-mono text-xs text-zinc-500">{formatTime(i.createdAt)}</span>, sortValue: (i) => i.createdAt },
      { key: 'updated', header: 'Updated', render: (i) => <span className="font-mono text-xs text-zinc-500">{formatTime(i.updatedAt)}</span>, sortValue: (i) => i.updatedAt },
    ],
    []
  );

  return (
    <div className="space-y-4">
      <PageHeader title="Incident Management" description="Track, assign and progress security incidents through their lifecycle." />
      {readOnly && (
        <div className="rounded-lg border border-red-400/40 bg-red-400/10 px-3.5 py-2 text-xs text-red-400">
          Read-only role — mutation actions are disabled. Contact an administrator for elevated access.
        </div>
      )}


      <div className="flex flex-wrap gap-2">
        <button
          onClick={() => setStatusFilter('')}
          className={`rounded-lg px-3.5 py-1.5 text-xs font-semibold ring-1 ${
            statusFilter === '' ? 'bg-red-500/15 text-red-300 ring-red-500/40' : 'bg-zinc-800/60 text-zinc-400 ring-zinc-700/50 hover:text-zinc-200'
          }`}
        >
          All ({data?.length ?? 0})
        </button>
        {STATUS_OPTIONS.map((s) => (
          <button
            key={s}
            onClick={() => setStatusFilter(s)}
            className={`rounded-lg px-3.5 py-1.5 text-xs font-semibold ring-1 ${
              statusFilter === s ? 'bg-red-500/15 text-red-300 ring-red-500/40' : 'bg-zinc-800/60 text-zinc-400 ring-zinc-700/50 hover:text-zinc-200'
            }`}
          >
            {s.toUpperCase()} ({(data ?? []).filter((i) => i.status === s).length})
          </button>
        ))}
      </div>

      {loading ? (
        <PanelSkeleton height="h-64" />
      ) : (
        <DataTable
          columns={columns}
          data={filtered}
          rowKey={(i) => i.id}
          onRowClick={(i) => navigate(`/incidents/${i.id}`)}
          emptyMessage="No incidents found"
        />
      )}
    </div>
  );
}
