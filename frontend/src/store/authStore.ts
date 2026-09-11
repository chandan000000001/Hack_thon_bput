import { create } from 'zustand';
import { supabase } from '../lib/supabaseClient';
import * as mockApi from '../services/mockApi';
import type { User } from '../types';
import { useUiStore } from './uiStore';

// Mock mode stays fully available behind VITE_USE_MOCK so the demo keeps
// working without a Supabase project or backend. Mock users are admins so
// every feature remains testable.
const USE_MOCK = import.meta.env.VITE_USE_MOCK !== 'false';
const MOCK_STORAGE_KEY = 'cyberguard_auth';

export type Role = 'viewer' | 'analyst' | 'admin';

// Granular permission keys served by GET /auth/me (backend migration 0005:
// permissions + role_permissions). Access decisions call can(<key>).
export type PermissionKey = string;

// Legacy composite keys used by components outside the Phase C-2 file scope.
// They map onto granular keys so existing can('analyze')-style checks keep
// working with correct permission-matrix semantics.
const LEGACY_PERMISSION_ALIASES: Record<string, string[]> = {
  analyze: ['analysis.run', 'media.upload'],
  mutate: [
    'incident.create',
    'incident.update',
    'incident.escalate',
    'incident.close',
    'alert.acknowledge',
    'alert.resolve',
    'response.execute',
  ],
  admin: ['users.manage'],
};

// Same matrix as backend/db/migrations/0005_permissions.sql. Only used when
// the backend response carries no permissions list (old backend), so the UI
// degrades to the documented default matrix instead of locking everything.
const FALLBACK_ROLE_PERMISSIONS: Record<Role, string[]> = {
  viewer: ['dashboard.view', 'alerts.view', 'incidents.view', 'reports.view'],
  analyst: [
    'dashboard.view',
    'alerts.view',
    'incidents.view',
    'reports.view',
    'analysis.run',
    'media.upload',
    'incident.create',
    'incident.update',
    'incident.escalate',
    'incident.close',
    'alert.acknowledge',
    'alert.resolve',
    'response.execute',
    'audit.view',
  ],
  admin: [
    'dashboard.view',
    'alerts.view',
    'incidents.view',
    'reports.view',
    'analysis.run',
    'media.upload',
    'incident.create',
    'incident.update',
    'incident.escalate',
    'incident.close',
    'alert.acknowledge',
    'alert.resolve',
    'response.execute',
    'response.execute_destructive',
    'audit.view',
    'users.manage',
  ],
};

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1';

interface AuthState {
  user: User | null;
  accessToken: string | null;
  isAuthenticated: boolean;
  /** True once hydrate() has finished (session restored or absent). */
  hydrated: boolean;
  role: Role;
  fullName: string | null;
  /** Granular permission keys granted to the caller (GET /auth/me). */
  permissions: string[];
  login: (email: string, password: string) => Promise<void>;
  signUp: (fullName: string, email: string, password: string) => Promise<{ confirmationPending: boolean }>;
  requestPasswordReset: (email: string) => Promise<void>;
  completePasswordReset: (newPassword: string) => Promise<void>;
  logout: () => Promise<void>;
  hydrate: () => Promise<void>;
  getToken: () => string | null;
  setAccessToken: (token: string | null) => void;
  can: (permission: PermissionKey) => boolean;
}

function toUser(supabaseUser: { id: string; email?: string | null }, role: Role = 'viewer'): User {
  const email = supabaseUser.email ?? '';
  return {
    id: supabaseUser.id,
    name: email.split('@')[0] || 'SOC Analyst',
    email,
    role,
  };
}

function normalizeRole(value: unknown): Role {
  return value === 'analyst' || value === 'admin' ? value : 'viewer';
}

function normalizePermissions(value: unknown, role: Role): string[] {
  if (Array.isArray(value)) {
    const keys = value.filter((k): k is string => typeof k === 'string' && k.length > 0);
    if (keys.length > 0) return keys;
  }
  return FALLBACK_ROLE_PERMISSIONS[role];
}

/**
 * Resolve role + full name + permissions from the backend (GET /auth/me).
 * Uses a direct fetch (not services/http.ts) to avoid a circular import with
 * the token getter. Falls back to viewer with the documented default
 * permission matrix on any failure.
 */
async function fetchAuthMe(
  token: string | null
): Promise<{ role: Role; fullName: string | null; permissions: string[] }> {
  if (!token) return { role: 'viewer', fullName: null, permissions: FALLBACK_ROLE_PERMISSIONS.viewer };
  try {
    const response = await fetch(`${API_BASE_URL}/auth/me`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!response.ok) {
      console.error('Failed to fetch /auth/me:', response.status, response.statusText);
      useUiStore.getState().addToast('Role service unavailable - read-only mode', 'high');
      return { role: 'viewer', fullName: null, permissions: FALLBACK_ROLE_PERMISSIONS.viewer };
    }
    const body = (await response.json()) as {
      role?: string;
      full_name?: string | null;
      permissions?: unknown;
    };
    const role = normalizeRole(body.role);
    return {
      role,
      fullName: body.full_name ?? null,
      permissions: normalizePermissions(body.permissions, role),
    };
  } catch (err) {
    console.error('Failed to fetch /auth/me:', err);
    useUiStore.getState().addToast('Role service unavailable - read-only mode', 'high');
    return { role: 'viewer', fullName: null, permissions: FALLBACK_ROLE_PERMISSIONS.viewer };
  }
}

export const useAuthStore = create<AuthState>((set, get) => ({
  user: null,
  accessToken: null,
  isAuthenticated: false,
  hydrated: false,
  role: 'viewer',
  fullName: null,
  permissions: [],

  login: async (email, password) => {
    if (USE_MOCK) {
      const { user, token } = await mockApi.mockLogin(email, password);
      localStorage.setItem(MOCK_STORAGE_KEY, JSON.stringify({ user, token }));
      set({
        user,
        accessToken: token,
        isAuthenticated: true,
        hydrated: true,
        role: 'admin',
        fullName: user.name,
        permissions: FALLBACK_ROLE_PERMISSIONS.admin,
      });
      return;
    }

    const { data, error } = await supabase.auth.signInWithPassword({ email, password });
    if (error || !data.session) {
      // Surface the Supabase message, e.g. "Invalid login credentials".
      throw new Error(error?.message ?? 'Login failed');
    }
    const { role, fullName, permissions } = await fetchAuthMe(data.session.access_token);
    set({
      user: toUser(data.session.user, role),
      accessToken: data.session.access_token,
      isAuthenticated: true,
      hydrated: true,
      role,
      fullName,
      permissions,
    });
  },

  signUp: async (fullName, email, password) => {
    if (USE_MOCK) {
      const mockUser: User = {
        id: `USR-SIGNUP-${Date.now()}`,
        name: fullName || email.split('@')[0],
        email,
        role: 'admin',
      };
      const token = `mock-jwt-${Date.now()}`;
      localStorage.setItem(MOCK_STORAGE_KEY, JSON.stringify({ user: mockUser, token }));
      set({
        user: mockUser,
        accessToken: token,
        isAuthenticated: true,
        hydrated: true,
        role: 'admin',
        fullName: mockUser.name,
        permissions: FALLBACK_ROLE_PERMISSIONS.admin,
      });
      return { confirmationPending: false };
    }

    const { data, error } = await supabase.auth.signUp({
      email,
      password,
      options: { data: { full_name: fullName } },
    });
    if (error) throw new Error(error.message);

    if (!data.session) {
      // Email confirmation is enabled: the user must confirm before signing in.
      return { confirmationPending: true };
    }

    const { role, fullName: profileName, permissions } = await fetchAuthMe(
      data.session.access_token
    );
    set({
      user: toUser(data.session.user, role),
      accessToken: data.session.access_token,
      isAuthenticated: true,
      hydrated: true,
      role,
      fullName: profileName ?? fullName,
      permissions,
    });
    return { confirmationPending: false };
  },

  requestPasswordReset: async (email) => {
    if (USE_MOCK) {
      await new Promise((resolve) => setTimeout(resolve, 600));
      return;
    }
    const { error } = await supabase.auth.resetPasswordForEmail(email, {
      redirectTo: `${window.location.origin}/reset-password`,
    });
    if (error) throw new Error(error.message);
  },

  completePasswordReset: async (newPassword) => {
    if (USE_MOCK) {
      await new Promise((resolve) => setTimeout(resolve, 600));
      return;
    }
    const { error } = await supabase.auth.updateUser({ password: newPassword });
    if (error) throw new Error(error.message);
  },

  logout: async () => {
    if (!USE_MOCK) {
      await supabase.auth.signOut().catch(() => undefined);
    }
    localStorage.removeItem(MOCK_STORAGE_KEY);
    set({
      user: null,
      accessToken: null,
      isAuthenticated: false,
      role: 'viewer',
      fullName: null,
      permissions: [],
    });
  },

  hydrate: async () => {
    if (USE_MOCK) {
      try {
        const raw = localStorage.getItem(MOCK_STORAGE_KEY);
        if (raw) {
          const { user, token } = JSON.parse(raw) as { user: User; token: string };
          if (user && token) {
            set({
              user,
              accessToken: token,
              isAuthenticated: true,
              role: user.role ?? 'admin',
              fullName: user.name,
              permissions: FALLBACK_ROLE_PERMISSIONS[user.role ?? 'admin'],
            });
          }
        }
      } catch {
        localStorage.removeItem(MOCK_STORAGE_KEY);
      }
      set({ hydrated: true });
      return;
    }

    try {
      const { data } = await supabase.auth.getSession();
      const session = data.session;
      if (session) {
        const { role, fullName, permissions } = await fetchAuthMe(session.access_token);
        set({
          user: toUser(session.user, role),
          accessToken: session.access_token,
          isAuthenticated: true,
          role,
          fullName,
          permissions,
        });
      }
    } finally {
      set({ hydrated: true });
    }
  },

  getToken: () => get().accessToken,

  setAccessToken: (token) => set({ accessToken: token }),

  // Phase C-2: permission-matrix check. In mock mode every permission is
  // granted so the self-contained demo stays fully functional. Legacy
  // composite keys ('analyze' | 'mutate' | 'admin') resolve through aliases
  // onto granular permission keys.
  can: (permission) => {
    if (USE_MOCK) return true;
    const { permissions } = get();
    const aliases = LEGACY_PERMISSION_ALIASES[permission];
    if (aliases) return aliases.some((key) => permissions.includes(key));
    return permissions.includes(permission);
  },
}));
