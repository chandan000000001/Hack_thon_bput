import { useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, ArrowRight, ArrowUpRight, Loader2, Users } from 'lucide-react';
import * as api from '../services/api';
import { useApi } from '../hooks/useApi';
import { useUiStore } from '../store/uiStore';
import { useAuthStore } from '../store/authStore';
import { ANALYSTS, formatTime } from '../constants';
import type { IncidentStatus } from '../types';
import SeverityBadge from '../components/common/SeverityBadge';
import StatusPill from '../components/common/StatusPill';
import { PanelSkeleton } from '../components/common/LoadingSkeleton';
import EmptyState from '../components/common/EmptyState';

const NEXT_ACTION: Partial<Record<IncidentStatus, string>> = {
  open: 'Start Investigation',
  investigating: 'Mark Contained',
  contained: 'Close Incident',
};

export default function IncidentDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const addToast = useUiStore((s) => s.addToast);
  const { data: incident, loading, error, refetch } = useApi(() => api.getIncident(id ?? ''), [id]);
  const [busy, setBusy] = useState(false);
  const readOnly = !useAuthStore((s) => s.can('analyze'));


  if (loading) {
    return (
      <div className="space-y-4">
        <PanelSkeleton height="h-32" />
        <PanelSkeleton height="h-64" />
      </div>
    );
  }

  if (error || !incident) {
    return (
      <div className="space-y-4">
        <Link to="/incidents" className="inline-flex items-center gap-1.5 text-xs text-red-400 hover:text-red-300">
          <ArrowLeft className="h-3.5 w-3.5" /> Back to Incidents
        </Link>
        <EmptyState icon={Loader2} title="Incident not found" description={error ?? `No incident with ID ${id}`} />
      </div>
    );
  }

  const runAction = async (fn: () => Promise<unknown>, message: string) => {
    setBusy(true);
    try {
      await fn();
      await refetch();
      addToast(message, 'safe');
    } catch (err) {
      addToast(err instanceof Error ? err.message : 'Action failed', 'high');
    } finally {
      setBusy(false);
    }
  };

  const transition = () => {
    const next = NEXT_ACTION[incident.status];
    if (!next || !id) return;
    const target: IncidentStatus = incident.status === 'open' ? 'investigating' : incident.status === 'investigating' ? 'contained' : 'closed';
    runAction(() => api.updateIncidentStatus(id, target), `Incident status updated to ${target}`);
  };

  const escalate = () => {
    if (!id) return;
    const reason = window.prompt('Reason for escalation:', 'Needs senior SOC management attention');
    if (!reason || !reason.trim()) return;
    runAction(() => api.escalateIncident(id, reason.trim()), 'Incident escalated to senior SOC management');
  };

  const assign = (analyst: string) => {
    if (!id) return;
    runAction(() => api.assignIncident(id, analyst), `Incident assigned to ${analyst}`);
  };

  const nextLabel = NEXT_ACTION[incident.status];

  return (
    <div className="space-y-5">
      {readOnly && (
        <div className="rounded-lg border border-red-400/40 bg-red-400/10 px-3.5 py-2 text-xs text-red-400">
          Read-only role — mutation actions are disabled. Contact an administrator for elevated access.
        </div>
      )}

      <Link to="/incidents" className="inline-flex items-center gap-1.5 text-xs text-red-400 hover:text-red-300">
        <ArrowLeft className="h-3.5 w-3.5" /> Back to Incidents
      </Link>

      {/* Header */}
      <div className="rounded-xl border border-zinc-700/50 bg-zinc-800/60 p-5 backdrop-blur">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="flex flex-wrap items-center gap-2.5">
              <span className="font-mono text-sm font-bold text-red-400">{incident.id}</span>
              <SeverityBadge severity={incident.severity} />
              <StatusPill status={incident.status} />
            </div>
            <h2 className="mt-1.5 text-lg font-bold text-zinc-100">{incident.title}</h2>
            <p className="mt-1 text-xs text-zinc-500">
              Created {formatTime(incident.createdAt)} — Updated {formatTime(incident.updatedAt)}
            </p>
          </div>
          <div className="flex flex-col items-end gap-2.5">
            <div className="flex items-center gap-2">
              <Users className="h-3.5 w-3.5 text-zinc-500" />
              <select
                value={incident.assignedTo ?? 'Unassigned'}
                disabled={readOnly}
                title={readOnly ? 'Read-only role' : undefined}
                onChange={(e) => assign(e.target.value)}
                className="rounded-lg border border-zinc-700/60 bg-zinc-800 px-2.5 py-1.5 text-xs text-zinc-200 outline-none focus:border-red-500/60"
              >
                {ANALYSTS.map((a) => (
                  <option key={a} value={a}>
                    {a}
                  </option>
                ))}
              </select>
            </div>
            <div className="flex gap-2">
              {nextLabel && (
                <button
                  onClick={transition}
                  disabled={busy || readOnly}
                  title={readOnly ? 'Read-only role' : undefined}
                  className="flex items-center gap-1.5 rounded-lg bg-red-500/15 px-3.5 py-1.5 text-xs font-bold text-red-300 ring-1 ring-red-500/40 hover:bg-red-500/25 disabled:opacity-60"
                >
                  {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <ArrowRight className="h-3.5 w-3.5" />}
                  {nextLabel}
                </button>
              )}
              <button
                onClick={escalate}
                disabled={busy || readOnly}
                title={readOnly ? 'Read-only role' : undefined}
                className="flex items-center gap-1.5 rounded-lg bg-red-500/10 px-3.5 py-1.5 text-xs font-bold text-red-400 ring-1 ring-red-500/40 hover:bg-red-500/20 disabled:opacity-60"
              >
                <ArrowUpRight className="h-3.5 w-3.5" />
                Escalate
              </button>
            </div>
          </div>
        </div>
      </div>

      <div className="grid gap-5 lg:grid-cols-2">
        {/* Timeline */}
        <div className="rounded-xl border border-zinc-700/50 bg-zinc-800/60 p-5 backdrop-blur">
          <h3 className="mb-4 text-sm font-semibold text-zinc-100">Incident Timeline</h3>
          <div className="relative space-y-5 pl-5">
            <div className="absolute bottom-2 left-[7px] top-2 w-px bg-zinc-700" />
            {[...incident.timeline].reverse().map((ev) => (
              <div key={ev.id} className="relative">
                <div className="absolute -left-5 top-1 h-3.5 w-3.5 rounded-full border-2 border-red-500 bg-zinc-900" />
                <div className="flex flex-wrap items-baseline gap-2">
                  <span className="text-sm font-semibold text-zinc-200">{ev.action}</span>
                  <span className="font-mono text-[10px] text-zinc-500">{formatTime(ev.timestamp)}</span>
                </div>
                <div className="mt-0.5 text-xs text-red-400">{ev.actor}</div>
                <p className="mt-1 text-xs leading-relaxed text-zinc-400">{ev.details}</p>
              </div>
            ))}
          </div>
        </div>

        {/* Linked alerts */}
        <div className="rounded-xl border border-zinc-700/50 bg-zinc-800/60 p-5 backdrop-blur">
          <h3 className="mb-4 text-sm font-semibold text-zinc-100">Linked Alerts ({incident.linkedAlertIds.length})</h3>
          <div className="space-y-2.5">
            {incident.linkedAlertIds.map((alertId) => (
              <LinkedAlertRow key={alertId} alertId={alertId} onOpen={() => navigate(`/alerts/${alertId}`)} />
            ))}
            {incident.linkedAlertIds.length === 0 && (
              <p className="text-xs text-zinc-500">No alerts linked to this incident</p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function LinkedAlertRow({ alertId, onOpen }: { alertId: string; onOpen: () => void }) {
  const { data: alert } = useApi(() => api.getAlert(alertId), [alertId]);
  if (!alert) {
    return (
      <div className="rounded-lg border border-zinc-700/50 bg-zinc-800/40 px-3.5 py-3 text-xs text-zinc-400">
        {alertId}
      </div>
    );
  }
  return (
    <button
      onClick={onOpen}
      className="w-full rounded-lg border border-zinc-700/50 bg-zinc-800/40 px-3.5 py-3 text-left hover:border-red-500/40 hover:bg-red-500/5"
    >
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-mono text-xs font-bold text-red-400">{alert.id}</span>
        <SeverityBadge severity={alert.severity} />
        <span className="ml-auto font-mono text-[11px] text-zinc-500">risk {alert.riskScore}</span>
      </div>
      <div className="mt-1 text-xs text-zinc-300">{alert.title}</div>
    </button>
  );
}
