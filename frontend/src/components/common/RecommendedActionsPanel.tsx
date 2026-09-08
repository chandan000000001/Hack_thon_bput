import { CheckCircle2, ClipboardCheck, ShieldCheck } from 'lucide-react';
import { useState } from 'react';
import type { RecommendedAction } from '../../types';

const AUTOMATION_STYLE: Record<RecommendedAction['automationLevel'], string> = {
  automatic: 'bg-zinc-300/15 text-zinc-200 ring-zinc-300/40',
  'semi-automatic': 'bg-red-400/15 text-red-400 ring-red-400/40',
  manual: 'bg-zinc-600/30 text-zinc-300 ring-zinc-500/40',
};

const PRIORITY_STYLE: Record<RecommendedAction['priority'], string> = {
  critical: 'bg-red-500/15 text-red-500 ring-red-500/40',
  high: 'bg-red-600/15 text-red-600 ring-red-600/40',
  medium: 'bg-red-400/15 text-red-400 ring-red-400/40',
  low: 'bg-zinc-600/30 text-zinc-400 ring-zinc-500/40',
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
      <div className="rounded-xl border border-zinc-300/30 bg-zinc-300/5 px-4 py-6 text-center text-sm text-zinc-200">
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
      {actions.map((action, index) => {
        // The backend can return the same recommended-action id twice for one
        // alert; a composite key keeps the React key list unique either way.
        const rowKey = `${action.id}-${index}`;
        const isExecuted = executed[action.id] || action.executed;
        return (
          <div
            key={rowKey}
            className={`rounded-xl border p-3.5 transition-colors ${
              isExecuted
                ? 'border-zinc-300/40 bg-zinc-300/5'
                : 'border-zinc-700/50 bg-zinc-800/40'
            }`}
          >
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-sm font-semibold text-zinc-100">{action.action}</span>
              <span className={`rounded px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide ring-1 ${AUTOMATION_STYLE[action.automationLevel]}`}>
                {action.automationLevel}
              </span>
              <span className={`rounded px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide ring-1 ${PRIORITY_STYLE[action.priority]}`}>
                {action.priority}
              </span>
            </div>
            <p className="mt-1 text-xs text-zinc-400">{action.description}</p>

            {isExecuted ? (
              <div className="mt-2.5 flex items-center gap-1.5 text-xs font-medium text-zinc-200">
                <CheckCircle2 className="h-3.5 w-3.5" />
                Executed (simulated){action.executedAt ? ` at ${new Date(action.executedAt).toLocaleTimeString()}` : ''}
              </div>
            ) : (
              <div className="mt-2.5 flex items-center gap-3">
                {action.requiresApproval && (
                  <label className="flex cursor-pointer items-center gap-1.5 text-xs text-zinc-400">
                    <input
                      type="checkbox"
                      checked={approvals[action.id] ?? false}
                      onChange={(e) => setApprovals((a) => ({ ...a, [action.id]: e.target.checked }))}
                      className="h-3.5 w-3.5 rounded border-zinc-600 bg-zinc-700 accent-red-500"
                    />
                    <ClipboardCheck className="h-3.5 w-3.5 text-red-400" />
                    I approve this action
                  </label>
                )}
                <button
                  onClick={() => execute(action.id)}
                  disabled={action.requiresApproval && !(approvals[action.id] ?? false)}
                  className="flex items-center gap-1.5 rounded-lg bg-red-500/15 px-3 py-1.5 text-xs font-semibold text-red-300 ring-1 ring-red-500/40 hover:bg-red-500/25 disabled:cursor-not-allowed disabled:opacity-40"
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
