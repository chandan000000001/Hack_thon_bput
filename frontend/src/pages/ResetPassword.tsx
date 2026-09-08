import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { ArrowLeft, Loader2, Lock, Shield } from 'lucide-react';
import { useAuthStore } from '../store/authStore';
import { useUiStore } from '../store/uiStore';

export default function ResetPassword() {
  const navigate = useNavigate();
  const addToast = useUiStore((s) => s.addToast);
  const completePasswordReset = useAuthStore((s) => s.completePasswordReset);
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (password.length < 8) {
      setError('Password must be at least 8 characters');
      return;
    }
    if (password !== confirmPassword) {
      setError('Passwords do not match');
      return;
    }
    setLoading(true);
    try {
      await completePasswordReset(password);
      setSuccess(true);
      addToast('Password updated. Please sign in with your new password.', 'safe');
      setTimeout(() => navigate('/login', { replace: true }), 1800);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not reset password. The link may have expired.');
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
          <p className="mt-1.5 text-center text-xs text-slate-500">Set a new password for your account</p>
        </div>

        <div className="rounded-2xl border border-slate-700/50 bg-slate-900/80 p-8 shadow-2xl backdrop-blur">
          <Link
            to="/login"
            className="mb-4 inline-flex items-center gap-1.5 text-xs text-cyan-400 hover:text-cyan-300"
          >
            <ArrowLeft className="h-3.5 w-3.5" /> Back to Sign In
          </Link>

          {success ? (
            <div className="rounded-lg border border-emerald-500/40 bg-emerald-500/10 px-3.5 py-2.5 text-xs text-emerald-400">
              Password updated successfully. Redirecting you to the sign-in page...
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label className="mb-1.5 block text-xs font-medium uppercase tracking-wider text-slate-400">New Password</label>
                <div className="relative">
                  <Lock className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" />
                  <input
                    type="password"
                    required
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    className="w-full rounded-lg border border-slate-700/60 bg-slate-800/60 py-2.5 pl-10 pr-3 text-sm text-slate-100 placeholder-slate-500 outline-none focus:border-cyan-500/60"
                    placeholder="Minimum 8 characters"
                  />
                </div>
              </div>
              <div>
                <label className="mb-1.5 block text-xs font-medium uppercase tracking-wider text-slate-400">Confirm New Password</label>
                <div className="relative">
                  <Lock className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" />
                  <input
                    type="password"
                    required
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
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
                {loading ? 'Updating...' : 'Update Password'}
              </button>
            </form>
          )}
        </div>
      </div>
    </div>
  );
}
