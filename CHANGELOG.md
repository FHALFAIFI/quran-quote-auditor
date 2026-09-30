# Changelog

## Challenge period (4–6 October 2026)

_Record every change made during the challenge here, with its date. Nothing yet._

## Pre-challenge work (not scored) — after the baseline tag

| Date | Commit(s) | Change |
|---|---|---|
| 2026-09-28 | `e864a02` | Shorter AI failure wait: 12 s budget, 8 s per attempt, cooldown |
| 2026-09-28 | `c2cf42b` | Labelled evaluation set, fallback results, clearer AI status banner |
| 2026-09-28 | `07a777a`, `2860743`, `125343a` | Vercel upload hygiene, RTL banner fix, deploy notes |
| 2026-09-29 | `0dc3a12` | Post-reset Gemini check: 503; AI extraction still unverified |
| 2026-09-29 | `334a531` | Groq provider; per-audit AI outcome; health separates configured from responded |
| 2026-09-29 | `48d92b2` | Editor workflow: source-backed corrections, approve/reject, revised article, review record |
| 2026-09-29 | `4b0a5c5` | Evaluation: AI mode stops on first fallback; correction-safety scoring |
| 2026-09-29 | `3e74cf3` | Documentation, label-review checklist, continuation plan |
| 2026-09-29 | `f51bbc3` | Copy-only reply draft for a social post; deploy attempt logged (blocked); submission drafts updated (local) |
| 2026-09-30 | `71769ae` | First real Groq calls: responded on 3/3 samples and 14/14 labelled cases, but detection unchanged (25/28, unmarked 1/4); labels unchanged; raw result `eval/results/ai-20260930-165858.json`; Groq privacy note in the page footer; deploy still blocked |
| 2026-09-30 | (this commit) | Unmarked-quote experiment: versioned prompts, prompt v2 now default (labelled 26/28, held-out 4/6 vs fallback 25/28 and 3/6); held-out set; eval runner `--cases/--tag/--pace`, stopped runs saved; Groq OTPM 429 finding; Vercel diagnosis |

## Pre-challenge baseline — 2026-09-28

Initial working version (tag `pre-challenge-baseline`, commit `532e965`). See [BASELINE.md](BASELINE.md) for the full inventory.
