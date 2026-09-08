import { CheckCircle2, Info, ShieldAlert, X, XCircle } from 'lucide-react';
import type { Severity } from '../../types';

const SEVERITY_VISUAL: Record<Severity, { icon: typeof Info; color: string; ring: string }> = {
  safe: { icon: CheckCircle2, color: 'text-zinc-200', ring: 'ring-zinc-500/40' },
  low: { icon: Info, color: 'text-zinc-400', ring: 'ring-zinc-500/40' },
  medium: { icon: Info, color: 'text-red-400', ring: 'ring-red-400/40' },
  high: { icon: ShieldAlert, color: 'text-red-500', ring: 'ring-red-600/40' },
  critical: { icon: XCircle, color: 'text-red-500', ring: 'ring-red-500/40' },
};

interface Props {
  message: string;
  severity: Severity;
  onClose: () => void;
}

export default function Toast({ message, severity, onClose }: Props) {
  const { icon: Icon, color, ring } = SEVERITY_VISUAL[severity];
  return (
    <div
      className={`toast-enter pointer-events-auto flex items-start gap-2.5 rounded-xl border border-zinc-700/60 bg-zinc-900/95 px-3.5 py-3 shadow-xl ring-1 backdrop-blur ${ring}`}
    >
      <Icon className={`mt-0.5 h-4 w-4 shrink-0 ${color}`} />
      <p className="flex-1 text-xs leading-relaxed text-zinc-200">{message}</p>
      <button onClick={onClose} className="shrink-0 text-zinc-500 hover:text-zinc-200">
        <X className="h-3.5 w-3.5" />
      </button>
    </div>
  );
}
