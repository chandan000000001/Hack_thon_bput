import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Loader2, Lock, Mail, Shield } from 'lucide-react';
import { useAuthStore } from '../store/authStore';
import { isMockMode } from '../services/api';

export default function Login() {
  const navigate = useNavigate();
  const login = useAuthStore((s) => s.login);
  const [email, setEmail] = useState('admin@cyberguard.local');
  const [password, setPassword] = useState('demo1234');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await login(email, password);
      navigate('/dashboard', { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="cyber-grid flex min-h-screen items-center justify-center bg-slate-950 px-4">
      <div className="pointer-events-none fixed left-1/2 top-1/2 h-96 w-96 -translate-x-1/2 -translate-y-1/2 rounded-full bg-cyan-500/5 blur-3xl" />
      <div className="w-full max-w-md">
        <div className="mb-8 flex flex-col items-center">
          <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-cyan-500/10 ring-1 ring-cyan-500/40">
            <Shield className="h-7 w-7 text-cyan-400" />
          </div>
          <h1 className="mt-4 font-mono text-2xl font-bold tracking-[0.2em] text-cyan-400">CYBERGUARD</h1>
          <p className="mt-1.5 text-center text-xs text-slate-500">
            AI Powered Cyber Threat, Phishing & Digital Impersonation Detection and Response System
          </p>
        </div>

        <div className="rounded-2xl border border-slate-700/50 bg-slate-900/80 p-8 shadow-2xl backdrop-blur">
          {isMockMode() && (
            <div className="mb-5 text-center">
              <span className="rounded-md bg-cyan-500/15 px-2.5 py-1 font-mono text-[11px] font-bold tracking-wider text-cyan-400 ring-1 ring-cyan-500/50">
                MOCK MODE
              </span>
            </div>
          )}
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="mb-1.5 block text-xs font-medium uppercase tracking-wider text-slate-400">Email</label>
              <div className="relative">
                <Mail className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" />
                <input
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="w-full rounded-lg border border-slate-700/60 bg-slate-800/60 py-2.5 pl-10 pr-3 text-sm text-slate-100 placeholder-slate-500 outline-none focus:border-cyan-500/60"
                  placeholder="you@company.com"
                />
              </div>
            </div>
            <div>
              <label className="mb-1.5 block text-xs font-medium uppercase tracking-wider text-slate-400">Password</label>
              <div className="relative">
                <Lock className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" />
                <input
                  type="password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full rounded-lg border border-slate-700/60 bg-slate-800/60 py-2.5 pl-10 pr-3 text-sm text-slate-100 placeholder-slate-500 outline-none focus:border-cyan-500/60"
                  placeholder="••••••••"
                />
              </div>
            </div>

            {error && (
              <div className="rounded-lg border border-red-500/40 bg-red-500/10 px-3.5 py-2.5 text-xs text-red-400">
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              className="flex w-full items-center justify-center gap-2 rounded-lg bg-cyan-500 py-2.5 text-sm font-bold text-slate-950 hover:bg-cyan-400 disabled:opacity-60"
            >
              {loading && <Loader2 className="h-4 w-4 animate-spin" />}
              {loading ? 'Authenticating...' : 'Sign In'}
            </button>
          </form>

          <div className="mt-5 rounded-lg border border-slate-700/50 bg-slate-800/40 px-3.5 py-2.5 text-center">
            <p className="font-mono text-[11px] text-slate-400">
              Use your Supabase account (e.g. <span className="text-cyan-400">admin@cyberguard.local</span>)
            </p>
          </div>
        </div>

        <p className="mt-6 text-center text-[11px] text-slate-600">
          Simulated SOC environment — all data is mock and analysis is heuristic. No real threats are processed.
        </p>
      </div>
    </div>
  );
}
