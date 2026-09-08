import { useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, FolderPlus, Loader2 } from 'lucide-react';
import * as api from '../services/api';
import { useApi } from '../hooks/useApi';
import { useUiStore } from '../store/uiStore';
import { useAuthStore } from '../store/authStore';
import type { Alert, RecommendedAction } from '../types';
import RiskGauge from '../components/common/RiskGauge';
import SeverityBadge from '../components/common/SeverityBadge';
import IndicatorList from '../components/common/IndicatorList';
import ExplanationPanel from '../components/common/ExplanationPanel';
import MitreTags from '../components/common/MitreTags';
import RecommendedActionsPanel from '../components/common/RecommendedActionsPanel';
import { PanelSkeleton } from '../components/common/LoadingSkeleton';
import { MODULE_LABELS, formatTime } from '../constants';
import EmptyState from '../components/common/EmptyState';

type Tab = 'indicators' | 'explanation' | 'mitre' | 'response';

const TABS: [Tab, string][] = [
  ['indicators', 'Indicators'],
  ['explanation', 'Explanation'],
  ['mitre', 'MITRE ATT&CK'],
  ['response', 'Response'],
];

export default function AlertDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const addToast = useUiStore((s) => s.addToast);
  const { data: alert, loading, error, refetch } = useApi(() => api.getAlert(id ?? ''), [id]);
  const [tab, setTab] = useState<Tab>('indicators');
  const [creating, setCreating] = useState(false);
  const [savingStatus, setSavingStatus] = useState(false);
  const readOnly = !useAuthStore((s) => s.can('analyze'));


  if (loading) {
    return (
      <div className="space-y-4">
        <PanelSkeleton height="h-24" />
        <div className="grid gap-4 lg:grid-cols-4">
          <PanelSkeleton height="h-48" />
          <PanelSkeleton className="lg:col-span-3" height="h-48" />
        </div>
      </div>
    );
  }

  if (error || !alert) {
    return (
      <div className="space-y-4">
        <Link to="/alerts" className="inline-flex items-center gap-1.5 text-xs text-cyan-400 hover:text-cyan-300">
          <ArrowLeft className="h-3.5 w-3.5" /> Back to Alerts
        </Link>
        <EmptyState icon={Loader2} title="Alert not found" description={error ?? `No alert with ID ${id}`} />
      </div>
    );
  }

  const handleStatusChange = async (next: Alert['status']) => {
    if (!alert || next === alert.status) return;
    setSavingStatus(true);
    try {
      await api.updateAlertStatus(alert.id, next);
      addToast(`Alert status changed to ${next}`, 'safe');
      refetch();
    } catch (err) {
      addToast(err instanceof Error ? err.message : 'Failed to update alert status', 'high');
    } finally {
      setSavingStatus(false);
    }
  };

  const createIncident = async () => {
    setCreating(true);
    try {
      const incident = await api.createIncident(alert.id);
      addToast(`Incident ${incident.id} created from ${alert.id}`, 'safe');
      navigate(`/incidents/${incident.id}`);
    } catch (err) {
      addToast(err instanceof Error ? err.message : 'Failed to create incident', 'high');
    } finally {
      setCreating(false);
    }
  };

  return (
    <div className="space-y-5">
      {readOnly && (
        <div className="rounded-lg border border-amber-500/40 bg-amber-500/10 px-3.5 py-2 text-xs text-amber-400">
          Read-only role — mutation actions are disabled. Contact an administrator for elevated access.
        </div>
      )}

      <div className="flex items-center justify-between">
        <Link to="/alerts" className="inline-flex items-center gap-1.5 text-xs text-cyan-400 hover:text-cyan-300">
          <ArrowLeft className="h-3.5 w-3.5" /> Back to Alerts
        </Link>
        <button
          onClick={createIncident}
          disabled={creating || readOnly}
          title={readOnly ? 'Read-only role' : undefined}
          className="flex items-center gap-2 rounded-lg bg-cyan-500/15 px-4 py-2 text-xs font-bold text-cyan-300 ring-1 ring-cyan-500/40 hover:bg-cyan-500/25 disabled:opacity-60"
        >
          {creating ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <FolderPlus className="h-3.5 w-3.5" />}
          Create Incident
        </button>
      </div>

      {/* Header card */}
      <div className="rounded-xl border border-slate-700/50 bg-slate-800/60 p-5 backdrop-blur">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="flex flex-wrap items-center gap-2.5">
              <span className="font-mono text-sm font-bold text-cyan-400">{alert.id}</span>
              <SeverityBadge severity={alert.severity} />
              <select
                value={alert.status}
                disabled={savingStatus || readOnly}
                title={readOnly ? 'Read-only role' : undefined}
                onChange={(e) => handleStatusChange(e.target.value as Alert['status'])}
                className="rounded-full bg-slate-800 px-2.5 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-slate-200 ring-1 ring-slate-600 outline-none focus:ring-cyan-500/60 disabled:opacity-60"
              >
                {(['new', 'acknowledged', 'resolved', 'dismissed'] as const).map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
              <span className="text-[11px] uppercase tracking-wider text-slate-500">{MODULE_LABELS[alert.module]}</span>
            </div>
            <h2 className="mt-1.5 text-lg font-bold text-slate-100">{alert.title}</h2>
            <p className="mt-1 max-w-2xl text-sm text-slate-400">{alert.summary}</p>
          </div>
          <RiskGauge score={alert.riskScore} size="lg" />
        </div>

        <div className="mt-4 grid gap-3 border-t border-slate-700/50 pt-4 sm:grid-cols-2 lg:grid-cols-4">
          {(
            [
              ['Target User', alert.targetUser],
              ['Target Service', alert.targetService],
              ['Source IP', alert.sourceIp],
              ['Detected', formatTime(alert.timestamp)],
            ] as const
          ).map(([label, value]) => (
            <div key={label}>
              <div className="text-[10px] uppercase tracking-wider text-slate-500">{label}</div>
              <div className={`mt-0.5 truncate text-sm ${label === 'Source IP' || label === 'Target User' ? 'font-mono text-slate-200' : 'text-slate-200'}`}>
                {value ?? '—'}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 rounded-xl border border-slate-700/50 bg-slate-800/60 p-1 backdrop-blur">
        {TABS.map(([key, label]) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={`flex-1 rounded-lg px-3 py-2 text-xs font-semibold sm:text-sm ${
              tab === key ? 'bg-cyan-500/15 text-cyan-300 ring-1 ring-cyan-500/40' : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      <div>
        {tab === 'indicators' && <IndicatorList indicators={alert.indicators} />}
        {tab === 'explanation' && <ExplanationPanel explanation={alert.explanation} confidence={Math.min(97, 70 + alert.riskScore / 4)} />}
        {tab === 'mitre' && (
          <div className="space-y-3">
            <p className="text-xs text-slate-500">
              Techniques from the MITRE ATT&CK framework mapped to this detection. Mappings reflect the observed behaviors in the alert indicators.
            </p>
            <MitreTags techniques={alert.mitreTechniques} />
            {alert.mitreTechniques.map((t) => (
              <div key={t.id} className="rounded-lg border border-slate-700/50 bg-slate-800/40 p-3.5">
                <div className="flex items-center gap-2">
                  <span className="font-mono text-sm font-bold text-cyan-400">{t.id}</span>
                  <span className="text-sm font-semibold text-slate-200">{t.name}</span>
                  <span className="ml-auto rounded bg-slate-700/60 px-2 py-0.5 text-[10px] uppercase tracking-wider text-slate-400">{t.tactic}</span>
                </div>
                <p className="mt-1.5 text-xs leading-relaxed text-slate-400">
                  Technique <span className="font-mono text-slate-300">{t.id}</span> under the <span className="text-slate-300">{t.tactic}</span> tactic was mapped because the indicators in this alert match behaviors documented for {t.name}. Review the MITRE ATT&CK knowledge base entry for full detection and mitigation guidance.
                </p>
              </div>
            ))}
          </div>
        )}
        {tab === 'response' && (
          <RecommendedActionsPanel
            actions={alert.recommendedActions}
            onExecute={(actionId) => {
              const action = alert.recommendedActions.find((a: RecommendedAction) => a.id === actionId);
              addToast(`Response executed (simulated): ${action?.action ?? actionId}`, 'safe');
            }}
          />
        )}
      </div>
    </div>
  );
}
