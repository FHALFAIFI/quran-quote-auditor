# Sources, licences and attribution record

Last reviewed: 2026-10-02 (pre-challenge work; Groq provider live on Render; licence and secret review before the repository was made public; §1b written on 2026-10-02 from Tanzil's own files).

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

## 1b. Uthmani-script texts (used only to build and check the Uthmani matching rules; not read by the running app)

| Item | Detail |
|---|---|
| **Tanzil Quran text, Uthmani, Version 1.1** | Tanzil Project, https://tanzil.net. The file's own copyright block says: *Copyright (C) 2007-2026 Tanzil Project, License: Creative Commons Attribution 3.0*; permission to copy and distribute **verbatim** copies, **changing it is not allowed**; the text may be used in any website or application provided its source (Tanzil Project) is clearly indicated and a link is made to tanzil.net; the notice must be included in all verbatim copies and reproduced in files containing a substantial portion. Tanzil's FAQ separately says its resources are "available for non-commercial purposes" (read 2 Oct 2026); this project is non-commercial, and a commercial use would need Tanzil's confirmation. Downloaded on 2 Oct 2026 from Tanzil's download service (`https://tanzil.net/pub/download/index.php?quranType=uthmani&outType=xml&marks=true&sajdah=true&rub=true&alef=true&tatweel=true`; the options are the download page's defaults plus rub-el-hizb signs); SHA-256 of the XML file `c5052534d63d3856ce25413ff464d0b609f90169a202a1615aa8707efec81244` (a second download the same day gave the same bytes). The option set matters: without the tatweel option Tanzil writes «ٱلرَّحْمَٰنِ» where the text used here has «ٱلرَّحْمَـٰنِ». The credit and link: **Quran text: Tanzil Project, https://tanzil.net**. |
| Where it is used | `tests/fixtures/uthmani_verses.json`: 20 verses taken from Tanzil's XML (the `text` attribute of each aya), **with Tanzil's copyright block inside the file**, used only by the offline unit tests. `eval/uthmani_heldout.json` and `eval/uthmani_dev.json`: short verbatim excerpts inside invented articles (49 verses cited in all, at most 0.9% of the words of the Quran, counting every cited verse whole), each file carrying Tanzil's notice in its `_notice` field; the result files in `eval/results/` that quote those excerpts carry it too. 43 of the 46 unedited Uthmani excerpts in the two sets were checked to be verbatim runs of Tanzil's verses (the other 3 are the Quranpedia-encoded dev cases). `eval/validate_uthmani.py` and `eval/check_uthmani_rules.py` read Tanzil's XML through `eval/tanzil_text.py` (downloaded once to the system temp directory, or the path in `TANZIL_XML`; never committed). No whole-mushaf copy of any Uthmani text is committed. |
| Hand-edited test inputs | The wrong-word cases are hand edits of those excerpts, marked in each case's `source` field and not presented as Quran text. Tanzil's terms say the text may not be changed, and I have not asked Tanzil whether deliberately altered, labelled test inputs are acceptable; until it answers this is an open question, not a permission. |
| Quranpedia mushaf 2 | `GET https://api.quranpedia.net/v1/mushafs/2` (description: Hafs, Uthmani script, King Fahd Complex, text edition), one request on 2 Oct 2026, same source and usage policy as §1. Used offline only to check the rules against a second Uthmani spelling; never fetched by the app and no whole-text copy is committed. (Three cases in `eval/uthmani_dev.json` are written in this encoding.) |
| History of this data | The first versions of the fixture and of the two evaluation sets (committed and pushed on 2 Oct 2026) were taken from a copy of the same Uthmani text served by the Quran.com API (api.quran.com, Quran Foundation). I read that service's developer terms afterwards (https://api-docs.quran.foundation/legal/developer-terms/, last updated 2026-09-26): they restrict redistributing its content and storing it for more than a week, and they are not clear to me on whether they bind its unauthenticated endpoint. That copy is **letter for letter the Tanzil text** (all 6,236 verses compared on 2 Oct 2026; 110 of its strings carry surrounding spaces, and the tatweel option decides the match), so the data files were regenerated from Tanzil's own XML, the scripts no longer call that API, and the six commits that carried the first versions were rebuilt (old → new IDs in `CHANGELOG.md`). As of 2 Oct 2026 I have not asked Quran Foundation or Tanzil anything, and I hold no permission from either; the open question about hand-edited test inputs is above. |
| Role | Data for tests and evaluation. The authority for every verdict, source verse and proposed correction remains the Quranpedia Hafs text (§1); the Uthmani rules only decide whether a quotation's spelling is the same word. |

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
| Status | **Responds.** Locally (30 Sep 2026) real calls returned HTTP 200 on 14/14 labelled cases; on the live demo (2 Oct 2026) real audits returned HTTP 200, and one back-to-back audit returned 429 (free tier, 7,000 input tokens/minute), after which the app falls back visibly. Observed benefit: none measured live (the model proposed the same 7 quotations the deterministic path found); one 3-word misquotation added in one local run. See docs/TEST_LOG.md, docs/EVALUATION.md. |

## 2c. Hosting — Render (web service, free instance)

| Item | Detail |
|---|---|
| Service | https://quran-quote-auditor.onrender.com, built from this repository's `main` branch (settings: docs/RENDER_DEPLOY.md). Free instances sleep when idle and have no persistent disk. |
| Secrets | `GROQ_API_KEY` is entered in Render's dashboard only; it is not in the repository, its history, or `render.yaml`. |

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

## 4b. Ordinary Arabic prose used only to measure false suggestions (local, not part of the repository)

| Item | Detail |
|---|---|
| Source | Arabic Wikipedia (https://ar.wikipedia.org), plain-text extracts through its public API: 36 secular and 27 Islamic-topic articles, fetched on 2026-09-30 with a descriptive User-Agent and pauses between requests (the API answered 429 when asked too fast; the job waited and retried). |
| Licence | CC BY-SA 4.0 (Wikipedia contributors). |
| Use | Read locally to count how often the phrase search reports something in ordinary prose (`docs/EVALUATION.md`). The text is **not committed, not redistributed and not used at runtime**; only aggregate counts and a few short phrases quoted in the evaluation appear in the repository. |

## 5. Project code

MIT licence (see `LICENSE`). Development was assisted by Claude Code, an AI coding
assistant, under the author's direction. It was not used at runtime.

## 6. Existing tools compared in the presentation (read 30 Sep and 2 Oct 2026; not used or copied)

| Tool | What the deck says | Read |
|---|---|---|
| quran-validator (https://github.com/yazinsai/quran-validator) | validates verses in LLM output, can detect untagged quotes, auto-corrects, checks explicit references | README read 2 Oct 2026 |
| Mizan playground (https://mizan.rollingcatsoftware.com/playground) | letter/word counting and Abjad values for an entered verse or Arabic text | page read 2 Oct 2026 |
| Qalam (https://qalam.ai/faq/userGuide) | an Arabic proofreader whose guide describes verifying/formatting highlighted Quran text | read 30 Sep 2026; on 2 Oct only a search snippet of the same guide was seen |

The deck states that these exist and does not claim to be the first; no code or text from them is used.

## 7. Submission materials kept outside the repository

The presentation, the demo video, the screenshots and the build scripts live in a git-ignored local folder and are not part of this repository.

| Item | Rights note |
|---|---|
| Presentation | Built on the organizer's PowerPoint template and logos, used as the organizer's guide allows for submissions; the template itself is not published here. Fonts Readex Pro and Urbanist are embedded by that template (SIL OFL). |
| Screenshots | Captured by the author from this project's own live page; they contain no keys or private data. |
| Demo video | A real screen recording of the live page with burned-in Arabic captions and **no audio track**. An earlier draft had narration made with the macOS «Majed» system voice; Apple's macOS licence restricts using system voices for public sharing, so that narration is not in any file meant for upload (the old files sit in a folder marked DO-NOT-UPLOAD). No music, no stock footage. The author may add their own recorded voice later. |

