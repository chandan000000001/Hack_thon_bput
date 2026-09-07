import { useMemo } from 'react';
import { BarChart3, Download, FileJson, FileSpreadsheet } from 'lucide-react';
import * as api from '../services/api';
import { useApi } from '../hooks/useApi';
import { useUiStore } from '../store/uiStore';
import PageHeader from '../components/common/PageHeader';
import { PanelSkeleton } from '../components/common/LoadingSkeleton';
import { formatTime } from '../constants';
import { SEVERITY_COLORS, getSeverityFromScore } from '../services/mockEngine';

export default function Reports() {
  const addToast = useUiStore((s) => s.addToast);
  const { data: summary, loading } = useApi(() => api.getDashboardSummary(), []);
  const { data: alerts } = useApi(() => api.listAlerts({ limit: 200 }), []);

  const avgRisk = useMemo(() => {
    if (!alerts || alerts.length === 0) return 0;
    return Math.round(alerts.reduce((sum, a) => sum + a.riskScore, 0) / alerts.length);
  }, [alerts]);

  const topModule = useMemo(() => {
    if (!summary) return '—';
    const sorted = [...summary.threatCategories].sort((a, b) => b.count - a.count);
    return sorted[0] ? `${sorted[0].name} (${sorted[0].count})` : '—';
  }, [summary]);

  const exportJson = () => {
    if (!summary || !alerts) return;
    const report = {
      generatedAt: new Date().toISOString(),
      note: api.isMockMode()
        ? 'CYBERGUARD mock-mode report. All data is simulated.'
        : 'CYBERGUARD report generated from the live backend.',
      summary: {
        totalEventsAnalyzed: summary.totalEventsAnalyzed,
        threatsDetected: summary.threatsDetected,
        phishingAttempts: summary.phishingAttempts,
        impersonationAttempts: summary.impersonationAttempts,
        suspectedDeepfakes: summary.suspectedDeepfakes,
        accountTakeoverAttempts: summary.accountTakeoverAttempts,
        riskDistribution: summary.riskDistribution,
        threatCategories: summary.threatCategories,
        incidentSummary: summary.incidentSummary,
      },
      alerts: alerts.map((a) => ({
        id: a.id,
        title: a.title,
        module: a.module,
        severity: a.severity,
        riskScore: a.riskScore,
        status: a.status,
        targetUser: a.targetUser,
        targetService: a.targetService,
        sourceIp: a.sourceIp,
        timestamp: a.timestamp,
        mitreTechniques: a.mitreTechniques.map((t) => t.id),
      })),
    };
    const blob = new Blob([JSON.stringify(report, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `cyberguard-report-${new Date().toISOString().slice(0, 10)}.json`;
    a.click();
    URL.revokeObjectURL(url);
    addToast('JSON report downloaded', 'safe');
  };

  const exportCsv = () => {
    if (!alerts) return;
    const header = ['id', 'title', 'module', 'severity', 'riskScore', 'status', 'targetUser', 'targetService', 'sourceIp', 'timestamp', 'mitre'];
    const escape = (v: string) => `"${v.replace(/"/g, '""')}"`;
    const rows = alerts.map((a) =>
      [
        a.id,
        a.title,
        a.module,
        a.severity,
        String(a.riskScore),
        a.status,
        a.targetUser ?? '',
        a.targetService ?? '',
        a.sourceIp ?? '',
        a.timestamp,
        a.mitreTechniques.map((t) => t.id).join('|'),
      ]
        .map(escape)
        .join(',')
    );
    const csv = [header.join(','), ...rows].join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `cyberguard-alerts-${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
    addToast('CSV report downloaded', 'safe');
  };

  return (
    <div className="space-y-5">
      <PageHeader
        title="Reports & Export"
        description="Generate and download point-in-time threat reports. All exports are generated client-side from mock data."
        actions={
          <>
            <button
              onClick={exportJson}
              disabled={loading}
              className="flex items-center gap-2 rounded-lg bg-cyan-500/15 px-4 py-2 text-xs font-bold text-cyan-300 ring-1 ring-cyan-500/40 hover:bg-cyan-500/25 disabled:opacity-60"
            >
              <FileJson className="h-3.5 w-3.5" /> Export JSON Report
            </button>
            <button
              onClick={exportCsv}
              disabled={loading}
              className="flex items-center gap-2 rounded-lg bg-emerald-500/15 px-4 py-2 text-xs font-bold text-emerald-400 ring-1 ring-emerald-500/40 hover:bg-emerald-500/25 disabled:opacity-60"
            >
              <FileSpreadsheet className="h-3.5 w-3.5" /> Export CSV Report
            </button>
          </>
        }
      />

      {loading || !summary ? (
        <div className="grid gap-4 md:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <PanelSkeleton key={i} height="h-28" />
          ))}
        </div>
      ) : (
        <>
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            <div className="rounded-xl border border-slate-700/50 bg-slate-800/60 p-4 backdrop-blur">
              <div className="text-xs uppercase tracking-wider text-slate-400">Total Events Analyzed</div>
              <div className="mt-1.5 text-2xl font-bold text-cyan-400">{summary.totalEventsAnalyzed.toLocaleString()}</div>
              <div className="mt-1 text-xs text-slate-500">across all detection modules</div>
            </div>
            <div className="rounded-xl border border-slate-700/50 bg-slate-800/60 p-4 backdrop-blur">
              <div className="text-xs uppercase tracking-wider text-slate-400">Average Risk Score</div>
              <div className="mt-1.5 flex items-baseline gap-2">
                <span className="text-2xl font-bold" style={{ color: SEVERITY_COLORS[getSeverityFromScore(avgRisk)] }}>
                  {avgRisk}
                </span>
                <span className="text-xs uppercase text-slate-500">{getSeverityFromScore(avgRisk)}</span>
              </div>
              <div className="mt-1 text-xs text-slate-500">mean across {alerts?.length ?? 0} alerts</div>
            </div>
            <div className="rounded-xl border border-slate-700/50 bg-slate-800/60 p-4 backdrop-blur">
              <div className="text-xs uppercase tracking-wider text-slate-400">Top Threat Module</div>
              <div className="mt-1.5 flex items-center gap-2 text-lg font-bold text-orange-500">
                <BarChart3 className="h-5 w-5" />
                {topModule}
              </div>
              <div className="mt-1 text-xs text-slate-500">most frequently detected category</div>
            </div>
            <div className="rounded-xl border border-slate-700/50 bg-slate-800/60 p-4 backdrop-blur">
              <div className="text-xs uppercase tracking-wider text-slate-400">Threats by Category</div>
              <div className="mt-2 space-y-1.5">
                {summary.threatCategories.slice(0, 3).map((c) => (
                  <div key={c.name} className="flex items-center justify-between text-xs">
                    <span className="text-slate-300">{c.name}</span>
                    <span className="font-mono font-bold text-slate-100">{c.count}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div className="rounded-xl border border-slate-700/50 bg-slate-800/60 p-5 backdrop-blur">
            <div className="mb-3 flex items-center gap-2">
              <Download className="h-4 w-4 text-cyan-400" />
              <h3 className="text-sm font-semibold text-slate-100">Export Contents</h3>
            </div>
            <div className="grid gap-4 text-xs leading-relaxed text-slate-400 md:grid-cols-2">
              <div>
                <div className="mb-1 font-semibold text-slate-200">JSON Report</div>
                Full dashboard summary (event counts, risk distribution, threat categories, incident summary) plus every alert with its indicators' MITRE mappings. Suitable for programmatic processing or archiving.
              </div>
              <div>
                <div className="mb-1 font-semibold text-slate-200">CSV Report</div>
                One row per alert with ID, title, module, severity, risk score, status, targets, source IP and MITRE technique IDs. Suitable for spreadsheets and SIEM import.
              </div>
            </div>
            <p className="mt-3 border-t border-slate-700/50 pt-3 font-mono text-[11px] text-slate-600">
              Last dashboard refresh context: {formatTime(summary.recentAlerts[0]?.timestamp ?? new Date().toISOString())} (newest alert)
            </p>
          </div>
        </>
      )}
    </div>
  );
}
