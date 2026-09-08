import { useMemo, useState } from 'react';
import { Loader2, Zap } from 'lucide-react';
import * as api from '../services/api';
import type { ResponseActionCatalog } from '../types';
import { useApi } from '../hooks/useApi';
import { useUiStore } from '../store/uiStore';
import { useAuthStore } from '../store/authStore';
import PageHeader from '../components/common/PageHeader';
import DataTable, { type Column } from '../components/common/DataTable';
import { PanelSkeleton } from '../components/common/LoadingSkeleton';
import { formatTime } from '../constants';

export default function ResponseActions() {
  const addToast = useUiStore((s) => s.addToast);
  const { data: catalog, loading } = useApi(() => api.listResponseCatalog(), []);
  const { data: history, refetch: refetchHistory } = useApi(() => api.listResponseHistory(), []);

  const [selectedAction, setSelectedAction] = useState('');
  const [target, setTarget] = useState('');
  const [approved, setApproved] = useState(false);
  const [executing, setExecuting] = useState(false);
  const readOnly = !useAuthStore((s) => s.can('analyze'));


  const selected = useMemo(
    () => catalog?.find((c) => c.id === selectedAction) ?? null,
    [catalog, selectedAction]
  );

  const catalogColumns: Column<ResponseActionCatalog>[] = useMemo(
    () => [
      { key: 'action', header: 'Action', render: (c) => <span className="text-sm font-medium text-slate-200">{c.action}</span>, sortValue: (c) => c.action },
      { key: 'tt', header: 'Target Type', render: (c) => <span className="font-mono text-xs text-slate-400">{c.targetType}</span>, sortValue: (c) => c.targetType },
      {
        key: 'auto',
        header: 'Automation',
        render: (c) => (
          <span
            className={`rounded px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide ring-1 ${
              c.automationLevel === 'automatic'
                ? 'bg-emerald-500/15 text-emerald-400 ring-emerald-500/40'
                : c.automationLevel === 'semi-automatic'
                  ? 'bg-amber-500/15 text-amber-500 ring-amber-500/40'
                  : 'bg-slate-600/30 text-slate-300 ring-slate-500/40'
            }`}
          >
            {c.automationLevel}
          </span>
        ),
        sortValue: (c) => c.automationLevel,
      },
      {
        key: 'appr',
        header: 'Approval',
        render: (c) =>
          c.requiresApproval ? (
            <span className="rounded bg-red-500/15 px-1.5 py-0.5 text-[10px] font-bold uppercase text-red-400 ring-1 ring-red-500/40">Required</span>
          ) : (
            <span className="text-xs text-slate-500">Not required</span>
          ),
        sortValue: (c) => (c.requiresApproval ? 1 : 0),
      },
      { key: 'desc', header: 'Description', render: (c) => <span className="block max-w-md text-xs text-slate-400">{c.description}</span> },
    ],
    []
  );

  const execute = async () => {
    if (!selectedAction || !target.trim()) {
      addToast('Select an action and provide a target', 'medium');
      return;
    }
    if (selected?.requiresApproval && !approved) {
      addToast('Destructive actions require explicit approval first', 'high');
      return;
    }
    setExecuting(true);
    try {
      const execution = await api.executeResponse(selectedAction, target.trim(), approved || !selected?.requiresApproval);
      addToast(`Executed (simulated): ${execution.actionName} on ${execution.target}`, 'safe');
      setTarget('');
      setApproved(false);
      setSelectedAction('');
      refetchHistory();
    } catch (err) {
      addToast(err instanceof Error ? err.message : 'Execution failed', 'high');
    } finally {
      setExecuting(false);
    }
  };

  return (
    <div className="space-y-5">
      <PageHeader
        title="Response Actions"
        description="Simulated response playbook execution. Destructive actions require explicit human approval and every execution is recorded in the audit log."
      />
      {readOnly && (
        <div className="rounded-lg border border-amber-500/40 bg-amber-500/10 px-3.5 py-2 text-xs text-amber-400">
          Read-only role — mutation actions are disabled. Contact an administrator for elevated access.
        </div>
      )}


      {/* Action catalog */}
      <div>
        <h3 className="mb-2 text-sm font-semibold text-slate-200">Action Catalog</h3>
        {loading ? (
          <PanelSkeleton height="h-56" />
        ) : (
          <DataTable columns={catalogColumns} data={catalog ?? []} rowKey={(c) => c.id} emptyMessage="No response actions configured" />
        )}
      </div>

      <div className="grid gap-5 lg:grid-cols-2">
        {/* Execute form */}
        <div className="rounded-xl border border-slate-700/50 bg-slate-800/60 p-5 backdrop-blur">
          <div className="mb-4 flex items-center gap-2">
            <Zap className="h-4 w-4 text-cyan-400" />
            <h3 className="text-sm font-semibold text-slate-100">Execute Action (Simulated)</h3>
          </div>
          <div className="space-y-3.5">
            <div>
              <label className="mb-1.5 block text-xs font-medium uppercase tracking-wider text-slate-400">Action</label>
              <select
                value={selectedAction}
                onChange={(e) => {
                  setSelectedAction(e.target.value);
                  setApproved(false);
                }}
                className="w-full rounded-lg border border-slate-700/60 bg-slate-800 px-3 py-2 text-sm text-slate-200 outline-none focus:border-cyan-500/60"
              >
                <option value="">Select an action...</option>
                {(catalog ?? []).map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.action} {c.requiresApproval ? '(approval required)' : ''}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="mb-1.5 block text-xs font-medium uppercase tracking-wider text-slate-400">Target</label>
              <input
                value={target}
                onChange={(e) => setTarget(e.target.value)}
                placeholder="e.g., 185.220.101.7, user@company.com, host-10.0.4.21"
                className="w-full rounded-lg border border-slate-700/60 bg-slate-800/60 px-3 py-2 font-mono text-sm text-slate-100 placeholder-slate-600 outline-none focus:border-cyan-500/60"
              />
            </div>

            {selected?.requiresApproval && (
              <label className="flex cursor-pointer items-center gap-2 rounded-lg border border-amber-500/40 bg-amber-500/5 px-3 py-2.5 text-xs text-amber-400">
                <input
                  type="checkbox"
                  checked={approved}
                  disabled={readOnly}
                  title={readOnly ? 'Read-only role' : undefined}
                  onChange={(e) => setApproved(e.target.checked)}
                  className="h-4 w-4 rounded border-slate-600 bg-slate-700 accent-cyan-500"
                />
                I approve this destructive action on the target above
              </label>
            )}

            <button
              onClick={execute}
              disabled={executing || readOnly || !selectedAction || !target.trim() || (selected?.requiresApproval === true && !approved)}
              title={readOnly ? 'Read-only role' : undefined}
              className="flex w-full items-center justify-center gap-2 rounded-lg bg-cyan-500 py-2.5 text-sm font-bold text-slate-950 hover:bg-cyan-400 disabled:cursor-not-allowed disabled:opacity-40"
            >
              {executing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Zap className="h-4 w-4" />}
              {executing ? 'Executing...' : 'Execute (Simulated)'}
            </button>
            <p className="text-center text-[11px] text-slate-600">
              No real infrastructure is modified. All executions are simulated and audit-logged.
            </p>
          </div>
        </div>

        {/* Execution history */}
        <div>
          <h3 className="mb-2 text-sm font-semibold text-slate-200">Execution History</h3>
          <div className="overflow-x-auto rounded-xl border border-slate-700/50">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-slate-700/50 bg-slate-900/80 text-[11px] uppercase tracking-wider text-slate-400">
                  <th className="px-3 py-2">Action</th>
                  <th className="px-3 py-2">Target</th>
                  <th className="px-3 py-2">Status</th>
                  <th className="px-3 py-2">Executed By</th>
                  <th className="px-3 py-2">Time</th>
                </tr>
              </thead>
              <tbody>
                {(history ?? []).map((e, i) => (
                  <tr key={e.id} className={`border-b border-slate-800/60 text-xs last:border-0 ${i % 2 === 1 ? 'bg-slate-800/20' : ''}`}>
                    <td className="px-3 py-2.5 font-medium text-slate-200">{e.actionName}</td>
                    <td className="max-w-40 truncate px-3 py-2.5 font-mono text-slate-400">{e.target}</td>
                    <td className="px-3 py-2.5">
                      <span
                        className={`rounded-full px-2 py-0.5 text-[10px] font-bold uppercase ring-1 ${
                          e.status === 'executed'
                            ? 'bg-emerald-500/15 text-emerald-400 ring-emerald-500/40'
                            : e.status === 'approved'
                              ? 'bg-cyan-500/15 text-cyan-400 ring-cyan-500/40'
                              : e.status === 'rejected'
                                ? 'bg-red-500/15 text-red-400 ring-red-500/40'
                                : 'bg-amber-500/15 text-amber-500 ring-amber-500/40'
                        }`}
                      >
                        {e.status}
                      </span>
                    </td>
                    <td className="max-w-36 truncate px-3 py-2.5 font-mono text-[11px] text-slate-400">{e.executedBy}</td>
                    <td className="px-3 py-2.5 font-mono text-[11px] text-slate-500">{formatTime(e.timestamp)}</td>
                  </tr>
                ))}
                {(history ?? []).length === 0 && (
                  <tr>
                    <td colSpan={5} className="px-3 py-8 text-center text-xs text-slate-500">
                      No executions recorded yet
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
