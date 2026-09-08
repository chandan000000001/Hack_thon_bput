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
    <div className="cyber-grid flex min-h-screen items-center justify-center bg-zinc-950 px-4">
      <div className="pointer-events-none fixed left-1/2 top-1/2 h-96 w-96 -tranzinc-x-1/2 -tranzinc-y-1/2 rounded-full bg-red-500/5 blur-3xl" />
      <div className="w-full max-w-md">
        <div className="mb-8 flex flex-col items-center">
          <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-red-500/10 ring-1 ring-red-500/40">
            <Shield className="h-7 w-7 text-red-400" />
          </div>
          <h1 className="mt-4 font-mono text-2xl font-bold tracking-[0.2em] text-red-400">CYBERGUARD</h1>
          <p className="mt-1.5 text-center text-xs text-zinc-500">Set a new password for your account</p>
        </div>

        <div className="rounded-2xl border border-zinc-700/50 bg-zinc-900/80 p-8 shadow-2xl backdrop-blur">
          <Link
            to="/login"
            className="mb-4 inline-flex items-center gap-1.5 text-xs text-red-400 hover:text-red-300"
          >
            <ArrowLeft className="h-3.5 w-3.5" /> Back to Sign In
          </Link>

          {success ? (
            <div className="rounded-lg border border-zinc-300/40 bg-zinc-300/10 px-3.5 py-2.5 text-xs text-zinc-200">
              Password updated successfully. Redirecting you to the sign-in page...
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label className="mb-1.5 block text-xs font-medium uppercase tracking-wider text-zinc-400">New Password</label>
                <div className="relative">
                  <Lock className="absolute left-3 top-1/2 h-4 w-4 -tranzinc-y-1/2 text-zinc-500" />
                  <input
                    type="password"
                    required
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    className="w-full rounded-lg border border-zinc-700/60 bg-zinc-800/60 py-2.5 pl-10 pr-3 text-sm text-zinc-100 placeholder-zinc-500 outline-none focus:border-red-500/60"
                    placeholder="Minimum 8 characters"
                  />
                </div>
              </div>
              <div>
                <label className="mb-1.5 block text-xs font-medium uppercase tracking-wider text-zinc-400">Confirm New Password</label>
                <div className="relative">
                  <Lock className="absolute left-3 top-1/2 h-4 w-4 -tranzinc-y-1/2 text-zinc-500" />
                  <input
                    type="password"
                    required
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    className="w-full rounded-lg border border-zinc-700/60 bg-zinc-800/60 py-2.5 pl-10 pr-3 text-sm text-zinc-100 placeholder-zinc-500 outline-none focus:border-red-500/60"
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
                className="flex w-full items-center justify-center gap-2 rounded-lg bg-red-600 py-2.5 text-sm font-bold text-white hover:bg-red-500 disabled:opacity-60"
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
