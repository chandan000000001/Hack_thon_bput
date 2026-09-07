import { useEffect, useRef } from 'react';
import { supabase } from '../lib/supabaseClient';
import { useUiStore } from '../store/uiStore';
import type { Severity } from '../types';

// Mock mode keeps the existing 20-second simulated generator in MainLayout;
// realtime subscriptions only run in real mode.
const USE_MOCK = import.meta.env.VITE_USE_MOCK !== 'false';

/**
 * Subscribe to live alert INSERTs on the `alerts` table while enabled.
 *
 * Real mode: opens the `cyberguard-alerts` Supabase Realtime channel
 * (postgres_changes INSERT on public.alerts), shows a toast per new alert
 * and fires the page-provided refresh callback.
 * Mock mode: no-op (the simulated generator already runs globally).
 */
export function useRealtimeAlerts(enabled: boolean, onRefresh?: () => void): void {
  const addToast = useUiStore((s) => s.addToast);
  const refreshRef = useRef(onRefresh);
  refreshRef.current = onRefresh;

  useEffect(() => {
    if (!enabled || USE_MOCK) return;

    const channel = supabase
      .channel('cyberguard-alerts')
      .on(
        'postgres_changes',
        { event: 'INSERT', schema: 'public', table: 'alerts' },
        (payload) => {
          const row = (payload.new ?? {}) as Record<string, unknown>;
          const title = typeof row.title === 'string' ? row.title : 'New alert';
          const severity = (typeof row.severity === 'string' ? row.severity : 'medium') as Severity;
          addToast(`New alert: ${title}`, severity);
          refreshRef.current?.();
        }
      )
      .subscribe();

    return () => {
      void supabase.removeChannel(channel);
    };
  }, [enabled, addToast]);
}
