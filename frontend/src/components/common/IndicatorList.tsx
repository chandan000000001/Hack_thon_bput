import { AlertTriangle, Bug, Fingerprint, Globe, Hash, KeyRound, Link, Mail, Server, Terminal } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import type { Indicator } from '../../types';
import SeverityBadge, { SEVERITY_STYLES } from './SeverityBadge';

const TYPE_ICONS: Record<string, LucideIcon> = {
  sender_domain: Mail,
  sender_invalid: Mail,
  lookalike_domain: Fingerprint,
  lookalike_url: Fingerprint,
  urgency_language: AlertTriangle,
  urgency_pressure: AlertTriangle,
  credential_request: KeyRound,
  credential_path: KeyRound,
  suspicious_url: Link,
  ip_url: Globe,
  ip_host: Globe,
  no_tls: Globe,
  http_only: Globe,
  suspicious_tld: Globe,
  suspicious_tld_url: Globe,
  suspicious_port: Server,
  suspicious_ports: Server,
  high_outbound_volume: Server,
  beaconing_pattern: Server,
  dns_tunneling: Terminal,
  password_spraying: KeyRound,
  failed_login_burst: KeyRound,
  impossible_travel: Globe,
  unknown_device: Terminal,
  unusual_hour: Hash,
  synthetic_voice_pattern: Bug,
  facial_boundary_inconsistency: Bug,
  default: Hash,
};

function iconFor(type: string): LucideIcon {
  return TYPE_ICONS[type] ?? TYPE_ICONS.default;
}

const SEVERITY_ORDER: Indicator['severity'][] = ['critical', 'high', 'medium', 'low', 'safe'];

export default function IndicatorList({ indicators }: { indicators: Indicator[] }) {
  if (indicators.length === 0) {
    return (
      <div className="rounded-xl border border-zinc-300/30 bg-zinc-300/5 px-4 py-6 text-center text-sm text-zinc-200">
        No malicious indicators detected
      </div>
    );
  }

  const grouped = SEVERITY_ORDER.map((sev) => ({ sev, items: indicators.filter((i) => i.severity === sev) })).filter(
    (g) => g.items.length > 0
  );

  return (
    <div className="space-y-3">
      {grouped.map(({ sev, items }) => (
        <div key={sev}>
          <div className={`mb-1.5 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wider ${SEVERITY_STYLES[sev].text}`}>
            <span className={`h-1.5 w-1.5 rounded-full ${SEVERITY_STYLES[sev].dot}`} />
            {sev} ({items.length})
          </div>
          <div className="space-y-2">
            {items.map((ind) => {
              const Icon = iconFor(ind.type);
              return (
                <div
                  key={ind.id}
                  className="flex items-start gap-3 rounded-lg border border-zinc-700/50 bg-zinc-800/40 px-3 py-2.5"
                >
                  <Icon className="mt-0.5 h-4 w-4 shrink-0 text-red-400" />
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-mono text-[13px] text-zinc-100 break-all">{ind.value}</span>
                      <span className="rounded bg-zinc-700/60 px-1.5 py-0.5 font-mono text-[10px] text-zinc-400">{ind.type}</span>
                      <SeverityBadge severity={ind.severity} />
                    </div>
                    <p className="mt-1 text-xs leading-relaxed text-zinc-400">{ind.description}</p>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}
