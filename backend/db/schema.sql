-- ============================================================================
-- CYBERGUARD Supabase Schema (Part 1)
-- Execute this file in the Supabase SQL editor (Database -> SQL editor).
-- The service_role key used by the backend bypasses RLS automatically.
-- ============================================================================

-- ---------------------------------------------------------------------------
-- Extensions
-- ---------------------------------------------------------------------------
create extension if not exists pgcrypto;

-- Optional: pgvector is only needed by later detection parts (embeddings).
-- If the extension is not available in your Supabase project, comment out
-- the next line and re-run; nothing else in Part 1 depends on it.
create extension if not exists vector;

-- ---------------------------------------------------------------------------
-- Enum types
-- ---------------------------------------------------------------------------
create type severity_level as enum ('safe', 'low', 'medium', 'high', 'critical');
create type threat_module as enum ('phishing', 'url', 'impersonation', 'deepfake', 'account_takeover', 'network', 'api_abuse');
create type event_status as enum ('received', 'analyzing', 'completed', 'failed');
create type alert_status as enum ('new', 'acknowledged', 'resolved', 'dismissed');
create type incident_status as enum ('open', 'investigating', 'contained', 'closed');
create type automation_level as enum ('automatic', 'semi-automatic', 'manual');
create type execution_status as enum ('pending', 'approved', 'executed', 'rejected');

-- ---------------------------------------------------------------------------
-- Tables
-- ---------------------------------------------------------------------------

create table profiles (
    id uuid primary key references auth.users (id) on delete cascade,
    full_name text,
    role text not null default 'analyst',
    created_at timestamptz not null default now()
);

create table events (
    id uuid primary key default gen_random_uuid(),
    event_type text not null,
    source text not null,
    raw_data jsonb not null default '{}',
    status event_status not null default 'received',
    created_at timestamptz not null default now()
);

create table media_files (
    id uuid primary key default gen_random_uuid(),
    event_id uuid references events (id) on delete cascade,
    file_name text,
    storage_path text,
    file_type text,
    size_bytes bigint,
    file_hash text,
    created_at timestamptz not null default now()
);

create table alerts (
    id uuid primary key default gen_random_uuid(),
    event_id uuid references events (id) on delete set null,
    title text not null,
    module threat_module not null,
    threat_type text,
    severity severity_level not null,
    risk_score integer not null check (risk_score between 0 and 100),
    confidence numeric(5, 4),
    status alert_status not null default 'new',
    summary text,
    indicators jsonb not null default '[]',
    explanation text,
    mitre jsonb not null default '[]',
    target_user text,
    target_service text,
    source_ip text,
    created_at timestamptz not null default now()
);

create table recommended_actions (
    id uuid primary key default gen_random_uuid(),
    alert_id uuid references alerts (id) on delete cascade,
    action text not null,
    description text,
    automation_level automation_level not null default 'manual',
    requires_approval boolean not null default false,
    priority severity_level not null default 'low',
    executed boolean not null default false,
    executed_at timestamptz,
    created_at timestamptz not null default now()
);

create table incidents (
    id uuid primary key default gen_random_uuid(),
    title text not null,
    severity severity_level not null,
    status incident_status not null default 'open',
    assigned_to text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table incident_alerts (
    incident_id uuid references incidents (id) on delete cascade,
    alert_id uuid references alerts (id) on delete cascade,
    primary key (incident_id, alert_id)
);

create table incident_events (
    id uuid primary key default gen_random_uuid(),
    incident_id uuid references incidents (id) on delete cascade,
    action text not null,
    actor text not null,
    details text,
    created_at timestamptz not null default now()
);

create table response_catalog (
    id uuid primary key default gen_random_uuid(),
    action text not null,
    target_type text,
    automation_level automation_level not null default 'manual',
    requires_approval boolean not null default false,
    description text
);

create table response_executions (
    id uuid primary key default gen_random_uuid(),
    catalog_id uuid references response_catalog (id) on delete set null,
    action_name text not null,
    target text,
    status execution_status not null default 'pending',
    executed_by text,
    approved_by text,
    created_at timestamptz not null default now()
);

create table audit_logs (
    id uuid primary key default gen_random_uuid(),
    user_id uuid,
    user_name text,
    action text not null,
    resource text,
    details text,
    created_at timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- Indexes
-- ---------------------------------------------------------------------------
create index idx_alerts_severity on alerts (severity);
create index idx_alerts_module on alerts (module);
create index idx_alerts_created_at on alerts (created_at);
create index idx_events_status on events (status);
create index idx_audit_logs_created_at on audit_logs (created_at);
create index idx_incident_alerts_alert_id on incident_alerts (alert_id);

-- ---------------------------------------------------------------------------
-- Row Level Security
-- The backend uses the service_role key, which bypasses RLS automatically.
-- These policies govern direct client access (e.g. Supabase JS with anon key).
-- ---------------------------------------------------------------------------

alter table profiles enable row level security;
alter table events enable row level security;
alter table media_files enable row level security;
alter table alerts enable row level security;
alter table recommended_actions enable row level security;
alter table incidents enable row level security;
alter table incident_alerts enable row level security;
alter table incident_events enable row level security;
alter table response_catalog enable row level security;
alter table response_executions enable row level security;
alter table audit_logs enable row level security;

-- profiles: owning user can read and update their own profile
create policy "profiles_select_own" on profiles
    for select to authenticated
    using (auth.uid() = id);

create policy "profiles_update_own" on profiles
    for update to authenticated
    using (auth.uid() = id)
    with check (auth.uid() = id);

-- Read access for all authenticated users
create policy "events_select_authenticated" on events
    for select to authenticated using (true);
create policy "media_files_select_authenticated" on media_files
    for select to authenticated using (true);
create policy "alerts_select_authenticated" on alerts
    for select to authenticated using (true);
create policy "recommended_actions_select_authenticated" on recommended_actions
    for select to authenticated using (true);
create policy "incidents_select_authenticated" on incidents
    for select to authenticated using (true);
create policy "incident_alerts_select_authenticated" on incident_alerts
    for select to authenticated using (true);
create policy "incident_events_select_authenticated" on incident_events
    for select to authenticated using (true);
create policy "response_catalog_select_authenticated" on response_catalog
    for select to authenticated using (true);
create policy "response_executions_select_authenticated" on response_executions
    for select to authenticated using (true);
create policy "audit_logs_select_authenticated" on audit_logs
    for select to authenticated using (true);

-- Write access for authenticated users (ingest/mutate tables)
create policy "events_insert_authenticated" on events
    for insert to authenticated with check (true);
create policy "events_update_authenticated" on events
    for update to authenticated with check (true);

create policy "alerts_insert_authenticated" on alerts
    for insert to authenticated with check (true);
create policy "alerts_update_authenticated" on alerts
    for update to authenticated with check (true);

create policy "incidents_insert_authenticated" on incidents
    for insert to authenticated with check (true);
create policy "incidents_update_authenticated" on incidents
    for update to authenticated with check (true);

create policy "incident_alerts_insert_authenticated" on incident_alerts
    for insert to authenticated with check (true);
create policy "incident_alerts_update_authenticated" on incident_alerts
    for update to authenticated with check (true);

create policy "incident_events_insert_authenticated" on incident_events
    for insert to authenticated with check (true);
create policy "incident_events_update_authenticated" on incident_events
    for update to authenticated with check (true);

create policy "recommended_actions_insert_authenticated" on recommended_actions
    for insert to authenticated with check (true);
create policy "recommended_actions_update_authenticated" on recommended_actions
    for update to authenticated with check (true);

create policy "response_executions_insert_authenticated" on response_executions
    for insert to authenticated with check (true);
create policy "response_executions_update_authenticated" on response_executions
    for update to authenticated with check (true);

create policy "audit_logs_insert_authenticated" on audit_logs
    for insert to authenticated with check (true);
create policy "audit_logs_update_authenticated" on audit_logs
    for update to authenticated with check (true);

-- ---------------------------------------------------------------------------
-- Auto-create a profile row for every new auth user
-- ---------------------------------------------------------------------------
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
    insert into public.profiles (id, full_name)
    values (
        new.id,
        coalesce(new.raw_user_meta_data ->> 'full_name', new.email)
    )
    on conflict (id) do nothing;
    return new;
end;
$$;

create trigger on_auth_user_created
    after insert on auth.users
    for each row
    execute function public.handle_new_user();

-- ---------------------------------------------------------------------------
-- Seed: response catalog (recommended response actions)
-- ---------------------------------------------------------------------------
insert into response_catalog (action, target_type, automation_level, requires_approval, description) values
    ('Block suspicious URL', 'url', 'semi-automatic', true,
     'Add the URL to the blocklist and deny access from managed endpoints.'),
    ('Quarantine email', 'email', 'semi-automatic', true,
     'Move the suspicious email out of user inboxes into quarantine.'),
    ('Warn the user', 'user', 'automatic', false,
     'Notify the targeted user about the threat and safe handling steps.'),
    ('Require additional authentication', 'session', 'automatic', false,
     'Force step-up authentication (e.g. MFA) for the affected account.'),
    ('Revoke active session', 'session', 'semi-automatic', true,
     'Terminate the suspicious session and force re-authentication.'),
    ('Block suspicious IP/device', 'network', 'semi-automatic', true,
     'Block the flagged IP address or device identifier at the perimeter.'),
    ('Flag multimedia for manual verification', 'media', 'manual', false,
     'Mark the media item for human review by an analyst.'),
    ('Report impersonation', 'external', 'manual', false,
     'Report the impersonation attempt to the affected brand or platform.'),
    ('Notify administrator/SOC', 'notification', 'automatic', false,
     'Send an alert to the administrator or SOC channel for triage.'),
    ('Escalate the incident for investigation', 'incident', 'semi-automatic', true,
     'Escalate the incident to senior analysts for deeper investigation.');
