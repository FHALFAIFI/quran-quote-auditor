-- LOCAL POSTGRES EMULATION OF SUPABASE AUTH — NOT SUPABASE. Used only by tests/test_account_rls_pg.py on a throwaway cluster.
--
-- Just enough of a Supabase project for deploy/supabase/001_drafts.sql to run and for its Row-Level Security to be exercised:
--   * the roles anon, authenticated (no BYPASSRLS) and service_role (BYPASSRLS), as Supabase creates them;
--   * Supabase's default privileges: every new table in public is granted to anon, authenticated and service_role, so the
--     migration's own REVOKE is what keeps anon out (as it must be on the real service);
--   * auth.users (id only) and auth.uid(), written as Supabase writes it: the `sub` of the request's JWT claims, read from the
--     GUCs PostgREST sets (request.jwt.claim.sub, or request.jwt.claims as JSON).
-- What this cannot show: PostgREST's own JWT checking and role switching, Supabase's real auth schema, its grants on other
-- schemas, and anything about the hosted service (see deploy/supabase/INTEGRATION_CHECKLIST.md).

do $$ begin   -- roles belong to the cluster: created once, for every scratch database
  if not exists (select 1 from pg_roles where rolname = 'anon') then create role anon nologin noinherit; end if;
  if not exists (select 1 from pg_roles where rolname = 'authenticated') then create role authenticated nologin noinherit; end if;
  if not exists (select 1 from pg_roles where rolname = 'service_role') then create role service_role nologin noinherit bypassrls; end if;
end $$;

create schema auth;
create table auth.users (id uuid primary key);

create or replace function auth.uid() returns uuid language sql stable as $$
  select coalesce(
    nullif(current_setting('request.jwt.claim.sub', true), ''),
    (nullif(current_setting('request.jwt.claims', true), '')::jsonb ->> 'sub')
  )::uuid
$$;

grant usage on schema auth to anon, authenticated, service_role;
grant execute on function auth.uid() to anon, authenticated, service_role;
grant usage on schema public to anon, authenticated, service_role;
alter default privileges in schema public grant all on tables to anon, authenticated, service_role;
alter default privileges in schema public grant all on sequences to anon, authenticated, service_role;
alter default privileges in schema public grant all on functions to anon, authenticated, service_role;
