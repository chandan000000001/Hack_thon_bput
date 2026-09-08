import type {
  Alert,
  AnalysisResult,
  AuditLog,
  DashboardSummary,
  Incident,
  IncidentStatus,
  ResponseActionCatalog,
  ResponseExecution,
  Severity,
  ThreatModule,
  User,
} from '../types';
import * as mockApi from './mockApi';
import { db, addAuditLog } from './mockData';
import { ApiError, apiFetch } from './http';
import {
  mapAlert,
  mapAnalysisResult,
  mapAuditLog,
  mapDashboardSummary,
  mapIncident,
  mapResponseCatalog,
  mapResponseExecution,
} from './mappers';
import { useAuthStore } from '../store/authStore';

// ---------------------------------------------------------------------------
// Service facade — the ONLY module pages import.
// USE_MOCK=true  -> delegate to the in-browser mock API (no behaviour change).
// USE_MOCK=false -> live Supabase Auth + real backend at VITE_API_BASE_URL.
// Raw log listing endpoints (login events, network flows, API logs) have no
// backend counterpart yet and still fall back to the mock layer with a
// console warning.
// ---------------------------------------------------------------------------

const USE_MOCK = import.meta.env.VITE_USE_MOCK !== 'false';

function notYetIntegrated<T>(functionName: string, mockCall: () => Promise<T>): Promise<T> {
  console.warn('[CYBERGUARD] endpoint not yet integrated, using mock:', functionName);
  return mockCall();
}

export async function login(email: string, password: string): Promise<{ user: User; token: string }> {
  if (USE_MOCK) return mockApi.mockLogin(email, password);
  // Real login is performed by the auth store via Supabase Auth.
  await useAuthStore.getState().login(email, password);
  const state = useAuthStore.getState();
  return { user: state.user as User, token: state.accessToken ?? '' };
}

export async function logout(): Promise<void> {
  if (USE_MOCK) return;
  await useAuthStore.getState().logout();
}

export async function getDashboardSummary(): Promise<DashboardSummary> {
  if (USE_MOCK) return mockApi.mockGetDashboardSummary();
  const row = await apiFetch('/dashboard/summary');
  return mapDashboardSummary(row);
}

export async function listAlerts(filters?: {
  severity?: Severity;
  module?: ThreatModule;
  status?: string;
  search?: string;
  limit?: number;
  offset?: number;
}): Promise<Alert[]> {
  if (USE_MOCK) return mockApi.mockListAlerts(filters);
  const params = new URLSearchParams();
  if (filters?.severity) params.set('severity', filters.severity);
  if (filters?.module) params.set('module', filters.module);
  if (filters?.status) params.set('status', filters.status);
  if (filters?.search) params.set('search', filters.search);
  if (filters?.limit !== undefined) params.set('limit', String(filters.limit));
  if (filters?.offset !== undefined) params.set('offset', String(filters.offset));
  const rows = await apiFetch(`/alerts?${params.toString()}`);
  return (Array.isArray(rows) ? rows : []).map(mapAlert);
}

export async function getAlert(id: string): Promise<Alert | null> {
  if (USE_MOCK) return mockApi.mockGetAlert(id);
  try {
    const row = await apiFetch(`/alerts/${id}`);
    return row ? mapAlert(row) : null;
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) return null;
    throw err;
  }
}

export async function updateAlertStatus(id: string, status: Alert['status']): Promise<Alert> {
  if (USE_MOCK) {
    const alert = db.alerts.find((a) => a.id === id);
    if (!alert) throw new Error(`Alert ${id} not found`);
    alert.status = status;
    addAuditLog({
      userId: 'USR-001',
      userName: 'admin@cyberguard.local',
      action: 'UPDATE_ALERT_STATUS',
      resource: id,
      details: `Alert status changed to ${status}`,
    });
    return alert;
  }
  const row = await apiFetch(`/alerts/${id}/status`, {
    method: 'PATCH',
    body: JSON.stringify({ status }),
  });
  return mapAlert(row);
}

// ---------------------------------------------------------------------------
// Analysis pipelines (Part 3-5 backend endpoints)
// ---------------------------------------------------------------------------

export async function analyzeEmail(sender: string, subject: string, body: string): Promise<AnalysisResult> {
  if (USE_MOCK) return mockApi.mockAnalyzeEmail(sender, subject, body);
  const row = await apiFetch('/analysis/email', {
    method: 'POST',
    body: JSON.stringify({ sender, subject, body }),
  });
  return mapAnalysisResult(row);
}

export async function analyzeUrl(url: string): Promise<AnalysisResult> {
  if (USE_MOCK) return mockApi.mockAnalyzeUrl(url);
  const row = await apiFetch('/analysis/url', { method: 'POST', body: JSON.stringify({ url }) });
  return mapAnalysisResult(row);
}

export async function analyzeImpersonation(message: string, claimedIdentity: string): Promise<AnalysisResult> {
  if (USE_MOCK) return mockApi.mockAnalyzeImpersonation(message, claimedIdentity);
  const row = await apiFetch('/analysis/impersonation', {
    method: 'POST',
    body: JSON.stringify({ message, claimed_identity: claimedIdentity }),
  });
  return mapAnalysisResult(row);
}

export async function analyzeMedia(file: File): Promise<AnalysisResult> {
  if (USE_MOCK) return mockApi.mockAnalyzeMedia({ name: file.name, size: file.size, type: file.type });
  // Multipart upload: no Content-Type header so the browser sets the boundary.
  const formData = new FormData();
  formData.append('file', file);
  const row = await apiFetch('/analysis/media', { method: 'POST', body: formData });
  return mapAnalysisResult(row);
}

export async function analyzeAuthLog(
  events: Array<{ user: string; ip: string; location: string; device: string; status: string; timestamp: string }>
): Promise<AnalysisResult> {
  if (USE_MOCK) return mockApi.mockAnalyzeAuthLog(events);
  const row = await apiFetch('/analysis/account-takeover', {
    method: 'POST',
    body: JSON.stringify({ events }),
  });
  return mapAnalysisResult(row);
}

export async function analyzeNetworkFlow(
  flows: Array<{ sourceIp: string; destIp: string; port: number; bytesOut: number; protocol: string }>,
  apiLogs: Array<{ endpoint: string; method: string; statusCode: number; sourceIp: string }> = []
): Promise<AnalysisResult> {
  if (USE_MOCK) return mockApi.mockAnalyzeNetworkFlow(flows);
  const row = await apiFetch('/analysis/network', {
    method: 'POST',
    body: JSON.stringify({ flows, api_logs: apiLogs }),
  });
  return mapAnalysisResult(row);
}

export async function analyzeApiLog(
  logs: Array<{ endpoint: string; method: string; statusCode: number; sourceIp: string }>
): Promise<AnalysisResult> {
  if (USE_MOCK) return mockApi.mockAnalyzeApiLog(logs);
  const row = await apiFetch('/analysis/network', {
    method: 'POST',
    body: JSON.stringify({ flows: [], api_logs: logs }),
  });
  return mapAnalysisResult(row);
}

// ---------------------------------------------------------------------------
// Incidents
// ---------------------------------------------------------------------------

export async function listIncidents(): Promise<Incident[]> {
  if (USE_MOCK) return mockApi.mockListIncidents();
  const rows = await apiFetch('/incidents');
  return (Array.isArray(rows) ? rows : []).map(mapIncident);
}

export async function getIncident(id: string): Promise<Incident | null> {
  if (USE_MOCK) return mockApi.mockGetIncident(id);
  try {
    const row = await apiFetch(`/incidents/${id}`);
    return row ? mapIncident(row) : null;
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) return null;
    throw err;
  }
}

export async function createIncident(alertId: string): Promise<Incident> {
  if (USE_MOCK) return mockApi.mockCreateIncident(alertId);
  // The incidents endpoint derives its title/severity from the linked alert.
  const alert = await getAlert(alertId).catch(() => null);
  const row = await apiFetch('/incidents', {
    method: 'POST',
    body: JSON.stringify({
      title: alert?.title ?? `Incident from alert ${alertId}`,
      severity: alert?.severity ?? 'medium',
      linked_alert_ids: [alertId],
    }),
  });
  return mapIncident(row);
}

export async function updateIncidentStatus(id: string, status: IncidentStatus): Promise<Incident> {
  if (USE_MOCK) return mockApi.mockUpdateIncidentStatus(id, status);
  const row = await apiFetch(`/incidents/${id}/status`, {
    method: 'PATCH',
    body: JSON.stringify({ status }),
  });
  return mapIncident(row);
}

export async function assignIncident(id: string, analyst: string): Promise<Incident> {
  if (USE_MOCK) return mockApi.mockAssignIncident(id, analyst);
  const row = await apiFetch(`/incidents/${id}/assign`, {
    method: 'PATCH',
    body: JSON.stringify({ assigned_to: analyst }),
  });
  return mapIncident(row);
}

export async function escalateIncident(id: string, reason?: string): Promise<Incident> {
  if (USE_MOCK) return mockApi.mockEscalateIncident(id);
  const row = await apiFetch(`/incidents/${id}/escalate`, {
    method: 'POST',
    body: JSON.stringify({ reason: reason ?? 'Escalated from the SOC console' }),
  });
  return mapIncident(row);
}

// ---------------------------------------------------------------------------
// Response actions
// ---------------------------------------------------------------------------

export async function listResponseCatalog(): Promise<ResponseActionCatalog[]> {
  if (USE_MOCK) return mockApi.mockListResponseCatalog();
  const rows = await apiFetch('/responses/catalog');
  return (Array.isArray(rows) ? rows : []).map(mapResponseCatalog);
}

export async function executeResponse(actionId: string, target: string, approved: boolean): Promise<ResponseExecution> {
  if (USE_MOCK) return mockApi.mockExecuteResponse(actionId, target, approved);
  const row = await apiFetch('/responses/execute', {
    method: 'POST',
    body: JSON.stringify({ catalog_id: actionId, target, approved }),
  });
  return mapResponseExecution(row);
}

export async function listResponseHistory(): Promise<ResponseExecution[]> {
  if (USE_MOCK) return mockApi.mockListResponseHistory();
  const rows = await apiFetch('/responses/history');
  return (Array.isArray(rows) ? rows : []).map(mapResponseExecution);
}

// ---------------------------------------------------------------------------
// Audit logs
// ---------------------------------------------------------------------------

export async function listAuditLogs(): Promise<AuditLog[]> {
  if (USE_MOCK) return mockApi.mockListAuditLogs();
  const rows = await apiFetch('/audit/logs?limit=200');
  return (Array.isArray(rows) ? rows : []).map(mapAuditLog);
}

export async function listLoginEvents(): Promise<import('../types').LoginEvent[]> {
  if (USE_MOCK) return mockApi.mockListLoginEvents();
  return notYetIntegrated('listLoginEvents', () => mockApi.mockListLoginEvents());
}

export async function listNetworkFlows(): Promise<import('../types').NetworkFlow[]> {
  if (USE_MOCK) return mockApi.mockListNetworkFlows();
  return notYetIntegrated('listNetworkFlows', () => mockApi.mockListNetworkFlows());
}

export async function listApiLogs(): Promise<import('../types').ApiLogEntry[]> {
  if (USE_MOCK) return mockApi.mockListApiLogs();
  return notYetIntegrated('listApiLogs', () => mockApi.mockListApiLogs());
}

// ---------------------------------------------------------------------------
// SOC assistant
// ---------------------------------------------------------------------------

export async function assistantChat(message: string): Promise<string> {
  if (USE_MOCK) return mockApi.mockAssistantChat(message);
  const row = await apiFetch('/assistant/chat', {
    method: 'POST',
    body: JSON.stringify({ message }),
  });
  const record = row && typeof row === 'object' ? (row as Record<string, unknown>) : {};
  return String(record.reply ?? 'The assistant is temporarily unable to generate a response.');
}

export async function addAlert(alert: Alert): Promise<void> {
  if (USE_MOCK) return mockApi.mockAddAlert(alert);
  return notYetIntegrated('addAlert', async () => mockApi.mockAddAlert(alert));
}

// ---------------------------------------------------------------------------
// RBAC (auth/me is resolved inside the auth store; admin endpoints here)
// ---------------------------------------------------------------------------

export interface AdminUser {
  id: string;
  email: string | null;
  full_name: string | null;
  role: 'viewer' | 'analyst' | 'admin';
  created_at: string | null;
}

export async function listAdminUsers(): Promise<AdminUser[]> {
  if (USE_MOCK) {
    await new Promise((r) => setTimeout(r, 300));
    return [
      { id: 'USR-001', email: 'admin@cyberguard.local', full_name: 'SOC Administrator', role: 'admin', created_at: new Date('2026-01-05').toISOString() },
      { id: 'USR-002', email: 'analyst@cyberguard.local', full_name: 'Demo Analyst', role: 'analyst', created_at: new Date('2026-01-06').toISOString() },
      { id: 'USR-003', email: 'viewer@cyberguard.local', full_name: 'Demo Viewer', role: 'viewer', created_at: new Date('2026-01-07').toISOString() },
    ];
  }
  const rows = await apiFetch('/admin/users');
  return (Array.isArray(rows) ? rows : []) as AdminUser[];
}

export async function updateUserRole(
  userId: string,
  role: 'viewer' | 'analyst' | 'admin'
): Promise<AdminUser> {
  if (USE_MOCK) {
    await new Promise((r) => setTimeout(r, 300));
    return { id: userId, email: null, full_name: null, role, created_at: null };
  }
  const row = await apiFetch(`/admin/users/${userId}/role`, {
    method: 'PATCH',
    body: JSON.stringify({ role }),
  });
  return row as AdminUser;
}

export function isMockMode(): boolean {
  return USE_MOCK;
}

export { mockApi };
