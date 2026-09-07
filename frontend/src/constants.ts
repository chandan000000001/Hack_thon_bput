import type { ThreatModule } from './types';

export const MODULE_LABELS: Record<ThreatModule, string> = {
  phishing: 'Phishing',
  url: 'Malicious URL',
  impersonation: 'Impersonation',
  deepfake: 'Deepfake',
  account_takeover: 'Account Takeover',
  network: 'Network Threat',
  api_abuse: 'API Abuse',
};

export const MODULE_OPTIONS: ThreatModule[] = [
  'phishing',
  'url',
  'impersonation',
  'deepfake',
  'account_takeover',
  'network',
  'api_abuse',
];

export const SEVERITY_OPTIONS = ['safe', 'low', 'medium', 'high', 'critical'] as const;

export const ANALYSTS = ['Unassigned', 'Alice Chen', 'Bob Kumar', 'Carlos Reyes'];

export function formatTime(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export function formatBytes(bytes: number): string {
  if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(2)} GB`;
  if (bytes >= 1024 ** 2) return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
  if (bytes >= 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${bytes} B`;
}
