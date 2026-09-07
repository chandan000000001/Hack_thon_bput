import { CheckCircle2, Info, ShieldAlert, X, XCircle } from 'lucide-react';
import type { Severity } from '../../types';

const SEVERITY_VISUAL: Record<Severity, { icon: typeof Info; color: string; ring: string }> = {
  safe: { icon: CheckCircle2, color: 'text-emerald-400', ring: 'ring-emerald-500/40' },
  low: { icon: Info, color: 'text-yellow-500', ring: 'ring-yellow-500/40' },
  medium: { icon: Info, color: 'text-amber-500', ring: 'ring-amber-500/40' },
  high: { icon: ShieldAlert, color: 'text-orange-500', ring: 'ring-orange-500/40' },
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
      className={`toast-enter pointer-events-auto flex items-start gap-2.5 rounded-xl border border-slate-700/60 bg-slate-900/95 px-3.5 py-3 shadow-xl ring-1 backdrop-blur ${ring}`}
    >
      <Icon className={`mt-0.5 h-4 w-4 shrink-0 ${color}`} />
      <p className="flex-1 text-xs leading-relaxed text-slate-200">{message}</p>
      <button onClick={onClose} className="shrink-0 text-slate-500 hover:text-slate-200">
        <X className="h-3.5 w-3.5" />
      </button>
    </div>
  );
}
