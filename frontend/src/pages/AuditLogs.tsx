import { useMemo, useState } from 'react';
import { Search } from 'lucide-react';
import * as api from '../services/api';
import type { AuditLog } from '../types';
import { useApi } from '../hooks/useApi';
import PageHeader from '../components/common/PageHeader';
import DataTable, { type Column } from '../components/common/DataTable';
import { PanelSkeleton } from '../components/common/LoadingSkeleton';
import { formatTime } from '../constants';

const ACTION_COLORS: Record<string, string> = {
  LOGIN: 'text-zinc-200',
  LOGIN_FAILED: 'text-red-400',
  LOGOUT: 'text-zinc-400',
  EXECUTE_ACTION: 'text-red-400',
  APPROVE_ACTION: 'text-red-400',
  CREATE_INCIDENT: 'text-red-400',
  UPDATE_INCIDENT: 'text-red-400',
  CLOSE_INCIDENT: 'text-zinc-200',
  ESCALATE_INCIDENT: 'text-red-400',
  ASSIGN_INCIDENT: 'text-red-400',
  VIEW_ALERT: 'text-zinc-400',
  UPDATE_ALERT: 'text-red-400',
};

export default function AuditLogs() {
  const [search, setSearch] = useState('');
  const { data, loading } = useApi(() => api.listAuditLogs(), []);

  const filtered = useMemo(() => {
    const q = search.toLowerCase();
    if (!q) return data ?? [];
    return (data ?? []).filter(
      (l) =>
        l.userName.toLowerCase().includes(q) ||
        l.action.toLowerCase().includes(q) ||
        l.resource.toLowerCase().includes(q) ||
        l.details.toLowerCase().includes(q)
    );
  }, [data, search]);

  const columns: Column<AuditLog>[] = useMemo(
    () => [
      { key: 'time', header: 'Timestamp', render: (l) => <span className="font-mono text-xs text-zinc-500">{formatTime(l.timestamp)}</span>, sortValue: (l) => l.timestamp },
      { key: 'user', header: 'User', render: (l) => <span className="font-mono text-xs text-zinc-300">{l.userName}</span>, sortValue: (l) => l.userName },
      {
        key: 'action',
        header: 'Action',
        render: (l) => <span className={`font-mono text-xs font-bold ${ACTION_COLORS[l.action] ?? 'text-zinc-300'}`}>{l.action}</span>,
        sortValue: (l) => l.action,
      },
      { key: 'resource', header: 'Resource', render: (l) => <span className="font-mono text-xs text-red-400">{l.resource}</span>, sortValue: (l) => l.resource },
      { key: 'details', header: 'Details', render: (l) => <span className="block max-w-lg text-xs text-zinc-400">{l.details}</span> },
    ],
    []
  );

  return (
    <div className="space-y-4">
      <PageHeader
        title="Audit Logs"
        description="Complete trail of user and system activity: logins, incident changes, response executions and report exports."
      />

      <div className="relative">
        <Search className="absolute left-3 top-1/2 h-4 w-4 -tranzinc-y-1/2 text-zinc-500" />
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search by user, action, resource or details..."
          className="w-full rounded-lg border border-zinc-700/60 bg-zinc-800/60 py-2 pl-10 pr-3 text-sm text-zinc-100 placeholder-zinc-600 outline-none focus:border-red-500/60"
        />
      </div>

      {loading ? (
        <PanelSkeleton height="h-72" />
      ) : (
        <DataTable columns={columns} data={filtered} rowKey={(l) => l.id} emptyMessage="No audit entries match the search" />
      )}
    </div>
  );
}
