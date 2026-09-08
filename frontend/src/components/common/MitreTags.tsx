import { Crosshair } from 'lucide-react';
import type { MitreTechnique } from '../../types';

// Monochrome tactic accents — red shades + white/zinc neutrals only.
const TACTIC_COLOR: Record<string, string> = {
  'Initial Access': 'text-red-400',
  'Credential Access': 'text-red-500',
  'Command and Control': 'text-red-300',
  Exfiltration: 'text-white',
  'Defense Evasion': 'text-zinc-300',
  Collection: 'text-zinc-400',
  'Lateral Movement': 'text-zinc-400',
  Discovery: 'text-zinc-300',
  Execution: 'text-zinc-200',
  Persistence: 'text-zinc-500',
  'Resource Development': 'text-zinc-400',
};

export default function MitreTags({ techniques }: { techniques: MitreTechnique[] }) {
  if (techniques.length === 0) {
    return (
      <div className="rounded-xl border border-zinc-700/50 bg-zinc-800/40 px-4 py-5 text-center text-xs text-zinc-500">
        No MITRE ATT&CK techniques mapped for this result
      </div>
    );
  }
  return (
    <div className="flex flex-wrap gap-2">
      {techniques.map((t) => (
        <div
          key={t.id}
          className="rounded-lg border border-zinc-700/60 bg-zinc-800/50 px-3 py-2"
          title={`${t.id} — ${t.name} (${t.tactic})`}
        >
          <div className="flex items-center gap-1.5">
            <Crosshair className="h-3 w-3 text-zinc-500" />
            <span className="font-mono text-xs font-bold text-red-400">{t.id}</span>
            <span className="text-xs text-zinc-200">{t.name}</span>
          </div>
          <div className={`mt-0.5 text-[10px] uppercase tracking-wider ${TACTIC_COLOR[t.tactic] ?? 'text-zinc-500'}`}>
            {t.tactic}
          </div>
        </div>
      ))}
    </div>
  );
}
