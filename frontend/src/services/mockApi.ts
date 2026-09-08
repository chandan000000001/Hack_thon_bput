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
import {
  analyzeApiLog,
  analyzeAuthLog,
  analyzeEmailText,
  analyzeImpersonation,
  analyzeMedia,
  analyzeNetworkFlow,
  analyzeUrl,
  getSeverityFromScore,
  type ApiLogInput,
  type AuthEventInput,
  type FlowInput,
} from './mockEngine';
import { addAuditLog, db } from './mockData';

const delay = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));
const jitter = () => delay(400 + Math.floor(Math.random() * 500));

const DEMO_USER: User = {
  id: 'USR-001',
  name: 'SOC Administrator',
  email: 'admin@cyberguard.local',
  role: 'admin',
};

// ---------------------------------------------------------------------------
// Auth
// ---------------------------------------------------------------------------
export async function mockLogin(email: string, password: string): Promise<{ user: User; token: string }> {
  await jitter();
  if (email.trim().toLowerCase() === 'admin@cyberguard.local' && password === 'demo1234') {
    addAuditLog({
      userId: DEMO_USER.id,
      userName: DEMO_USER.email,
      action: 'LOGIN',
      resource: 'auth/session',
      details: 'Successful mock login',
    });
    return { user: DEMO_USER, token: `mock-jwt-${Date.now()}` };
  }
  throw new Error('Invalid credentials. Use admin@cyberguard.local / demo1234');
}

// ---------------------------------------------------------------------------
// Dashboard
// ---------------------------------------------------------------------------
export async function mockGetDashboardSummary(): Promise<DashboardSummary> {
  await jitter();
  const alerts = db.alerts;
  const countBy = (fn: (a: Alert) => boolean) => alerts.filter(fn).length;

  const bands: { name: string; color: string }[] = [
    { name: 'Safe', color: '#e4e4e7' },
    { name: 'Low', color: '#71717a' },
    { name: 'Medium', color: '#f87171' },
    { name: 'High', color: '#dc2626' },
    { name: 'Critical', color: '#ef4444' },
  ];
  const riskDistribution = bands.map((b) => ({
    name: b.name,
    color: b.color,
    value: countBy((a) => a.severity === b.name.toLowerCase() as Severity),
  }));

  const moduleLabels: [ThreatModule, string][] = [
    ['phishing', 'Phishing'],
    ['url', 'Malicious URL'],
    ['impersonation', 'Impersonation'],
    ['deepfake', 'Deepfake'],
    ['account_takeover', 'Account Takeover'],
    ['network', 'Network Threat'],
    ['api_abuse', 'API Abuse'],
  ];
  const threatCategories = moduleLabels
    .map(([m, label]) => ({ name: label, count: countBy((a) => a.module === m) }))
    .sort((a, b) => b.count - a.count);

  // Build a 24h timeline from alert timestamps
  const now = Date.now();
  const attackTimeline = Array.from({ length: 24 }, (_, i) => {
    const hourStart = now - (23 - i) * 3600 * 1000;
    const hourEnd = hourStart + 3600 * 1000;
    const inHour = alerts.filter((a) => {
      const t = new Date(a.timestamp).getTime();
      return t >= hourStart && t < hourEnd;
    });
    const hour = new Date(hourStart).getHours();
    return {
      hour: `${String(hour).padStart(2, '0')}:00`,
      threats: inHour.length,
      events: Math.max(2, inHour.length + 18 + ((hour * 7) % 11)),
    };
  });

  // Top targeted users/services derived from alerts
  const userHits = new Map<string, { attacks: number; lastAttack: string }>();
  const serviceHits = new Map<string, { attacks: number; severities: Severity[] }>();
  for (const a of alerts) {
    if (a.targetUser) {
      const cur = userHits.get(a.targetUser) ?? { attacks: 0, lastAttack: a.timestamp };
      cur.attacks += 1;
      if (a.timestamp > cur.lastAttack) cur.lastAttack = a.timestamp;
      userHits.set(a.targetUser, cur);
    }
    if (a.targetService) {
      const cur = serviceHits.get(a.targetService) ?? { attacks: 0, severities: [] as Severity[] };
      cur.attacks += 1;
      cur.severities.push(a.severity);
      serviceHits.set(a.targetService, cur);
    }
  }
  const severityRank: Record<Severity, number> = { safe: 0, low: 1, medium: 2, high: 3, critical: 4 };
  const topTargetedUsers = [...userHits.entries()]
    .map(([user, v]) => ({ user, attacks: v.attacks, lastAttack: v.lastAttack }))
    .sort((a, b) => b.attacks - a.attacks)
    .slice(0, 5);
  const topTargetedServices = [...serviceHits.entries()]
    .map(([service, v]) => ({
      service,
      attacks: v.attacks,
      riskLevel: v.severities.reduce((worst, s) => (severityRank[s] > severityRank[worst] ? s : worst), 'safe' as Severity),
    }))
    .sort((a, b) => b.attacks - a.attacks)
    .slice(0, 5);

  const incidentSummary = {
    open: db.incidents.filter((i) => i.status === 'open').length,
    investigating: db.incidents.filter((i) => i.status === 'investigating').length,
    contained: db.incidents.filter((i) => i.status === 'contained').length,
    closed: db.incidents.filter((i) => i.status === 'closed').length,
  };

  const recentAlerts = [...alerts].sort((a, b) => b.timestamp.localeCompare(a.timestamp)).slice(0, 10);
  const totalEventsAnalyzed = 1284 + alerts.length * 37 + db.networkFlows.length * 12 + db.apiLogs.length * 9;

  return {
    totalEventsAnalyzed,
    threatsDetected: alerts.filter((a) => a.severity === 'high' || a.severity === 'critical').length,
    phishingAttempts: countBy((a) => a.module === 'phishing'),
    impersonationAttempts: countBy((a) => a.module === 'impersonation'),
    suspectedDeepfakes: countBy((a) => a.module === 'deepfake'),
    accountTakeoverAttempts: countBy((a) => a.module === 'account_takeover'),
    riskDistribution,
    threatCategories,
    attackTimeline,
    topTargetedUsers,
    topTargetedServices,
    recentAlerts,
    incidentSummary,
  };
}

// ---------------------------------------------------------------------------
// Alerts
// ---------------------------------------------------------------------------
export async function mockListAlerts(filters?: {
  severity?: Severity;
  module?: ThreatModule;
  status?: string;
  search?: string;
}): Promise<Alert[]> {
  await jitter();
  let alerts = [...db.alerts];
  if (filters?.severity) alerts = alerts.filter((a) => a.severity === filters.severity);
  if (filters?.module) alerts = alerts.filter((a) => a.module === filters.module);
  if (filters?.status) alerts = alerts.filter((a) => a.status === filters.status);
  if (filters?.search) {
    const q = filters.search.toLowerCase();
    alerts = alerts.filter(
      (a) =>
        a.title.toLowerCase().includes(q) ||
        a.summary.toLowerCase().includes(q) ||
        a.id.toLowerCase().includes(q) ||
        (a.targetUser ?? '').toLowerCase().includes(q)
    );
  }
  return alerts.sort((a, b) => b.timestamp.localeCompare(a.timestamp));
}

export async function mockGetAlert(id: string): Promise<Alert | null> {
  await jitter();
  return db.alerts.find((a) => a.id === id) ?? null;
}

export function mockAddAlert(alert: Alert): void {
  db.alerts.unshift(alert);
}

// ---------------------------------------------------------------------------
// Analysis wrappers
// ---------------------------------------------------------------------------
export async function mockAnalyzeEmail(sender: string, subject: string, body: string): Promise<AnalysisResult> {
  await jitter();
  return analyzeEmailText(sender, subject, body);
}

export async function mockAnalyzeUrl(url: string): Promise<AnalysisResult> {
  await jitter();
  return analyzeUrl(url);
}

export async function mockAnalyzeImpersonation(message: string, claimedIdentity: string): Promise<AnalysisResult> {
  await jitter();
  return analyzeImpersonation(message, claimedIdentity);
}

export async function mockAnalyzeMedia(file: { name: string; size: number; type: string }): Promise<AnalysisResult> {
  await new Promise((r) => setTimeout(r, 700 + Math.floor(Math.random() * 600)));
  return analyzeMedia(file);
}

export async function mockAnalyzeAuthLog(events: AuthEventInput[]): Promise<AnalysisResult> {
  await jitter();
  return analyzeAuthLog(events);
}

export async function mockAnalyzeNetworkFlow(flows: FlowInput[]): Promise<AnalysisResult> {
  await jitter();
  return analyzeNetworkFlow(flows);
}

export async function mockAnalyzeApiLog(logs: ApiLogInput[]): Promise<AnalysisResult> {
  await jitter();
  return analyzeApiLog(logs);
}

// ---------------------------------------------------------------------------
// Incidents
// ---------------------------------------------------------------------------
export async function mockListIncidents(): Promise<Incident[]> {
  await jitter();
  return [...db.incidents].sort((a, b) => b.updatedAt.localeCompare(a.updatedAt));
}

export async function mockGetIncident(id: string): Promise<Incident | null> {
  await jitter();
  return db.incidents.find((i) => i.id === id) ?? null;
}

export async function mockCreateIncident(alertId: string): Promise<Incident> {
  await jitter();
  const alert = db.alerts.find((a) => a.id === alertId);
  if (!alert) throw new Error(`Alert ${alertId} not found`);
  const existing = db.incidents.find((i) => i.linkedAlertIds.includes(alertId));
  if (existing) return existing;
  const user = DEMO_USER.name;
  const now = new Date().toISOString();
  const incident: Incident = {
    id: `INC-${String(db.incidents.length + 1).padStart(3, '0')}`,
    title: alert.title,
    severity: alert.severity,
    status: 'open',
    assignedTo: undefined,
    linkedAlertIds: [alert.id],
    timeline: [
      {
        id: `EV-${Date.now()}`,
        action: 'Incident Created',
        actor: user,
        timestamp: now,
        details: `Incident opened from alert ${alert.id}: ${alert.summary}`,
      },
    ],
    createdAt: now,
    updatedAt: now,
  };
  db.incidents.unshift(incident);
  addAuditLog({
    userId: DEMO_USER.id,
    userName: DEMO_USER.email,
    action: 'CREATE_INCIDENT',
    resource: incident.id,
    details: `Created incident from alert ${alertId}`,
  });
  return incident;
}

export async function mockUpdateIncidentStatus(id: string, status: IncidentStatus): Promise<Incident> {
  await delay(300);
  const incident = db.incidents.find((i) => i.id === id);
  if (!incident) throw new Error(`Incident ${id} not found`);
  incident.status = status;
  incident.updatedAt = new Date().toISOString();
  incident.timeline.push({
    id: `EV-${Date.now()}`,
    action: 'Status Changed',
    actor: DEMO_USER.name,
    timestamp: incident.updatedAt,
    details: `Status changed to ${status}`,
  });
  addAuditLog({
    userId: DEMO_USER.id,
    userName: DEMO_USER.email,
    action: 'UPDATE_INCIDENT',
    resource: id,
    details: `Status changed to ${status}`,
  });
  return incident;
}

export async function mockAssignIncident(id: string, analyst: string): Promise<Incident> {
  await delay(250);
  const incident = db.incidents.find((i) => i.id === id);
  if (!incident) throw new Error(`Incident ${id} not found`);
  incident.assignedTo = analyst === 'Unassigned' ? undefined : analyst;
  incident.updatedAt = new Date().toISOString();
  incident.timeline.push({
    id: `EV-${Date.now()}`,
    action: 'Assignment Changed',
    actor: DEMO_USER.name,
    timestamp: incident.updatedAt,
    details: `Assigned to ${analyst}`,
  });
  addAuditLog({
    userId: DEMO_USER.id,
    userName: DEMO_USER.email,
    action: 'ASSIGN_INCIDENT',
    resource: id,
    details: `Assigned to ${analyst}`,
  });
  return incident;
}

export async function mockEscalateIncident(id: string): Promise<Incident> {
  await delay(250);
  const incident = db.incidents.find((i) => i.id === id);
  if (!incident) throw new Error(`Incident ${id} not found`);
  incident.updatedAt = new Date().toISOString();
  incident.timeline.push({
    id: `EV-${Date.now()}`,
    action: 'Escalated',
    actor: DEMO_USER.name,
    timestamp: incident.updatedAt,
    details: 'Incident escalated to senior SOC management for priority handling',
  });
  addAuditLog({
    userId: DEMO_USER.id,
    userName: DEMO_USER.email,
    action: 'ESCALATE_INCIDENT',
    resource: id,
    details: 'Incident escalated to management',
  });
  return incident;
}

// ---------------------------------------------------------------------------
// Response actions
// ---------------------------------------------------------------------------
export async function mockListResponseCatalog(): Promise<ResponseActionCatalog[]> {
  await jitter();
  return [...db.responseCatalog];
}

export async function mockListResponseHistory(): Promise<ResponseExecution[]> {
  await jitter();
  return [...db.responseHistory].sort((a, b) => b.timestamp.localeCompare(a.timestamp));
}

export async function mockExecuteResponse(
  actionId: string,
  target: string,
  approved: boolean
): Promise<ResponseExecution> {
  await jitter();
  const catalog = db.responseCatalog.find((c) => c.id === actionId);
  let name = catalog?.action;
  if (!name) {
    for (const alert of db.alerts) {
      const match = alert.recommendedActions.find((a) => a.id === actionId);
      if (match) {
        name = match.action;
        break;
      }
    }
  }
  if (!name) {
    throw new Error(`Unknown action ${actionId}`);
  }
  if (catalog?.requiresApproval && !approved) {
    throw new Error('This action requires explicit approval before execution');
  }
  const execution: ResponseExecution = {
    id: `EXE-${String(db.responseHistory.length + 1).padStart(3, '0')}`,
    actionId,
    actionName: name,
    target,
    status: approved ? 'executed' : 'executed',
    executedBy: DEMO_USER.email,
    approvedBy: approved ? DEMO_USER.email : undefined,
    timestamp: new Date().toISOString(),
  };
  db.responseHistory.unshift(execution);
  addAuditLog({
    userId: DEMO_USER.id,
    userName: DEMO_USER.email,
    action: 'EXECUTE_ACTION',
    resource: actionId,
    details: `Executed ${name} (simulated) on ${target}`,
  });
  return execution;
}

// ---------------------------------------------------------------------------
// Audit logs
// ---------------------------------------------------------------------------
export async function mockListAuditLogs(): Promise<AuditLog[]> {
  await jitter();
  return [...db.auditLogs].sort((a, b) => b.timestamp.localeCompare(a.timestamp));
}

// ---------------------------------------------------------------------------
// Raw log listings (login events / network flows / API logs)
// ---------------------------------------------------------------------------
export async function mockListLoginEvents() {
  await jitter();
  return [...db.loginEvents].sort((a, b) => b.timestamp.localeCompare(a.timestamp));
}

export async function mockListNetworkFlows() {
  await jitter();
  return [...db.networkFlows].sort((a, b) => b.timestamp.localeCompare(a.timestamp));
}

export async function mockListApiLogs() {
  await jitter();
  return [...db.apiLogs].sort((a, b) => b.timestamp.localeCompare(a.timestamp));
}

// ---------------------------------------------------------------------------
// SOC Assistant (context-aware canned responses)
// ---------------------------------------------------------------------------
export async function mockAssistantChat(message: string): Promise<string> {
  await delay(600 + Math.floor(Math.random() * 700));
  const q = message.toLowerCase();
  const criticals = db.alerts.filter((a) => a.severity === 'critical');
  const highs = db.alerts.filter((a) => a.severity === 'high');
  const newest = [...db.alerts].sort((a, b) => b.timestamp.localeCompare(a.timestamp)).slice(0, 5);

  if (q.includes('critical') || q.includes('show critical')) {
    const lines = criticals
      .map((a) => `- ${a.id} [${a.severity.toUpperCase()}] ${a.title} (risk ${a.riskScore})`)
      .join('\n');
    return `There are currently ${criticals.length} critical alerts:\n\n${lines}\n\nI recommend starting with the most recent ones — check the Alerts page and open each for indicators, explanation and recommended actions.`;
  }
  if (q.includes('phishing')) {
    const phish = db.alerts.filter((a) => a.module === 'phishing');
    return `Phishing overview: ${phish.length} phishing alerts in the database. The most severe is "${phish[0]?.title}" (risk ${phish[0]?.riskScore}). Common patterns detected: lookalike sender domains (micr0soft-verify.xyz style substitution), raw-IP credential URLs, and artificial urgency language. The Phishing Analysis page lets you test any email against the heuristic engine — try the provided phishing sample.`;
  }
  if (q.includes('mitre')) {
    const techs = new Map<string, { name: string; tactic: string; count: number }>();
    for (const a of db.alerts) {
      for (const t of a.mitreTechniques) {
        const cur = techs.get(t.id) ?? { name: t.name, tactic: t.tactic, count: 0 };
        cur.count += 1;
        techs.set(t.id, cur);
      }
    }
    const sorted = [...techs.entries()].sort((a, b) => b[1].count - a[1].count).slice(0, 8);
    const lines = sorted.map(([id, t]) => `- ${id} ${t.name} (${t.tactic}) — seen ${t.count}x`).join('\n');
    return `MITRE ATT&CK techniques detected across current alerts:\n\n${lines}\n\nFull mappings are available on each alert's "MITRE ATT&CK" tab.`;
  }
  if (q.includes('investigate') || q.includes('first')) {
    const top = [...db.alerts]
      .filter((a) => a.severity === 'critical' || a.severity === 'high')
      .sort((a, b) => b.riskScore - a.riskScore)[0];
    return `I recommend investigating ${top.id} first: "${top.title}" (risk score ${top.riskScore}, ${top.severity}). ${top.summary}. Suggested first step: ${top.recommendedActions[0]?.action ?? 'review indicators'}. Remember that actions marked semi-automatic require your approval before simulated execution.`;
  }
  if (q.includes('incident')) {
    const open = db.incidents.filter((i) => i.status !== 'closed');
    return `Incident summary: ${open.length} active incidents (${db.incidents.filter((i) => i.status === 'open').length} open, ${db.incidents.filter((i) => i.status === 'investigating').length} investigating, ${db.incidents.filter((i) => i.status === 'contained').length} contained). The most recently updated is "${open[0]?.title}". Open the Incidents page to manage assignments and status transitions.`;
  }
  if (q.includes('alert') || q.includes('threat') || q.includes('summarize') || q.includes('today')) {
    const lines = newest.map((a) => `- [${a.severity.toUpperCase()}] ${a.title} (risk ${a.riskScore})`).join('\n');
    return `Threat summary for today: ${db.alerts.length} total alerts, of which ${criticals.length} are critical and ${highs.length} are high severity. Busiest modules are phishing and account takeover. Newest alerts:\n\n${lines}\n\nAsk me "show critical alerts", "list MITRE techniques detected", or "what should I investigate first?" for details.`;
  }
  if (q.includes('help') || q.includes('what can you')) {
    return `I'm the SOC Assistant running in mock mode. I can summarize today's threats, list critical alerts, report on phishing campaigns, enumerate MITRE ATT&CK techniques seen, review incident status, and suggest what to investigate first. I answer from the in-browser mock database, so try the quick action buttons below.`;
  }
  return `I'm the SOC Assistant (mock mode). I can help you with:\n\n- "Summarize today's threats" — overview of alert volume and severity\n- "Show critical alerts" — list of current critical alerts\n- "List MITRE techniques detected" — ATT&CK mapping across alerts\n- "What should I investigate first?" — prioritized recommendation\n- "Incident status" — open incident summary\n\nAll answers come from the local mock database.`;
}

// ---------------------------------------------------------------------------
// Live simulation alert generator
// ---------------------------------------------------------------------------
let simCounter = 0;
const SIM_MODULES: { module: ThreatModule; titles: string[] }[] = [
  { module: 'phishing', titles: ['Phishing Email Detected - {brand} Credential Lure', 'Smishing Campaign Detected Against Finance Team', 'QR-Code Phishing Reference in Email Body'] },
  { module: 'url', titles: ['Lookalike Domain Observed in DNS Logs', 'Suspicious URL Click Blocked by Proxy', 'New Credential-Harvesting Page Indexed'] },
  { module: 'impersonation', titles: ['Executive Impersonation Attempt in Chat', 'Vendor Payment Request Flagged as Fraudulent', 'IT Support Impersonation on Messaging Channel'] },
  { module: 'deepfake', titles: ['Voice Clip Shows Synthetic Speech Indicators', 'Video Call Frame Anomalies Detected', 'AI-Generated Profile Photo Flagged'] },
  { module: 'account_takeover', titles: ['MFA Fatigue Burst on Executive Account', 'Failed Login Burst from Tor Exit', 'Unknown Device Login for Service Account'] },
  { module: 'network', titles: ['Outbound Beaconing to Unknown Host', 'High-Volume Transfer to File-Sharing Domain', 'Suspicious Port Activity on DMZ Host'] },
  { module: 'api_abuse', titles: ['Rate Limit Breach on Auth Endpoint', 'Sequential Enumeration on Public API', 'Repeated 401s from Single Token'] },
];
const SIM_BRANDS = ['Microsoft', 'PayPal', 'Google', 'Amazon', 'Apple'];
const SIM_USERS = ['john.doe@company.com', 'jane.smith@company.com', 'alice.wong@company.com', 'bob.marley@company.com', 'emma.davis@company.com', 'svc-reports'];
const SIM_IPS = ['185.220.101.7', '45.33.32.156', '91.219.237.22', '10.0.4.21', '45.33.49.12'];
const SIM_TECHNIQUES = [
  { id: 'T1566.002', name: 'Spearphishing Link', tactic: 'Initial Access' },
  { id: 'T1078', name: 'Valid Accounts', tactic: 'Defense Evasion' },
  { id: 'T1110', name: 'Brute Force', tactic: 'Credential Access' },
  { id: 'T1071.001', name: 'Application Layer Protocol: Web Protocols', tactic: 'Command and Control' },
  { id: 'T1041', name: 'Exfiltration Over C2 Channel', tactic: 'Exfiltration' },
  { id: 'T1656', name: 'Impersonation', tactic: 'Initial Access' },
];

export function generateSimulatedAlert(): Alert {
  simCounter += 1;
  const entry = SIM_MODULES[simCounter % SIM_MODULES.length];
  const brand = SIM_BRANDS[simCounter % SIM_BRANDS.length];
  const title = entry.titles[simCounter % entry.titles.length].replace('{brand}', brand);
  const risk = 45 + ((simCounter * 17) % 50);
  const severity = getSeverityFromScore(risk);
  const now = new Date().toISOString();
  const recs = severity === 'high' || severity === 'critical'
    ? [
        { id: `RA-S${simCounter}-1`, action: 'Notify Targeted Users', description: 'Send awareness notice to affected recipients', automationLevel: 'manual' as const, requiresApproval: false, priority: 'high' as const },
        { id: `RA-S${simCounter}-2`, action: 'Block Indicator', description: 'Blocklist the primary indicator', automationLevel: 'automatic' as const, requiresApproval: false, priority: 'high' as const },
      ]
    : [
        { id: `RA-S${simCounter}-1`, action: 'Monitor Indicator', description: 'Add to watchlist for correlation', automationLevel: 'manual' as const, requiresApproval: false, priority: 'medium' as const },
      ];
  return {
    id: `ALT-SIM-${String(simCounter).padStart(3, '0')}`,
    title,
    module: entry.module,
    severity,
    riskScore: risk,
    status: 'new',
    summary: `Live simulation alert #${simCounter}: heuristic engine flagged ${entry.module.replace('_', ' ')} activity`,
    indicators: [
      { id: `IND-S${simCounter}-1`, type: 'simulated_event', value: title, severity, description: 'Generated by live simulation for demonstration' },
      { id: `IND-S${simCounter}-2`, type: 'source_ip', value: SIM_IPS[simCounter % SIM_IPS.length], severity: 'medium', description: 'Source associated with the simulated event' },
    ],
    explanation: `This alert was generated by the live simulation feature to demonstrate real-time detection flow. The heuristic engine scored the synthetic event ${risk}/100 (${severity}). Open the alert to review indicators, explanation and recommended actions. This is simulated data, not a real detection.`,
    recommendedActions: recs,
    mitreTechniques: [SIM_TECHNIQUES[simCounter % SIM_TECHNIQUES.length]],
    targetUser: SIM_USERS[simCounter % SIM_USERS.length],
    targetService: 'Simulated Source',
    sourceIp: SIM_IPS[simCounter % SIM_IPS.length],
    timestamp: now,
  };
}
