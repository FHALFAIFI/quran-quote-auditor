# Deploying on Render (prepared 30 Sep 2026, not yet done)

No Render service exists yet. This guide creates one by hand in the dashboard and deploys the **latest `main` commit**
(`git log -1`; since 1 Oct 2026 it includes the end-of-quotation fix, so the two known false "matched" verdicts are gone; `3273078` is only the commit the guide was first written for). `render.yaml` holds the same values for a Blueprint, but the manual
route below is the one to follow: it lets you choose the commit.

Checked locally on 30 Sep for `3273078` (re-checked on 1 Oct for the latest commit: see `docs/TEST_LOG.md`): a clean `git archive` build with Python 3.12.13 and
`pip install -r requirements.txt` (via uv), started with the command below on `PORT=10000`. Results:
`/api/health` 200, `/` 200, and `POST /api/audit` on sample 2 gave 200 with 7 quotations, 3 needing review, `mode: reduced`.
There was no AI key; nothing has been tried on Render itself.

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
| `QURANPEDIA_CONTACT` | *(optional)* a contact e-mail for Quranpedia's User-Agent |

Everything else keeps the defaults in `.env.example`. `PORT` is set by Render; do not add it.

## Deploy the latest commit

> The branch gained the unmarked-phrase search on 30 Sep and the end-boundary fix on 1 Oct (see `CHANGELOG.md`). Deploy the commit whose hash is at the top of `git log` on `main` (push it to GitHub first), and log that hash. Nothing has been deployed by this work.

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

## Free-tier notes

- The service sleeps after about 15 minutes idle. The first request afterwards can take close to a minute,
  and the Quran text is fetched again (about 1.6 MB). Open `/api/health` and run one audit before recording.
- Memory and speed (measured locally, **not on Render**): a real `uvicorn` process with the phrase search peaked at 94.1 MB (Python 3.12, macOS); Render Free has 512 MB. A full-size article (~1,000 words) took about 0.1–0.4 s here; Render's shared CPU will be slower. See `docs/EVALUATION.md`.
- The file system is temporary. The Quran cache in the temp directory is lost on each restart,
  which only costs one fetch.
- Groq's free tier: each audit sends about 550–615 input tokens, and the limit is 7,000 input tokens per minute
  (roughly 11–12 audits per minute). After a 429 the app skips AI for 120 s and says so in each result.
