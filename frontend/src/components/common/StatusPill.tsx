/**
 * Monochrome status pills — strict black / white / red palette.
 * Active/problem states use red; informational states use light zinc;
 * terminal/positive states use white; inactive states use muted zinc.
 */
const STATUS_STYLES: Record<string, string> = {
  open: 'bg-red-500/15 text-red-400 ring-red-500/40',
  investigating: 'bg-red-400/15 text-red-400 ring-red-400/40',
  contained: 'bg-zinc-500/20 text-zinc-200 ring-zinc-500/40',
  closed: 'bg-white/10 text-white ring-white/30',
  received: 'bg-zinc-600/30 text-zinc-300 ring-zinc-500/40',
  analyzing: 'bg-red-400/15 text-red-400 ring-red-400/40',
  completed: 'bg-white/10 text-white ring-white/30',
  failed: 'bg-red-500/15 text-red-400 ring-red-500/40',
  new: 'bg-zinc-500/20 text-zinc-200 ring-zinc-500/40',
  acknowledged: 'bg-red-400/15 text-red-400 ring-red-400/40',
  resolved: 'bg-white/10 text-white ring-white/30',
  dismissed: 'bg-zinc-600/30 text-zinc-400 ring-zinc-500/40',
  pending: 'bg-red-400/15 text-red-400 ring-red-400/40',
  approved: 'bg-zinc-500/20 text-zinc-200 ring-zinc-500/40',
  executed: 'bg-white/10 text-white ring-white/30',
  rejected: 'bg-red-500/15 text-red-400 ring-red-500/40',
};

export default function StatusPill({ status }: { status: string }) {
  const style = STATUS_STYLES[status] ?? STATUS_STYLES.received;
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-[11px] font-semibold uppercase tracking-wide ring-1 ${style}`}
    >
      {status.replace(/_/g, ' ')}
    </span>
  );
}
