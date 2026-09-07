import type { LucideIcon } from 'lucide-react';

interface Props {
  icon: LucideIcon;
  title: string;
  description?: string;
}

export default function EmptyState({ icon: Icon, title, description }: Props) {
  return (
    <div className="flex flex-col items-center justify-center rounded-xl border border-slate-700/50 bg-slate-800/30 px-6 py-12 text-center">
      <div className="flex h-12 w-12 items-center justify-center rounded-full bg-slate-800 ring-1 ring-slate-700">
        <Icon className="h-5 w-5 text-slate-500" />
      </div>
      <h3 className="mt-3 text-sm font-semibold text-slate-300">{title}</h3>
      {description && <p className="mt-1 max-w-sm text-xs text-slate-500">{description}</p>}
    </div>
  );
}
