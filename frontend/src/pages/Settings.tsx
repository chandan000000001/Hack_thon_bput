import { useState } from 'react';
import { Info, Lock, Server, Shield, User } from 'lucide-react';
import { useAuthStore } from '../store/authStore';
import PageHeader from '../components/common/PageHeader';
import { SEVERITY_COLORS } from '../theme';
import { getSeverityFromScore } from '../services/mockEngine';
import { getApiBaseUrl } from '../lib/apiConfig';

const BANDS: [number, number, string][] = [
  [0, 20, 'Benign activity; no action required. Monitor-only logging.'],
  [21, 40, 'Minor anomalies worth tracking; no immediate response.'],
  [41, 60, 'Suspicious patterns detected; investigate and correlate.'],
  [61, 80, 'Likely malicious activity; begin response playbook.'],
  [81, 100, 'Confirmed-style threat signature; immediate containment.'],
];

export default function Settings() {
  const user = useAuthStore((s) => s.user);
  const [mockMode] = useState(import.meta.env.VITE_USE_MOCK !== 'false');

  return (
    <div className="max-w-3xl space-y-5">
      <PageHeader title="Settings" description="Profile, environment and detection reference configuration." />

      {/* Profile */}
      <div className="rounded-xl border border-zinc-700/50 bg-zinc-800/60 p-5 backdrop-blur">
        <div className="mb-4 flex items-center gap-2">
          <User className="h-4 w-4 text-red-400" />
          <h3 className="text-sm font-semibold text-zinc-100">Profile</h3>
        </div>
        <div className="grid gap-3 sm:grid-cols-3">
          <div>
            <div className="text-[10px] uppercase tracking-wider text-zinc-500">Name</div>
            <div className="mt-0.5 text-sm text-zinc-200">{user?.name ?? '—'}</div>
          </div>
          <div>
            <div className="text-[10px] uppercase tracking-wider text-zinc-500">Email</div>
            <div className="mt-0.5 font-mono text-sm text-zinc-200">{user?.email ?? '—'}</div>
          </div>
          <div>
            <div className="text-[10px] uppercase tracking-wider text-zinc-500">Role</div>
            <div className="mt-0.5 text-sm uppercase tracking-wide text-red-400">{user?.role ?? '—'}</div>
          </div>
        </div>
      </div>

      {/* Mock mode */}
      <div className="rounded-xl border border-zinc-700/50 bg-zinc-800/60 p-5 backdrop-blur">
        <div className="mb-4 flex items-center gap-2">
          <Shield className="h-4 w-4 text-red-400" />
          <h3 className="text-sm font-semibold text-zinc-100">Mock Mode</h3>
        </div>
        <label className="flex items-center justify-between gap-4">
          <div>
            <div className="text-sm text-zinc-200">Use mock API backend</div>
            <p className="mt-0.5 text-xs text-zinc-500">Backend integration not yet configured</p>
          </div>
          <input type="checkbox" checked={mockMode} disabled className="h-5 w-5 accent-red-500" />
        </label>
        <div className="mt-4">
          <div className="mb-1.5 flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-zinc-500">
            <Server className="h-3 w-3" /> Backend URL
          </div>
          <input
            value={getApiBaseUrl()}
            disabled
            className="w-full rounded-lg border border-zinc-700/60 bg-zinc-900/80 px-3 py-2 font-mono text-sm text-zinc-400"
          />
          <p className="mt-1.5 flex items-center gap-1 text-[11px] text-zinc-500">
            <Lock className="h-3 w-3" /> Auto-resolves based on environment (localhost vs Cloudflare tunnel)
          </p>
        </div>
      </div>

      {/* Risk threshold reference */}
      <div className="rounded-xl border border-zinc-700/50 bg-zinc-800/60 p-5 backdrop-blur">
        <div className="mb-4 flex items-center gap-2">
          <Info className="h-4 w-4 text-red-400" />
          <h3 className="text-sm font-semibold text-zinc-100">Risk Threshold Reference</h3>
        </div>
        <p className="mb-4 text-xs leading-relaxed text-zinc-400">
          Severity ramp (monochrome theme): <span className="text-zinc-200">Safe #e4e4e7</span> ·{' '}
          <span className="text-zinc-400">Low #71717a</span> ·{' '}
          <span className="text-red-400">Medium #f87171</span> ·{' '}
          <span className="text-red-500">High #dc2626</span> ·{' '}
          <span className="text-red-500">Critical #ef4444</span> (pulsing ring).
        </p>
        <div className="overflow-hidden rounded-lg border border-zinc-700/50">
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="border-b border-zinc-700/50 bg-zinc-900/80 text-[11px] uppercase tracking-wider text-zinc-400">
                <th className="px-3 py-2">Severity</th>
                <th className="px-3 py-2">Score Range</th>
                <th className="px-3 py-2">Color</th>
                <th className="px-3 py-2">Description</th>
              </tr>
            </thead>
            <tbody>
              {BANDS.map(([min, max, desc]) => {
                const severity = getSeverityFromScore(min);
                return (
                  <tr key={severity} className="border-b border-zinc-800/60 last:border-0">
                    <td className="px-3 py-2.5 font-bold uppercase tracking-wide" style={{ color: SEVERITY_COLORS[severity] }}>
                      {severity}
                    </td>
                    <td className="px-3 py-2.5 font-mono text-zinc-300">
                      {min}–{max}
                    </td>
                    <td className="px-3 py-2.5">
                      <span className="inline-block h-3.5 w-8 rounded" style={{ backgroundColor: SEVERITY_COLORS[severity] }} />
                    </td>
                    <td className="px-3 py-2.5 text-zinc-400">{desc}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* About */}
      <div className="rounded-xl border border-zinc-700/50 bg-zinc-800/60 p-5 backdrop-blur">
        <div className="mb-3 flex items-center gap-2">
          <Shield className="h-4 w-4 text-red-400" />
          <h3 className="text-sm font-semibold text-zinc-100">About CYBERGUARD</h3>
        </div>
        <div className="space-y-1.5 text-xs text-zinc-400">
          <p>
            <span className="text-zinc-200">Version:</span> 1.0.0 (frontend prototype, mock mode)
          </p>
          <p>
            <span className="text-zinc-200">Tech stack:</span> Vite, React 18, TypeScript (strict), Tailwind CSS, react-router-dom v6, Recharts, lucide-react, Zustand
          </p>
          <p>
            <span className="text-zinc-200">Detection:</span> All threat analysis runs in a local heuristic engine (mockEngine.ts). Results are deterministic simulations and not trained-model verdicts.
          </p>
          <p>
            <span className="text-zinc-200">Data:</span> All alerts, incidents and logs are simulated. No real threat intelligence or personal data is used.
          </p>
        </div>
      </div>
    </div>
  );
}
