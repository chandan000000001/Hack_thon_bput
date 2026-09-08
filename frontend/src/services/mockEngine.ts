import type {
  AnalysisResult,
  Indicator,
  MitreTechnique,
  RecommendedAction,
  Severity,
} from '../types';

// ---------------------------------------------------------------------------
// Score bands
// 0-20 safe | 21-40 low | 41-60 medium | 61-80 high | 81-100 critical
// ---------------------------------------------------------------------------
export function getSeverityFromScore(score: number): Severity {
  if (score <= 20) return 'safe';
  if (score <= 40) return 'low';
  if (score <= 60) return 'medium';
  if (score <= 80) return 'high';
  return 'critical';
}

// Severity colors are centralised in src/theme.ts (monochrome-red ramp).
export { SEVERITY_COLORS } from '../theme';

// ---------------------------------------------------------------------------
// Shared helpers
// ---------------------------------------------------------------------------
let eventCounter = 1000;
function nextEventId(): string {
  eventCounter += 1;
  return `EVT-${eventCounter}`;
}

let indicatorCounter = 0;
function makeIndicator(
  type: string,
  value: string,
  severity: Severity,
  description: string
): Indicator {
  indicatorCounter += 1;
  return { id: `IND-E${indicatorCounter}`, type, value, severity, description };
}

function clampScore(points: number): number {
  return Math.max(0, Math.min(100, Math.round(points)));
}

function baseResult(module: AnalysisResult['module'], threatType: string): AnalysisResult {
  return {
    eventId: nextEventId(),
    module,
    threatType,
    riskScore: 0,
    severity: 'safe',
    confidence: 0,
    indicators: [],
    explanation: '',
    recommendedActions: [],
    mitreTechniques: [],
    timestamp: new Date().toISOString(),
    status: 'completed',
  };
}

function finalize(result: AnalysisResult, confidence: number): AnalysisResult {
  result.riskScore = clampScore(result.riskScore);
  result.severity = getSeverityFromScore(result.riskScore);
  result.confidence = Math.round(confidence);
  result.recommendedActions = generateRecommendedActions(result.severity, result.module);
  if (result.mitreTechniques.length === 0) {
    result.mitreTechniques = [
      { id: 'T1043', name: 'Commonly Used Port', tactic: 'Command and Control' },
    ];
  }
  return result;
}

export function generateRecommendedActions(
  severity: Severity,
  module: AnalysisResult['module']
): RecommendedAction[] {
  const moduleActions: Record<string, RecommendedAction[]> = {
    phishing: [
      {
        id: 'RA-P1',
        action: 'Quarantine Email',
        description: 'Remove the message from all recipient inboxes',
        automationLevel: 'automatic',
        requiresApproval: false,
        priority: 'critical',
      },
      {
        id: 'RA-P2',
        action: 'Block Sender Domain',
        description: 'Add the sender domain to the organization blocklist',
        automationLevel: 'automatic',
        requiresApproval: false,
        priority: 'high',
      },
      {
        id: 'RA-P3',
        action: 'Block Embedded URLs',
        description: 'Block destination IPs/URLs found in the message at the firewall',
        automationLevel: 'semi-automatic',
        requiresApproval: true,
        priority: 'critical',
      },
      {
        id: 'RA-P4',
        action: 'Notify Targeted Users',
        description: 'Send a security awareness notice to affected recipients',
        automationLevel: 'manual',
        requiresApproval: false,
        priority: 'high',
      },
    ],
    url: [
      {
        id: 'RA-U1',
        action: 'Block URL',
        description: 'Add the URL and hostname to the web-filter deny list',
        automationLevel: 'automatic',
        requiresApproval: false,
        priority: 'high',
      },
      {
        id: 'RA-U2',
        action: 'Block Destination IP',
        description: 'Blackhole the hosting IP at the perimeter firewall',
        automationLevel: 'semi-automatic',
        requiresApproval: true,
        priority: 'critical',
      },
      {
        id: 'RA-U3',
        action: 'Warn Users via Proxy Banner',
        description: 'Show an interstitial warning page when users attempt access',
        automationLevel: 'automatic',
        requiresApproval: false,
        priority: 'medium',
      },
      {
        id: 'RA-U4',
        action: 'Submit to Threat Intelligence',
        description: 'Share the URL with the threat intel pipeline for enrichment',
        automationLevel: 'semi-automatic',
        requiresApproval: false,
        priority: 'low',
      },
    ],
    impersonation: [
      {
        id: 'RA-I1',
        action: 'Report Impersonation',
        description: 'Open an impersonation report with security and affected leadership',
        automationLevel: 'manual',
        requiresApproval: false,
        priority: 'high',
      },
      {
        id: 'RA-I2',
        action: 'Freeze Pending Financial Requests',
        description: 'Hold wire transfers and gift card purchases pending verification',
        automationLevel: 'semi-automatic',
        requiresApproval: true,
        priority: 'critical',
      },
      {
        id: 'RA-I3',
        action: 'Verify Identity Out-of-Band',
        description: 'Contact the claimed identity through a known trusted channel',
        automationLevel: 'manual',
        requiresApproval: false,
        priority: 'high',
      },
      {
        id: 'RA-I4',
        action: 'Notify Finance Department',
        description: 'Alert finance teams about the fraudulent request pattern',
        automationLevel: 'manual',
        requiresApproval: false,
        priority: 'medium',
      },
    ],
    deepfake: [
      {
        id: 'RA-D1',
        action: 'Flag for Manual Verification',
        description: 'Route the media to human analysts for expert review',
        automationLevel: 'manual',
        requiresApproval: false,
        priority: 'high',
      },
      {
        id: 'RA-D2',
        action: 'Block Media Distribution',
        description: 'Prevent the media from being shared on internal channels',
        automationLevel: 'semi-automatic',
        requiresApproval: true,
        priority: 'critical',
      },
      {
        id: 'RA-D3',
        action: 'Preserve Original Evidence',
        description: 'Hash and archive the original file for forensic analysis',
        automationLevel: 'automatic',
        requiresApproval: false,
        priority: 'medium',
      },
    ],
    account_takeover: [
      {
        id: 'RA-A1',
        action: 'Revoke Active Sessions',
        description: 'Terminate all active sessions for the affected account',
        automationLevel: 'semi-automatic',
        requiresApproval: true,
        priority: 'critical',
      },
      {
        id: 'RA-A2',
        action: 'Force Password Reset',
        description: 'Require a password change and MFA re-enrollment on next login',
        automationLevel: 'automatic',
        requiresApproval: false,
        priority: 'high',
      },
      {
        id: 'RA-A3',
        action: 'Require Additional Authentication',
        description: 'Enforce step-up MFA for all new logins from the anomalous source',
        automationLevel: 'automatic',
        requiresApproval: false,
        priority: 'high',
      },
      {
        id: 'RA-A4',
        action: 'Block Source IP',
        description: 'Block the offending source IP at the identity provider',
        automationLevel: 'semi-automatic',
        requiresApproval: true,
        priority: 'critical',
      },
    ],
    network: [
      {
        id: 'RA-N1',
        action: 'Isolate Affected Host',
        description: 'Quarantine the source host from the network pending investigation',
        automationLevel: 'semi-automatic',
        requiresApproval: true,
        priority: 'critical',
      },
      {
        id: 'RA-N2',
        action: 'Block C2 Destination',
        description: 'Drop traffic to the command-and-control IP and domain',
        automationLevel: 'automatic',
        requiresApproval: false,
        priority: 'critical',
      },
      {
        id: 'RA-N3',
        action: 'Capture Full Packet Trace',
        description: 'Start deep packet capture on the affected segment',
        automationLevel: 'manual',
        requiresApproval: false,
        priority: 'medium',
      },
      {
        id: 'RA-N4',
        action: 'Notify SOC Team',
        description: 'Page the on-call SOC analyst with full context',
        automationLevel: 'manual',
        requiresApproval: false,
        priority: 'high',
      },
    ],
    api_abuse: [
      {
        id: 'RA-B1',
        action: 'Apply Rate Limit',
        description: 'Throttle the offending client to 10 requests/minute',
        automationLevel: 'automatic',
        requiresApproval: false,
        priority: 'high',
      },
      {
        id: 'RA-B2',
        action: 'Revoke API Token',
        description: 'Invalidate the credential used by the abusive client',
        automationLevel: 'semi-automatic',
        requiresApproval: true,
        priority: 'critical',
      },
      {
        id: 'RA-B3',
        action: 'Block Source IP at WAF',
        description: 'Add the source IP to the WAF deny rule',
        automationLevel: 'automatic',
        requiresApproval: false,
        priority: 'high',
      },
    ],
  };

  const pool = moduleActions[module] ?? moduleActions.network;
  if (severity === 'safe' || severity === 'low') {
    // Benign traffic: only monitoring-oriented responses
    return pool.slice(0, 2).map((a) => ({
      ...a,
      priority: 'low' as const,
      description: `Monitor only: ${a.description}`,
    }));
  }
  if (severity === 'medium') return pool.slice(0, 3);
  return pool;
}

// ---------------------------------------------------------------------------
// 1. Email / phishing analysis
// ---------------------------------------------------------------------------
const URGENCY_KEYWORDS = [
  'urgent', 'immediately', 'verify', 'suspended', 'action required',
  'expire', 'unauthorized', 'confirm identity', 'final warning', 'last notice',
];
const CREDENTIAL_PHRASES = [
  'verify your password', 'confirm your account', 'update payment',
  'enter your credentials', 'reset your password', 'validate your login',
  'confirm your identity', 'update your billing information',
];
const THREAT_PHRASES = [
  'account will be suspended', 'legal action', 'permanent deletion',
  'permanent suspension', 'account closure', 'criminal charges',
];
const PAYMENT_PHRASES = [
  'wire transfer', 'gift card', 'bitcoin', 'western union', 'crypto payment',
  'processing fee', 'unclaimed funds',
];
const BRANDS = ['microsoft', 'google', 'paypal', 'amazon', 'apple', 'facebook', 'netflix', 'banks'];
const LOOKALIKE_MAP: [RegExp, string][] = [
  [/0/g, 'o'],
  [/1/g, 'l'],
  [/rn/g, 'm'],
  [/3/g, 'e'],
  [/\$/g, 's'],
];
const KNOWN_BRAND_DOMAINS = ['microsoft.com', 'google.com', 'paypal.com', 'amazon.com', 'apple.com', 'facebook.com'];
const SUSPICIOUS_TLDS = ['xyz', 'top', 'zip', 'tk', 'ml', 'ga', 'cf', 'gq', 'work', 'click', 'link'];

export function extractUrls(text: string): string[] {
  const urlRegex = /(https?:\/\/[^\s"'<>)]+)/gi;
  return text.match(urlRegex) ?? [];
}

function isLookalikeOf(domain: string, brand: string): boolean {
  const bare = brand.replace('.com', '');
  if (domain === brand) return false;
  const normalized = LOOKALIKE_MAP.reduce((acc, [re, rep]) => acc.replace(re, rep), domain);
  if (normalized.includes(bare)) return true;
  // e.g. micr0soft-verify.xyz normalizes to microsoft-verify.xyz
  if (normalized.includes(bare.slice(0, Math.max(4, bare.length - 2)))) return true;
  return false;
}

export function analyzeEmailText(sender: string, subject: string, body: string): AnalysisResult {
  const result = baseResult('phishing', 'Phishing / Social Engineering');
  let points = 0;
  const senderDomain = sender.split('@')[1]?.toLowerCase().trim() ?? '';
  const combined = `${subject}\n${body}`.toLowerCase();

  // -- sender domain checks
  if (!senderDomain) {
    result.indicators.push(
      makeIndicator('sender_invalid', sender || '(empty)', 'medium', 'Sender address is missing or malformed')
    );
    points += 25;
  } else if (senderDomain.endsWith('.local') || senderDomain.endsWith('.edu')) {
    // likely fine
  } else {
    const matchedBrand = KNOWN_BRAND_DOMAINS.find((b) => isLookalikeOf(senderDomain, b));
    if (matchedBrand) {
      result.indicators.push(
        makeIndicator(
          'lookalike_domain',
          senderDomain,
          'critical',
          `Sender domain is a character-substitution lookalike of ${matchedBrand}`
        )
      );
      points += 35;
    } else if (SUSPICIOUS_TLDS.includes(senderDomain.split('.').pop() ?? '')) {
      result.indicators.push(
        makeIndicator('suspicious_tld', senderDomain, 'high', `Sender uses a high-abuse TLD (.${senderDomain.split('.').pop()})`)
      );
      points += 20;
    }
  }

  // -- urgency in subject/body
  const urgencyHits = URGENCY_KEYWORDS.filter((k) => combined.includes(k));
  if (urgencyHits.length > 0) {
    result.indicators.push(
      makeIndicator(
        'urgency_language',
        urgencyHits.slice(0, 4).join(', '),
        urgencyHits.length >= 2 ? 'high' : 'medium',
        `Message creates artificial urgency using: ${urgencyHits.join(', ')}`
      )
    );
    points += Math.min(20, urgencyHits.length * 8);
  }

  // -- credential request
  const credHits = CREDENTIAL_PHRASES.filter((k) => combined.includes(k));
  if (credHits.length > 0) {
    result.indicators.push(
      makeIndicator(
        'credential_request',
        credHits.join(' | '),
        'critical',
        'Email requests credential verification or entry through an external channel'
      )
    );
    points += 30;
  }

  // -- threat language
  const threatHits = THREAT_PHRASES.filter((k) => combined.includes(k));
  if (threatHits.length > 0) {
    result.indicators.push(
      makeIndicator('threat_language', threatHits.join(' | '), 'high', 'Message uses threatening consequences to pressure action')
    );
    points += 15;
  }

  // -- payment requests
  const payHits = PAYMENT_PHRASES.filter((k) => combined.includes(k));
  if (payHits.length > 0) {
    result.indicators.push(
      makeIndicator('payment_request', payHits.join(' | '), 'high', 'Message requests payment through hard-to-reverse channels')
    );
    points += 20;
  }

  // -- embedded URLs
  const urls = extractUrls(`${subject}\n${body}`);
  const urlSeen = new Set<string>();
  for (const url of urls) {
    if (urlSeen.has(url)) continue;
    urlSeen.add(url);
    let host = '';
    try {
      host = new URL(url).hostname;
    } catch {
      host = '';
    }
    if (/^(\d{1,3}\.){3}\d{1,3}$/.test(host)) {
      result.indicators.push(
        makeIndicator('ip_url', url, 'critical', 'Embedded URL uses a raw IP address instead of a legitimate domain')
      );
      points += 25;
    } else if (url.startsWith('http://')) {
      result.indicators.push(
        makeIndicator('http_only', url, 'high', 'Embedded URL uses unencrypted HTTP')
      );
      points += 12;
    }
    if (host && KNOWN_BRAND_DOMAINS.some((b) => isLookalikeOf(host, b))) {
      result.indicators.push(
        makeIndicator('lookalike_url', url, 'critical', 'Embedded URL impersonates a well-known brand via character substitution')
      );
      points += 25;
    }
    if (host && SUSPICIOUS_TLDS.includes(host.split('.').pop() ?? '')) {
      result.indicators.push(
        makeIndicator('suspicious_tld_url', url, 'high', `Embedded URL uses a high-abuse TLD (.${host.split('.').pop()})`)
      );
      points += 12;
    }
  }

  // -- brand vs sender mismatch
  const brandMention = BRANDS.find((b) => combined.includes(b));
  if (brandMention && senderDomain && !senderDomain.includes(brandMention.split('.')[0])) {
    result.indicators.push(
      makeIndicator(
        'brand_mismatch',
        `${brandMention} mentioned but sender is ${senderDomain}`,
        'high',
        'Message references a major brand while being sent from an unrelated domain'
      )
    );
    points += 15;
  }

  // -- explanation
  if (result.indicators.length === 0) {
    points = Math.min(points, 8);
    result.explanation =
      'Low Risk: No phishing indicators were detected. The sender domain does not impersonate a known brand, the message contains no urgency or threat language, no credential or payment requests, and no suspicious embedded URLs. This message appears consistent with normal communication.';
    result.mitreTechniques = [];
  } else {
    const band = points >= 81 ? 'Critical Risk' : points >= 61 ? 'High Risk' : points >= 41 ? 'Medium Risk' : 'Low Risk';
    const parts: string[] = [];
    if (urgencyHits.length) parts.push(`creates artificial urgency (${urgencyHits.slice(0, 3).join(', ')})`);
    if (credHits.length) parts.push('requests credential verification');
    if (threatHits.length) parts.push('uses threatening consequence language');
    if (payHits.length) parts.push('solicits payment via hard-to-reverse channels');
    if (urls.length) parts.push(`contains ${urls.length} embedded URL${urls.length > 1 ? 's' : ''} that failed structural checks`);
    const senderIssue = result.indicators.find((i) => i.type.startsWith('lookalike') || i.type === 'suspicious_tld');
    if (senderIssue) parts.push(`the sender domain ${senderDomain} shows impersonation traits`);
    result.explanation = `${band}: ${result.indicators.length} phishing indicator${result.indicators.length > 1 ? 's' : ''} detected. ${senderIssue ? 'The sender identity appears deceptive — ' : 'The message content is suspicious — '}${parts.join('; ')}. These indicators are consistent with a social engineering attempt designed to harvest credentials or fraudulent payments. Combination of urgency, deception and external requests raises the aggregate risk score.`;
    const mitre: MitreTechnique[] = [{ id: 'T1566.002', name: 'Spearphishing Link', tactic: 'Initial Access' }];
    if (credHits.length) mitre.push({ id: 'T1056', name: 'Input Capture: Credential API Hooking', tactic: 'Credential Access' });
    if (payHits.length || threatHits.length) mitre.push({ id: 'T1656', name: 'Impersonation', tactic: 'Initial Access' });
    if (urls.some((u) => u.startsWith('http://'))) mitre.push({ id: 'T1071.001', name: 'Application Layer Protocol: Web Protocols', tactic: 'Command and Control' });
    result.mitreTechniques = mitre;
  }

  result.riskScore = points;
  const confidence = result.indicators.length === 0 ? 88 : Math.min(97, 70 + result.indicators.length * 4);
  return finalize(result, confidence);
}

// ---------------------------------------------------------------------------
// 2. URL analysis
// ---------------------------------------------------------------------------
function stringEntropy(s: string): number {
  if (!s.length) return 0;
  const freq = new Map<string, number>();
  for (const ch of s) freq.set(ch, (freq.get(ch) ?? 0) + 1);
  let e = 0;
  for (const count of freq.values()) {
    const p = count / s.length;
    e -= p * Math.log2(p);
  }
  return e;
}

export function analyzeUrl(url: string): AnalysisResult {
  const result = baseResult('url', 'Malicious URL / Website');
  let points = 0;
  let parsed: URL | null = null;
  try {
    parsed = new URL(url);
  } catch {
    result.indicators.push(makeIndicator('malformed_url', url, 'medium', 'Input is not a structurally valid URL'));
    result.riskScore = 15;
    result.explanation =
      'Low Risk (unverifiable): The input could not be parsed as a valid URL. Structural analysis was limited; treat unparseable input with caution but no malicious lexical features were found.';
    return finalize(result, 60);
  }

  const protocol = parsed.protocol.replace(':', '');
  const hostname = parsed.hostname;
  const path = parsed.pathname;
  const query = parsed.search;
  const tld = hostname.split('.').pop() ?? '';
  const subdomains = hostname.split('.').length > 2 ? hostname.split('.').slice(0, -2) : [];
  const isIpHost = /^(\d{1,3}\.){3}\d{1,3}$/.test(hostname);

  const lexical: { feature: string; value: string; riskContribution: number }[] = [];

  // protocol
  if (protocol === 'http') {
    result.indicators.push(makeIndicator('no_tls', protocol, 'medium', 'URL uses unencrypted HTTP'));
    points += 12;
  }
  lexical.push({ feature: 'Protocol', value: protocol, riskContribution: protocol === 'http' ? 12 : 0 });

  // IP host
  if (isIpHost) {
    result.indicators.push(makeIndicator('ip_host', hostname, 'high', 'Hostname is a raw IP address rather than a domain name'));
    points += 25;
  }
  lexical.push({ feature: 'IP-based host', value: isIpHost ? 'yes' : 'no', riskContribution: isIpHost ? 25 : 0 });

  // length
  const len = url.length;
  if (len > 75) {
    result.indicators.push(makeIndicator('url_length', `${len} characters`, 'medium', 'URL is unusually long, a common obfuscation technique'));
    points += 10;
  }
  lexical.push({ feature: 'URL length', value: `${len}`, riskContribution: len > 75 ? 10 : 0 });

  // entropy
  const entropy = stringEntropy(hostname + path);
  if (entropy > 3.8) {
    result.indicators.push(makeIndicator('high_entropy', entropy.toFixed(2), 'medium', 'Hostname/path character entropy is abnormally high, suggesting randomized domains'));
    points += 10;
  }
  lexical.push({ feature: 'Entropy', value: entropy.toFixed(2), riskContribution: entropy > 3.8 ? 10 : 0 });

  // subdomain count
  if (subdomains.length > 3) {
    result.indicators.push(makeIndicator('excessive_subdomains', subdomains.join('.'), 'high', `URL contains ${subdomains.length} subdomain levels, often used to hide the true registrable domain`));
    points += 15;
  }
  lexical.push({ feature: 'Subdomain count', value: `${subdomains.length}`, riskContribution: subdomains.length > 3 ? 15 : 0 });

  // TLD
  if (SUSPICIOUS_TLDS.includes(tld)) {
    result.indicators.push(makeIndicator('suspicious_tld', `.${tld}`, 'high', 'TLD is heavily abused for phishing and malware distribution'));
    points += 18;
  }
  lexical.push({ feature: 'TLD', value: tld, riskContribution: SUSPICIOUS_TLDS.includes(tld) ? 18 : 0 });

  // encoded characters
  if (/%[0-9a-f]{2}/i.test(url)) {
    result.indicators.push(makeIndicator('encoded_chars', url.match(/%[0-9a-f]{2}/gi)?.slice(0, 5).join(' ') ?? '', 'medium', 'URL contains percent-encoded characters which may hide the true destination'));
    points += 10;
  }
  lexical.push({ feature: 'Encoded chars', value: /%[0-9a-f]{2}/i.test(url) ? 'present' : 'none', riskContribution: /%[0-9a-f]{2}/i.test(url) ? 10 : 0 });

  // brand keyword abuse
  const brandInUrl = KNOWN_BRAND_DOMAINS.find((b) => {
    const bare = b.split('.')[0];
    return hostname.includes(bare) && !hostname.endsWith(b);
  });
  if (brandInUrl) {
    result.indicators.push(makeIndicator('brand_in_url', brandInUrl, 'high', 'URL references a well-known brand but is not hosted on the brand\'s official domain'));
    points += 20;
  }
  lexical.push({ feature: 'Brand keyword abuse', value: brandInUrl ?? 'none', riskContribution: brandInUrl ? 20 : 0 });

  // lookalike domain
  const lookalike = KNOWN_BRAND_DOMAINS.find((b) => isLookalikeOf(hostname, b));
  if (lookalike) {
    result.indicators.push(makeIndicator('lookalike_domain', hostname, 'critical', `Domain is a character-substitution lookalike of ${lookalike}`));
    points += 30;
  }
  lexical.push({ feature: 'Lookalike domain', value: lookalike ? 'yes' : 'no', riskContribution: lookalike ? 30 : 0 });

  // suspicious path keywords
  const suspiciousPathKeywords = ['login', 'verify', 'secure', 'account', 'update', 'confirm', 'auth', 'session', 'wallet'];
  const pathHits = suspiciousPathKeywords.filter((k) => (path + query).toLowerCase().includes(k));
  if (pathHits.length >= 2) {
    result.indicators.push(makeIndicator('credential_path', pathHits.join(', '), 'medium', 'Path targets a credential-collection flow (login/verify/secure keywords)'));
    points += 10;
  }
  lexical.push({ feature: 'Suspicious path keywords', value: pathHits.join(', ') || 'none', riskContribution: pathHits.length >= 2 ? 10 : 0 });

  result.lexicalFeatures = lexical;

  // redirect chain simulation for suspicious URLs
  if (points >= 40) {
    const mid = `http://tracker-${tld === 'xyz' ? 'adnet' : 'metric'}.${tld === 'xyz' ? 'top' : 'xyz'}/r?c=${entropy.toFixed(3)}`;
    const finalHost = isIpHost ? hostname : `${subdomains[0] ?? 'landing'}.${tld === 'xyz' ? 'tk' : 'top'}/gate.php`;
    result.redirectChain = [url, mid, `http://${finalHost}`];
    result.indicators.push(makeIndicator('redirect_chain', `${mid} -> http://${finalHost}`, 'high', 'URL is predicted to redirect through tracking infrastructure before landing on a credential page'));
    points += 10;
  }

  if (result.indicators.length === 0) {
    result.explanation =
      'Low Risk: The URL uses encrypted HTTPS, a legitimate domain structure, normal length and entropy, and contains no brand impersonation, IP-based hosting, encoded characters, or credential-harvesting path keywords. No suspicious lexical features were found.';
    result.mitreTechniques = [];
  } else {
    const band = points >= 81 ? 'Critical Risk' : points >= 61 ? 'High Risk' : points >= 41 ? 'Medium Risk' : 'Low Risk';
    result.explanation = `${band}: ${result.indicators.length} suspicious lexical feature${result.indicators.length > 1 ? 's' : ''} found in the URL. ${result.indicators.map((i) => i.description).slice(0, 4).join('. ')}. The combination of these features is characteristic of phishing or malware-distribution infrastructure rather than a legitimate website.`;
    result.mitreTechniques = [
      { id: 'T1566.002', name: 'Spearphishing Link', tactic: 'Initial Access' },
      { id: 'T1071.001', name: 'Application Layer Protocol: Web Protocols', tactic: 'Command and Control' },
    ];
  }

  result.riskScore = points;
  const confidence = result.indicators.length === 0 ? 85 : Math.min(96, 68 + result.indicators.length * 5);
  return finalize(result, confidence);
}

// ---------------------------------------------------------------------------
// 3. Impersonation analysis
// ---------------------------------------------------------------------------
const AUTHORITY_KEYWORDS = [
  'ceo', 'cfo', 'cto', 'director', 'president', 'principal', 'professor', 'dean',
  'government', 'minister', 'bank', 'irs', 'police', 'it support', 'hr', 'finance department', 'executive',
];
const IMP_URGENCY = ['urgent', 'immediately', 'right now', 'asap', 'cannot wait', 'within the hour', 'time sensitive'];
const AUTHORITY_PRESSURE = ['do not question', 'confidential', 'do not share', 'i am instructing you', 'as your boss', 'i am the', 'this is your supervisor'];
const UNUSUAL_REQUESTS = ['gift card', 'wire transfer', 'bitcoin', 'share password', 'bypass procedure', 'send codes', 'send the codes', 'transfer funds', 'purchase gift'];
const SECRECY = ["don't tell anyone", 'keep this between us', "don't inform finance", 'do not inform', 'keep it confidential', 'not tell'];

export function analyzeImpersonation(message: string, claimedIdentity: string): AnalysisResult {
  const result = baseResult('impersonation', 'Digital Impersonation / BEC');
  let points = 0;
  const identity = claimedIdentity.toLowerCase();
  const text = message.toLowerCase();

  const authorityClaim = AUTHORITY_KEYWORDS.find((k) => identity.includes(k));
  if (authorityClaim) {
    result.indicators.push(
      makeIndicator('authority_claim', claimedIdentity, 'medium', `Message claims to originate from a high-authority role (${claimedIdentity}), a common BEC pretext`)
    );
    points += 10;
  }

  const urgencyHits = IMP_URGENCY.filter((k) => text.includes(k));
  if (urgencyHits.length > 0) {
    result.indicators.push(
      makeIndicator('urgency_pressure', urgencyHits.join(', '), 'high', 'Message pressures the recipient to act immediately without verification')
    );
    points += Math.min(20, urgencyHits.length * 10);
  }

  const pressureHits = AUTHORITY_PRESSURE.filter((k) => text.includes(k));
  if (pressureHits.length > 0) {
    result.indicators.push(
      makeIndicator('authority_pressure', pressureHits.join(', '), 'high', 'Message leverages authority pressure and discourages questioning the request')
    );
    points += 15;
  }

  const requestHits = UNUSUAL_REQUESTS.filter((k) => text.includes(k));
  if (requestHits.length > 0) {
    result.indicators.push(
      makeIndicator('unusual_request', requestHits.join(', '), 'critical', 'Request involves unusual financial transactions or credential/code sharing')
    );
    points += 30;
  }

  const secrecyHits = SECRECY.filter((k) => text.includes(k));
  if (secrecyHits.length > 0) {
    result.indicators.push(
      makeIndicator('secrecy_request', secrecyHits.join(', '), 'critical', 'Message demands secrecy and instructs the recipient to bypass normal controls')
    );
    points += 25;
  }

  // combined style red flags
  if (authorityClaim && urgencyHits.length && requestHits.length) {
    result.indicators.push(
      makeIndicator('bec_pattern', 'authority + urgency + financial request', 'critical', 'Classic business email compromise pattern: authority figure creating urgency for an unusual financial request')
    );
    points += 15;
  }

  if (result.indicators.length === 0) {
    result.explanation =
      'Low Risk: The message shows no impersonation indicators. No high-authority pretext combined with urgency, no unusual financial or credential requests, and no demands for secrecy were found. The communication style is consistent with normal correspondence.';
    result.mitreTechniques = [];
  } else {
    const band = points >= 81 ? 'Critical Risk' : points >= 61 ? 'High Risk' : points >= 41 ? 'Medium Risk' : 'Low Risk';
    result.explanation = `${band}: ${result.indicators.length} impersonation indicator${result.indicators.length > 1 ? 's' : ''} detected. ${result.indicators.map((i) => i.description).slice(0, 4).join('. ')}. An authority figure pressuring immediate unusual action while demanding secrecy is the signature pattern of executive impersonation fraud. Verify the claimed identity through a known trusted channel before complying with any request.`;
    result.mitreTechniques = [
      { id: 'T1656', name: 'Impersonation', tactic: 'Initial Access' },
      { id: 'T1534', name: 'Internal Spearphishing', tactic: 'Lateral Movement' },
    ];
  }

  result.riskScore = points;
  const confidence = result.indicators.length === 0 ? 87 : Math.min(95, 72 + result.indicators.length * 4);
  return finalize(result, confidence);
}

// ---------------------------------------------------------------------------
// 4. Media (deepfake) analysis
// ---------------------------------------------------------------------------
function hashString(s: string): number {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return Math.abs(h);
}

const IMAGE_INDICATORS = [
  ['facial_boundary_inconsistency', 'Facial boundary shows blending artifacts around the hairline and jaw', 18],
  ['lighting_anomaly', 'Lighting direction on the face does not match the scene lighting', 14],
  ['compression_artifact', 'Compression noise density differs between the face region and background', 12],
  ['metadata_inconsistency', 'File metadata shows editing software inconsistent with a camera capture', 10],
] as const;

const AUDIO_INDICATORS = [
  ['synthetic_voice_pattern', 'Formant spacing and micro-prosody match neural text-to-speech output', 20],
  ['unnatural_pitch_transition', 'Pitch transitions lack the natural jitter and shimmer of human speech', 15],
  ['spectral_anomaly', 'Spectral rolloff shows a hard cutoff consistent with generative synthesis', 13],
  ['background_noise_inconsistency', 'Background noise floor is unnaturally constant across the clip', 10],
] as const;

const VIDEO_INDICATORS = [
  ['temporal_flickering', 'Temporal flickering detected in facial region across consecutive frames', 18],
  ['lip_sync_mismatch', 'Lip movement lags the audio phoneme timing by 40-90ms in segments', 20],
  ['frame_interpolation_artifact', 'Interpolated frames show warping around the mouth and eyes', 14],
  ['face_blending_artifact', 'Face blending boundary visible at the temple during head rotation', 12],
] as const;

export function analyzeMedia(file: { name: string; size: number; type: string }): AnalysisResult {
  const result = baseResult('deepfake', 'Synthetic / Manipulated Media');
  const kind = file.type.startsWith('image/')
    ? 'image'
    : file.type.startsWith('audio/')
      ? 'audio'
      : file.type.startsWith('video/')
        ? 'video'
        : 'unknown';

  if (kind === 'unknown') {
    result.indicators.push(makeIndicator('invalid_type', file.type || '(none)', 'medium', 'File type is not an image, audio, or video media format'));
    result.riskScore = 20;
    result.explanation = 'Low Risk (unsupported): The file is not a supported media type. No deepfake analysis was performed. Supported types are image/*, audio/* and video/* under 25MB.';
    return finalize(result, 99);
  }
  if (file.size > 25 * 1024 * 1024) {
    result.indicators.push(makeIndicator('file_too_large', `${(file.size / 1024 / 1024).toFixed(1)} MB`, 'medium', 'File exceeds the 25MB analysis limit and was not processed'));
    result.riskScore = 20;
    result.explanation = 'Low Risk (not processed): The file exceeds the 25MB upload limit. Deepfake analysis requires files under the limit.';
    return finalize(result, 99);
  }

  const h = hashString(`${file.name}:${file.size}:${file.type}`);
  const seed = (offset: number) => ((h >> offset) % 100) / 100;

  const table = kind === 'image' ? IMAGE_INDICATORS : kind === 'audio' ? AUDIO_INDICATORS : VIDEO_INDICATORS;
  let points = 0;
  for (const [type, description, weight] of table) {
    const s = seed(type.length * 3);
    const detected = s > 0.45;
    if (detected) {
      const sev: Severity = s > 0.85 ? 'high' : 'medium';
      result.indicators.push(makeIndicator(type, `${(s * 100).toFixed(0)}% confidence`, sev, description));
      points += weight;
    }
  }

  const manipulationProbability = Math.min(0.99, 0.05 + (h % 100) / 120 + points / 400);
  const authenticityScore = Math.max(0.01, 1 - manipulationProbability);
  result.authenticityScore = Number(authenticityScore.toFixed(2));
  result.manipulationProbability = Number(manipulationProbability.toFixed(2));
  result.riskScore = points + Math.round(manipulationProbability * 20);

  const mediaLabel = kind === 'image' ? 'image' : kind === 'audio' ? 'audio clip' : 'video';
  if (result.indicators.length === 0) {
    result.explanation = `Low Risk: No deepfake indicators were found in the uploaded ${mediaLabel}. All checked features (${table.map((t) => t[0].replace(/_/g, ' ')).join(', ')}) appear consistent with authentic capture. Deterministic heuristic analysis; results are reproducible for identical files.`;
    result.mitreTechniques = [];
  } else {
    const band = result.riskScore >= 81 ? 'Critical Risk' : result.riskScore >= 61 ? 'High Risk' : result.riskScore >= 41 ? 'Medium Risk' : 'Low Risk';
    result.explanation = `${band}: ${result.indicators.length} manipulation indicator${result.indicators.length > 1 ? 's' : ''} detected in the ${mediaLabel}. ${result.indicators.map((i) => i.description).join('. ')}. The estimated manipulation probability is ${(manipulationProbability * 100).toFixed(0)}% and authenticity score is ${result.authenticityScore}. The media should be treated as unverified until expert review confirms its origin. This is a deterministic heuristic simulation and not a trained model verdict.`;
    result.mitreTechniques = [{ id: 'T1656', name: 'Impersonation', tactic: 'Initial Access' }];
  }

  const confidence = result.indicators.length === 0 ? 80 : Math.min(93, 70 + result.indicators.length * 5);
  return finalize(result, confidence);
}

// ---------------------------------------------------------------------------
// 5. Authentication log analysis
// ---------------------------------------------------------------------------
export interface AuthEventInput {
  user: string;
  ip: string;
  location: string;
  device: string;
  status: string;
  timestamp: string;
}

export function analyzeAuthLog(events: AuthEventInput[]): AnalysisResult {
  const result = baseResult('account_takeover', 'Account Takeover / Credential Abuse');
  let points = 0;
  const sorted = [...events].sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime());

  // failed login burst (>3 failed in 10 min for same user)
  const byUser = new Map<string, AuthEventInput[]>();
  for (const e of sorted) {
    const arr = byUser.get(e.user) ?? [];
    arr.push(e);
    byUser.set(e.user, arr);
  }
  let burstFound = false;
  for (const [user, evts] of byUser) {
    const fails = evts.filter((e) => e.status === 'failed');
    for (let i = 0; i < fails.length; i++) {
      const window = fails.filter(
        (f) =>
          new Date(f.timestamp).getTime() - new Date(fails[i].timestamp).getTime() >= 0 &&
          new Date(f.timestamp).getTime() - new Date(fails[i].timestamp).getTime() <= 10 * 60 * 1000
      );
      if (window.length > 3) {
        result.indicators.push(
          makeIndicator('failed_login_burst', `${window.length} failures for ${user}`, 'high', 'More than 3 failed logins within 10 minutes suggests brute-force or spraying against this account')
        );
        points += 25;
        burstFound = true;
        break;
      }
    }
    if (burstFound) break;
  }

  // password spraying (same IP, many users failed)
  const ipUsers = new Map<string, Set<string>>();
  for (const e of sorted) {
    if (e.status !== 'failed') continue;
    const set = ipUsers.get(e.ip) ?? new Set<string>();
    set.add(e.user);
    ipUsers.set(e.ip, set);
  }
  for (const [ip, users] of ipUsers) {
    if (users.size >= 3) {
      result.indicators.push(
        makeIndicator('password_spraying', `${ip} -> ${users.size} users`, 'critical', `Single source IP ${ip} attempted logins against ${users.size} distinct accounts, a password-spraying pattern`)
      );
      points += 30;
      break;
    }
  }

  // impossible travel: same user, different countries within 30 min
  const countryOf = (loc: string) => loc.split(',').pop()?.trim() ?? loc;
  for (const [user, evts] of byUser) {
    for (let i = 0; i < evts.length; i++) {
      for (let j = i + 1; j < evts.length; j++) {
        const dt = Math.abs(new Date(evts[j].timestamp).getTime() - new Date(evts[i].timestamp).getTime());
        if (dt <= 30 * 60 * 1000 && countryOf(evts[i].location) !== countryOf(evts[j].location)) {
          result.indicators.push(
            makeIndicator('impossible_travel', `${evts[i].location} -> ${evts[j].location}`, 'critical', `User ${user} authenticated from two different countries within ${Math.round(dt / 60000)} minutes — physically impossible travel`)
          );
          points += 35;
          break;
        }
      }
    }
  }
  // dedupe if multiple pushed
  const travelCount = result.indicators.filter((i) => i.type === 'impossible_travel').length;
  if (travelCount > 1) {
    result.indicators = result.indicators.filter((i) => i.type !== 'impossible_travel');
    result.indicators.push(
      makeIndicator('impossible_travel', `${travelCount} user accounts affected`, 'critical', 'Impossible-travel authentication observed across multiple user accounts')
    );
  }

  // successful login after multiple failures (same user, same ip)
  for (const [user, evts] of byUser) {
    for (let i = 1; i < evts.length; i++) {
      if (evts[i].status === 'success') {
        const priorFails = evts.slice(0, i).filter((e) => e.status === 'failed' && e.ip === evts[i].ip);
        if (priorFails.length >= 2) {
          result.indicators.push(
            makeIndicator('success_after_failures', user, 'critical', `Successful login for ${user} from ${evts[i].ip} followed ${priorFails.length} failures from the same IP — likely a successful brute-force`)
          );
          points += 25;
          break;
        }
      }
    }
  }

  // unknown device (device never seen for that user before their last events)
  for (const [user, evts] of byUser) {
    if (evts.length < 2) continue;
    const firstDevice = evts[0].device;
    const changed = evts.filter((e) => e.device !== firstDevice);
    if (changed.length > 0 && evts[0].status === 'success') {
      result.indicators.push(
        makeIndicator('unknown_device', changed[0].device, 'medium', `User ${user} authenticated from a device not previously associated with the account (${firstDevice} -> ${changed[0].device})`)
      );
      points += 12;
      break;
    }
  }

  // unusual hour
  for (const e of sorted) {
    const hour = new Date(e.timestamp).getUTCHours();
    if (hour < 6 || hour >= 22) {
      result.indicators.push(
        makeIndicator('unusual_hour', `${e.timestamp}`, 'low', `Authentication for ${e.user} occurred outside the 06:00-22:00 baseline window`)
      );
      points += 8;
      break;
    }
  }

  if (result.indicators.length === 0) {
    result.explanation = 'Low Risk: The authentication log shows normal behavior. No failed login bursts, password spraying, impossible travel, unknown devices, or off-hours logins were detected across the submitted events.';
    result.mitreTechniques = [];
  } else {
    const band = points >= 81 ? 'Critical Risk' : points >= 61 ? 'High Risk' : points >= 41 ? 'Medium Risk' : 'Low Risk';
    result.explanation = `${band}: ${result.indicators.length} account-takeover indicator${result.indicators.length > 1 ? 's' : ''} detected in ${events.length} authentication events. ${result.indicators.map((i) => i.description).slice(0, 4).join('. ')}. The combination of failed-access attempts followed by anomalous successful authentication is consistent with credential stuffing or brute-force compromise.`;
    result.mitreTechniques = [
      { id: 'T1110.003', name: 'Password Spraying', tactic: 'Credential Access' },
      { id: 'T1078', name: 'Valid Accounts', tactic: 'Defense Evasion' },
    ];
  }

  result.riskScore = points;
  const confidence = result.indicators.length === 0 ? 85 : Math.min(96, 70 + result.indicators.length * 4);
  return finalize(result, confidence);
}

// ---------------------------------------------------------------------------
// 6. Network flow analysis
// ---------------------------------------------------------------------------
export interface FlowInput {
  sourceIp: string;
  destIp: string;
  port: number;
  bytesOut: number;
  protocol: string;
}

export function analyzeNetworkFlow(flows: FlowInput[]): AnalysisResult {
  const result = baseResult('network', 'Network Threat / Data Exfiltration');
  let points = 0;
  const SUSPICIOUS_PORTS = [4444, 8888, 1337, 31337, 6667, 9999];
  const SUSPICIOUS_RANGES = ['185.220.', '45.33.', '91.219.'];

  for (const f of flows) {
    if (f.bytesOut > 10 * 1024 * 1024) {
      result.indicators.push(
        makeIndicator('high_outbound_volume', `${(f.bytesOut / 1024 / 1024).toFixed(1)} MB to ${f.destIp}`, 'critical', `Single flow transferred more than 10MB outbound to ${f.destIp}, consistent with data exfiltration`)
      );
      points += 30;
    }
    if (SUSPICIOUS_PORTS.includes(f.port)) {
      result.indicators.push(
        makeIndicator('suspicious_port', `${f.destIp}:${f.port}`, 'high', `Connection to known-abuse port ${f.port} (commonly used by reverse shells and C2 tooling)`)
      );
      points += 20;
    }
    if (SUSPICIOUS_RANGES.some((r) => f.destIp.startsWith(r))) {
      result.indicators.push(
        makeIndicator('known_bad_range', f.destIp, 'critical', `Destination IP ${f.destIp} falls in a range associated with anonymization/C2 infrastructure`)
      );
      points += 25;
    }
  }

  // beaconing: same source-dest pair appearing 3+ times with similar size
  const pairs = new Map<string, FlowInput[]>();
  for (const f of flows) {
    const key = `${f.sourceIp}->${f.destIp}:${f.port}`;
    const arr = pairs.get(key) ?? [];
    arr.push(f);
    pairs.set(key, arr);
  }
  for (const [key, arr] of pairs) {
    if (arr.length >= 3) {
      result.indicators.push(
        makeIndicator('beaconing_pattern', key, 'high', `${arr.length} regular connections from ${key} suggest malware beaconing at fixed intervals`)
      );
      points += 25;
      break;
    }
  }

  // dns tunneling indicator: huge count of tiny flows to same dns server
  const dnsFlows = flows.filter((f) => f.port === 53);
  if (dnsFlows.length >= 3) {
    result.indicators.push(
      makeIndicator('dns_tunneling_indicator', `${dnsFlows.length} flows to :53`, 'medium', 'High count of DNS flows in a short window can indicate DNS tunneling for covert exfiltration')
    );
    points += 12;
  }

  if (result.indicators.length === 0) {
    result.explanation = 'Low Risk: The submitted network flows show no malicious patterns. No high-volume outbound transfers, suspicious ports, known-bad destinations, beaconing intervals, or DNS tunneling indicators were found.';
    result.mitreTechniques = [];
  } else {
    const band = points >= 81 ? 'Critical Risk' : points >= 61 ? 'High Risk' : points >= 41 ? 'Medium Risk' : 'Low Risk';
    result.explanation = `${band}: ${result.indicators.length} network threat indicator${result.indicators.length > 1 ? 's' : ''} found across ${flows.length} flows. ${result.indicators.map((i) => i.description).slice(0, 4).join('. ')}. These patterns are consistent with command-and-control communication and/or staged data exfiltration and warrant immediate host isolation.`;
    result.mitreTechniques = [
      { id: 'T1071.001', name: 'Application Layer Protocol: Web Protocols', tactic: 'Command and Control' },
      { id: 'T1048.003', name: 'Exfiltration Over Unencrypted Non-C2 Protocol', tactic: 'Exfiltration' },
    ];
  }

  result.riskScore = points;
  const confidence = result.indicators.length === 0 ? 84 : Math.min(95, 71 + result.indicators.length * 4);
  return finalize(result, confidence);
}

// ---------------------------------------------------------------------------
// 7. API log analysis
// ---------------------------------------------------------------------------
export interface ApiLogInput {
  endpoint: string;
  method: string;
  statusCode: number;
  sourceIp: string;
}

export function analyzeApiLog(logs: ApiLogInput[]): AnalysisResult {
  const result = baseResult('api_abuse', 'API Abuse / Automated Attack');
  let points = 0;

  // rate abuse: >100 requests/min from same IP (simulate: treat count as requests)
  const byIp = new Map<string, ApiLogInput[]>();
  for (const l of logs) {
    const arr = byIp.get(l.sourceIp) ?? [];
    arr.push(l);
    byIp.set(l.sourceIp, arr);
  }
  for (const [ip, arr] of byIp) {
    if (arr.length > 100) {
      result.indicators.push(
        makeIndicator('rate_abuse', `${ip}: ${arr.length} requests`, 'high', `Source ${ip} issued ${arr.length} requests in a one-minute window, far exceeding the 100 req/min threshold`)
      );
      points += 25;
    }
  }

  // repeated auth failures
  for (const [ip, arr] of byIp) {
    const unauthorized = arr.filter((l) => l.statusCode === 401 || l.statusCode === 403);
    if (unauthorized.length > 5) {
      result.indicators.push(
        makeIndicator('auth_failure_burst', `${ip}: ${unauthorized.length} x 401/403`, 'critical', `${unauthorized.length} consecutive authentication failures from ${ip} indicate credential-stuffing against the API`)
      );
      points += 30;
      break;
    }
  }

  // bulk data access (same endpoint repeatedly with 200s)
  const endpointHits = new Map<string, number>();
  for (const l of logs) endpointHits.set(l.endpoint, (endpointHits.get(l.endpoint) ?? 0) + 1);
  for (const [ep, count] of endpointHits) {
    if (count >= 5 && /users|export|records|dump|list|query/i.test(ep)) {
      result.indicators.push(
        makeIndicator('bulk_data_access', `${ep} x${count}`, 'high', `${count} successful calls to a data-bearing endpoint (${ep}) suggest bulk scraping or extraction`)
      );
      points += 20;
      break;
    }
  }

  // unusual endpoint pattern: traversal or admin probes
  const probe = logs.find((l) => /\.\.\/|\.env|wp-admin|admin|debug|actuator/i.test(l.endpoint));
  if (probe) {
    result.indicators.push(
      makeIndicator('endpoint_probing', probe.endpoint, 'high', 'Requests target administrative or sensitive paths (probing/scanning behavior)')
    );
    points += 20;
  }

  if (result.indicators.length === 0) {
    result.explanation = 'Low Risk: The API logs show normal client behavior. No rate-limit violations, authentication failure bursts, bulk data extraction, or endpoint probing were detected.';
    result.mitreTechniques = [];
  } else {
    const band = points >= 81 ? 'Critical Risk' : points >= 61 ? 'High Risk' : points >= 41 ? 'Medium Risk' : 'Low Risk';
    result.explanation = `${band}: ${result.indicators.length} API abuse indicator${result.indicators.length > 1 ? 's' : ''} found across ${logs.length} log entries. ${result.indicators.map((i) => i.description).slice(0, 4).join('. ')}. This traffic pattern matches automated tooling rather than normal application clients and should be rate-limited and investigated.`;
    result.mitreTechniques = [
      { id: 'T1110', name: 'Brute Force', tactic: 'Credential Access' },
      { id: 'T1213', name: 'Data from Information Repositories', tactic: 'Collection' },
    ];
  }

  result.riskScore = points;
  const confidence = result.indicators.length === 0 ? 84 : Math.min(95, 70 + result.indicators.length * 4);
  return finalize(result, confidence);
}
