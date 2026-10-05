"""Row-Level Security of deploy/supabase/001_drafts.sql, tested in a LOCAL POSTGRES EMULATION OF SUPABASE AUTH — NOT SUPABASE.

A throwaway Postgres cluster (initdb in a temporary directory, listening on 127.0.0.1 only, stopped at the end) gets
tests/supabase_auth_shim.sql (the roles anon / authenticated / service_role, Supabase's default grants, auth.users and an
auth.uid() that reads the request's JWT claims the way Supabase's does) and then the migration itself. Each statement runs as
the role PostgREST would switch to, with the claim PostgREST would set (``set local role authenticated; set local
request.jwt.claim.sub = …``). The statements have the shapes PostgrestStore sends (filters on id, user_id and version).

What this shows: the policies, grants and triggers as written. What it cannot show: Supabase's own auth schema and auth.uid(),
PostgREST's JWT checking and role switching, the hosted project's grants — see deploy/supabase/INTEGRATION_CHECKLIST.md.

Skipped when the Postgres binaries (initdb, pg_ctl, psql) are not installed. Nothing leaves the machine."""

from __future__ import annotations

import itertools
import os
import shutil
import socket
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "deploy" / "supabase" / "001_drafts.sql"
SHIM = ROOT / "tests" / "supabase_auth_shim.sql"

A = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
B = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
SECRET = "نص-سري-للاختبار-٧٣٤١"


def _bin(name: str) -> str | None:
    for d in (os.environ.get("PG_BIN"), "/opt/homebrew/bin", "/usr/local/bin", "/usr/lib/postgresql/16/bin"):
        if d and (Path(d) / name).exists():
            return str(Path(d) / name)
    return shutil.which(name)


BINS = {n: _bin(n) for n in ("initdb", "pg_ctl", "psql")}
pytestmark = pytest.mark.skipif(not all(BINS.values()), reason="Postgres binaries (initdb, pg_ctl, psql) not installed")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Result:
    def __init__(self, proc: subprocess.CompletedProcess):
        self.ok = proc.returncode == 0
        self.out = [line for line in proc.stdout.splitlines() if line.strip()]
        self.err = proc.stderr

    def __repr__(self):
        return f"Result(ok={self.ok}, out={self.out!r}, err={self.err!r})"


class Cluster:
    def __init__(self, base: Path):
        self.data, self.port = base / "data", _free_port()
        env = {**os.environ, "LC_ALL": "C"}
        subprocess.run([BINS["initdb"], "-D", str(self.data), "-U", "postgres", "-A", "trust", "--no-locale", "-E", "UTF8"],
                       check=True, capture_output=True, env=env)
        subprocess.run([BINS["pg_ctl"], "-D", str(self.data), "-l", str(base / "log"), "-w", "start",
                        "-o", f"-p {self.port} -c listen_addresses=127.0.0.1 -k ''"], check=True, capture_output=True, env=env)
        self.counter = itertools.count(1)

    def stop(self):
        subprocess.run([BINS["pg_ctl"], "-D", str(self.data), "-m", "immediate", "stop"], capture_output=True)

    def psql(self, db: str, sql: str = "", files: tuple[Path, ...] = ()) -> Result:
        cmd = [BINS["psql"], "-X", "-q", "-A", "-t", "-v", "ON_ERROR_STOP=1", "-h", "127.0.0.1", "-p", str(self.port), "-U", "postgres", "-d", db]
        for f in files:
            cmd += ["-f", str(f)]
        return Result(subprocess.run(cmd, input=sql, capture_output=True, text=True))

    def new_db(self) -> "DB":
        name = f"rls_{next(self.counter)}"
        assert self.psql("postgres", f"create database {name};").ok
        r = self.psql(name, files=(SHIM, MIGRATION))
        assert r.ok, r.err
        assert self.psql(name, f"insert into auth.users (id) values ('{A}'), ('{B}');").ok
        return DB(self, name)


class DB:
    def __init__(self, cluster: Cluster, name: str):
        self.cluster, self.name = cluster, name

    def admin(self, sql: str) -> Result:
        return self.cluster.psql(self.name, sql)

    def as_role(self, role: str, sql: str, sub: str | None = None) -> Result:
        claim = f"set local request.jwt.claim.sub = '{sub}';" if sub else ""
        return self.cluster.psql(self.name, f"begin; set local role {role}; {claim}\n{sql}\ncommit;")

    def user(self, sub: str, sql: str) -> Result:
        return self.as_role("authenticated", sql, sub)

    def anon(self, sql: str) -> Result:
        return self.as_role("anon", sql)

    def new_draft(self, sub: str, body: str = SECRET, title: str = "t") -> str:
        r = self.user(sub, f"insert into public.drafts (title, body) values ('{title}', '{body}') returning id;")
        assert r.ok, r.err
        return r.out[0]


@pytest.fixture(scope="module")
def cluster(tmp_path_factory):
    c = Cluster(tmp_path_factory.mktemp("pg"))
    try:
        yield c
    finally:
        c.stop()


@pytest.fixture
def db(cluster):
    return cluster.new_db()


def denied(r: Result) -> bool:
    return not r.ok and "permission denied" in r.err


# ----------------------------------------------------------------------------------------------------------- structure
def test_migration_is_rerunnable(db):
    r = db.cluster.psql(db.name, files=(MIGRATION,))
    assert r.ok, r.err


def test_every_command_has_a_policy_for_authenticated_only(db):
    rows = db.admin("select tablename, cmd, array_to_string(roles, ','), coalesce(qual, ''), coalesce(with_check, '') "
                    "from pg_policies where schemaname = 'public' order by 1, 2;").out
    got = {}
    for line in rows:
        table, cmd, roles, qual, check = line.split("|")
        got[(table, cmd)] = (roles, qual, check)
    for table in ("drafts", "preferences"):
        for cmd in ("SELECT", "INSERT", "UPDATE", "DELETE"):
            roles, qual, check = got.pop((table, cmd))
            assert roles == "authenticated", (table, cmd, roles)
            if cmd in ("SELECT", "DELETE", "UPDATE"):
                assert "user_id = ( SELECT auth.uid()" in qual, (table, cmd, qual)
            if cmd in ("INSERT", "UPDATE"):
                assert "user_id = ( SELECT auth.uid()" in check, (table, cmd, check)
    assert got == {}, f"unexpected policies: {got}"    # in particular none on deletion_log, none for anon or public
    flags = db.admin("select relname, relrowsecurity, relforcerowsecurity from pg_class "
                     "where relnamespace = 'public'::regnamespace and relkind = 'r' order by 1;").out
    assert flags == ["deletion_log|t|f", "drafts|t|t", "preferences|t|t"]


def test_least_privilege_grants(db):
    """Supabase grants ALL on every new public table to anon and authenticated by default (emulated by the shim). Found in the
    5 Oct review: the migration only GRANTed the four commands, so authenticated kept TRUNCATE (which RLS does not filter),
    REFERENCES and TRIGGER, and both roles kept the deletion_log id sequence."""
    rows = db.admin("""
        select t, r, p from unnest(array['public.drafts', 'public.preferences', 'public.deletion_log']) t,
                            unnest(array['anon', 'authenticated']) r,
                            unnest(array['SELECT', 'INSERT', 'UPDATE', 'DELETE', 'TRUNCATE', 'REFERENCES', 'TRIGGER']) p
        where has_table_privilege(r, t, p) order by 1, 2, 3;""").out
    expected = [f"public.{t}|authenticated|{p}" for t in ("drafts", "preferences") for p in ("DELETE", "INSERT", "SELECT", "UPDATE")]
    assert rows == expected
    seq = db.admin("select r from unnest(array['anon', 'authenticated']) r "
                   "where has_sequence_privilege(r, 'public.deletion_log_id_seq', 'USAGE,SELECT,UPDATE');").out
    assert seq == []


# -------------------------------------------------------------------------------------------------------------- anon
@pytest.mark.parametrize("sql", [
    "select count(*) from public.drafts;",
    "insert into public.drafts (user_id, body) values ('%s', 'x');" % A,
    "update public.drafts set body = 'x';",
    "delete from public.drafts;",
    "truncate public.drafts;",
    "select count(*) from public.preferences;",
    "insert into public.preferences (user_id) values ('%s');" % A,
    "select count(*) from public.deletion_log;",
    "insert into public.deletion_log (user_hash, requested_at) values (repeat('a', 64), now());",
    "select nextval('public.deletion_log_id_seq');",
])
def test_anon_is_refused_everything(db, sql):
    db.new_draft(A)
    assert denied(db.anon(sql)), sql


# --------------------------------------------------------------------------------------------------- cross-user (RLS)
def test_b_cannot_read_change_or_delete_a(db):
    a1, a2 = db.new_draft(A), db.new_draft(A, body="ثانية")
    assert db.user(A, "insert into public.preferences (suggest_on, distinct_on) values (false, true);").ok
    # what PostgREST sends for B: the server's own user_id filter left out, so RLS alone decides
    for sql in (f"select count(*) from public.drafts where id = '{a1}';",
                "select count(*) from public.drafts;",
                f"select count(*) from public.drafts where user_id = '{A}';",
                "select count(*) from public.preferences;"):
        r = db.user(B, sql)
        assert r.ok and r.out == ["0"], (sql, r)
    for sql in (f"update public.drafts set body = 'اختراق' where id = '{a1}' returning id;",
                f"update public.drafts set body = 'اختراق' where id = '{a2}' and version = 1 returning id;",
                f"delete from public.drafts where id = '{a1}' returning id;",
                "delete from public.drafts returning id;",
                "update public.preferences set suggest_on = true returning user_id;",
                "delete from public.preferences returning user_id;"):
        r = db.user(B, sql)
        assert r.ok and r.out == [], (sql, r)
    # without WHERE or RETURNING Postgres applies only the UPDATE / DELETE policy (not the SELECT one): each must hold alone
    for sql in ("update public.drafts set body = 'اختراق';", "delete from public.drafts;",
                "update public.preferences set suggest_on = true;", "delete from public.preferences;"):
        r = db.user(B, sql)
        assert r.ok, (sql, r)
    r = db.user(A, "select body, version from public.drafts;")
    assert sorted(r.out) == sorted([f"{SECRET}|1", "ثانية|1"])
    assert db.user(A, "select suggest_on, distinct_on from public.preferences;").out == ["f|t"]


def test_insert_for_another_user_is_refused(db):
    for sql in (f"insert into public.drafts (user_id, body) values ('{B}', 'x');",
                f"insert into public.preferences (user_id) values ('{B}');"):
        r = db.user(A, sql)
        assert not r.ok and "row-level security" in r.err, (sql, r)
    # an upsert onto B's preferences row (what PostgREST's merge-duplicates becomes) is refused as well
    assert db.user(B, "insert into public.preferences (suggest_on) values (true);").ok
    r = db.user(A, f"insert into public.preferences (user_id, suggest_on) values ('{B}', false) "
                   "on conflict (user_id) do update set suggest_on = excluded.suggest_on;")
    assert not r.ok
    assert db.user(B, "select suggest_on from public.preferences;").out == ["t"]
    assert db.admin("select count(*) from public.drafts;").out == ["0"]


def test_update_cannot_reassign_the_owner_or_server_columns(db):
    d = db.new_draft(A)
    before = db.admin(f"select created_at from public.drafts where id = '{d}';").out
    r = db.user(A, f"update public.drafts set user_id = '{B}', id = gen_random_uuid(), version = 99, "
                   f"created_at = '2000-01-01' where id = '{d}' returning id, user_id, version;")
    assert r.ok and r.out == [f"{d}|{A}|2"], r
    assert db.admin(f"select created_at from public.drafts where id = '{d}';").out == before
    assert db.user(B, "select count(*) from public.drafts;").out == ["0"]
    assert db.user(A, "insert into public.preferences (suggest_on) values (true);").ok
    r = db.user(A, f"update public.preferences set user_id = '{B}' returning user_id;")
    assert r.ok and r.out == [A], r


def test_server_columns_ignored_on_insert(db):
    r = db.user(A, "insert into public.drafts (id, body, version, created_at) values "
                   "('00000000-0000-4000-8000-000000000000', 'x', 50, '2000-01-01') returning id, version, created_at > '2001-01-01';")
    assert r.ok and r.out[0].split("|")[1:] == ["1", "t"] and not r.out[0].startswith("00000000-"), r


def test_stale_version_matches_no_row(db):
    d = db.new_draft(A, body="الأصل")
    first = db.user(A, f"update public.drafts set body = 'الأول' where id = '{d}' and user_id = '{A}' and version = 1 returning version;")
    assert first.out == ["2"]
    stale = db.user(A, f"update public.drafts set body = 'الثاني' where id = '{d}' and user_id = '{A}' and version = 1 returning version;")
    assert stale.ok and stale.out == []
    assert db.user(A, f"select body, version from public.drafts where id = '{d}';").out == ["الأول|2"]


def test_authenticated_without_a_user_sees_and_writes_nothing(db):
    db.new_draft(A)
    r = db.as_role("authenticated", "select count(*) from public.drafts;")
    assert r.ok and r.out == ["0"]
    assert not db.as_role("authenticated", "insert into public.drafts (body) values ('x');").ok
    assert not db.as_role("authenticated", "insert into public.preferences (suggest_on) values (true);").ok


def test_truncate_is_refused_to_signed_in_users(db):
    db.new_draft(A)
    db.new_draft(B)
    for table in ("drafts", "preferences"):
        assert denied(db.user(B, f"truncate public.{table};")), table
    assert db.admin("select count(*) from public.drafts;").out == ["2"]


def test_deletion_log_is_closed_to_users_and_open_to_the_service_role(db):
    for sql in ("select count(*) from public.deletion_log;",
                "insert into public.deletion_log (user_hash, requested_at) values (repeat('a', 64), now());",
                "select nextval('public.deletion_log_id_seq');"):
        assert denied(db.user(A, sql)), sql
    r = db.as_role("service_role", "insert into public.deletion_log (user_hash, requested_at, completed_at) "
                                   "values (repeat('a', 64), now(), now()) returning id;")
    assert r.ok and r.out == ["1"], r
    bad = db.as_role("service_role", "insert into public.deletion_log (user_hash, requested_at) values ('not-a-hash', now());")
    assert not bad.ok and "check constraint" in bad.err


# ------------------------------------------------------------------------------------------------------- limits
def test_draft_limit_is_per_user(db):
    assert db.user(A, "insert into public.drafts (body) select i::text from generate_series(1, 200) i;").ok
    r = db.user(A, "insert into public.drafts (body) values ('201');")
    assert not r.ok and "draft_limit" in r.err
    db.new_draft(B)


def test_size_checks(db):
    assert not db.user(A, "insert into public.drafts (body) values (repeat('ب', 20001));").ok
    assert db.user(A, "insert into public.drafts (body) values (repeat('ب', 20000));").ok
    assert not db.user(A, "insert into public.drafts (title, body) values (repeat('ع', 201), 'x');").ok
    assert not db.user(A, "insert into public.drafts (body, audited_text) values ('x', repeat('ب', 20001));").ok


# ------------------------------------------------------------------------------------------------------- deletion
def test_user_deleting_everything_removes_only_their_rows(db):
    db.new_draft(A), db.new_draft(A), db.new_draft(B)
    assert db.user(A, "insert into public.preferences (suggest_on) values (true);").ok
    assert db.user(B, "insert into public.preferences (suggest_on) values (true);").ok
    # what PostgrestStore.delete_all sends
    r = db.user(A, f"delete from public.drafts where user_id = '{A}' returning id;")
    assert r.ok and len(r.out) == 2
    assert db.user(A, f"delete from public.preferences where user_id = '{A}';").ok
    assert db.admin(f"select count(*) from public.drafts where user_id = '{A}';").out == ["0"]
    assert db.admin(f"select count(*) from public.preferences where user_id = '{A}';").out == ["0"]
    assert db.admin(f"select count(*) from public.drafts where user_id = '{B}';").out == ["1"]
    assert db.admin(f"select count(*) from public.preferences where user_id = '{B}';").out == ["1"]


def test_deleting_the_auth_user_cascades_to_every_row(db):
    db.new_draft(A), db.new_draft(A), db.new_draft(B)
    assert db.user(A, "insert into public.preferences (suggest_on) values (true);").ok
    assert db.admin(f"delete from auth.users where id = '{A}';").ok
    assert db.admin("select user_id, count(*) from public.drafts group by 1;").out == [f"{B}|1"]
    assert db.admin("select count(*) from public.preferences;").out == ["0"]
