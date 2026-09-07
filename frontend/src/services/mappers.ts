import type {
  Alert,
  AnalysisResult,
  AuditLog,
  DashboardSummary,
  Incident,
  Indicator,
  MitreTechnique,
  RecommendedAction,
  ResponseActionCatalog,
  ResponseExecution,
  Severity,
  ThreatModule,
} from '../types';

// ---------------------------------------------------------------------------
// snake_case (backend JSON) -> camelCase (frontend types) mappers.
// Every mapper tolerates missing optional fields with safe defaults.
// ---------------------------------------------------------------------------

const SEVERITIES: Severity[] = ['safe', 'low', 'medium', 'high', 'critical'];
const MODULES: ThreatModule[] = [
  'phishing',
  'url',
  'impersonation',
  'deepfake',
  'account_takeover',
  'network',
  'api_abuse',
];
const ALERT_STATUSES = ['new', 'acknowledged', 'resolved', 'dismissed'] as const;

function asRecord(value: unknown): Record<string, any> {
  return value && typeof value === 'object' ? (value as Record<string, any>) : {};
}

function mapSeverity(value: unknown): Severity {
  return SEVERITIES.includes(value as Severity) ? (value as Severity) : 'low';
}

function mapModule(value: unknown): ThreatModule {
  return MODULES.includes(value as ThreatModule) ? (value as ThreatModule) : 'phishing';
}

function asArray(value: unknown): Record<string, any>[] {
  return Array.isArray(value) ? value.map(asRecord) : [];
}

function mapIndicator(row: Record<string, any>, index: number): Indicator {
  return {
    id: String(row.id ?? `ind-${index}`),
    type: String(row.type ?? 'unknown'),
    value: String(row.value ?? ''),
    severity: mapSeverity(row.severity),
    description: String(row.description ?? ''),
  };
}

function mapMitreTechnique(row: Record<string, any>): MitreTechnique {
  return {
    id: String(row.id ?? ''),
    name: String(row.name ?? ''),
    tactic: String(row.tactic ?? ''),
  };
}

function mapRecommendedAction(row: Record<string, any>): RecommendedAction {
  return {
    id: String(row.id ?? ''),
    action: String(row.action ?? ''),
    description: String(row.description ?? ''),
    automationLevel: row.automation_level ?? 'manual',
    requiresApproval: Boolean(row.requires_approval),
    priority: row.priority ?? 'low',
    executed: Boolean(row.executed),
    executedAt: row.executed_at ?? undefined,
  };
}

export function mapAlert(row: unknown): Alert {
  const data = asRecord(row);
  return {
    id: String(data.id ?? ''),
    title: String(data.title ?? 'Untitled alert'),
    module: mapModule(data.module),
    severity: mapSeverity(data.severity),
    riskScore: Number(data.risk_score ?? 0),
    status: ALERT_STATUSES.includes(data.status) ? data.status : 'new',
    summary: String(data.summary ?? ''),
    indicators: asArray(data.indicators).map(mapIndicator),
    explanation: String(data.explanation ?? ''),
    recommendedActions: asArray(data.recommended_actions).map(mapRecommendedAction),
    mitreTechniques: asArray(data.mitre).map(mapMitreTechnique),
    targetUser: data.target_user ?? undefined,
    targetService: data.target_service ?? undefined,
    sourceIp: data.source_ip ?? undefined,
    timestamp: String(data.created_at ?? ''),
  };
}

export function mapDashboardSummary(row: unknown): DashboardSummary {
  const data = asRecord(row);
  const incidentSummary = asRecord(data.incident_summary);
  return {
    totalEventsAnalyzed: Number(data.total_events_analyzed ?? 0),
    threatsDetected: Number(data.threats_detected ?? 0),
    phishingAttempts: Number(data.phishing_attempts ?? 0),
    impersonationAttempts: Number(data.impersonation_attempts ?? 0),
    suspectedDeepfakes: Number(data.suspected_deepfakes ?? 0),
    accountTakeoverAttempts: Number(data.account_takeover_attempts ?? 0),
    riskDistribution: asArray(data.risk_distribution).map((band) => ({
      name: String(band.name ?? ''),
      value: Number(band.value ?? 0),
      color: String(band.color ?? '#64748b'),
    })),
    threatCategories: asArray(data.threat_categories).map((category) => ({
      name: String(category.name ?? ''),
      count: Number(category.count ?? 0),
    })),
    attackTimeline: asArray(data.attack_timeline).map((slot) => ({
      hour: String(slot.hour ?? ''),
      threats: Number(slot.threats ?? 0),
      events: Number(slot.events ?? 0),
    })),
    topTargetedUsers: asArray(data.top_targeted_users).map((user) => ({
      user: String(user.user ?? ''),
      attacks: Number(user.attacks ?? 0),
      lastAttack: String(user.last_attack ?? ''),
    })),
    topTargetedServices: asArray(data.top_targeted_services).map((service) => ({
      service: String(service.service ?? ''),
      attacks: Number(service.attacks ?? 0),
      riskLevel: mapSeverity(service.risk_level),
    })),
    recentAlerts: asArray(data.recent_alerts).map(mapAlert),
    incidentSummary: {
      open: Number(incidentSummary.open ?? 0),
      investigating: Number(incidentSummary.investigating ?? 0),
      contained: Number(incidentSummary.contained ?? 0),
      closed: Number(incidentSummary.closed ?? 0),
    },
  };
}

export function mapIncident(row: unknown): Incident {
  const data = asRecord(row);
  return {
    id: String(data.id ?? ''),
    title: String(data.title ?? ''),
    severity: mapSeverity(data.severity),
    status: data.status ?? 'open',
    assignedTo: data.assigned_to ?? undefined,
    linkedAlertIds: Array.isArray(data.linked_alert_ids)
      ? data.linked_alert_ids.map(String)
      : [],
    timeline: asArray(data.timeline).map((event, index) => ({
      id: String(event.id ?? `evt-${index}`),
      action: String(event.action ?? ''),
      actor: String(event.actor ?? ''),
      timestamp: String(event.created_at ?? event.timestamp ?? ''),
      details: String(event.details ?? ''),
    })),
    createdAt: String(data.created_at ?? ''),
    updatedAt: String(data.updated_at ?? ''),
  };
}

export function mapAuditLog(row: unknown): AuditLog {
  const data = asRecord(row);
  return {
    id: String(data.id ?? ''),
    userId: String(data.user_id ?? ''),
    userName: String(data.user_name ?? ''),
    action: String(data.action ?? ''),
    resource: String(data.resource ?? ''),
    details: String(data.details ?? ''),
    timestamp: String(data.created_at ?? ''),
  };
}

export function mapResponseCatalog(row: unknown): ResponseActionCatalog {
  const data = asRecord(row);
  return {
    id: String(data.id ?? ''),
    action: String(data.action ?? ''),
    targetType: String(data.target_type ?? ''),
    automationLevel: data.automation_level ?? 'manual',
    requiresApproval: Boolean(data.requires_approval),
    description: String(data.description ?? ''),
  };
}

export function mapResponseExecution(row: unknown): ResponseExecution {
  const data = asRecord(row);
  return {
    id: String(data.id ?? ''),
    actionId: String(data.catalog_id ?? ''),
    actionName: String(data.action_name ?? ''),
    target: String(data.target ?? ''),
    status: data.status ?? 'pending',
    executedBy: String(data.executed_by ?? ''),
    approvedBy: data.approved_by ?? undefined,
    timestamp: String(data.created_at ?? ''),
  };
}

export function mapAnalysisResult(row: unknown): AnalysisResult {
  const data = asRecord(row);
  // Backend confidence is a 0-1 fraction (or null); the UI renders it as a
  // percentage. Missing confidence falls back to 90%.
  const rawConfidence = data.confidence;
  const confidence =
    rawConfidence === undefined || rawConfidence === null
      ? 90
      : Number(rawConfidence) <= 1
        ? Math.round(Number(rawConfidence) * 100)
        : Math.round(Number(rawConfidence));
  return {
    eventId: String(data.event_id ?? data.id ?? ''),
    module: mapModule(data.module),
    threatType: String(data.threat_type ?? data.module ?? ''),
    riskScore: Number(data.risk_score ?? 0),
    severity: mapSeverity(data.severity),
    confidence,
    indicators: asArray(data.indicators).map(mapIndicator),
    explanation: String(data.explanation ?? ''),
    recommendedActions: asArray(data.recommended_actions).map(mapRecommendedAction),
    mitreTechniques: asArray(data.mitre).map(mapMitreTechnique),
    timestamp: String(data.created_at ?? ''),
    status: data.status ?? 'completed',
    authenticityScore:
      data.authenticity_score !== undefined && data.authenticity_score !== null
        ? Number(data.authenticity_score)
        : undefined,
    manipulationProbability:
      data.manipulation_probability !== undefined && data.manipulation_probability !== null
        ? Number(data.manipulation_probability)
        : undefined,
    method: data.method !== undefined && data.method !== null ? String(data.method) : undefined,
    simulated: data.simulated !== undefined && data.simulated !== null ? Boolean(data.simulated) : undefined,
  };
}
