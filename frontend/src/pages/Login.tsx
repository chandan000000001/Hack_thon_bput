import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { KeyRound, Loader2, Lock, Mail, Shield, User } from 'lucide-react';
import { useAuthStore } from '../store/authStore';
import { isMockMode } from '../services/api';

type Mode = 'signin' | 'signup' | 'forgot';

export default function Login() {
  const navigate = useNavigate();
  const login = useAuthStore((s) => s.login);
  const signUp = useAuthStore((s) => s.signUp);
  const requestPasswordReset = useAuthStore((s) => s.requestPasswordReset);
  const [mode, setMode] = useState<Mode>('signin');
  const [email, setEmail] = useState('admin@cyberguard.local');
  const [password, setPassword] = useState('');
  const [fullName, setFullName] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const resetMessages = () => {
    setError(null);
    setNotice(null);
  };

  const handleSignIn = async () => {
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

  const handleSignUp = async () => {
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
      const { confirmationPending } = await signUp(fullName.trim(), email, password);
      if (confirmationPending) {
        resetMessages();
        setNotice('Check your email to confirm your account, then sign in.');
      } else {
        navigate('/dashboard', { replace: true });
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Sign up failed');
    } finally {
      setLoading(false);
    }
  };

  const handleForgot = async () => {
    setLoading(true);
    try {
      await requestPasswordReset(email);
      resetMessages();
      setNotice('Reset link sent to your email.');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not send reset link');
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    resetMessages();
    if (mode === 'signin') return handleSignIn();
    if (mode === 'signup') return handleSignUp();
    return handleForgot();
  };

  const submitLabel =
    mode === 'signin' ? 'Sign In' : mode === 'signup' ? 'Create Account' : 'Send Reset Link';

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

          {/* Mode tabs */}
          <div className="mb-5 grid grid-cols-3 gap-1 rounded-lg bg-slate-800/60 p-1">
            {(
              [
                ['signin', 'Sign In'],
                ['signup', 'Create Account'],
                ['forgot', 'Forgot Password'],
              ] as [Mode, string][]
            ).map(([value, label]) => (
              <button
                key={value}
                type="button"
                onClick={() => {
                  setMode(value);
                  resetMessages();
                }}
                className={`rounded-md px-2 py-1.5 text-[11px] font-semibold ${
                  mode === value
                    ? 'bg-cyan-500/15 text-cyan-300 ring-1 ring-cyan-500/40'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                {label}
              </button>
            ))}
          </div>

          {mode === 'forgot' && (
            <p className="mb-4 text-center text-xs text-slate-500">
              Enter your account email and we will send you a password reset link.
            </p>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            {mode === 'signup' && (
              <div>
                <label className="mb-1.5 block text-xs font-medium uppercase tracking-wider text-slate-400">Full Name</label>
                <div className="relative">
                  <User className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" />
                  <input
                    type="text"
                    required
                    value={fullName}
                    onChange={(e) => setFullName(e.target.value)}
                    className="w-full rounded-lg border border-slate-700/60 bg-slate-800/60 py-2.5 pl-10 pr-3 text-sm text-slate-100 placeholder-slate-500 outline-none focus:border-cyan-500/60"
                    placeholder="Jane Analyst"
                  />
                </div>
              </div>
            )}

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

            {mode !== 'forgot' && (
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
                    placeholder={mode === 'signup' ? 'Minimum 8 characters' : '••••••••'}
                  />
                </div>
              </div>
            )}

            {mode === 'signup' && (
              <div>
                <label className="mb-1.5 block text-xs font-medium uppercase tracking-wider text-slate-400">Confirm Password</label>
                <div className="relative">
                  <KeyRound className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" />
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
            )}

            {error && (
              <div className="rounded-lg border border-red-500/40 bg-red-500/10 px-3.5 py-2.5 text-xs text-red-400">
                {error}
              </div>
            )}
            {notice && (
              <div className="rounded-lg border border-emerald-500/40 bg-emerald-500/10 px-3.5 py-2.5 text-xs text-emerald-400">
                {notice}
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              className="flex w-full items-center justify-center gap-2 rounded-lg bg-cyan-500 py-2.5 text-sm font-bold text-slate-950 hover:bg-cyan-400 disabled:opacity-60"
            >
              {loading && <Loader2 className="h-4 w-4 animate-spin" />}
              {loading ? 'Please wait...' : submitLabel}
            </button>
          </form>

          <div className="mt-5 rounded-lg border border-slate-700/50 bg-slate-800/40 px-3.5 py-2.5 text-center">
            <p className="font-mono text-[11px] leading-relaxed text-slate-400">
              Seeded demo accounts: <span className="text-cyan-400">admin@</span>,{' '}
              <span className="text-cyan-400">analyst@</span>,{' '}
              <span className="text-cyan-400">viewer@cyberguard.local</span>
            </p>
          </div>
        </div>

        <p className="mt-6 text-center text-[11px] text-slate-600">
          Simulated SOC environment — all data is mock in mock mode and analysis is heuristic. No real threats are processed.
        </p>
      </div>
    </div>
  );
}
