import type { ReactNode } from 'react';

export default function ChartCard({ title, children, subtitle }: { title: string; children: ReactNode; subtitle?: string }) {
  return (
    <div className="rounded-xl border border-slate-700/50 bg-slate-800/60 p-4 backdrop-blur">
      <div className="mb-3 flex items-baseline justify-between">
        <h3 className="text-sm font-semibold text-slate-100">{title}</h3>
        {subtitle && <span className="text-[11px] text-slate-500">{subtitle}</span>}
      </div>
      {children}
    </div>
  );
}
