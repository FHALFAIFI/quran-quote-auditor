# Sources, licences and attribution record

Last reviewed: 2026-09-29 (pre-challenge work; Groq provider added).

## 1. Quran text — Quranpedia (authoritative source)

| Item | Detail |
|---|---|
| Provider | Quranpedia — الموسوعة القرآنية, https://quranpedia.net |
| Endpoint | `GET https://api.quranpedia.net/v1/mushafs/1` (mushaf 1 = Hafs ʿan ʿĀṣim) |
| Docs & policy | https://api.quranpedia.net/ · https://quranpedia.net/api-docs#usage-policy |
| Terms (summary, as read on 2026-09-28) | Free, no authentication. Attribution is optional for apps that query live but appreciated; it is required when republishing data as a dataset. Do not bulk-scrape or republish. Limits: 120 requests/min and 10,000/day per IP. Include a contact in the User-Agent for high-volume clients. |
| How this app complies | One documented request per server instance fetches the whole mushaf. It is cached for up to 24 h in that instance (memory plus temp dir) and never republished or committed. Every verse links back to Quranpedia, the footer credits Quranpedia, and an optional contact goes in the User-Agent via `QURANPEDIA_CONTACT`. |
| Challenge alignment | The organizer's reference pack lists the King Fahd Complex edition *or the text on quranpedia.net* as the approved Quran text. |
| Test fixture | `tests/fixtures/hafs_subset.json` contains 36 verses copied from the same endpoint on 2026-09-28. It is used only for offline unit tests, credited inside the file, and never used by the running app. |
| Metadata | `app/surahs.py` holds surah names and verse counts derived from the same endpoint (no verse text), plus common alternative surah names written by hand. |

## 2. AI provider — Google Gemini (candidate extraction only)

| Item | Detail |
|---|---|
| Service | Gemini API `models/{model}:generateContent`, default model `gemini-3.8-flash` (configurable) |
| Terms | https://ai.google.dev/gemini-api/terms. Data use depends on your tier; check before processing real content. |
| Role | Proposes candidate quotation spans and nearby reference strings as JSON. **It is never a source of Quran text or of verdicts.** Every candidate is re-located in the article, and anything not present is discarded. |
| Verification status | **Unverified** — every real request returned 503 or 429 (28–29 Sep 2026). See docs/TEST_LOG.md. |
| Key | Supplied by the deployer through `GEMINI_API_KEY`. It is not included in this repository. |

## 2b. AI provider — Groq (candidate extraction only; default when its key is set)

| Item | Detail |
|---|---|
| Service | Groq OpenAI-compatible Chat Completions, `POST https://api.groq.com/openai/v1/chat/completions`, strict `response_format: json_schema` |
| Model | `qwen/qwen3.8-27b` by default (configurable via `GROQ_MODEL`). Groq lists it as a **preview** model (docs read 2026-09-29: https://console.groq.com/docs/models, https://console.groq.com/docs/structured-outputs, https://console.groq.com/docs/reasoning). `reasoning_effort: "none"` is sent for qwen models. |
| Data | "Your Data in GroqCloud" (https://console.groq.com/docs/your-data, read 2026-09-29): by default inference data is not retained, except up to 30 days for reliability/abuse monitoring; Zero Data Retention can be enabled per organization. Check the current terms before processing real content. |
| Role | Identical to Gemini's: proposes candidate spans and nearby reference strings only. **Never a source of Quran text, verdicts or corrections.** |
| Key | `GROQ_API_KEY`, supplied by the deployer; not in this repository. |
| Verification status | **Unverified** — no real Groq call has been made yet (no key configured). See docs/TEST_LOG.md. |

## 3. Fonts and design

| Asset | Licence | Use |
|---|---|---|
| Readex Pro (Google Fonts) | SIL Open Font License 1.1 | UI text; also the font of the organizer's template |
| Amiri Quran (Google Fonts) | SIL Open Font License 1.1 | Displaying source verses |
| Colours: navy `#12183F`, violet `#6150EA`, blue `#3F6FE6`, turquoise `#2EF2C2` and tints | Taken from the challenge template's palette | Challenge branding |

Fonts are loaded from `fonts.googleapis.com`/`fonts.gstatic.com`, so visitors' browsers
contact Google Fonts. The organizer's PDFs and PPTX are **not** included in this repository (they are git-ignored).

## 4. Software dependencies (pinned in `requirements*.txt`)

Development-only, not in requirements: Playwright (Apache-2.0) for `scripts/ui_e2e.mjs`, installed in a scratch directory;
Node.js built-in test runner for `tests/revision.test.mjs`.


| Package | Licence |
|---|---|
| FastAPI, Pydantic, pydantic-core, annotated-types, annotated-doc, typing-inspection | MIT |
| Starlette, httpx, httpcore, uvicorn, click, idna | BSD-3-Clause |
| anyio, h11, pytest, pluggy, iniconfig | MIT |
| certifi | MPL-2.0 |
| typing_extensions | PSF-2.0 |
| packaging | Apache-2.0 / BSD-2-Clause |
| Pygments | BSD-2-Clause |

## 5. Project code

MIT licence (see `LICENSE`). Development was assisted by Claude Code, an AI coding
assistant, under the author's direction. It was not used at runtime.
