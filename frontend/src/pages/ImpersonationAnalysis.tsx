import { useState } from 'react';
import { Loader2, PlayCircle, UserX } from 'lucide-react';
import * as api from '../services/api';
import type { AnalysisResult } from '../types';
import PageHeader from '../components/common/PageHeader';
import RiskGauge from '../components/common/RiskGauge';
import SeverityBadge from '../components/common/SeverityBadge';
import IndicatorList from '../components/common/IndicatorList';
import ExplanationPanel from '../components/common/ExplanationPanel';
import MitreTags from '../components/common/MitreTags';
import RecommendedActionsPanel from '../components/common/RecommendedActionsPanel';
import { PanelSkeleton } from '../components/common/LoadingSkeleton';
import { useUiStore } from '../store/uiStore';

const NORMAL_SAMPLE = {
  identity: 'Team Lead',
  message:
    'Hi team, please remember to submit your weekly reports by Friday. The template is in the shared drive. Thanks.',
};

const FAKE_CEO_SAMPLE = {
  identity: 'Chief Executive Officer',
  message:
    'This is urgent and confidential. I am in a board meeting and cannot call. Purchase three Amazon gift cards worth $500 each for a client settlement immediately and send me the codes via this email. Do not inform finance until I return. This must be done within the hour.',
};

export default function ImpersonationAnalysis() {
  const addToast = useUiStore((s) => s.addToast);
  const [claimedIdentity, setClaimedIdentity] = useState('');
  const [message, setMessage] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<AnalysisResult | null>(null);

  const analyze = async () => {
    if (!claimedIdentity.trim() || !message.trim()) {
      addToast('Claimed identity and message are required', 'medium');
      return;
    }
    setLoading(true);
    try {
      const res = await api.analyzeImpersonation(message, claimedIdentity);
      setResult(res);
      addToast(`Analysis complete: risk ${res.riskScore}/100 (${res.severity})`, res.severity);
    } catch (err) {
      addToast(err instanceof Error ? err.message : 'Analysis failed. Please try again.', 'high');
    } finally {
      setLoading(false);
    }
  };

  const handleExecute = (actionId: string) => {
    const action = result?.recommendedActions.find((a) => a.id === actionId);
    addToast(`Response executed (simulated): ${action?.action ?? actionId}`, 'safe');
  };

  return (
    <div>
      <PageHeader
        title="Digital Impersonation Detection"
        description="Detect CEO fraud, authority impersonation and business email compromise patterns in messages."
      />

      <div className="grid gap-5 lg:grid-cols-2">
        <div className="rounded-xl border border-slate-700/50 bg-slate-800/60 p-5 backdrop-blur">
          <div className="mb-4 flex items-center gap-2">
            <UserX className="h-4 w-4 text-cyan-400" />
            <h3 className="text-sm font-semibold text-slate-100">Message to Analyze</h3>
          </div>

          <div className="space-y-3.5">
            <div>
              <label className="mb-1.5 block text-xs font-medium uppercase tracking-wider text-slate-400">Claimed Identity</label>
              <input
                value={claimedIdentity}
                onChange={(e) => setClaimedIdentity(e.target.value)}
                placeholder="e.g., CEO, Bank Manager, IT Support"
                className="w-full rounded-lg border border-slate-700/60 bg-slate-800/60 px-3 py-2 text-sm text-slate-100 placeholder-slate-600 outline-none focus:border-cyan-500/60"
              />
            </div>
            <div>
              <label className="mb-1.5 block text-xs font-medium uppercase tracking-wider text-slate-400">Message</label>
              <textarea
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                rows={8}
                placeholder="Paste the message content here..."
                className="w-full resize-y rounded-lg border border-slate-700/60 bg-slate-800/60 px-3 py-2 text-sm leading-relaxed text-slate-100 placeholder-slate-600 outline-none focus:border-cyan-500/60"
              />
            </div>

            <div className="flex flex-wrap gap-2">
              <button
                onClick={() => {
                  setClaimedIdentity(NORMAL_SAMPLE.identity);
                  setMessage(NORMAL_SAMPLE.message);
                }}
                className="rounded-lg bg-slate-700/50 px-3 py-1.5 text-xs font-medium text-slate-300 ring-1 ring-slate-600/50 hover:bg-slate-700"
              >
                Load Normal Message
              </button>
              <button
                onClick={() => {
                  setClaimedIdentity(FAKE_CEO_SAMPLE.identity);
                  setMessage(FAKE_CEO_SAMPLE.message);
                }}
                className="rounded-lg bg-red-500/10 px-3 py-1.5 text-xs font-medium text-red-400 ring-1 ring-red-500/40 hover:bg-red-500/20"
              >
                Load Fake CEO Sample
              </button>
            </div>

            <button
              onClick={analyze}
              disabled={loading}
              className="flex w-full items-center justify-center gap-2 rounded-lg bg-cyan-500 py-2.5 text-sm font-bold text-slate-950 hover:bg-cyan-400 disabled:opacity-60"
            >
              {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <PlayCircle className="h-4 w-4" />}
              {loading ? 'Analyzing...' : 'Analyze Message'}
            </button>
          </div>
        </div>

        <div className="space-y-4">
          {loading && (
            <div className="rounded-xl border border-slate-700/50 bg-slate-800/60 p-5 backdrop-blur">
              <div className="mb-4 flex items-center gap-2 text-sm text-slate-400">
                <Loader2 className="h-4 w-4 animate-spin text-cyan-400" />
                Evaluating authority, urgency, secrecy and request patterns...
              </div>
              <PanelSkeleton rows={5} />
            </div>
          )}

          {!loading && !result && (
            <div className="flex h-full min-h-64 flex-col items-center justify-center rounded-xl border border-dashed border-slate-700/60 bg-slate-800/20 p-8 text-center">
              <UserX className="h-10 w-10 text-slate-600" />
              <p className="mt-3 text-sm text-slate-400">Results appear here after analysis</p>
              <p className="mt-1 text-xs text-slate-600">Try the Fake CEO sample to see BEC detection in action</p>
            </div>
          )}

          {!loading && result && (
            <>
              <div className="flex items-center gap-6 rounded-xl border border-slate-700/50 bg-slate-800/60 p-5 backdrop-blur">
                <RiskGauge score={result.riskScore} size="lg" />
                <div className="space-y-2">
                  <SeverityBadge severity={result.severity} />
                  <div className="text-xs text-slate-400">
                    Threat type: <span className="text-slate-200">{result.threatType}</span>
                  </div>
                  <div className="text-xs text-slate-400">
                    Claimed identity: <span className="text-slate-200">{claimedIdentity}</span>
                  </div>
                  <div className="text-xs text-slate-400">
                    Event: <span className="font-mono text-slate-300">{result.eventId}</span>
                  </div>
                </div>
              </div>
              <IndicatorList indicators={result.indicators} />
              <ExplanationPanel explanation={result.explanation} confidence={result.confidence} />
              <div>
                <h3 className="mb-2 text-sm font-semibold text-slate-200">MITRE ATT&CK Mapping</h3>
                <MitreTags techniques={result.mitreTechniques} />
              </div>
              <div>
                <h3 className="mb-2 text-sm font-semibold text-slate-200">Recommended Response</h3>
                <RecommendedActionsPanel actions={result.recommendedActions} onExecute={handleExecute} />
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
