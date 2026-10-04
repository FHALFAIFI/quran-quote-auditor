# Optional accounts on Supabase — owner's steps (roadmap Stage 2)

**Status (4 Oct 2026, challenge period):** the code is on the unmerged branch `accounts-flag`, behind `ACCOUNTS_ENABLED`
(off by default). **No Supabase project exists. Nothing here has been run against the real service.** The SQL in
`001_drafts.sql` has been reviewed, not executed; Row-Level Security is therefore untested. Every local test ran against
in-memory stores or a local fake (`scripts/fake_supabase.py`).

Do not turn the flag on in production until every decision in the last section is made and every live check below passes.

## 1. Create the project

1. Create a Supabase project (Pro plan for production: the Free plan pauses after a week of inactivity and states no
   backups — see `docs/PRODUCTION_ROADMAP.md`, Stage 2 costs). **Choose the region deliberately**: it is where drafts and
   email addresses are stored. A region outside Saudi Arabia is a cross-border transfer under the PDPL; get the legal review
   first.
2. Settings → JWT keys: **use asymmetric JWT signing keys** (ES256, the default for new projects, or RS256). The server
   refuses `HS256` tokens on purpose (no shared secret on our server, no algorithm confusion). A legacy project still on the
   HS256 secret must migrate to signing keys first.
3. Settings → API → set the access-token (JWT) expiry to 3600 seconds (the server's deleted-account denylist assumes at most
   one hour).

## 2. Run the SQL

SQL editor → paste `deploy/supabase/001_drafts.sql` → Run (or `psql "$DATABASE_URL" -f deploy/supabase/001_drafts.sql`).
It creates `drafts`, `preferences` and `deletion_log`, the triggers (200 drafts per user, server-controlled columns, version
bump) and RLS policies (`user_id = auth.uid()` for select/insert/update/delete; no access for `anon`). Then check in
Database → Tables that RLS shows **enabled** on all three tables.

## 3. Auth: email magic link

1. Authentication → Providers → Email: enabled; "Confirm email" on; password sign-in may stay off (the app never asks for
   one). Google/Apple are not used.
2. Authentication → URL configuration: **Site URL** = the production origin (for example `https://<your-domain>`); add the
   redirect URL `https://<your-domain>/**` (the app sends `redirect_to=https://<your-domain>/?acct=<nonce>`; the nonce
   lets the tab that asked for the link receive the session).
3. Authentication → Emails → SMTP: set a **custom SMTP sender** on your own domain (Supabase's built-in sender is rate
   limited and meant for testing). Publish **SPF** and **DKIM** records for that domain (and DMARC). Edit the magic-link
   template into Arabic if wanted; keep `{{ .ConfirmationURL }}`.
4. Authentication → Rate limits: keep the email limit low (for example a few per hour per address).

## 4. Render environment variables

| Variable | Value | Secret? |
|---|---|---|
| `ACCOUNTS_ENABLED` | `true` (only after the checks below) | no |
| `SUPABASE_URL` | `https://<project-ref>.supabase.co` (HTTPS required) | no |
| `SUPABASE_ANON_KEY` | the project's anon / publishable key (it is sent to browsers by design; RLS protects the rows) | no |
| `SUPABASE_JWKS_URL` | optional; default `<SUPABASE_URL>/auth/v1/.well-known/jwks.json` | no |
| `SUPABASE_JWT_ISSUER` | optional; default `<SUPABASE_URL>/auth/v1` | no |
| `SUPABASE_JWT_AUDIENCE` | optional; default `authenticated` | no |
| `SUPABASE_SERVICE_ROLE_KEY` | optional; only if the auth user itself must be deleted when the writer deletes the account. Server-only: never sent to a browser, never logged. Without it the rows are deleted and the response says the sign-in identity was not | **yes** |
| `ACCOUNT_RATE_LIMIT_PER_MINUTE` | optional; default 60 account requests per address per minute | no |
| `ACCOUNT_TOKEN_LEEWAY_SECONDS` | optional; default 30 (clock skew allowed on `exp`/`nbf`/`iat`; capped at 120) | no |

If `ACCOUNTS_ENABLED=true` but `SUPABASE_URL` (HTTPS) or `SUPABASE_ANON_KEY` is missing, the server logs a warning and keeps
accounts **off** (fail closed). With the flag on, the page's CSP `connect-src` adds exactly the `SUPABASE_URL` origin.

## 5. Live acceptance checks — ALL NOT RUN

Run these on the deployed service with two test accounts that are not real people's (roadmap Stage 2 list). Record each
in `docs/TEST_LOG.md` with the date, the commit and the result.

| # | Check | Local evidence so far (not a substitute) | Live status |
|---|---|---|---|
| 1 | Guest unchanged: `ui_journey_e2e`, `ui_final_qa`, `ui_a11y_check` pass with the flag on and no sign-in; the network log shows no auth request | the suites pass locally with the flag on; `ui_account_e2e` checks the guest network log against the fake | **NOT RUN** |
| 2 | Cross-user isolation through the API (ids guessed, `user_id` swapped in body and query, replay after sign-out and deletion) **and directly against Postgres with RLS** (B's token on A's rows; the anon key alone) | API: `tests/test_account_api.py` with MemoryStore. RLS: **none** (no database) | **NOT RUN** |
| 3 | Expired, wrong-audience, wrong-issuer, `alg:none`, tampered tokens refused | `tests/test_account_tokens.py` with local keys | **NOT RUN** |
| 4 | Expiry mid-edit keeps the text and shows the refusal; "sign out everywhere" ends a second browser's session within the token lifetime | expiry: `ui_account_e2e` against the fake. "Sign out everywhere" is **not built** (see roadmap status) | **NOT RUN** |
| 5 | Nothing uploaded until «احفظ في حسابي» (network log) | `ui_account_e2e` against the fake | **NOT RUN** |
| 6 | After deletion: no row with that user id, the magic link no longer works, export returns 401 | API test + fake | **NOT RUN** |
| 7 | Export, delete, re-import gives the same text and decisions | export only; **re-import is not built** | **NOT RUN** |
| 8 | Two tabs, second save refused with a visible choice | API test + `ui_account_e2e` against the fake | **NOT RUN** |
| 9 | Size and count limits refused clearly | API test (MemoryStore) | **NOT RUN** |
| 10 | axe 0 and keyboard-only at 1366 / 390 / 320 for sign-in and the draft list | `ui_account_e2e` against the fake | **NOT RUN** |
| 11 | Backup restore drill into a scratch project; read one draft back | none | **NOT RUN** |

Direct RLS checks to run once the SQL is applied (psql or the REST API, with real test tokens):

```
# as B (B's access token): A's draft must not be visible or changeable
curl -s "$SUPABASE_URL/rest/v1/drafts?id=eq.<A_DRAFT_ID>" -H "apikey: $ANON" -H "Authorization: Bearer $B_TOKEN"        # → []
curl -s -X PATCH "$SUPABASE_URL/rest/v1/drafts?id=eq.<A_DRAFT_ID>" -H "apikey: $ANON" -H "Authorization: Bearer $B_TOKEN" \
     -H "Content-Type: application/json" -H "Prefer: return=representation" -d '{"body":"x"}'                         # → []
curl -s -X POST "$SUPABASE_URL/rest/v1/drafts" -H "apikey: $ANON" -H "Authorization: Bearer $B_TOKEN" \
     -H "Content-Type: application/json" -d '{"user_id":"<A_USER_ID>","body":"x"}'                                     # → 403, 42501
# with the anon key alone
curl -s "$SUPABASE_URL/rest/v1/drafts" -H "apikey: $ANON"                                                              # → 401/permission denied
curl -s "$SUPABASE_URL/rest/v1/deletion_log" -H "apikey: $ANON" -H "Authorization: Bearer $B_TOKEN"                    # → permission denied
```

## 6. Decisions only the owner can make (none made)

- Provider (Supabase is the proposal) and **region**; the PDPL review of a cross-border transfer.
- The data controller's legal identity and a privacy contact address.
- The sender domain (SPF/DKIM/DMARC) for magic-link email.
- Retention of inactive accounts; an age policy; terms of use for stored drafts.
- Whether the server should hold `SUPABASE_SERVICE_ROLE_KEY` (needed to delete the auth identity itself).
- The `/privacy` and `/limitations` rewrite (prepared text in `docs/PRODUCTION_ROADMAP.md`, Stage 2 status) — to be published
  only together with turning the flag on.

An alternative to the service-role key, reviewed and **not used**: a `security definer` SQL function
`delete_my_account()` that deletes `auth.users where id = auth.uid()` (rows cascade) in one transaction. It avoids holding
the service-role key but gives the authenticated role a path into the `auth` schema; decide with whoever reviews the SQL.
