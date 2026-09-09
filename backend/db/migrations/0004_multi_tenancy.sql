-- ============================================================================
-- CYBERGUARD Migration 0004: Multi-Tenancy (Organizations) — IDEMPOTENT
-- Run this whole file in the Supabase SQL editor (Database -> SQL editor).
-- It is safe to re-run: every step checks before it changes anything.
--
-- What it does:
--   1. Creates the organizations table (with RLS enabled).
--   2. Creates the "Default Organization" and captures its ID.
--   3. Adds org_id (uuid -> organizations.id) to profiles, events, alerts,
--      incidents and audit_logs (skipped if the column already exists).
--   4. Backfills EVERY existing row in those tables with the Default
--      Organization id, so no pre-existing demo data is orphaned.
--   5. Adds an index on org_id for each of those tables.
--   6. Recreates the handle_new_user trigger so brand-new signups are
--      automatically assigned to the Default Organization (the application
--      layer ALSO falls back to the Default Organization at runtime, so a
--      user without an org never crashes a request).
--
-- RLS NOTE: Row Level Security can be tightened further using auth.jwt()
-- (e.g. a policy comparing profiles.org_id with the caller's JWT claims).
-- For CYBERGUARD the FastAPI backend always talks to Postgres with the
-- service-role key (which bypasses RLS), so the PRIMARY enforcement of
-- tenant isolation is the service layer: every SELECT is filtered with
-- eq('org_id', ...) and every INSERT carries the caller's org_id
-- (see app/core/security.py, app/core/supabase_client.py and app/services/).
-- ============================================================================

-- ---------------------------------------------------------------------------
-- 1. Organizations table
-- ---------------------------------------------------------------------------
create table if not exists organizations (
    id uuid primary key default gen_random_uuid(),
    name text not null,
    created_at timestamptz not null default now()
);

-- Unique name so the Default Organization insert below is race/idempotency
-- safe (insert ... on conflict (name) do nothing).
create unique index if not exists organizations_name_unique_idx
    on organizations (name);

-- RLS: authenticated users may read the directory; only the service-role
-- client (bypassing RLS) can insert/update organizations.
alter table organizations enable row level security;

drop policy if exists "organizations_select_authenticated" on organizations;
create policy "organizations_select_authenticated"
    on organizations
    for select
    to authenticated
    using (true);

comment on table organizations is
    'Tenant directory for CYBERGUARD multi-tenancy. RLS can be tightened further with auth.jwt()-based policies; the FastAPI service-role client enforces tenant isolation primarily at the service layer (org_id filtering on every read, org_id on every write).';

-- ---------------------------------------------------------------------------
-- 2-5. Default Organization + org_id column, backfill, NOT NULL, indexes
-- ---------------------------------------------------------------------------
do $$
declare
    v_default_org uuid;
begin
    -- 2. Create the Default Organization (no-op if it already exists).
    insert into organizations (name)
    values ('Default Organization')
    on conflict (name) do nothing;

    select id into v_default_org
    from organizations
    where name = 'Default Organization'
    limit 1;

    if v_default_org is null then
        raise exception 'Default Organization could not be created';
    end if;

    -- 3+4. profiles: add column, backfill all existing rows.
    if not exists (
        select 1 from information_schema.columns
        where table_schema = 'public' and table_name = 'profiles' and column_name = 'org_id'
    ) then
        alter table profiles add column org_id uuid references organizations (id);
    end if;
    update profiles set org_id = v_default_org where org_id is null;
    alter table profiles alter column org_id set not null;

    -- 3+4. events
    if not exists (
        select 1 from information_schema.columns
        where table_schema = 'public' and table_name = 'events' and column_name = 'org_id'
    ) then
        alter table events add column org_id uuid references organizations (id);
    end if;
    update events set org_id = v_default_org where org_id is null;
    alter table events alter column org_id set not null;

    -- 3+4. alerts
    if not exists (
        select 1 from information_schema.columns
        where table_schema = 'public' and table_name = 'alerts' and column_name = 'org_id'
    ) then
        alter table alerts add column org_id uuid references organizations (id);
    end if;
    update alerts set org_id = v_default_org where org_id is null;
    alter table alerts alter column org_id set not null;

    -- 3+4. incidents
    if not exists (
        select 1 from information_schema.columns
        where table_schema = 'public' and table_name = 'incidents' and column_name = 'org_id'
    ) then
        alter table incidents add column org_id uuid references organizations (id);
    end if;
    update incidents set org_id = v_default_org where org_id is null;
    alter table incidents alter column org_id set not null;

    -- 3+4. audit_logs
    if not exists (
        select 1 from information_schema.columns
        where table_schema = 'public' and table_name = 'audit_logs' and column_name = 'org_id'
    ) then
        alter table audit_logs add column org_id uuid references organizations (id);
    end if;
    update audit_logs set org_id = v_default_org where org_id is null;
    alter table audit_logs alter column org_id set not null;

    -- 5. One index per tenant table so every org-scoped query stays fast.
    create index if not exists idx_profiles_org_id on profiles (org_id);
    create index if not exists idx_events_org_id on events (org_id);
    create index if not exists idx_alerts_org_id on alerts (org_id);
    create index if not exists idx_incidents_org_id on incidents (org_id);
    create index if not exists idx_audit_logs_org_id on audit_logs (org_id);
end;
$$;

-- ---------------------------------------------------------------------------
-- 6. handle_new_user: new signups land in the Default Organization.
--    (Supersedes the 0003 version; same behaviour plus org_id. The backend
--    ALSO falls back to the Default Organization at runtime, so an
--    unassigned user can never crash org scoping.)
-- ---------------------------------------------------------------------------
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
    insert into public.profiles (id, full_name, email, role, org_id)
    values (
        new.id,
        coalesce(new.raw_user_meta_data ->> 'full_name', new.email),
        new.email,
        'viewer',
        (select id from organizations where name = 'Default Organization' limit 1)
    )
    on conflict (id) do nothing;
    return new;
end;
$$;
