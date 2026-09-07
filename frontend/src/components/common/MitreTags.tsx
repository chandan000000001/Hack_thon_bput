import { Crosshair } from 'lucide-react';
import type { MitreTechnique } from '../../types';

const TACTIC_COLOR: Record<string, string> = {
  'Initial Access': 'text-red-400',
  'Credential Access': 'text-orange-400',
  'Command and Control': 'text-amber-400',
  Exfiltration: 'text-fuchsia-400',
  'Defense Evasion': 'text-cyan-400',
  Collection: 'text-emerald-400',
  'Lateral Movement': 'text-sky-400',
  Discovery: 'text-indigo-400',
  Execution: 'text-violet-400',
  Persistence: 'text-yellow-400',
  'Resource Development': 'text-teal-400',
};

export default function MitreTags({ techniques }: { techniques: MitreTechnique[] }) {
  if (techniques.length === 0) {
    return (
      <div className="rounded-xl border border-slate-700/50 bg-slate-800/40 px-4 py-5 text-center text-xs text-slate-500">
        No MITRE ATT&CK techniques mapped for this result
      </div>
    );
  }
  return (
    <div className="flex flex-wrap gap-2">
      {techniques.map((t) => (
        <div
          key={t.id}
          className="rounded-lg border border-slate-700/60 bg-slate-800/50 px-3 py-2"
          title={`${t.id} — ${t.name} (${t.tactic})`}
        >
          <div className="flex items-center gap-1.5">
            <Crosshair className="h-3 w-3 text-slate-500" />
            <span className="font-mono text-xs font-bold text-cyan-400">{t.id}</span>
            <span className="text-xs text-slate-200">{t.name}</span>
          </div>
          <div className={`mt-0.5 text-[10px] uppercase tracking-wider ${TACTIC_COLOR[t.tactic] ?? 'text-slate-500'}`}>
            {t.tactic}
          </div>
        </div>
      ))}
    </div>
  );
}
