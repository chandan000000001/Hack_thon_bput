import { CheckCircle2, ClipboardCheck, ShieldCheck } from 'lucide-react';
import { useState } from 'react';
import type { RecommendedAction } from '../../types';

const AUTOMATION_STYLE: Record<RecommendedAction['automationLevel'], string> = {
  automatic: 'bg-emerald-500/15 text-emerald-400 ring-emerald-500/40',
  'semi-automatic': 'bg-amber-500/15 text-amber-500 ring-amber-500/40',
  manual: 'bg-slate-600/30 text-slate-300 ring-slate-500/40',
};

const PRIORITY_STYLE: Record<RecommendedAction['priority'], string> = {
  critical: 'bg-red-500/15 text-red-500 ring-red-500/40',
  high: 'bg-orange-500/15 text-orange-500 ring-orange-500/40',
  medium: 'bg-amber-500/15 text-amber-500 ring-amber-500/40',
  low: 'bg-slate-600/30 text-slate-400 ring-slate-500/40',
};

interface Props {
  actions: RecommendedAction[];
  onExecute: (actionId: string) => void;
}

export default function RecommendedActionsPanel({ actions, onExecute }: Props) {
  const [approvals, setApprovals] = useState<Record<string, boolean>>({});
  const [executed, setExecuted] = useState<Record<string, boolean>>({});

  if (actions.length === 0) {
    return (
      <div className="rounded-xl border border-emerald-500/30 bg-emerald-500/5 px-4 py-6 text-center text-sm text-emerald-400">
        No response actions required for this severity
      </div>
    );
  }

  const execute = (actionId: string) => {
    setExecuted((e) => ({ ...e, [actionId]: true }));
    onExecute(actionId);
  };

  return (
    <div className="space-y-2.5">
      {actions.map((action) => {
        const isExecuted = executed[action.id] || action.executed;
        return (
          <div
            key={action.id}
            className={`rounded-xl border p-3.5 transition-colors ${
              isExecuted
                ? 'border-emerald-500/40 bg-emerald-500/5'
                : 'border-slate-700/50 bg-slate-800/40'
            }`}
          >
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-sm font-semibold text-slate-100">{action.action}</span>
              <span className={`rounded px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide ring-1 ${AUTOMATION_STYLE[action.automationLevel]}`}>
                {action.automationLevel}
              </span>
              <span className={`rounded px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide ring-1 ${PRIORITY_STYLE[action.priority]}`}>
                {action.priority}
              </span>
            </div>
            <p className="mt-1 text-xs text-slate-400">{action.description}</p>

            {isExecuted ? (
              <div className="mt-2.5 flex items-center gap-1.5 text-xs font-medium text-emerald-400">
                <CheckCircle2 className="h-3.5 w-3.5" />
                Executed (simulated){action.executedAt ? ` at ${new Date(action.executedAt).toLocaleTimeString()}` : ''}
              </div>
            ) : (
              <div className="mt-2.5 flex items-center gap-3">
                {action.requiresApproval && (
                  <label className="flex cursor-pointer items-center gap-1.5 text-xs text-slate-400">
                    <input
                      type="checkbox"
                      checked={approvals[action.id] ?? false}
                      onChange={(e) => setApprovals((a) => ({ ...a, [action.id]: e.target.checked }))}
                      className="h-3.5 w-3.5 rounded border-slate-600 bg-slate-700 accent-cyan-500"
                    />
                    <ClipboardCheck className="h-3.5 w-3.5 text-amber-500" />
                    I approve this action
                  </label>
                )}
                <button
                  onClick={() => execute(action.id)}
                  disabled={action.requiresApproval && !(approvals[action.id] ?? false)}
                  className="flex items-center gap-1.5 rounded-lg bg-cyan-500/15 px-3 py-1.5 text-xs font-semibold text-cyan-300 ring-1 ring-cyan-500/40 hover:bg-cyan-500/25 disabled:cursor-not-allowed disabled:opacity-40"
                >
                  <ShieldCheck className="h-3.5 w-3.5" />
                  Apply (Simulated)
                </button>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
