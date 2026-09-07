import { createClient } from '@supabase/supabase-js';

// Browser-side Supabase client: anon key only, scoped by RLS.
// The service role key must never appear in the frontend.
export const supabase = createClient(
  import.meta.env.VITE_SUPABASE_URL ?? '',
  import.meta.env.VITE_SUPABASE_ANON_KEY ?? ''
);
