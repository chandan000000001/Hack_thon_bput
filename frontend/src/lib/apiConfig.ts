/**
 * Dynamic API Base URL resolver for CYBERGUARD.
 *
 * Automatically detects whether the user is accessing the app from:
 * 1. Localhost (e.g. http://localhost:5173, http://127.0.0.1:5173) -> http://localhost:8000/api/v1
 * 2. Cloudflare Tunnel (e.g. https://*.trycloudflare.com) -> https://treasures-paste-trips-left.trycloudflare.com/api/v1
 * 3. Local Network IP (e.g. http://192.168.x.x:5173) -> http://<ip>:8000/api/v1
 *
 * Also allows manual override via localStorage.setItem('CYBERGUARD_API_BASE_URL', '...').
 */

export function getApiBaseUrl(): string {
  // 1. Check for manual override in localStorage (useful for testing/debugging)
  if (typeof window !== 'undefined' && window.localStorage) {
    try {
      const override = window.localStorage.getItem('CYBERGUARD_API_BASE_URL');
      if (override) return override.replace(/\/+$/, '');
    } catch {
      // Ignore storage access errors in restricted iframe/browser modes
    }
  }

  const envUrl = import.meta.env.VITE_API_BASE_URL?.trim();
  const cloudflareEnvUrl = import.meta.env.VITE_CLOUDFLARE_API_BASE_URL?.trim();

  const defaultLocalUrl = 'http://localhost:8000/api/v1';
  const defaultCloudflareUrl = 'https://treasures-paste-trips-left.trycloudflare.com/api/v1';

  const isEnvCloudflare = Boolean(envUrl && envUrl.includes('trycloudflare.com'));
  const isEnvLocal = Boolean(envUrl && (envUrl.includes('localhost') || envUrl.includes('127.0.0.1')));

  const localApiUrl = (isEnvLocal ? envUrl : defaultLocalUrl) || defaultLocalUrl;
  const cloudflareApiUrl = cloudflareEnvUrl || (isEnvCloudflare ? envUrl : defaultCloudflareUrl) || defaultCloudflareUrl;

  // 2. Runtime browser location detection
  if (typeof window !== 'undefined' && window.location) {
    const { hostname, protocol } = window.location;

    // A) Localhost or Loopback IP
    if (hostname === 'localhost' || hostname === '127.0.0.1' || hostname === '[::1]') {
      return localApiUrl.replace(/\/+$/, '');
    }

    // B) Cloudflare Tunnel or HTTPS access
    if (hostname.endsWith('trycloudflare.com') || protocol === 'https:') {
      return cloudflareApiUrl.replace(/\/+$/, '');
    }

    // C) Local LAN IP access (e.g. 192.168.x.x, 10.x.x.x, 172.16-31.x.x)
    if (/^(192\.168\.|10\.|172\.(1[6-9]|2[0-9]|3[0-1])\.)/.test(hostname)) {
      return `http://${hostname}:8000/api/v1`;
    }
  }

  // 3. Fallback to configured or local default
  return (envUrl || defaultLocalUrl).replace(/\/+$/, '');
}
