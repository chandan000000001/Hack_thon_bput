import type { LucideIcon } from 'lucide-react';
import { ArrowDownRight, ArrowUpRight, Minus } from 'lucide-react';

interface Props {
  title: string;
  value: number;
  icon: LucideIcon;
  trend: 'up' | 'down' | 'neutral';
  trendValue: string;
  color: string;
}

const TREND_COLOR = {
  up: 'text-zinc-200',
  down: 'text-red-400',
  neutral: 'text-zinc-400',
};

export default function StatCard({ title, value, icon: Icon, trend, trendValue, color }: Props) {
  return (
    <div className="relative overflow-hidden rounded-xl border border-zinc-700/50 bg-zinc-800/60 p-4 backdrop-blur">
      <div
        className="pointer-events-none absolute -right-6 -top-6 h-20 w-20 rounded-full opacity-20 blur-2xl"
        style={{ backgroundColor: color }}
      />
      <div className="flex items-start justify-between">
        <div>
          <div className="text-xs font-medium uppercase tracking-wider text-zinc-400">{title}</div>
          <div className="mt-1.5 text-2xl font-bold text-zinc-100">{value.toLocaleString()}</div>
        </div>
        <div
          className="flex h-9 w-9 items-center justify-center rounded-lg"
          style={{ backgroundColor: `${color}1a`, color }}
        >
          <Icon className="h-4.5 w-4.5" style={{ width: 18, height: 18 }} />
        </div>
      </div>
      <div className={`mt-2 flex items-center gap-1 text-xs ${TREND_COLOR[trend]}`}>
        {trend === 'up' && <ArrowUpRight className="h-3 w-3" />}
        {trend === 'down' && <ArrowDownRight className="h-3 w-3" />}
        {trend === 'neutral' && <Minus className="h-3 w-3" />}
        <span>{trendValue}</span>
        <span className="text-zinc-500">vs last week</span>
      </div>
    </div>
  );
}
