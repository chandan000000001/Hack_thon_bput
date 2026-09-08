import { useEffect, useRef, useState } from 'react';
import { useLocation } from 'react-router-dom';
import { ChevronDown, LogOut, Radio, Shield, User } from 'lucide-react';
import { useAuthStore } from '../../store/authStore';
import { useUiStore } from '../../store/uiStore';

const ROUTE_TITLES: [RegExp, string][] = [
  [/^\/dashboard/, 'Security Operations Center'],
  [/^\/phishing/, 'AI-Powered Phishing Detection'],
  [/^\/url-analysis/, 'Malicious URL & Website Detection'],
  [/^\/impersonation/, 'Digital Impersonation Detection'],
  [/^\/deepfake/, 'Deepfake & Manipulated Media Detection'],
  [/^\/account-takeover/, 'Credential Theft & Account Takeover'],
  [/^\/network-threats/, 'Network & API Threat Detection'],
  [/^\/alerts\/.+/, 'Alert Detail'],
  [/^\/alerts/, 'Security Alerts'],
  [/^\/incidents\/.+/, 'Incident Detail'],
  [/^\/incidents/, 'Incident Management'],
  [/^\/response-actions/, 'Response Actions'],
  [/^\/audit-logs/, 'Audit Logs'],
  [/^\/reports/, 'Reports & Export'],
  [/^\/settings/, 'Settings'],
];

export default function Topbar() {
  const location = useLocation();
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);
  const liveSimulation = useUiStore((s) => s.liveSimulation);
  const toggleLiveSimulation = useUiStore((s) => s.toggleLiveSimulation);
  const addToast = useUiStore((s) => s.addToast);
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  const title = ROUTE_TITLES.find(([re]) => re.test(location.pathname))?.[1] ?? 'CYBERGUARD';

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setMenuOpen(false);
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const handleToggleSimulation = () => {
    toggleLiveSimulation();
    const next = !liveSimulation;
    addToast(next ? 'Live alerts enabled' : 'Live alerts disabled', next ? 'low' : 'safe');
  };

  return (
    <header className="relative z-30 flex h-14 items-center justify-between border-b border-zinc-700/50 bg-zinc-900/80 px-5 backdrop-blur">
      <h1 className="text-base font-semibold text-zinc-100">{title}</h1>

      <div className="flex items-center gap-3">
        {/* MOCK MODE badge — always visible */}
        <span className="rounded-md border border-red-600 bg-transparent px-2.5 py-1 font-mono text-[11px] font-bold tracking-wider text-red-500">
          MOCK MODE
        </span>

        {/* Live alerts toggle (Supabase Realtime in real mode) */}
        <button
          onClick={handleToggleSimulation}
          className={`flex items-center gap-2 rounded-md px-2.5 py-1.5 text-xs font-medium ring-1 ${
            liveSimulation
              ? 'bg-zinc-300/10 text-zinc-200 ring-zinc-300/50'
              : 'bg-zinc-800/60 text-zinc-400 ring-zinc-700/50 hover:text-zinc-200'
          }`}
        >
          {liveSimulation && <Radio className="h-3.5 w-3.5 animate-pulse-dot text-zinc-200" />}
          <span>Live Alerts</span>
        </button>

        {/* User menu */}
        <div className="relative" ref={menuRef}>
          <button
            onClick={() => setMenuOpen((o) => !o)}
            className="flex items-center gap-2 rounded-md bg-zinc-800/60 px-2.5 py-1.5 text-xs text-zinc-300 ring-1 ring-zinc-700/50 hover:bg-zinc-800"
          >
            <span className="flex h-6 w-6 items-center justify-center rounded-full bg-red-500/20 text-red-300 ring-1 ring-red-500/40">
              <Shield className="h-3.5 w-3.5" />
            </span>
            <span className="hidden md:inline">{user?.name ?? 'Operator'}</span>
            <span
              className={`hidden rounded px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide ring-1 ${
                user?.role === 'admin'
                  ? 'bg-red-500/15 text-red-400 ring-red-500/40'
                  : user?.role === 'analyst'
                    ? 'bg-red-500/15 text-red-400 ring-red-500/40'
                    : 'bg-zinc-600/30 text-zinc-300 ring-zinc-500/40'
              }`}
            >
              {user?.role ?? 'viewer'}
            </span>
            <ChevronDown className="h-3.5 w-3.5 text-zinc-500" />
          </button>
          {menuOpen && (
            <div className="absolute right-0 top-full z-30 mt-1 w-52 rounded-lg border border-zinc-700/60 bg-zinc-900 p-1.5 shadow-xl">
              <div className="px-2.5 py-2">
                <div className="flex items-center gap-2 text-sm text-zinc-100">
                  <User className="h-3.5 w-3.5 text-zinc-500" />
                  {user?.name}
                </div>
                <div className="mt-0.5 truncate pl-5.5 font-mono text-[11px] text-zinc-500">{user?.email}</div>
                <div className="mt-1 pl-5.5 text-[10px] uppercase tracking-wider text-red-400">{user?.role}</div>
              </div>
              <div className="my-1 border-t border-zinc-700/50" />
              <button
                onClick={() => {
                  setMenuOpen(false);
                  logout();
                }}
                className="flex w-full items-center gap-2 rounded-md px-2.5 py-2 text-sm text-zinc-300 hover:bg-zinc-800 hover:text-red-400"
              >
                <LogOut className="h-3.5 w-3.5" />
                Logout
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
