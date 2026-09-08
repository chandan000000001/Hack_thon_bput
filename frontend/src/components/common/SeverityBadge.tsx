import type { Severity } from '../../types';

/**
 * Monochrome-red severity ramp (src/theme.ts):
 *   safe #e4e4e7 (black text) · low #71717a (white) · medium #f87171 (black)
 *   high #dc2626 (white) · critical #ef4444 (white + pulse ring)
 *
 * `solid`  — filled chip using the ramp swatch with black/white text
 * `text`   — soft on-dark text color for headings/labels
 * `bg`/`ring` — soft tinted pill variant
 * `dot`    — small status dot color
 */
export const SEVERITY_STYLES: Record<
  Severity,
  { bg: string; text: string; ring: string; solid: string; dot: string; label: string }
> = {
  safe: {
    bg: 'bg-zinc-200/15',
    text: 'text-zinc-200',
    ring: 'ring-zinc-200/40',
    solid: 'bg-zinc-200 text-zinc-950',
    dot: 'bg-zinc-200',
    label: 'SAFE',
  },
  low: {
    bg: 'bg-zinc-500/20',
    text: 'text-zinc-400',
    ring: 'ring-zinc-500/40',
    solid: 'bg-zinc-500 text-white',
    dot: 'bg-zinc-500',
    label: 'LOW',
  },
  medium: {
    bg: 'bg-red-400/15',
    text: 'text-red-400',
    ring: 'ring-red-400/40',
    solid: 'bg-red-400 text-zinc-950',
    dot: 'bg-red-400',
    label: 'MEDIUM',
  },
  high: {
    bg: 'bg-red-600/15',
    text: 'text-red-500',
    ring: 'ring-red-600/40',
    solid: 'bg-red-600 text-white',
    dot: 'bg-red-600',
    label: 'HIGH',
  },
  critical: {
    bg: 'bg-red-500/15',
    text: 'text-red-500',
    ring: 'ring-red-500/40',
    solid: 'bg-red-500 text-white severity-pulse',
    dot: 'bg-red-500',
    label: 'CRITICAL',
  },
};

export default function SeverityBadge({ severity }: { severity: Severity }) {
  const s = SEVERITY_STYLES[severity];
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-[11px] font-bold uppercase tracking-wider ring-1 ring-black/20 ${s.solid}`}
    >
      {s.label}
    </span>
  );
}
