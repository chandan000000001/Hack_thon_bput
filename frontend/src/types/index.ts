export type Severity = 'safe' | 'low' | 'medium' | 'high' | 'critical';
export type ThreatModule =
  | 'phishing'
  | 'url'
  | 'impersonation'
  | 'deepfake'
  | 'account_takeover'
  | 'network'
  | 'api_abuse';
export type IncidentStatus = 'open' | 'investigating' | 'contained' | 'closed';
export type EventStatus = 'received' | 'analyzing' | 'completed' | 'failed';

export interface User {
  id: string;
  name: string;
  email: string;
  role: 'admin' | 'analyst' | 'viewer';
  avatar?: string;
}

export interface Indicator {
  id: string;
  type: string;
  value: string;
  severity: Severity;
  description: string;
}

export interface MitreTechnique {
  id: string;
  name: string;
  tactic: string;
}

export interface RecommendedAction {
  id: string;
  action: string;
  description: string;
  automationLevel: 'automatic' | 'semi-automatic' | 'manual';
  requiresApproval: boolean;
  priority: 'low' | 'medium' | 'high' | 'critical';
  executed?: boolean;
  executedAt?: string;
}

export interface AnalysisResult {
  eventId: string;
  /** True when the backend queued the analysis (202); render a pending panel. */
  queued?: boolean;
  module: ThreatModule;
  threatType: string;
  riskScore: number;
  severity: Severity;
  confidence: number;
  indicators: Indicator[];
  explanation: string;
  /** LLM provenance: groq | openrouter | rule_based | cache:<orig>; undefined in mock mode. */
  explanationProvider?: string;
  recommendedActions: RecommendedAction[];
  mitreTechniques: MitreTechnique[];
  timestamp: string;
  status: EventStatus;
  // Optional extras produced by specific detectors
  redirectChain?: string[];
  authenticityScore?: number;
  manipulationProbability?: number;
  lexicalFeatures?: { feature: string; value: string; riskContribution: number }[];
  // Media forensics extras (deepfake module)
  method?: string;
  simulated?: boolean;
}

export interface Alert {
  id: string;
  title: string;
  module: ThreatModule;
  severity: Severity;
  riskScore: number;
  status: 'new' | 'acknowledged' | 'resolved' | 'dismissed';
  summary: string;
  indicators: Indicator[];
  explanation: string;
  /** LLM provenance: groq | openrouter | rule_based | cache:<orig>; undefined in mock mode. */
  explanationProvider?: string;
  recommendedActions: RecommendedAction[];
  mitreTechniques: MitreTechnique[];
  targetUser?: string;
  targetService?: string;
  sourceIp?: string;
  timestamp: string;
}

export interface IncidentEvent {
  id: string;
  action: string;
  actor: string;
  timestamp: string;
  details: string;
}

export interface Incident {
  id: string;
  title: string;
  severity: Severity;
  status: IncidentStatus;
  assignedTo?: string;
  linkedAlertIds: string[];
  timeline: IncidentEvent[];
  createdAt: string;
  updatedAt: string;
}

export interface LoginEvent {
  id: string;
  userId: string;
  username: string;
  sourceIp: string;
  location: string;
  device: string;
  status: 'success' | 'failed';
  riskScore: number;
  timestamp: string;
  anomalies: string[];
}

export interface NetworkFlow {
  id: string;
  sourceIp: string;
  destIp: string;
  destDomain: string;
  port: number;
  protocol: string;
  bytesOut: number;
  bytesIn: number;
  anomalyScore: number;
  flags: string[];
  timestamp: string;
}

export interface ApiLogEntry {
  id: string;
  endpoint: string;
  method: string;
  sourceIp: string;
  userAgent: string;
  statusCode: number;
  responseTime: number;
  anomalyScore: number;
  flags: string[];
  timestamp: string;
}

export interface AuditLog {
  id: string;
  userId: string;
  userName: string;
  action: string;
  resource: string;
  details: string;
  timestamp: string;
}

export interface DashboardSummary {
  totalEventsAnalyzed: number;
  threatsDetected: number;
  phishingAttempts: number;
  impersonationAttempts: number;
  suspectedDeepfakes: number;
  accountTakeoverAttempts: number;
  riskDistribution: { name: string; value: number; color: string }[];
  threatCategories: { name: string; count: number }[];
  attackTimeline: { hour: string; threats: number; events: number }[];
  topTargetedUsers: { user: string; attacks: number; lastAttack: string }[];
  topTargetedServices: { service: string; attacks: number; riskLevel: Severity }[];
  recentAlerts: Alert[];
  incidentSummary: { open: number; investigating: number; contained: number; closed: number };
}

export interface ResponseActionCatalog {
  id: string;
  action: string;
  targetType: string;
  automationLevel: 'automatic' | 'semi-automatic' | 'manual';
  requiresApproval: boolean;
  description: string;
}

export interface ResponseExecution {
  id: string;
  actionId: string;
  actionName: string;
  target: string;
  status: 'pending' | 'approved' | 'executed' | 'rejected';
  executedBy: string;
  approvedBy?: string;
  timestamp: string;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: number;
}
