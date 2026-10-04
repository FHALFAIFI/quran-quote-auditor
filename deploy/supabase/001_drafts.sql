-- Quran Quote Auditor — optional accounts (roadmap Stage 2): private drafts and preferences.
--
-- STATUS: written and reviewed on 4 Oct 2026 (challenge period), NOT EXECUTED against any database. No Supabase project
-- exists for this application. Row-Level Security below is therefore reviewed, not tested. Run it in the owner's project
-- (SQL editor, or `psql "$DATABASE_URL" -f 001_drafts.sql`) and then run the live acceptance checks in README.md.
--
-- Design:
--   * Two guards. The FastAPI server verifies the JWT and filters every query by the verified user id; independently,
--     RLS lets a role see only rows whose user_id = auth.uid(). PostgREST is called with the writer's own token, so RLS
--     applies to the same user. The anon role gets no access at all.
--   * No content is ever written to a log table. deletion_log holds a hash of the user id and two timestamps.
--   * Limits are enforced here as well as in the API: 20,000 characters per text field, 200 drafts per user.
--   * id, user_id, created_at, version and updated_at cannot be set by the client: triggers fix them.

begin;

create extension if not exists pgcrypto;   -- gen_random_uuid() (built in from Postgres 13; kept for older images)

-- ------------------------------------------------------------------------------------------------------------- drafts
create table if not exists public.drafts (
  id            uuid        primary key default gen_random_uuid(),
  user_id       uuid        not null default auth.uid() references auth.users (id) on delete cascade,
  title         text        not null default '' check (char_length(title) <= 200),
  body          text        not null default '' check (char_length(body) <= 20000),
  decisions     jsonb       check (decisions is null or pg_column_size(decisions) <= 200000),
  audited_text  text        check (audited_text is null or char_length(audited_text) <= 20000),
  body_length   integer     generated always as (char_length(body)) stored,
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now(),
  version       integer     not null default 1
);

create index if not exists drafts_user_updated on public.drafts (user_id, updated_at desc);

-- Before insert: at most 200 drafts per user (serialised per user by an advisory lock, so two parallel inserts cannot both
-- pass the count), and the server-controlled columns take their defaults whatever the client sent.
create or replace function public.drafts_before_insert() returns trigger
language plpgsql set search_path = '' as $$
begin
  perform pg_advisory_xact_lock(hashtextextended(new.user_id::text, 0));
  if (select count(*) from public.drafts d where d.user_id = new.user_id) >= 200 then
    raise exception 'draft_limit' using errcode = 'check_violation';
  end if;
  new.id := gen_random_uuid();
  new.created_at := now();
  new.updated_at := now();
  new.version := 1;
  return new;
end $$;

-- Before update: the owner, id and creation time never change; every update bumps version (optimistic concurrency: the
-- API updates "where id = … and version = <the version the browser had>", so a stale save matches no row and is refused).
create or replace function public.drafts_before_update() returns trigger
language plpgsql set search_path = '' as $$
begin
  new.id := old.id;
  new.user_id := old.user_id;
  new.created_at := old.created_at;
  new.version := old.version + 1;
  new.updated_at := now();
  return new;
end $$;

drop trigger if exists drafts_before_insert on public.drafts;
create trigger drafts_before_insert before insert on public.drafts for each row execute function public.drafts_before_insert();
drop trigger if exists drafts_before_update on public.drafts;
create trigger drafts_before_update before update on public.drafts for each row execute function public.drafts_before_update();

alter table public.drafts enable row level security;
alter table public.drafts force row level security;

drop policy if exists drafts_select on public.drafts;
drop policy if exists drafts_insert on public.drafts;
drop policy if exists drafts_update on public.drafts;
drop policy if exists drafts_delete on public.drafts;
create policy drafts_select on public.drafts for select to authenticated using (user_id = (select auth.uid()));
create policy drafts_insert on public.drafts for insert to authenticated with check (user_id = (select auth.uid()));
create policy drafts_update on public.drafts for update to authenticated using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));
create policy drafts_delete on public.drafts for delete to authenticated using (user_id = (select auth.uid()));

revoke all on public.drafts from anon, public;
grant select, insert, update, delete on public.drafts to authenticated;

-- -------------------------------------------------------------------------------------------------------- preferences
create table if not exists public.preferences (
  user_id      uuid        primary key default auth.uid() references auth.users (id) on delete cascade,
  suggest_on   boolean     not null default true,
  distinct_on  boolean     not null default false,
  updated_at   timestamptz not null default now()
);

create or replace function public.preferences_touch() returns trigger
language plpgsql set search_path = '' as $$
begin
  if tg_op = 'UPDATE' then
    new.user_id := old.user_id;
  end if;
  new.updated_at := now();
  return new;
end $$;

drop trigger if exists preferences_touch on public.preferences;
create trigger preferences_touch before insert or update on public.preferences for each row execute function public.preferences_touch();

alter table public.preferences enable row level security;
alter table public.preferences force row level security;

drop policy if exists preferences_select on public.preferences;
drop policy if exists preferences_insert on public.preferences;
drop policy if exists preferences_update on public.preferences;
drop policy if exists preferences_delete on public.preferences;
create policy preferences_select on public.preferences for select to authenticated using (user_id = (select auth.uid()));
create policy preferences_insert on public.preferences for insert to authenticated with check (user_id = (select auth.uid()));
create policy preferences_update on public.preferences for update to authenticated using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()));
create policy preferences_delete on public.preferences for delete to authenticated using (user_id = (select auth.uid()));

revoke all on public.preferences from anon, public;
grant select, insert, update, delete on public.preferences to authenticated;

-- ------------------------------------------------------------------------------------------------------- deletion_log
-- Proof that an account deletion was carried out. No content and no raw user id: a SHA-256 of the user id and two times.
-- RLS on with NO policy: neither anon nor authenticated can read or write it; only the server's service role (which
-- bypasses RLS) inserts, after deleting the auth user.
create table if not exists public.deletion_log (
  id            bigint generated always as identity primary key,
  user_hash     text        not null check (user_hash ~ '^[0-9a-f]{64}$'),
  requested_at  timestamptz not null,
  completed_at  timestamptz
);

alter table public.deletion_log enable row level security;
revoke all on public.deletion_log from anon, authenticated, public;

commit;

-- Review notes (not executed):
--   * `(select auth.uid())` instead of `auth.uid()` lets Postgres evaluate it once per statement (Supabase's RLS advice).
--   * `force row level security` makes the policies apply to the table owner too; the service role still bypasses RLS.
--   * The count trigger runs as the invoker; under RLS it counts only the caller's rows, which is exactly the set limited.
--   * The 409 path relies on PATCH ... ?id=eq.X&version=eq.N returning no row when the version moved on.
