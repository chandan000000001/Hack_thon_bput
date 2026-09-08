import { useState } from 'react';
import { Loader2, Mail, PlayCircle, ShieldAlert } from 'lucide-react';
import * as api from '../services/api';
import type { AnalysisResult, RecommendedAction } from '../types';
import PageHeader from '../components/common/PageHeader';
import RiskGauge from '../components/common/RiskGauge';
import SeverityBadge from '../components/common/SeverityBadge';
import IndicatorList from '../components/common/IndicatorList';
import ExplanationPanel from '../components/common/ExplanationPanel';
import MitreTags from '../components/common/MitreTags';
import RecommendedActionsPanel from '../components/common/RecommendedActionsPanel';
import { PanelSkeleton } from '../components/common/LoadingSkeleton';
import { useUiStore } from '../store/uiStore';
import { useAuthStore } from '../store/authStore';

const BENIGN_SAMPLE = {
  sender: 'notices@university.edu',
  subject: 'Library hours update',
  body: 'The central library will remain open until 10 PM during examination week. No action is required from students.',
};

const PHISHING_SAMPLE = {
  sender: 'security-alert@micr0soft-verify.xyz',
  subject: 'URGENT: Verify your account immediately',
  body: 'Your account will be suspended within 24 hours. Click here http://185.220.101.7/login to verify your password and restore access. Failure to comply will result in permanent suspension.',
};

export default function PhishingAnalysis() {
  const addToast = useUiStore((s) => s.addToast);
  const [sender, setSender] = useState('');
  const [subject, setSubject] = useState('');
  const [body, setBody] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const readOnly = !useAuthStore((s) => s.can('analyze'));


  const analyze = async () => {
    if (!sender.trim() || !body.trim()) {
      addToast('Sender and email body are required', 'medium');
      return;
    }
    setLoading(true);
    try {
      const res = await api.analyzeEmail(sender, subject, body);
      setResult(res);
      addToast(`Analysis complete: risk ${res.riskScore}/100 (${res.severity})`, res.severity);
    } catch (err) {
      addToast(err instanceof Error ? err.message : 'Analysis failed. Please try again.', 'high');
    } finally {
      setLoading(false);
    }
  };

  const handleExecute = (actionId: string) => {
    const action = result?.recommendedActions.find((a: RecommendedAction) => a.id === actionId);
    addToast(`Response executed (simulated): ${action?.action ?? actionId}`, 'safe');
  };

  return (
    <div>
      <PageHeader
        title="AI-Powered Phishing Detection"
        description="Analyze emails for phishing, social engineering and credential harvesting using heuristic indicators."
      />
      {readOnly && (
        <div className="rounded-lg border border-red-400/40 bg-red-400/10 px-3.5 py-2 text-xs text-red-400">
          Read-only role — mutation actions are disabled. Contact an administrator for elevated access.
        </div>
      )}


      <div className="grid gap-5 lg:grid-cols-2">
        {/* Input form */}
        <div className="rounded-xl border border-zinc-700/50 bg-zinc-800/60 p-5 backdrop-blur">
          <div className="mb-4 flex items-center gap-2">
            <Mail className="h-4 w-4 text-red-400" />
            <h3 className="text-sm font-semibold text-zinc-100">Email Content</h3>
          </div>

          <div className="space-y-3.5">
            <div>
              <label className="mb-1.5 block text-xs font-medium uppercase tracking-wider text-zinc-400">Sender Address</label>
              <input
                value={sender}
                onChange={(e) => setSender(e.target.value)}
                placeholder="sender@example-domain.com"
                className="w-full rounded-lg border border-zinc-700/60 bg-zinc-800/60 px-3 py-2 font-mono text-sm text-zinc-100 placeholder-zinc-600 outline-none focus:border-red-500/60"
              />
            </div>
            <div>
              <label className="mb-1.5 block text-xs font-medium uppercase tracking-wider text-zinc-400">Subject</label>
              <input
                value={subject}
                onChange={(e) => setSubject(e.target.value)}
                placeholder="Email subject line"
                className="w-full rounded-lg border border-zinc-700/60 bg-zinc-800/60 px-3 py-2 text-sm text-zinc-100 placeholder-zinc-600 outline-none focus:border-red-500/60"
              />
            </div>
            <div>
              <label className="mb-1.5 block text-xs font-medium uppercase tracking-wider text-zinc-400">Email Body</label>
              <textarea
                value={body}
                onChange={(e) => setBody(e.target.value)}
                rows={8}
                placeholder="Paste the full email body here..."
                className="w-full resize-y rounded-lg border border-zinc-700/60 bg-zinc-800/60 px-3 py-2 text-sm leading-relaxed text-zinc-100 placeholder-zinc-600 outline-none focus:border-red-500/60"
              />
            </div>

            <div className="flex flex-wrap gap-2">
              <button
                onClick={() => {
                  setSender(BENIGN_SAMPLE.sender);
                  setSubject(BENIGN_SAMPLE.subject);
                  setBody(BENIGN_SAMPLE.body);
                }}
                className="rounded-lg bg-zinc-700/50 px-3 py-1.5 text-xs font-medium text-zinc-300 ring-1 ring-zinc-600/50 hover:bg-zinc-700"
              >
                Load Benign Sample
              </button>
              <button
                onClick={() => {
                  setSender(PHISHING_SAMPLE.sender);
                  setSubject(PHISHING_SAMPLE.subject);
                  setBody(PHISHING_SAMPLE.body);
                }}
                className="rounded-lg bg-red-500/10 px-3 py-1.5 text-xs font-medium text-red-400 ring-1 ring-red-500/40 hover:bg-red-500/20"
              >
                Load Phishing Sample
              </button>
            </div>

            <button
              onClick={analyze}
              disabled={loading || readOnly}
              title={readOnly ? 'Read-only role' : undefined}
              className="flex w-full items-center justify-center gap-2 rounded-lg bg-red-600 py-2.5 text-sm font-bold text-white hover:bg-red-500 disabled:opacity-60"
            >
              {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <PlayCircle className="h-4 w-4" />}
              {loading ? 'Analyzing...' : 'Analyze Email'}
            </button>
          </div>
        </div>

        {/* Results */}
        <div className="space-y-4">
          {loading && (
            <div className="rounded-xl border border-zinc-700/50 bg-zinc-800/60 p-5 backdrop-blur">
              <div className="mb-4 flex items-center gap-2 text-sm text-zinc-400">
                <Loader2 className="h-4 w-4 animate-spin text-red-400" />
                Running heuristic phishing analysis...
              </div>
              <PanelSkeleton rows={5} />
              <div className="mt-4">
                <PanelSkeleton rows={3} />
              </div>
            </div>
          )}

          {!loading && !result && (
            <div className="flex h-full min-h-64 flex-col items-center justify-center rounded-xl border border-dashed border-zinc-700/60 bg-zinc-800/20 p-8 text-center">
              <ShieldAlert className="h-10 w-10 text-zinc-600" />
              <p className="mt-3 text-sm text-zinc-400">Results appear here after analysis</p>
              <p className="mt-1 text-xs text-zinc-600">Load a sample or paste your own email content</p>
            </div>
          )}

          {!loading && result && (
            <>
              <div className="flex items-center gap-6 rounded-xl border border-zinc-700/50 bg-zinc-800/60 p-5 backdrop-blur">
                <RiskGauge score={result.riskScore} size="lg" />
                <div className="space-y-2">
                  <SeverityBadge severity={result.severity} />
                  <div className="text-xs text-zinc-400">
                    Threat type: <span className="text-zinc-200">{result.threatType}</span>
                  </div>
                  <div className="text-xs text-zinc-400">
                    Confidence: <span className="font-mono font-semibold text-red-400">{result.confidence}%</span>
                  </div>
                  <div className="text-xs text-zinc-400">
                    Event: <span className="font-mono text-zinc-300">{result.eventId}</span>
                  </div>
                </div>
              </div>
              <IndicatorList indicators={result.indicators} />
              <ExplanationPanel explanation={result.explanation} confidence={result.confidence} />
              <div>
                <h3 className="mb-2 text-sm font-semibold text-zinc-200">MITRE ATT&CK Mapping</h3>
                <MitreTags techniques={result.mitreTechniques} />
              </div>
              <div>
                <h3 className="mb-2 text-sm font-semibold text-zinc-200">Recommended Response</h3>
                <RecommendedActionsPanel actions={result.recommendedActions} onExecute={handleExecute} />
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
