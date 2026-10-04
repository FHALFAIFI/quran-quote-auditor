# Deploying on Render

The live demo (https://quran-quote-auditor.onrender.com) was created from this guide on 1–2 Oct 2026 (pre-challenge). The service does not expose its commit hash, so read it on the service's Events page; `docs/TEST_LOG.md` records what was observed. This guide creates a service by hand in the dashboard and deploys the **latest `main` commit**
(`git log -1`; since 1 Oct 2026 it includes the end-of-quotation fix (the two known false "matched" verdicts are gone) and the matching start-of-quotation rule (a possibly wrong first word reads "uncertain", never "matched"); `3273078` is only the commit the guide was first written for). `render.yaml` holds the same values for a Blueprint, but the manual
route below is the one to follow: it lets you choose the commit.

Checked locally on 30 Sep for `3273078` (re-checked on 1 Oct for the latest commit: see `docs/TEST_LOG.md`): a clean `git archive` build with Python 3.12.13 and
`pip install -r requirements.txt` (via uv), started with the command below on `PORT=10000`. Results:
`/api/health` 200, `/` 200, and `POST /api/audit` on sample 2 gave 200 with 7 quotations, 3 needing review, `mode: reduced`.
There was no AI key in that check; the later live checks on Render itself are in `docs/TEST_LOG.md`.

## Settings (New → Web Service → connect GitHub `FHALFAIFI/quran-quote-auditor`)

| Field | Value |
|---|---|
| Branch | `main` |
| Language / runtime | Python 3 |
| Root directory | *(empty)* |
| Build command | `pip install -r requirements.txt` |
| Start command | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
| Instance type | Free |
| Region | Frankfurt (any is fine) |
| Health check path (Advanced) | `/api/health` |
| Auto-deploy (Advanced) | **Off** |

**Python version:** do **not** set `PYTHON_VERSION`. The repository's `.python-version` (`3.12`) selects the latest 3.12 patch. If you do set `PYTHON_VERSION`, Render requires a full version
such as `3.12.13`. In the build log, check that the line with the Python version shows 3.12.x.

## Environment variables (Advanced → Environment Variables)

| Name | Value |
|---|---|
| `AI_PROVIDER` | `groq` |
| `GROQ_API_KEY` | *your key: type it into Render only, never into chat, a file or a screenshot* |
| `GROQ_MODEL` | `qwen/qwen3.8-27b` |
| `EXTRACTION_PROMPT` | `v2` |
| `GROQ_MAX_COMPLETION_TOKENS` | `800` (see below: needed on a Groq account limited to 1,000 output tokens/minute; the code default is 4096) |
| `QURANPEDIA_CONTACT` | *(optional)* a contact e-mail for Quranpedia's User-Agent |

Everything else keeps the defaults in `.env.example`. `PORT` is set by Render; do not add it.

## Deploy the latest commit

> Deploy the commit whose hash is at the top of `git log` on `main` (push it to GitHub first) and log that hash. Observed on 2 Oct: the service redeployed itself about 40 s after each push to `main`, although `render.yaml` sets auto-deploy off; check the Auto-Deploy setting if you want manual control.

1. Create the service with the settings above. Render starts a first deploy of the latest `main` commit.
2. If you prefer to be explicit: service page → **Manual Deploy** → **Deploy a specific commit** → paste that hash.
3. Wait for "Live" in the Events tab. Note the deploy's commit in `docs/TEST_LOG.md`.

## Check it (in this order, and log each result)

1. `https://<service>.onrender.com/api/health` should show `"mode": "ai"`, `"ai_configured": true`,
   `"provider_name": "groq"` and `ai_last_call.outcome: "never_called"`. The key must not appear anywhere.
   Health checks make no Groq call.
2. Open the page, then run the sample «مقال عن الصبر» once to load the Quran text. The result notice
   must say whether the model responded («استجاب نموذج …») or show the fallback warning.
3. `python scripts/e2e_check.py https://<service>.onrender.com` for the API, sample and error-case checks.
4. Only if the live site shows it: write down what AI added, with the model name as displayed.

## External uptime monitor (not set up; for the owner)

Nothing is signed up for. Any free HTTP uptime service that can request a URL on a schedule and look for a keyword in the answer will do.
`/api/health` is public, needs no key and returns no personal data and no article text.

1. **URL:** `https://<service>.onrender.com/api/health?deep=1`, method GET, every 5 minutes, timeout 60 s (a sleeping Free
   instance takes about a minute to wake). `?deep=1` first makes sure the Quran text is loaded, so a fresh instance does not report
   "not loaded". It costs at most one Quranpedia request per 24 hours (or one per minute while the source is failing), exactly as an
   audit would. Render's own health check (`healthCheckPath: /api/health`, without `deep`) never fetches anything.
2. **Alert when** (the JSON is compact, no spaces):
   - the status is not 200, or there is no answer within 60 s, twice in a row: the service is down;
   - the keyword `"source_ok":true` is **absent**: the Quran text is stale (served from an old copy) or Quranpedia is unreachable
     (`source.last_error` names the error type);
   - the keyword `"http_status":429` is **present** in the answer: the model's last call was refused for its rate limit. A service
     that can evaluate JSON can instead alert when `ai_recent.rate_limited / ai_recent.calls` passes a threshold (proposal: 0.2 with
     at least 5 calls). `ai_recent` counts real model calls since the process started (`calls`, `ok`, `failed`, `rate_limited`,
     `since`); calls skipped during a cooldown are not counted. The counters start again at every restart, and a Free instance restarts
     after each sleep. With the model off (`AI_PROVIDER=none`), `ai_recent` is `null`.
3. **After each deploy:** check by hand that `build` equals the commit that was released.
4. **Fire one alert on purpose** (for example, point the monitor at `/api/health-missing` for one check), see that it arrives, and
   record it in `docs/TEST_LOG.md`. That record is the Stage 4 evidence; it does not exist yet.

Note for the Free plan: a check every 5 minutes keeps the instance awake (it sleeps after 15 idle minutes), which uses about 744 of
the workspace's 750 free instance hours a month (render.com/docs/free, read 4 Oct 2026). On a paid instance this does not matter.

Error reporting: there is no external error-reporting service. The app's own log lines go to Render's log only; they carry the path,
the status and, for an unexpected error, the exception type. As defence in depth, `app/logging_safety.py` removes any run of Arabic
text longer than 20 letters from every log record (message, arguments and traceback, percent-encoded or not) before it is written.

## Free-tier notes

- The service sleeps after about 15 minutes idle. The first request afterwards can take close to a minute,
  and the Quran text is fetched again (about 1.6 MB). Open `/api/health` and run one audit before recording.
- Memory and speed (measured locally, **not on Render**): a real `uvicorn` process with the phrase search peaked at 94.1 MB (Python 3.12, macOS); Render Free has 512 MB. A full-size article (~1,000 words) took about 0.1–0.4 s here; Render's shared CPU will be slower. See `docs/EVALUATION.md`.
- The file system is temporary. The Quran cache in the temp directory is lost on each restart,
  which only costs one fetch.
- Groq's free tier: each audit sends about 550–615 input tokens, and the limit is 7,000 input tokens per minute
  (roughly 11–12 audits per minute). After a 429 the app skips AI for 120 s and says so in each result.
- **A second limit, on output tokens (note of 3 Oct 2026).** Groq answered HTTP 429 («Request too large … output tokens per minute (OTPM): Limit 1000, Requested 1100–1994») to audits of the live service on 30 Sep–3 Oct 2026 while the app reserved the default 4096 output tokens per request; Groq's own «Requested» figure was never 4096 and its estimate is not documented, so the cause is observed, not proven. On 3 Oct 2026 `GROQ_MAX_COMPLETION_TOKENS=800` was set on Render and two live audits of the demonstration article (one audit, one video take) both answered HTTP 200 (`ai.outcome` ok, 4 proposed, 4 located, 0 added by the model). That is two calls, not a controlled test. The demonstration article needs about 75–90 output tokens, but an answer longer than the cap is cut off and the whole AI result is dropped (the deterministic result stands, AI is skipped for the cooldown), so an article with many quotations may need a higher value. Set `GROQ_MAX_COMPLETION_TOKENS=800` in the Render dashboard (Environment) before relying on the model; it is not in `render.yaml`.
