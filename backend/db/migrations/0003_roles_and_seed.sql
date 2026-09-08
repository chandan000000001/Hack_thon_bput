-- ============================================================================
-- CYBERGUARD Migration 0003: Roles & Seed (idempotent)
-- Run in the Supabase SQL editor AFTER 0001 (db/schema.sql).
--
-- IMPORTANT: the three demo users must already exist in Supabase Auth
-- (Authentication -> Users -> "Add user") with passwords of your choice:
--     admin@cyberguard.local    -> becomes admin
--     analyst@cyberguard.local  -> becomes analyst
--     viewer@cyberguard.local   -> becomes viewer
-- Their profiles rows are auto-created by the handle_new_user trigger; this
-- migration backfills their email and assigns the demo roles idempotently.
-- ============================================================================

-- Default role for brand-new users is the least-privileged one.
alter table profiles alter column role set default 'viewer';

-- Email lives on profiles because the service role REST API cannot query
-- auth.users directly (admin user list needs it).
alter table profiles add column if not exists email text;

-- Trigger: new auth users get a profile with their email and viewer role.
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
    insert into public.profiles (id, full_name, email, role)
    values (
        new.id,
        coalesce(new.raw_user_meta_data ->> 'full_name', new.email),
        new.email,
        'viewer'
    )
    on conflict (id) do nothing;
    return new;
end;
$$;

-- Backfill emails for profiles created before this migration.
update profiles p
set email = u.email
from auth.users u
where p.id = u.id
  and (p.email is null or p.email = '');

-- ---------------------------------------------------------------------------
-- Seed demo roles (idempotent: safe to re-run, only touches matching emails)
-- ---------------------------------------------------------------------------
update profiles set role = 'admin'   where email = 'admin@cyberguard.local';
update profiles set role = 'analyst' where email = 'analyst@cyberguard.local';
update profiles set role = 'viewer'  where email = 'viewer@cyberguard.local';
