const STATUS_STYLES: Record<string, string> = {
  open: 'bg-red-500/15 text-red-400 ring-red-500/40',
  investigating: 'bg-amber-500/15 text-amber-500 ring-amber-500/40',
  contained: 'bg-cyan-500/15 text-cyan-400 ring-cyan-500/40',
  closed: 'bg-emerald-500/15 text-emerald-400 ring-emerald-500/40',
  received: 'bg-slate-600/30 text-slate-300 ring-slate-500/40',
  analyzing: 'bg-amber-500/15 text-amber-500 ring-amber-500/40',
  completed: 'bg-emerald-500/15 text-emerald-400 ring-emerald-500/40',
  failed: 'bg-red-500/15 text-red-400 ring-red-500/40',
  new: 'bg-cyan-500/15 text-cyan-400 ring-cyan-500/40',
  acknowledged: 'bg-amber-500/15 text-amber-500 ring-amber-500/40',
  resolved: 'bg-emerald-500/15 text-emerald-400 ring-emerald-500/40',
  dismissed: 'bg-slate-600/30 text-slate-400 ring-slate-500/40',
  pending: 'bg-amber-500/15 text-amber-500 ring-amber-500/40',
  approved: 'bg-cyan-500/15 text-cyan-400 ring-cyan-500/40',
  executed: 'bg-emerald-500/15 text-emerald-400 ring-emerald-500/40',
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
