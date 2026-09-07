import { BrainCircuit } from 'lucide-react';

interface Props {
  explanation: string;
  confidence: number;
}

const KEY_PHRASES = [
  'Critical Risk', 'High Risk', 'Medium Risk', 'Low Risk',
  'impossible travel', 'character substitution', 'credential harvesting',
  'data exfiltration', 'beaconing', 'password spraying', 'synthetic',
  'impersonation', 'brute force', 'credential stuffing', 'DNS tunneling',
];

function highlight(text: string): React.ReactNode[] {
  const parts: React.ReactNode[] = [];
  let remaining = text;
  let key = 0;
  while (remaining.length > 0) {
    let earliest: { idx: number; phrase: string } | null = null;
    for (const phrase of KEY_PHRASES) {
      const idx = remaining.toLowerCase().indexOf(phrase.toLowerCase());
      if (idx !== -1 && (earliest === null || idx < earliest.idx)) {
        earliest = { idx, phrase };
      }
    }
    if (!earliest) {
      parts.push(<span key={key++}>{remaining}</span>);
      break;
    }
    if (earliest.idx > 0) parts.push(<span key={key++}>{remaining.slice(0, earliest.idx)}</span>);
    parts.push(
      <mark key={key++} className="rounded bg-cyan-500/20 px-1 font-medium text-cyan-300">
        {remaining.slice(earliest.idx, earliest.idx + earliest.phrase.length)}
      </mark>
    );
    remaining = remaining.slice(earliest.idx + earliest.phrase.length);
  }
  return parts;
}

export default function ExplanationPanel({ explanation, confidence }: Props) {
  return (
    <div className="rounded-xl border border-slate-700/50 bg-slate-800/40 p-4">
      <div className="flex items-center gap-2">
        <BrainCircuit className="h-4.5 w-4.5 text-cyan-400" style={{ width: 18, height: 18 }} />
        <h3 className="text-sm font-semibold text-slate-100">AI Explanation</h3>
        <span className="ml-auto text-[10px] uppercase tracking-wider text-slate-500">Simulated XAI output</span>
      </div>
      <p className="mt-3 text-[13px] leading-relaxed text-slate-300">{highlight(explanation)}</p>
      <div className="mt-4">
        <div className="flex items-center justify-between text-xs">
          <span className="text-slate-400">Detection Confidence</span>
          <span className="font-mono font-semibold text-cyan-400">{confidence}%</span>
        </div>
        <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-slate-700/60">
          <div
            className="h-full rounded-full bg-gradient-to-r from-cyan-600 to-cyan-400"
            style={{ width: `${Math.min(100, confidence)}%`, transition: 'width 700ms ease' }}
          />
        </div>
      </div>
    </div>
  );
}
