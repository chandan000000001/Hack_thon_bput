import { create } from 'zustand';
import { supabase } from '../lib/supabaseClient';
import * as mockApi from '../services/mockApi';
import type { User } from '../types';

// Mock mode stays fully available behind VITE_USE_MOCK so the demo keeps
// working without a Supabase project or backend. Mock users are admins so
// every feature remains testable.
const USE_MOCK = import.meta.env.VITE_USE_MOCK !== 'false';
const MOCK_STORAGE_KEY = 'cyberguard_auth';

export type Role = 'viewer' | 'analyst' | 'admin';
export type Permission = 'analyze' | 'mutate' | 'admin';

const ROLE_LEVELS: Record<Role, number> = { viewer: 1, analyst: 2, admin: 3 };
const PERMISSION_MIN_ROLE: Record<Permission, Role> = {
  analyze: 'analyst',
  mutate: 'analyst',
  admin: 'admin',
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
  login: (email: string, password: string) => Promise<void>;
  signUp: (fullName: string, email: string, password: string) => Promise<{ confirmationPending: boolean }>;
  requestPasswordReset: (email: string) => Promise<void>;
  completePasswordReset: (newPassword: string) => Promise<void>;
  logout: () => Promise<void>;
  hydrate: () => Promise<void>;
  getToken: () => string | null;
  setAccessToken: (token: string | null) => void;
  can: (permission: Permission) => boolean;
}

function toUser(supabaseUser: { id: string; email?: string | null }): User {
  const email = supabaseUser.email ?? '';
  return {
    id: supabaseUser.id,
    name: email.split('@')[0] || 'SOC Analyst',
    email,
    role: 'viewer',
  };
}

function normalizeRole(value: unknown): Role {
  return value === 'analyst' || value === 'admin' ? value : 'viewer';
}

/**
 * Resolve role + full name from the backend (GET /auth/me). Uses a direct
 * fetch (not services/http.ts) to avoid a circular import with the token
 * getter. Falls back to viewer on any failure.
 */
async function fetchAuthMe(token: string | null): Promise<{ role: Role; fullName: string | null }> {
  if (!token) return { role: 'viewer', fullName: null };
  try {
    const response = await fetch(`${API_BASE_URL}/auth/me`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!response.ok) return { role: 'viewer', fullName: null };
    const body = (await response.json()) as { role?: string; full_name?: string | null };
    return {
      role: normalizeRole(body.role),
      fullName: body.full_name ?? null,
    };
  } catch {
    return { role: 'viewer', fullName: null };
  }
}

export const useAuthStore = create<AuthState>((set, get) => ({
  user: null,
  accessToken: null,
  isAuthenticated: false,
  hydrated: false,
  role: 'viewer',
  fullName: null,

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
      });
      return;
    }

    const { data, error } = await supabase.auth.signInWithPassword({ email, password });
    if (error || !data.session) {
      // Surface the Supabase message, e.g. "Invalid login credentials".
      throw new Error(error?.message ?? 'Login failed');
    }
    const { role, fullName } = await fetchAuthMe(data.session.access_token);
    set({
      user: toUser(data.session.user),
      accessToken: data.session.access_token,
      isAuthenticated: true,
      hydrated: true,
      role,
      fullName,
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

    const { role, fullName: profileName } = await fetchAuthMe(data.session.access_token);
    set({
      user: toUser(data.session.user),
      accessToken: data.session.access_token,
      isAuthenticated: true,
      hydrated: true,
      role,
      fullName: profileName ?? fullName,
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
        const { role, fullName } = await fetchAuthMe(session.access_token);
        set({
          user: toUser(session.user),
          accessToken: session.access_token,
          isAuthenticated: true,
          role,
          fullName,
        });
      }
    } finally {
      set({ hydrated: true });
    }
  },

  getToken: () => get().accessToken,

  setAccessToken: (token) => set({ accessToken: token }),

  can: (permission) => {
    const role = get().role;
    return ROLE_LEVELS[role] >= ROLE_LEVELS[PERMISSION_MIN_ROLE[permission]];
  },
}));
