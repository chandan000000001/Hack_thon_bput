import { NavLink } from 'react-router-dom';
import {
  Bell,
  Bot,
  ChevronsLeft,
  ChevronsRight,
  FileBarChart,
  KeyRound,
  LayoutDashboard,
  Link,
  Mail,
  Network,
  ScrollText,
  Settings,
  Shield,
  ShieldAlert,
  UserX,
  Users,
  Video,
  Zap,
} from 'lucide-react';
import { useUiStore } from '../../store/uiStore';
import { useAuthStore, type Role } from '../../store/authStore';

const NAV_ITEMS: { to: string; label: string; icon: typeof Bell; minRole?: Role }[] = [
  { to: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { to: '/phishing', label: 'Phishing Analysis', icon: Mail },
  { to: '/url-analysis', label: 'URL Analysis', icon: Link },
  { to: '/impersonation', label: 'Impersonation', icon: UserX },
  { to: '/deepfake', label: 'Deepfake Detection', icon: Video },
  { to: '/account-takeover', label: 'Account Takeover', icon: KeyRound },
  { to: '/network-threats', label: 'Network & API', icon: Network },
  { to: '/alerts', label: 'Alerts', icon: Bell },
  { to: '/incidents', label: 'Incidents', icon: ShieldAlert },
  { to: '/response-actions', label: 'Response Actions', icon: Zap },
  { to: '/audit-logs', label: 'Audit Logs', icon: ScrollText },
  { to: '/reports', label: 'Reports', icon: FileBarChart },
  { to: '/settings', label: 'Settings', icon: Settings },
  { to: '/admin/users', label: 'User Management', icon: Users, minRole: 'admin' },
];

export default function Sidebar() {
  const collapsed = useUiStore((s) => s.sidebarCollapsed);
  const setAssistantOpen = useUiStore((s) => s.setAssistantOpen);
  const can = useAuthStore((s) => s.can);

  // Role-aware navigation: admin-only entries are hidden for other roles.
  const visibleItems = NAV_ITEMS.filter((item) => !item.minRole || can('admin'));

  return (
    <aside
      className={`flex h-full flex-col border-r border-slate-700/50 bg-slate-900/95 backdrop-blur transition-all duration-200 ${
        collapsed ? 'w-16' : 'w-64'
      }`}
    >
      {/* Logo */}
      <div className="flex items-center gap-3 border-b border-slate-700/50 px-4 py-4">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-cyan-500/10 ring-1 ring-cyan-500/40">
          <Shield className="h-5 w-5 text-cyan-400" />
        </div>
        {!collapsed && (
          <div className="min-w-0">
            <div className="truncate font-mono text-sm font-bold tracking-widest text-cyan-400">CYBERGUARD</div>
            <div className="truncate text-[10px] uppercase tracking-wider text-slate-500">SOC Command Center</div>
          </div>
        )}
      </div>

      {/* Navigation */}
      <nav className="flex-1 overflow-y-auto py-3">
        {visibleItems.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            title={collapsed ? label : undefined}
            className={({ isActive }) =>
              `flex items-center gap-3 border-l-2 py-2 pr-3 text-sm ${
                collapsed ? 'justify-center pl-0' : 'pl-4'
              } ${
                isActive
                  ? 'border-cyan-500 bg-slate-800/50 text-cyan-400'
                  : 'border-transparent text-slate-400 hover:bg-slate-800/30 hover:text-slate-100'
              }`
            }
          >
            <Icon className="h-4 w-4 shrink-0" />
            {!collapsed && <span className="truncate">{label}</span>}
          </NavLink>
        ))}
      </nav>

      {/* Bottom section */}
      <div className="border-t border-slate-700/50 p-3 space-y-2">
        <button
          onClick={() => setAssistantOpen(true)}
          className={`flex w-full items-center gap-3 rounded-lg bg-cyan-500/10 px-3 py-2.5 text-sm font-medium text-cyan-300 ring-1 ring-cyan-500/40 hover:bg-cyan-500/20 ${
            collapsed ? 'justify-center' : ''
          }`}
        >
          <Bot className="h-4 w-4 shrink-0" />
          {!collapsed && <span>SOC Assistant</span>}
        </button>
        <button
          onClick={() => useUiStore.getState().toggleSidebar()}
          className={`flex w-full items-center gap-3 rounded-lg px-3 py-2 text-xs text-slate-500 hover:bg-slate-800/40 hover:text-slate-300 ${
            collapsed ? 'justify-center' : ''
          }`}
        >
          {collapsed ? <ChevronsRight className="h-4 w-4" /> : <ChevronsLeft className="h-4 w-4" />}
          {!collapsed && <span>Collapse</span>}
        </button>
      </div>
    </aside>
  );
}
