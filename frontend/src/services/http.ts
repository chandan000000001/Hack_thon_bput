import { supabase } from '../lib/supabaseClient';
import { useAuthStore } from '../store/authStore';
import { getApiBaseUrl } from '../lib/apiConfig';

export class ApiError extends Error {
  status?: number;

  constructor(message: string, status?: number) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

function extractErrorDetail(body: unknown, res: Response): string {
  if (body && typeof body === 'object') {
    const record = body as Record<string, unknown>;
    if (typeof record.detail === 'string') return record.detail;
    if (Array.isArray(record.detail)) {
      // FastAPI validation errors: [{ msg, loc, type }, ...]
      return record.detail
        .map((item) => (item && typeof item === 'object' ? String((item as Record<string, unknown>).msg ?? '') : String(item)))
        .filter(Boolean)
        .join('; ');
    }
    if (typeof record.message === 'string') return record.message;
  }
  return `API error ${res.status}: ${res.statusText}`;
}

async function parseErrorResponse(res: Response): Promise<ApiError> {
  try {
    const body = await res.json();
    return new ApiError(extractErrorDetail(body, res), res.status);
  } catch {
    return new ApiError(`API error ${res.status}: ${res.statusText}`, res.status);
  }
}

export async function apiFetch(path: string, options: RequestInit = {}): Promise<any> {
  const isFormData = options.body instanceof FormData;
  const baseUrl = getApiBaseUrl();
  const execute = (token: string | null) =>
    fetch(`${baseUrl}${path}`, {
      ...options,
      headers: {
        ...(isFormData ? {} : { 'Content-Type': 'application/json' }),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...(options.headers ?? {}),
      },
    });

  let res = await execute(useAuthStore.getState().getToken());

  // On 401, refresh the Supabase session once and retry with the new token.
  if (res.status === 401) {
    const { error } = await supabase.auth.refreshSession();
    const freshToken = (await supabase.auth.getSession()).data.session?.access_token ?? null;
    if (error || !freshToken) {
      await useAuthStore.getState().logout();
      throw new ApiError('Session expired. Please sign in again.', 401);
    }
    useAuthStore.getState().setAccessToken(freshToken);
    res = await execute(freshToken);
  }

  if (!res.ok) throw await parseErrorResponse(res);
  if (res.status === 204) return null;
  return res.json();
}
