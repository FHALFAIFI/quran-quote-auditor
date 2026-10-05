# Accounts — what must be proven on a real Supabase project before `ACCOUNTS_ENABLED` is turned on

**Status (5 Oct 2026, challenge period):** branch `accounts-flag-review-20261005` (review of draft PR #4). **Not merged, not
live, flag off.** No Supabase project exists. Everything tested so far ran locally:

| Local evidence | What it is | What it is NOT |
|---|---|---|
| `tests/test_account_tokens.py`, `tests/test_account_api.py`, `tests/test_account_negative.py`, `tests/test_account_postgrest.py` | the server's token checks, isolation, limits, logs; PostgrestStore against an httpx mock and against `scripts/fake_supabase.py` | Supabase Auth or PostgREST |
| `tests/test_account_rls_pg.py` | `001_drafts.sql` executed in a **local Postgres 16 emulation of Supabase auth** (`tests/supabase_auth_shim.sql`: roles, default grants, `auth.users`, an `auth.uid()` written like Supabase's) | Supabase's own `auth` schema, its `postgres` role (not a superuser there), PostgREST's role switching |
| `scripts/ui_account_e2e.mjs` | the browser flow against the local fake (magic link, BroadcastChannel hand-off, 409, expiry, forged link, deletion) | real email, real tokens, real CORS |

Each item below says **what to run, the expected result, and where to record the evidence**. Record every result in
`docs/TEST_LOG.md` under a new dated section "Accounts — live integration on <project-ref>" with the commit SHA deployed,
the time (Riyadh), the command (tokens and keys replaced by `<A_TOKEN>`, `<ANON>`…) and the observed output. Keep raw
artefacts that contain personal data (email headers, request logs) **outside the repository**; note only where they are.
Use two test accounts on addresses you control (A and B), never a real writer's.

Shell set-up for the checks (fill from the project's API settings; never commit these values):

```
export SUPABASE_URL=https://<project-ref>.supabase.co  ANON=<anon key>  APP=https://<render-domain>
export A_TOKEN=<access token of A>  B_TOKEN=<access token of B>  A_ID=<A's auth user id>  B_ID=<B's auth user id>
# a token is taken from the address bar of the landing tab BEFORE the page clears it (DevTools → Network → the document
# request's redirect Location), or from the response of POST /auth/v1/verify in a terminal
```

---

## 0. Owner inputs needed first (none provided yet)

| Input | Why it blocks | Record in |
|---|---|---|
| Supabase organisation and **project** (plan: Pro for production — Free pauses and has no stated backups) | everything below | TEST_LOG (project ref only) |
| **Region** of the project | where drafts and email addresses are stored; a region outside KSA is a cross-border transfer under the PDPL | TEST_LOG + the privacy review |
| **Sender domain** for magic-link email, with DNS access for SPF, DKIM, DMARC | §3 | TEST_LOG |
| **Data controller** legal identity and a **privacy contact** address | `/privacy` cannot be published without them | privacy review file |
| **Retention** of inactive accounts and of deletion_log; **backup retention** accepted | `/privacy` text; §7 | privacy review file |
| **Age policy** (minimum age, or none) and terms of use for stored drafts | sign-up wording | privacy review file |
| Whether the server holds `SUPABASE_SERVICE_ROLE_KEY` (needed to delete the auth identity) | §6 | TEST_LOG |
| **Privacy / legal review** (PDPL, SDAIA cross-border rules) signed off | turning the flag on | privacy review file |
| CAPTCHA on sign-up (hCaptcha / Turnstile) yes or no | §8; a CAPTCHA script needs a CSP change and its own review | TEST_LOG |

---

## 1. Project settings

| # | Run | Expected | Evidence |
|---|---|---|---|
| 1.1 | `curl -s $SUPABASE_URL/auth/v1/.well-known/jwks.json` | `keys` holds at least one `EC` (ES256) or `RSA` (RS256) key with a `kid`; **no** `oct` key. A legacy project on the HS256 secret returns an empty set: the server would refuse every token (fails closed) — migrate to signing keys first | JSON with the key ids (public keys are not secret) |
| 1.2 | Decode a fresh access token's header and payload (e.g. `cut -d. -f1,2`, base64-decode; do not paste the token into a website) | header `alg` ES256/RS256 with a `kid` from 1.1; payload `iss` = `$SUPABASE_URL/auth/v1`, `aud` = `authenticated`, `role` = `authenticated`, `sub` = a UUID, `exp − iat` = 3600 | the decoded claims with the email redacted |
| 1.3 | Authentication → URL configuration | Site URL = `$APP`; redirect allow-list = `$APP/**` only (no wildcard host, no `localhost`) | screenshot |
| 1.4 | `curl -s -X POST "$SUPABASE_URL/auth/v1/otp?redirect_to=https://evil.example/" -H "apikey: $ANON" -H 'Content-Type: application/json' -d '{"email":"<A>"}'` then open the link | the link redirects to the **Site URL**, not to evil.example | the Location seen |
| 1.5 | Confirm the email link lands with `#access_token=…` (implicit flow). If the project forces PKCE (`?code=`), the browser code cannot sign in — the client must then be changed and re-reviewed | `#access_token` in the landing URL | note |
| 1.6 | Settings → API → Exposed schemas | `public` only (and `graphql_public` if GraphQL is kept); no other table in `public` that should not be reachable | screenshot |

## 2. Real RLS with Supabase's `auth.uid()` and roles

The emulation proved the policies as written; this proves them with Supabase's own `auth` schema, `postgres` role (not a
superuser on hosted projects) and PostgREST.

| # | Run | Expected | Evidence |
|---|---|---|---|
| 2.1 | Apply `001_drafts.sql` in the SQL editor (or `psql "$DATABASE_URL" -f`) as the project's `postgres` role; run it a **second** time | both succeed (the migration is re-runnable) | output |
| 2.2 | `select relname, relrowsecurity, relforcerowsecurity from pg_class where relnamespace='public'::regnamespace and relname in ('drafts','preferences','deletion_log');` | `t,t` for drafts and preferences; `t` for deletion_log | output |
| 2.3 | `select t, r, p from unnest(array['public.drafts','public.preferences','public.deletion_log']) t, unnest(array['anon','authenticated']) r, unnest(array['SELECT','INSERT','UPDATE','DELETE','TRUNCATE','REFERENCES','TRIGGER']) p where has_table_privilege(r,t,p);` | exactly 8 rows: authenticated × {SELECT, INSERT, UPDATE, DELETE} on drafts and preferences. **No TRUNCATE** (RLS does not filter TRUNCATE) | output |
| 2.4 | `select * from pg_policies where schemaname='public';` | 8 policies, all `{authenticated}`, each with `user_id = (select auth.uid())` in USING (select/update/delete) and WITH CHECK (insert/update); none on deletion_log | output |
| 2.5 | Through PostgREST as B: `curl -s "$SUPABASE_URL/rest/v1/drafts?id=eq.<A_DRAFT>" -H "apikey: $ANON" -H "Authorization: Bearer $B_TOKEN"` | `[]` | output |
| 2.6 | As B: `PATCH …/drafts?id=eq.<A_DRAFT>` with `{"body":"x"}` and `Prefer: return=representation`; `DELETE …/drafts?id=eq.<A_DRAFT>`; `PATCH …/drafts` with **no filter** and `{"body":"x"}` (PostgREST may require a filter; if it refuses, record that); then A reads the draft | `[]` each time; A's body and version unchanged | outputs |
| 2.7 | As A: `POST …/drafts` with `{"user_id":"$B_ID","body":"x"}` | 403 / code 42501 (row-level security) | output |
| 2.8 | As A: `PATCH …/drafts?id=eq.<A_DRAFT>` with `{"user_id":"$B_ID","version":99,"id":"00000000-0000-4000-8000-000000000000"}` | 200 with `user_id` = A, same id, version = old + 1 | output |
| 2.9 | Anon key alone: `curl -s "$SUPABASE_URL/rest/v1/drafts" -H "apikey: $ANON"`; same for `preferences`, `deletion_log`; `POST /rest/v1/rpc/…` for any function in `public` | 401 / permission denied; no rows | outputs |
| 2.10 | GraphQL (if enabled): `POST $SUPABASE_URL/graphql/v1` with the anon key and an introspection query; with B's token, query `draftsCollection` | no `drafts` type for anon; B sees only B's rows | outputs |
| 2.11 | SQL editor: `begin; set local role authenticated; select set_config('request.jwt.claims', json_build_object('sub','$B_ID','role','authenticated')::text, true); select count(*) from public.drafts where user_id='$A_ID'; truncate public.drafts; rollback;` | count `0`; TRUNCATE **permission denied** | output |
| 2.12 | 201st insert for A (`insert … select … from generate_series(1,200)` as A, then one more) | `draft_limit`; B can still insert | output |

## 3. Magic-link email delivery

| # | Run | Expected | Evidence |
|---|---|---|---|
| 3.1 | Authentication → SMTP: custom sender on the owner's domain; DNS: SPF, DKIM (the provider's selector), DMARC `p=quarantine` or stricter | records published (`dig TXT <domain>`, `dig TXT <selector>._domainkey.<domain>`, `dig TXT _dmarc.<domain>`) | dig output |
| 3.2 | Request a link from `$APP` to a Gmail and an Outlook address | delivered to the inbox (not spam) within a minute; headers `Authentication-Results: spf=pass dkim=pass dmarc=pass` | headers (kept outside the repo; TEST_LOG notes pass/fail) |
| 3.3 | Open the same link twice; open a link after its lifetime | second use and expired link land with `#error=…`; the page says «لم يُقبل رابط الدخول» | screenshots |
| 3.4 | Open the link in **another browser** than the one that asked | that page does not sign in (the nonce is not in its storage) and says so; the asking page is unaffected | screenshot |
| 3.5 | Arabic email template (if edited) renders right-to-left and keeps `{{ .ConfirmationURL }}` | correct link | screenshot |

## 4. Sessions: expiry, sign-out, "sign out everywhere", refresh-token revocation

The app keeps the access token in memory only and **discards the refresh token**; "sign out everywhere" is not a control
in the app.

| # | Run | Expected | Evidence |
|---|---|---|---|
| 4.1 | Set the access-token expiry to 3600 s (Settings → JWT); sign in; wait past `exp` (or set a short expiry on a test project); press «احفظ في حسابي» with text in the editor | refused: «لم يُحفظ: سجّل الدخول من جديد», text kept, sign-in form shown | screenshot + TEST_LOG |
| 4.2 | Sign in as A in browsers 1 and 2; sign out in 1; immediately save in 2 | 2 still works until its own token expires (expected: access tokens are not revocable at the provider); record how long | timings |
| 4.3 | After 4.2, replay browser 1's access token against `$APP/api/account/drafts` | **401** on the instance that received the sign-out; on another instance (if Render runs more than one) 200 until `exp` — record the instance count | output |
| 4.4 | Capture a refresh token from a landing URL (manually, test account), then `POST $SUPABASE_URL/auth/v1/logout?scope=global` with A's access token; then `POST $SUPABASE_URL/auth/v1/token?grant_type=refresh_token` with `{"refresh_token":"…"}` | the refresh is refused (400/401) after the global sign-out | outputs (tokens redacted) |
| 4.5 | Decide whether a "sign out everywhere" control is needed; if so, build it (calls `logout?scope=global`) and re-run 4.2 | — | decision in TEST_LOG |

## 5. JWKS rotation

| # | Run | Expected | Evidence |
|---|---|---|---|
| 5.1 | Settings → JWT keys: create a standby key; rotate (new key becomes current) | `jwks.json` lists both kids | JSON |
| 5.2 | Sign in after the rotation; save | accepted at once or within 30 s (`jwks_min_refetch`: an unknown kid triggers one refetch) | timings |
| 5.3 | A token signed by the previous key, still before `exp` | accepted while the old key stays in `jwks.json` | output |
| 5.4 | **Revoke** the previous key; replay a token it signed | refused once the server's cache refreshes: within `jwks_ttl` = 600 s. Record the actual window; if 10 minutes is too long for an emergency revocation, restart the service (empties the cache) as the runbook step | timings + runbook note |
| 5.5 | Make `jwks.json` unreachable (e.g. a wrong `SUPABASE_JWKS_URL` on a staging service) | sign-in refused with the generic 401; requests do not hang (at most one fetch per 30 s) | output + response times |

## 6. Account deletion semantics

| # | Run | Expected | Evidence |
|---|---|---|---|
| 6.1 | With `SUPABASE_SERVICE_ROLE_KEY` set on the server: delete account A from the page | answer `auth_user_deleted: true`; `select count(*) from auth.users where id='$A_ID'` = 0; drafts and preferences of A = 0 (cascade and the server's own deletes); B unchanged; one `deletion_log` row with a 64-hex hash and `completed_at` set | SQL output |
| 6.2 | Replay A's old access token at `$APP/api/account/export` | 401 | output |
| 6.3 | Open a magic link A requested before the deletion | refused | screenshot |
| 6.4 | Sign up again with A's address | a **new** user id; none of the old drafts | SQL output |
| 6.5 | Without the service-role key | answer `auth_user_deleted: false` and the page tells the writer to ask the operator; rows of A = 0; decide and document how the operator deletes the auth user and in what time | decision + TEST_LOG |
| 6.6 | Note: `deletion_log.user_hash` is an unsalted SHA-256 of the user id — anyone holding the id can match it. Confirm this is acceptable to the privacy review or add a secret salt | — | privacy review |

## 7. Backup and restore drill

| # | Run | Expected | Evidence |
|---|---|---|---|
| 7.1 | Database → Backups: confirm daily backups (Pro) or PITR, and the retention period | retention known | screenshot |
| 7.2 | Restore the latest backup into a **scratch** project; with a test token of that project read one known draft of A | the text matches what was saved | TEST_LOG |
| 7.3 | Check that an account deleted before the backup is absent, and one deleted after it is present in the restore | as expected; the privacy text must state that deleted data survives in backups until the retention ends | TEST_LOG + `/privacy` wording |
| 7.4 | Delete the scratch project | gone | screenshot |

## 8. Rate limits and abuse

| # | Run | Expected | Evidence |
|---|---|---|---|
| 8.1 | Authentication → Rate limits: email sends per hour, OTP verifications, token refreshes | low values chosen and recorded | screenshot |
| 8.2 | Request links for one address repeatedly | the provider refuses after the limit; the page shows «تعذّر إرسال رابط الدخول الآن» | output |
| 8.3 | Note: `/otp` with `create_user: true` lets anyone make the project send a link to any address. Decide on CAPTCHA (needs a CSP change: script and frame origins) | decision | TEST_LOG |
| 8.4 | 70 account API requests in a minute from one client | 429 after `ACCOUNT_RATE_LIMIT_PER_MINUTE` (60) | output |
| 8.5 | Same with a forged `X-Forwarded-For: 1.2.3.<n>` per request | **check whether the limit is bypassed**: the server keys on the first (client-supplied) entry of X-Forwarded-For (pre-existing behaviour shared with the audit limiter). If bypassed on Render, key on the entry Render appends | output |

## 9. Region, data residency, PDPL

| # | Run | Expected | Evidence |
|---|---|---|---|
| 9.1 | Record the project region and where backups, logs and email processing happen (Supabase's sub-processors list, the SMTP provider) | written list | privacy review |
| 9.2 | Legal review of the cross-border transfer (if any) and of the email address as personal data | signed off | privacy review |
| 9.3 | Supabase's API and auth logs keep request paths (they include `id=eq.<uuid>&user_id=eq.<uuid>`) and token claims (user id, email) for the provider's log retention | stated in `/privacy` | privacy review |
| 9.4 | Publish the `/privacy` and `/limitations` rewrite (prepared in `docs/PRODUCTION_ROADMAP.md`, Stage 2 status) **in the same release** that turns the flag on | pages updated | commit SHA |

## 10. The deployed app with the flag on

| # | Run | Expected | Evidence |
|---|---|---|---|
| 10.1 | `curl -sI $APP/` | CSP `connect-src 'self' https://<project-ref>.supabase.co`; nothing else added | header |
| 10.2 | `ui_journey_e2e`, `ui_final_qa`, `ui_a11y_check`, `ui_workspace_e2e` against `$APP` (`--server $APP`), no sign-in | all pass; no request to the Supabase origin in a guest session | counts |
| 10.3 | A full manual session (sign in, save, rename, 409 with two tabs, export, delete) in Chromium, Firefox and Safari, and on one phone | works; no CSP violation in the console; no token in localStorage, sessionStorage or cookies (the only account key there is `qqa-account-pending-v1`, holding nonces) | notes |
| 10.4 | Render logs for that session: search for `eyJ`, the draft's words, the email address | none; account lines are `account <METHOD> <route> id=<uuid> status=<code>` | grep counts |
| 10.5 | Turn the flag off again (`ACCOUNTS_ENABLED` unset) and redeploy | `/api/health` `accounts_enabled: false`; `/api/account/*` 404; CSP back to `connect-src 'self'` | output |

Only when every row above has a recorded pass, and section 0 is complete, may the flag be turned on in production.
