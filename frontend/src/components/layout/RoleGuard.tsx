import type { ReactNode } from 'react';
import { ShieldAlert } from 'lucide-react';
import { useAuthStore } from '../../store/authStore';
import type { Role } from '../../store/authStore';

interface Props {
  minimumRole: Role;
  children: ReactNode;
}

export default function RoleGuard({ minimumRole, children }: Props) {
  const role = useAuthStore((s) => s.role);
  const can = useAuthStore((s) => s.can);

  const allowed =
    minimumRole === 'admin' ? can('admin') : minimumRole === 'analyst' ? can('analyze') : true;

  if (allowed) {
    return <>{children}</>;
  }

  return (
    <div className="flex flex-col items-center rounded-xl border border-red-500/30 bg-red-500/5 py-14 text-center">
      <ShieldAlert className="h-10 w-10 text-red-400/70" />
      <p className="mt-3 text-sm font-semibold text-slate-100">
        Access denied: requires {minimumRole} role
      </p>
      <p className="mt-1 max-w-md text-xs leading-relaxed text-slate-500">
        Your account has the <span className="font-mono text-slate-300">{role}</span> role. Ask an
        administrator to elevate your access (Admin → User Management).
      </p>
    </div>
  );
}
