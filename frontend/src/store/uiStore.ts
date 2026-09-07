import { create } from 'zustand';
import type { Severity } from '../types';

export interface ToastItem {
  id: string;
  message: string;
  severity: Severity;
  timestamp: number;
}

interface UiState {
  sidebarCollapsed: boolean;
  liveSimulation: boolean;
  assistantOpen: boolean;
  toasts: ToastItem[];
  toggleSidebar: () => void;
  toggleLiveSimulation: () => void;
  setAssistantOpen: (open: boolean) => void;
  addToast: (message: string, severity?: Severity) => void;
  removeToast: (id: string) => void;
}

let toastCounter = 0;

export const useUiStore = create<UiState>((set) => ({
  sidebarCollapsed: false,
  liveSimulation: false,
  assistantOpen: false,
  toasts: [],

  toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),

  toggleLiveSimulation: () => set((s) => ({ liveSimulation: !s.liveSimulation })),

  setAssistantOpen: (open) => set({ assistantOpen: open }),

  addToast: (message, severity = 'medium') => {
    toastCounter += 1;
    const id = `toast-${toastCounter}`;
    set((s) => ({ toasts: [...s.toasts, { id, message, severity, timestamp: Date.now() }] }));
  },

  removeToast: (id) => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),
}));
