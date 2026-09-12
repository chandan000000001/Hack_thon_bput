import { useState } from 'react';
import { Link2, Loader2, PlayCircle } from 'lucide-react';
import * as api from '../services/api';
import type { AnalysisResult } from '../types';
import PageHeader from '../components/common/PageHeader';
import QueuedAnalysisPanel from '../components/common/QueuedAnalysisPanel';
import RiskGauge from '../components/common/RiskGauge';
import SeverityBadge from '../components/common/SeverityBadge';
import IndicatorList from '../components/common/IndicatorList';
import ExplanationPanel from '../components/common/ExplanationPanel';
import MitreTags from '../components/common/MitreTags';
import RecommendedActionsPanel from '../components/common/RecommendedActionsPanel';
import { PanelSkeleton } from '../components/common/LoadingSkeleton';
import { useUiStore } from '../store/uiStore';
import { useAuthStore } from '../store/authStore';
import { ArrowRight } from 'lucide-react';

const SAFE_SAMPLE = 'https://www.github.com/login';
const MALICIOUS_SAMPLE = 'http://secure-account-verification.micr0soft-support.xyz/auth/session?id=88213';

export default function UrlAnalysis() {
  const addToast = useUiStore((s) => s.addToast);
  const [url, setUrl] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const readOnly = !useAuthStore((s) => s.can('analyze'));


  const analyze = async () => {
    if (!url.trim()) {
      addToast('Enter a URL to analyze', 'medium');
      return;
    }
    setLoading(true);
    try {
      const res = await api.analyzeUrl(url.trim());
      setResult(res);
      addToast(`URL analysis complete: risk ${res.riskScore}/100 (${res.severity})`, res.severity);
    } catch (err) {
      addToast(err instanceof Error ? err.message : 'Analysis failed. Please try again.', 'high');
    } finally {
      setLoading(false);
    }
  };

  const breakdown = (() => {
    try {
      const u = new URL(url);
      const parts = u.hostname.split('.');
      return [
        { label: 'Protocol', value: u.protocol.replace(':', '') },
        { label: 'Hostname', value: u.hostname },
        { label: 'TLD', value: parts[parts.length - 1] ?? '-' },
        { label: 'Subdomains', value: parts.length > 2 ? parts.slice(0, -2).join('.') : '(none)' },
        { label: 'Path', value: u.pathname || '/' },
        { label: 'Query', value: u.search || '(none)' },
      ];
    } catch {
      return null;
    }
  })();

  return (
    <div className="space-y-5">
      <PageHeader
        title="Malicious URL & Website Detection"
        description="Lexical and structural analysis of URLs for phishing, spoofing and malware distribution patterns."
      />
      {readOnly && (
        <div className="rounded-lg border border-red-400/40 bg-red-400/10 px-3.5 py-2 text-xs text-red-400">
          Read-only role — mutation actions are disabled. Contact an administrator for elevated access.
        </div>
      )}


      <div className="rounded-xl border border-zinc-700/50 bg-zinc-800/60 p-5 backdrop-blur">
        <div className="flex flex-col gap-3 md:flex-row">
          <div className="relative flex-1">
            <Link2 className="absolute left-3 top-1/2 h-4 w-4 -tranzinc-y-1/2 text-zinc-500" />
            <input
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://suspicious-domain.example/login"
              onKeyDown={(e) => e.key === 'Enter' && analyze()}
              className="w-full rounded-lg border border-zinc-700/60 bg-zinc-800/60 py-2.5 pl-10 pr-3 font-mono text-sm text-zinc-100 placeholder-zinc-600 outline-none focus:border-red-500/60"
            />
          </div>
          <button
            onClick={analyze}
            disabled={loading || readOnly}
            title={readOnly ? 'Read-only role' : undefined}
            className="flex items-center justify-center gap-2 rounded-lg bg-red-600 px-6 py-2.5 text-sm font-bold text-white hover:bg-red-500 disabled:opacity-60"
          >
            {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <PlayCircle className="h-4 w-4" />}
            {loading ? 'Analyzing...' : 'Analyze URL'}
          </button>
        </div>
        <div className="mt-3 flex flex-wrap gap-2">
          <button
            onClick={() => setUrl(SAFE_SAMPLE)}
            className="rounded-lg bg-zinc-700/50 px-3 py-1.5 text-xs font-medium text-zinc-300 ring-1 ring-zinc-600/50 hover:bg-zinc-700"
          >
            Load Safe URL
          </button>
          <button
            onClick={() => setUrl(MALICIOUS_SAMPLE)}
            className="rounded-lg bg-red-500/10 px-3 py-1.5 text-xs font-medium text-red-400 ring-1 ring-red-500/40 hover:bg-red-500/20"
          >
            Load Malicious URL
          </button>
        </div>
      </div>

      {loading && (
        <div className="rounded-xl border border-zinc-700/50 bg-zinc-800/60 p-5 backdrop-blur">
          <div className="mb-4 flex items-center gap-2 text-sm text-zinc-400">
            <Loader2 className="h-4 w-4 animate-spin text-red-400" />
            Extracting lexical features and checking URL structure...
          </div>
          <PanelSkeleton rows={6} />
        </div>
      )}

      {!loading && !result && (
        <div className="flex min-h-40 items-center justify-center rounded-xl border border-dashed border-zinc-700/60 bg-zinc-800/20 p-8 text-center text-sm text-zinc-500">
          Enter a URL above and press Analyze URL to see the full structural breakdown
        </div>
      )}

      {!loading && result?.queued && <QueuedAnalysisPanel />}
          {!loading && result && !result.queued && (
        <div className="grid gap-5 lg:grid-cols-3">
          {/* Left: score + breakdown */}
          <div className="space-y-4">
            <div className="flex flex-col items-center rounded-xl border border-zinc-700/50 bg-zinc-800/60 p-5 backdrop-blur">
              <RiskGauge score={result.riskScore} size="lg" />
              <div className="mt-4 flex items-center gap-2">
                <SeverityBadge severity={result.severity} />
                <span className="text-xs text-zinc-400">
                  Confidence <span className="font-mono font-semibold text-red-400">{result.confidence}%</span>
                </span>
              </div>
            </div>

            {breakdown && (
              <div className="rounded-xl border border-zinc-700/50 bg-zinc-800/60 p-4 backdrop-blur">
                <h3 className="mb-3 text-sm font-semibold text-zinc-100">URL Breakdown</h3>
                <div className="space-y-2">
                  {breakdown.map((b) => (
                    <div key={b.label} className="flex items-baseline justify-between gap-3 text-xs">
                      <span className="shrink-0 text-zinc-500">{b.label}</span>
                      <span className="break-all text-right font-mono text-zinc-200">{b.value}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {result.redirectChain && result.redirectChain.length > 0 && (
              <div className="rounded-xl border border-red-600/40 bg-red-600/5 p-4">
                <h3 className="mb-3 text-sm font-semibold text-red-400">Simulated Redirect Chain</h3>
                <div className="space-y-2">
                  {result.redirectChain.map((hop, i) => (
                    <div key={i} className="flex items-center gap-2">
                      <div className="flex-1 break-all rounded-lg border border-zinc-700/50 bg-zinc-800/60 px-2.5 py-1.5 font-mono text-[11px] text-zinc-300">
                        {hop}
                      </div>
                      {i < result.redirectChain!.length - 1 && <ArrowRight className="h-3.5 w-3.5 shrink-0 text-red-400" />}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Right: analysis */}
          <div className="space-y-4 lg:col-span-2">
            {result.lexicalFeatures && result.lexicalFeatures.length > 0 && (
              <div className="rounded-xl border border-zinc-700/50 bg-zinc-800/60 p-4 backdrop-blur">
                <h3 className="mb-3 text-sm font-semibold text-zinc-100">Lexical Features</h3>
                <div className="overflow-hidden rounded-lg border border-zinc-700/50">
                  <table className="w-full text-left text-xs">
                    <thead>
                      <tr className="border-b border-zinc-700/50 bg-zinc-900/80 text-[11px] uppercase tracking-wider text-zinc-400">
                        <th className="px-3 py-2">Feature</th>
                        <th className="px-3 py-2">Value</th>
                        <th className="px-3 py-2 text-right">Risk Contribution</th>
                      </tr>
                    </thead>
                    <tbody>
                      {result.lexicalFeatures.map((f) => (
                        <tr key={f.feature} className="border-b border-zinc-800/60 last:border-0">
                          <td className="px-3 py-2 text-zinc-300">{f.feature}</td>
                          <td className="px-3 py-2 font-mono text-zinc-200">{f.value}</td>
                          <td className="px-3 py-2 text-right">
                            <span
                              className={`font-mono font-semibold ${
                                f.riskContribution === 0
                                  ? 'text-zinc-200'
                                  : f.riskContribution >= 20
                                    ? 'text-red-400'
                                    : 'text-red-400'
                              }`}
                            >
                              +{f.riskContribution}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            <IndicatorList indicators={result.indicators} />
            <ExplanationPanel explanation={result.explanation} confidence={result.confidence} provider={result.explanationProvider} />
            <div>
              <h3 className="mb-2 text-sm font-semibold text-zinc-200">MITRE ATT&CK Mapping</h3>
              <MitreTags techniques={result.mitreTechniques} />
            </div>
            <div>
              <h3 className="mb-2 text-sm font-semibold text-zinc-200">Recommended Response</h3>
              <RecommendedActionsPanel
                actions={result.recommendedActions}
                onExecute={(actionId) => {
                  const action = result.recommendedActions.find((a) => a.id === actionId);
                  addToast(`Response executed (simulated): ${action?.action ?? actionId}`, 'safe');
                }}
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
