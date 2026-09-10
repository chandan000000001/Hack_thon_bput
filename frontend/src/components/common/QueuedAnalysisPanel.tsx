import { Loader2 } from 'lucide-react';

/**
 * Phase D-2 (item 8): pending state for analyses the backend queued on a
 * background worker (HTTP 202 / status 'analyzing'). The real result lands
 * via Supabase Realtime alert toasts or the next fetch.
 */
export default function QueuedAnalysisPanel() {
  return (
    <div className="flex h-full min-h-64 flex-col items-center justify-center rounded-xl border border-red-500/30 bg-red-500/5 p-8 text-center">
      <Loader2 className="h-8 w-8 animate-spin text-red-400" />
      <p className="mt-4 text-sm font-semibold text-zinc-100">Queued for background analysis</p>
      <p className="mt-2 max-w-md text-xs leading-relaxed text-zinc-500">
        The detection pipeline is running on a background worker. The alert will appear on the
        Dashboard and in Security Alerts (with a live toast) as soon as it completes.
      </p>
    </div>
  );
}
