import type { Severity } from '../../types';

export const SEVERITY_STYLES: Record<Severity, { bg: string; text: string; ring: string; label: string }> = {
  safe: { bg: 'bg-emerald-500/15', text: 'text-emerald-400', ring: 'ring-emerald-500/40', label: 'SAFE' },
  low: { bg: 'bg-yellow-500/15', text: 'text-yellow-500', ring: 'ring-yellow-500/40', label: 'LOW' },
  medium: { bg: 'bg-amber-500/15', text: 'text-amber-500', ring: 'ring-amber-500/40', label: 'MEDIUM' },
  high: { bg: 'bg-orange-500/15', text: 'text-orange-500', ring: 'ring-orange-500/40', label: 'HIGH' },
  critical: { bg: 'bg-red-500/15', text: 'text-red-500', ring: 'ring-red-500/40', label: 'CRITICAL' },
};

export default function SeverityBadge({ severity }: { severity: Severity }) {
  const s = SEVERITY_STYLES[severity];
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-[11px] font-bold uppercase tracking-wider ring-1 ${s.bg} ${s.text} ${s.ring}`}
    >
      {s.label}
    </span>
  );
}
