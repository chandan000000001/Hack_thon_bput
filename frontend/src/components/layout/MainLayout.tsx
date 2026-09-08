import { useEffect } from 'react';
import { Outlet } from 'react-router-dom';
import Sidebar from './Sidebar';
import Topbar from './Topbar';
import Toast from '../common/Toast';
import SocAssistant from './SocAssistant';
import { useUiStore } from '../../store/uiStore';
import { useAuthStore } from '../../store/authStore';
import { generateSimulatedAlert } from '../../services/mockApi';
import { addAlert } from '../../services/api';

export default function MainLayout() {
  const toasts = useUiStore((s) => s.toasts);
  const removeToast = useUiStore((s) => s.removeToast);
  const assistantOpen = useUiStore((s) => s.assistantOpen);
  const setAssistantOpen = useUiStore((s) => s.setAssistantOpen);
  const liveSimulation = useUiStore((s) => s.liveSimulation);
  const user = useAuthStore((s) => s.user);

  // Toast auto-dismiss after 5 seconds
  useEffect(() => {
    if (toasts.length === 0) return;
    const timers = toasts.map((t) => setTimeout(() => removeToast(t.id), 5000));
    return () => timers.forEach(clearTimeout);
  }, [toasts, removeToast]);

  // Live simulation: generate a new alert every 20 seconds
  useEffect(() => {
    if (!liveSimulation) return;
    const interval = setInterval(() => {
      const alert = generateSimulatedAlert();
      addAlert(alert);
      useUiStore.getState().addToast(`New alert: ${alert.title}`, alert.severity);
    }, 20000);
    return () => clearInterval(interval);
  }, [liveSimulation]);

  return (
    <div className="flex h-screen overflow-hidden bg-zinc-950">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <Topbar />
        <main className="flex-1 overflow-y-auto p-5">
          <Outlet />
        </main>
      </div>

      {/* Toasts */}
      <div className="pointer-events-none fixed right-4 top-4 z-50 flex w-80 flex-col gap-2">
        {toasts.map((t) => (
          <Toast key={t.id} message={t.message} severity={t.severity} onClose={() => removeToast(t.id)} />
        ))}
      </div>

      {/* SOC Assistant slide-over */}
      {assistantOpen && <SocAssistant open={assistantOpen} userName={user?.name ?? 'Operator'} onClose={() => setAssistantOpen(false)} />}
    </div>
  );
}
