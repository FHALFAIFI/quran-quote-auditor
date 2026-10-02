# Proposed pilot, resources and operating costs

Status as of 2 October 2026 (pre-challenge). **Nothing in this file has happened.** There is no pilot partner, no user other than the author, no revenue, no funding, no endorsement and no registered organisation. This is a plan for what would have to be true to continue, and what would be measured.

## 1. Proposed pilot (not started)

| Item | Proposal |
|---|---|
| Who | One content team that publishes Arabic articles or posts quoting the Quran (a publisher, an Islamic-content site or a social-media desk), found and approached by the author **after** the challenge. No team has been contacted. |
| What | 4–6 weeks. Editors paste real drafts into the app before publishing (copy-only: the app posts nothing). The team keeps its normal checking process alongside it, so the pilot cannot make publication less safe. |
| Before it starts | (a) Move the hosting to an always-on instance; (b) put model processing on a setting that does not retain content (Groq Zero Data Retention, or run without the model), because real drafts may be unpublished; (c) have an Arabic specialist review the labelled sets ([LABEL_REVIEW.md](LABEL_REVIEW.md)); (d) agree in writing what data the team is willing to paste. |
| Measured, not assumed | **Usage**: audits per week, articles per editor. **Review quality**: for each quotation the tool flagged, did the editor agree it was a real issue (wording or reference), and did it miss anything the team's own check found? Counts of false alarms («غير محسوم», «possible») per article. **Editor decisions**: approve / reject / unresolved per proposal, with the reason for each rejection. **Time**: only if the team agrees to time its own checks with and without the tool; until then no time saving is claimed. **Costs**: hosting and model charges, listed monthly. |
| What would count as failure | A wrong correction approved because the tool looked sure; a missed misquotation the team's process caught and the tool did not; editors ignoring the uncertainty states. Each is reported as found. |
| Output | A short public report with the counts above and every failure case. If the team does not want to be named, it is not named. |

## 2. What the project needs to continue

| Resource | Today | For a pilot |
|---|---|---|
| Development | One participant (the author), with Claude Code as a coding assistant at build time only | Same, part-time; an Arabic specialist for label review and for judging uncertain cases (unpaid today, no one engaged) |
| Hosting | Render **Free** web service. Render's documentation (read 2 Oct 2026): it spins down after 15 minutes without traffic, a spin-up takes "about one minute", and the workspace has 750 free instance-hours a month. I measured 23 s once. No keep-alive trick is used. | A paid always-on instance. **Price not checked** (Render's pricing page could not be read from the tool I used on 2 Oct 2026): confirm on https://render.com/pricing before budgeting. The service is a small Python process; locally the first audit answers in about 0.7 s once the text is loaded (`docs/EVALUATION.md`), so no large instance is expected to be needed, but that is not measured on Render. |
| Quran text | Quranpedia API: free, no key, 120 requests/min and 10,000/day per IP, attribution asked, no frozen copies ([SOURCES.md](../SOURCES.md)). The app downloads the mushaf once per instance, cached for up to 24 h. | Same, with a contact in the User-Agent (`QURANPEDIA_CONTACT`). Ask Quranpedia whether a pilot service is acceptable and whether they prefer another arrangement. |
| Language model | Groq free tier, `qwen/qwen3.8-27b`. Groq's rate-limit page (read 2 Oct 2026) lists for the free plan 30 requests/min, 1,000 requests/day, 8,000 tokens/min, 200,000 tokens/day; a paid Developer plan exists with higher limits, whose price I did not read. **Our account also met a separate limit of 1,000 output tokens/minute for this model** (not on that page): audits answered 429 «request too large» while the app reserved 4096 output tokens, and answered 200 in two live calls on 3 Oct 2026 after `GROQ_MAX_COMPLETION_TOKENS=800` was set (not a controlled test; see `docs/TEST_LOG.md`). | Optional. The app works without the model, and **no benefit of the model has been measured** (on the live demo it proposed nothing new). A paid tier is justified only if the pilot shows the model adds real quotations, or for the data-retention setting above. |
| Data | Articles are processed in memory, never stored or logged by the server | Same. Any pilot data (counts only, no article text) is kept by the team or by the author with the team's consent. |
| Money | None spent beyond the author's own time | Hosting (always-on) and possibly model charges. Possible funding sources are open questions: a grant or sponsorship from an Islamic-content organisation, an institutional host, or the team itself. **None is arranged and none is promised.** |

## 3. Honest list of unknowns

- Whether editors would use it on real deadlines, and whether the uncertainty states help or annoy them.
- How often real articles contain unmarked quotations the tool misses ([EVALUATION.md](EVALUATION.md) measures this only on small, author-written sets).
- The cost per article at real volume; whether the free Quranpedia limits suffice.
- Whether Tanzil, Quranpedia and Quran Foundation terms permit what a pilot would do (SOURCES.md lists the open questions; nobody has been asked).
- Whether any organisation wants to fund or host a tool like this.
