import { useState } from 'react';
import * as api from '../services/api';
import type { AdminUser } from '../services/api';
import { useApi } from '../hooks/useApi';
import { useUiStore } from '../store/uiStore';
import PageHeader from '../components/common/PageHeader';
import DataTable, { type Column } from '../components/common/DataTable';
import RoleGuard from '../components/layout/RoleGuard';
import { PanelSkeleton } from '../components/common/LoadingSkeleton';
import { formatTime } from '../constants';

const ROLES: AdminUser['role'][] = ['viewer', 'analyst', 'admin'];

const ROLE_STYLES: Record<string, string> = {
  admin: 'bg-red-500/15 text-red-400 ring-red-500/40',
  analyst: 'bg-red-500/15 text-red-400 ring-red-500/40',
  viewer: 'bg-zinc-600/30 text-zinc-300 ring-zinc-500/40',
};

export default function AdminUsers() {
  const addToast = useUiStore((s) => s.addToast);
  const { data: users, loading, refetch } = useApi(() => api.listAdminUsers(), []);
  const [savingId, setSavingId] = useState<string | null>(null);

  const changeRole = async (user: AdminUser, role: AdminUser['role']) => {
    if (role === user.role) return;
    setSavingId(user.id);
    try {
      await api.updateUserRole(user.id, role);
      addToast(`${user.email ?? user.id} is now ${role}`, 'safe');
      refetch();
    } catch (err) {
      addToast(err instanceof Error ? err.message : 'Failed to update role', 'high');
      refetch();
    } finally {
      setSavingId(null);
    }
  };

  const columns: Column<AdminUser>[] = [
    {
      key: 'email',
      header: 'Email',
      render: (u) => <span className="font-mono text-xs text-zinc-200">{u.email ?? '—'}</span>,
      sortValue: (u) => u.email ?? '',
    },
    {
      key: 'name',
      header: 'Full Name',
      render: (u) => <span className="text-sm text-zinc-200">{u.full_name ?? '—'}</span>,
      sortValue: (u) => u.full_name ?? '',
    },
    {
      key: 'role',
      header: 'Role',
      render: (u) => (
        <select
          value={u.role}
          disabled={savingId === u.id}
          onChange={(e) => changeRole(u, e.target.value as AdminUser['role'])}
          className={`rounded-full bg-zinc-900/60 px-2.5 py-0.5 text-[11px] font-semibold uppercase tracking-wide ring-1 outline-none focus:ring-red-500/60 disabled:opacity-60 ${
            ROLE_STYLES[u.role] ?? 'bg-zinc-800 text-zinc-200 ring-zinc-600'
          }`}
        >
          {ROLES.map((role) => (
            <option key={role} value={role} className="bg-zinc-800 normal-case">
              {role}
            </option>
          ))}
        </select>
      ),
      sortValue: (u) => u.role,
    },
    {
      key: 'created',
      header: 'Created',
      render: (u) => (
        <span className="font-mono text-xs text-zinc-500">{formatTime(u.created_at ?? '')}</span>
      ),
      sortValue: (u) => u.created_at ?? '',
    },
  ];

  return (
    <RoleGuard minimumRole="admin">
      <div className="space-y-4">
        <PageHeader
          title="User Management"
          description="Assign viewer, analyst and admin roles. Role changes are audit-logged."
        />
        {loading ? (
          <PanelSkeleton height="h-64" />
        ) : (
          <DataTable
            columns={columns}
            data={users ?? []}
            rowKey={(u) => u.id}
            emptyMessage="No users found — run db/migrations/0003_roles_and_seed.sql after creating the demo users"
          />
        )}
        <p className="text-center text-[11px] text-zinc-600">
          New sign-ups start with the viewer role. Admins cannot change their own role (lockout prevention).
        </p>
      </div>
    </RoleGuard>
  );
}
