---
name: Pilot observation
about: One usability problem seen in a first-time-writer pilot session (docs/WRITER_PILOT.md). Real participants only.
title: "[pilot][S?] <task> — <short description>"
labels: pilot
---

<!--
Only observations from a real participant session (docs/WRITER_PILOT.md §1) belong here.
Assistant walkthroughs, browser automation and invented participants are NOT pilot results: report those as ordinary bugs.
Do not paste article text, participant names, or screenshots showing article text unless the participant agreed in writing.
-->

**Severity:** S1 / S2 / S3 / S4
<!-- S1 wrong verse text or wrong correction shown, or data exposure (any wrong correction is S1)
     S2 task blocked, or a misquotation shown as matched
     S3 confusion the participant recovered from
     S4 cosmetic -->

**Participants affected:** P_ (add each further participant who met it; count: _ of 5)

**Priority:** severity weight (S1 = 4, S2 = 3, S3 = 2, S4 = 1) × participants affected = _
<!-- Every S1 is fixed before release regardless of the score. -->

**Task:** T1 start / T2 verse suggestion / T3 audit long article / T4 settle uncertain / T5 approve and undo / T6 final review / T7 copy / Q1 model role / Q2 privacy

**Material:** own_published / own_rights_cleared / unpublished_agreed / backup_demo / backup_sample3

**Build and setting:** commit from `/api/health`: ______ ; service: live / no-model ; device, browser, viewport: ______

**What happened** (the screen state and what the participant did or said; no article text):

**What the participant expected:**

**Help given** (none / the hint, and after how long):

**Recorded counts from this moment** (missed quotations, unwanted «possible», wrong corrections, wrong approvals):

**Sheet rows:** WRITER_PILOT_SHEET rows for P_ / T_
