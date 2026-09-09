-- ============================================================================
-- CYBERGUARD Migration 0005: Permission Matrix (RBAC v2) — IDEMPOTENT
-- Run this whole file in the Supabase SQL editor (Database -> SQL editor).
-- Safe to re-run: seeds use upsert semantics and never duplicate rows.
--
-- What it does:
--   1. Creates the permissions table (granular permission keys).
--   2. Creates the role_permissions join table (role -> permission keys).
--   3. Seeds the 16 permission keys and the viewer/analyst/admin matrix.
--
-- Roles remain viewer < analyst < admin, but every protected endpoint now
-- checks a granular permission key via app/core/security.py
-- (get_role_permissions + require_permission) instead of a coarse role check.
-- The backend resolves permissions with the service-role client (which
-- bypasses RLS) and caches them per role for 5 minutes. If this migration
-- has not been applied yet, security.py falls back to the same matrix
-- hardcoded in code, so the demo keeps working either way.
-- ============================================================================

-- ---------------------------------------------------------------------------
-- 1-2. Tables
-- ---------------------------------------------------------------------------
create table if not exists permissions (
    key text primary key,
    description text
);

create table if not exists role_permissions (
    role text not null,
    permission_key text references permissions (key) on delete cascade,
    primary key (role, permission_key)
);

-- RLS: the matrix is not sensitive — authenticated users may read it
-- (useful for future UI work); writes stay service-role only.
alter table permissions enable row level security;
alter table role_permissions enable row level security;

drop policy if exists "permissions_select_authenticated" on permissions;
create policy "permissions_select_authenticated"
    on permissions
    for select
    to authenticated
    using (true);

drop policy if exists "role_permissions_select_authenticated" on role_permissions;
create policy "role_permissions_select_authenticated"
    on role_permissions
    for select
    to authenticated
    using (true);

-- ---------------------------------------------------------------------------
-- 3a. Seed the permission keys (upsert: re-running refreshes descriptions)
-- ---------------------------------------------------------------------------
insert into permissions (key, description) values
    ('dashboard.view',              'View the SOC dashboard and its aggregates'),
    ('alerts.view',                 'View alerts and alert details'),
    ('incidents.view',              'View incidents, timelines and linked alerts'),
    ('reports.view',                'View reports and exports'),
    ('analysis.run',                'Run text/flow detection pipelines (email, URL, impersonation, account takeover, network) and ingest events'),
    ('media.upload',                'Upload media for deepfake/media-forensics analysis'),
    ('incident.create',             'Create incidents'),
    ('incident.update',             'Update incidents: status transitions and assignment'),
    ('incident.escalate',           'Escalate incidents to critical severity'),
    ('incident.close',              'Transition an incident into the CLOSED state'),
    ('alert.acknowledge',           'Change alert status to acknowledged'),
    ('alert.resolve',               'Change alert status to resolved or dismissed'),
    ('response.execute',            'Execute (simulated) response actions'),
    ('response.execute_destructive', 'Execute approval-required (destructive) response actions'),
    ('audit.view',                  'Read the organization audit log'),
    ('users.manage',                'Manage users and roles (admin area)')
on conflict (key) do update set description = excluded.description;

-- ---------------------------------------------------------------------------
-- 3b. Seed the role -> permission matrix (idempotent)
--     viewer : read-only views
--     analyst: viewer + run analysis, work incidents/alerts, safe responses, audit
--     admin  : analyst + destructive responses + user management
-- ---------------------------------------------------------------------------
insert into role_permissions (role, permission_key)
values
    -- viewer
    ('viewer', 'dashboard.view'),
    ('viewer', 'alerts.view'),
    ('viewer', 'incidents.view'),
    ('viewer', 'reports.view'),
    -- analyst (all viewer permissions plus)
    ('analyst', 'dashboard.view'),
    ('analyst', 'alerts.view'),
    ('analyst', 'incidents.view'),
    ('analyst', 'reports.view'),
    ('analyst', 'analysis.run'),
    ('analyst', 'media.upload'),
    ('analyst', 'incident.create'),
    ('analyst', 'incident.update'),
    ('analyst', 'incident.escalate'),
    ('analyst', 'incident.close'),
    ('analyst', 'alert.acknowledge'),
    ('analyst', 'alert.resolve'),
    ('analyst', 'response.execute'),
    ('analyst', 'audit.view'),
    -- admin (all analyst permissions plus)
    ('admin', 'dashboard.view'),
    ('admin', 'alerts.view'),
    ('admin', 'incidents.view'),
    ('admin', 'reports.view'),
    ('admin', 'analysis.run'),
    ('admin', 'media.upload'),
    ('admin', 'incident.create'),
    ('admin', 'incident.update'),
    ('admin', 'incident.escalate'),
    ('admin', 'incident.close'),
    ('admin', 'alert.acknowledge'),
    ('admin', 'alert.resolve'),
    ('admin', 'response.execute'),
    ('admin', 'response.execute_destructive'),
    ('admin', 'audit.view'),
    ('admin', 'users.manage')
on conflict (role, permission_key) do nothing;
