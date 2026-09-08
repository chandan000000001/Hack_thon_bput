import { useState } from 'react';
import { Flag, Loader2, PlayCircle, Video } from 'lucide-react';
import * as api from '../services/api';
import type { AnalysisResult } from '../types';
import PageHeader from '../components/common/PageHeader';
import FileUpload from '../components/common/FileUpload';
import RiskGauge from '../components/common/RiskGauge';
import SeverityBadge from '../components/common/SeverityBadge';
import IndicatorList from '../components/common/IndicatorList';
import ExplanationPanel from '../components/common/ExplanationPanel';
import RecommendedActionsPanel from '../components/common/RecommendedActionsPanel';
import { PanelSkeleton } from '../components/common/LoadingSkeleton';
import { useUiStore } from '../store/uiStore';
import { useAuthStore } from '../store/authStore';

function MiniGauge({ label, value }: { label: string; value: number }) {
  const pct = Math.round(value * 100);
  const color = pct >= 60 ? '#ef4444' : pct >= 35 ? '#f59e0b' : '#10b981';
  const radius = 40;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference * (1 - value);
  return (
    <div className="flex flex-col items-center">
      <svg width={100} height={100} className="-rotate-90">
        <circle cx={50} cy={50} r={radius} fill="none" stroke="#1e293b" strokeWidth={8} />
        <circle
          cx={50}
          cy={50}
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth={8}
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          style={{ transition: 'stroke-dashoffset 700ms ease' }}
        />
      </svg>
      <span className="-mt-[62px] text-lg font-bold" style={{ color }}>
        {pct}%
      </span>
      <span className="mt-8 text-[11px] uppercase tracking-wider text-slate-400">{label}</span>
    </div>
  );
}

export default function DeepfakeAnalysis() {
  const addToast = useUiStore((s) => s.addToast);
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const readOnly = !useAuthStore((s) => s.can('analyze'));


  const analyze = async () => {
    if (!file) {
      addToast('Select a media file first', 'medium');
      return;
    }
    setLoading(true);
    try {
      const res = await api.analyzeMedia(file);
      setResult(res);
      addToast(`Media analysis complete: risk ${res.riskScore}/100 (${res.severity})`, res.severity);
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
        title="Deepfake & Manipulated Media Detection"
        description="Heuristic media forensics for images, audio and video. Deterministic per-file results in mock mode."
      />
      {readOnly && (
        <div className="rounded-lg border border-amber-500/40 bg-amber-500/10 px-3.5 py-2 text-xs text-amber-400">
          Read-only role — mutation actions are disabled. Contact an administrator for elevated access.
        </div>
      )}


      <div className="grid gap-5 lg:grid-cols-2">
        <div className="rounded-xl border border-slate-700/50 bg-slate-800/60 p-5 backdrop-blur">
          <div className="mb-4 flex items-center gap-2">
            <Video className="h-4 w-4 text-cyan-400" />
            <h3 className="text-sm font-semibold text-slate-100">Upload Media</h3>
          </div>
          <FileUpload
            accept="image/*,audio/*,video/*"
            maxSize={25 * 1024 * 1024}
            onFile={(f) => {
              setFile(f);
              setResult(null);
            }}
          />
          <button
            onClick={analyze}
            disabled={loading || !file || readOnly}
            title={readOnly ? 'Read-only role' : undefined}
            className="mt-4 flex w-full items-center justify-center gap-2 rounded-lg bg-cyan-500 py-2.5 text-sm font-bold text-slate-950 hover:bg-cyan-400 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <PlayCircle className="h-4 w-4" />}
            {loading ? 'Analyzing media...' : 'Analyze Media'}
          </button>
        </div>

        <div className="space-y-4">
          {loading && (
            <div className="rounded-xl border border-slate-700/50 bg-slate-800/60 p-5 backdrop-blur">
              <div className="mb-4 flex items-center gap-2 text-sm text-slate-400">
                <Loader2 className="h-4 w-4 animate-spin text-cyan-400" />
                Running media forensics: frame, spectral and metadata checks...
              </div>
              <PanelSkeleton rows={5} />
            </div>
          )}

          {!loading && !result && (
            <div className="flex h-full min-h-64 flex-col items-center justify-center rounded-xl border border-dashed border-slate-700/60 bg-slate-800/20 p-8 text-center">
              <Video className="h-10 w-10 text-slate-600" />
              <p className="mt-3 text-sm text-slate-400">Upload an image, audio clip or video to begin</p>
              <p className="mt-1 text-xs text-slate-600">Same file always produces the same deterministic verdict</p>
            </div>
          )}

          {!loading && result && (
            <>
              <div className="rounded-xl border border-slate-700/50 bg-slate-800/60 p-5 backdrop-blur">
                <div className="flex flex-wrap items-center justify-around gap-6">
                  <MiniGauge label="Authenticity" value={result.authenticityScore ?? 0} />
                  <MiniGauge label="Manipulation Probability" value={result.manipulationProbability ?? 0} />
                  <RiskGauge score={result.riskScore} size="md" />
                </div>
                <div className="mt-4 flex flex-wrap items-center justify-center gap-3">
                  <SeverityBadge severity={result.severity} />
                  {result.simulated !== undefined && (
                    <span
                      className={`rounded-full px-2.5 py-0.5 text-[11px] font-semibold uppercase tracking-wide ring-1 ${
                        result.simulated
                          ? 'bg-amber-500/15 text-amber-500 ring-amber-500/40'
                          : 'bg-emerald-500/15 text-emerald-400 ring-emerald-500/40'
                      }`}
                      title={result.method}
                    >
                      {result.simulated ? 'Simulated analysis' : 'Real forensic analysis'}
                    </span>
                  )}
                  <span className="text-xs text-slate-400">
                    Confidence <span className="font-mono font-semibold text-cyan-400">{result.confidence}%</span>
                  </span>
                  <span className="text-xs text-slate-400">
                    Event <span className="font-mono text-slate-300">{result.eventId}</span>
                  </span>
                </div>
              </div>

              <IndicatorList indicators={result.indicators} />
              <ExplanationPanel explanation={result.explanation} confidence={result.confidence} />
              <div>
                <h3 className="mb-2 text-sm font-semibold text-slate-200">Recommended Response</h3>
                <RecommendedActionsPanel actions={result.recommendedActions} onExecute={handleExecute} />
              </div>
              <button
                onClick={() => addToast('Media flagged for manual verification by forensic analysts', 'medium')}
                disabled={readOnly}
                title={readOnly ? 'Read-only role' : undefined}
                className="flex w-full items-center justify-center gap-2 rounded-lg border border-amber-500/50 bg-amber-500/10 py-2.5 text-sm font-bold text-amber-400 hover:bg-amber-500/20"
              >
                <Flag className="h-4 w-4" />
                Flag for Manual Verification
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
