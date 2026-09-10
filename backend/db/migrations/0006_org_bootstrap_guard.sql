-- ============================================================================
-- CYBERGUARD Migration 0006: Organization Bootstrap Guard (Phase D-1)
-- Run this whole file in the Supabase SQL editor. Idempotent: create or
-- replace, safe to re-run.
--
-- What it does:
--   Recreates the handle_new_user trigger so that BEFORE selecting the
--   Default Organization it first ensures the "Default Organization" row
--   exists (insert ... on conflict do nothing). This guarantees a brand-new
--   signup can never fail with a NULL org_id — even on a fresh project where
--   migration 0004 has not seeded the organization yet, or if the
--   organizations table was manually emptied.
--
--   The backend runtime mirrors this guard: supabase_client.
--   _get_default_org_id() inserts the Default Organization automatically
--   when its lookup returns nothing, instead of raising.
--
-- Note: requires the organizations table (migration 0004) and the unique
-- index organizations_name_unique_idx for the on-conflict clause.
-- ============================================================================

create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
    -- Bootstrap guard: make sure the Default Organization exists before
    -- resolving its id, so the org_id below can never be NULL.
    insert into organizations (name)
    values ('Default Organization')
    on conflict (name) do nothing;

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
