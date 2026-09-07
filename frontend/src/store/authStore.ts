import { create } from 'zustand';
import { supabase } from '../lib/supabaseClient';
import * as mockApi from '../services/mockApi';
import type { User } from '../types';

// Mock mode stays fully available behind VITE_USE_MOCK so the demo keeps
// working without a Supabase project or backend.
const USE_MOCK = import.meta.env.VITE_USE_MOCK !== 'false';
const MOCK_STORAGE_KEY = 'cyberguard_auth';

interface AuthState {
  user: User | null;
  accessToken: string | null;
  isAuthenticated: boolean;
  /** True once hydrate() has finished (session restored or absent). */
  hydrated: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  hydrate: () => Promise<void>;
  getToken: () => string | null;
  setAccessToken: (token: string | null) => void;
}

function toUser(supabaseUser: {
  id: string;
  email?: string | null;
}): User {
  const email = supabaseUser.email ?? '';
  return {
    id: supabaseUser.id,
    name: email.split('@')[0] || 'SOC Analyst',
    email,
    role: 'analyst',
  };
}

export const useAuthStore = create<AuthState>((set, get) => ({
  user: null,
  accessToken: null,
  isAuthenticated: false,
  hydrated: false,

  login: async (email, password) => {
    if (USE_MOCK) {
      const { user, token } = await mockApi.mockLogin(email, password);
      localStorage.setItem(MOCK_STORAGE_KEY, JSON.stringify({ user, token }));
      set({ user, accessToken: token, isAuthenticated: true, hydrated: true });
      return;
    }

    const { data, error } = await supabase.auth.signInWithPassword({ email, password });
    if (error || !data.session) {
      // Surface the Supabase message, e.g. "Invalid login credentials".
      throw new Error(error?.message ?? 'Login failed');
    }
    set({
      user: toUser(data.session.user),
      accessToken: data.session.access_token,
      isAuthenticated: true,
      hydrated: true,
    });
  },

  logout: async () => {
    if (!USE_MOCK) {
      await supabase.auth.signOut().catch(() => undefined);
    }
    localStorage.removeItem(MOCK_STORAGE_KEY);
    set({ user: null, accessToken: null, isAuthenticated: false });
  },

  hydrate: async () => {
    if (USE_MOCK) {
      try {
        const raw = localStorage.getItem(MOCK_STORAGE_KEY);
        if (raw) {
          const { user, token } = JSON.parse(raw) as { user: User; token: string };
          if (user && token) {
            set({ user, accessToken: token, isAuthenticated: true });
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
        set({
          user: toUser(session.user),
          accessToken: session.access_token,
          isAuthenticated: true,
        });
      }
    } finally {
      set({ hydrated: true });
    }
  },

  getToken: () => get().accessToken,

  setAccessToken: (token) => set({ accessToken: token }),
}));
