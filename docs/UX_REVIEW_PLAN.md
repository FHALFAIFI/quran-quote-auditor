# Arabic editor usability check

This is a plan, not a completed user study. The automated browser and accessibility checks in `docs/TEST_LOG.md` do not establish that a writer understands the tool. The plan was proposed with the review branch of 3 Oct 2026 (a Codex patch) and kept, with the questions below tied to the states the interface now distinguishes.

## Participants and material

Ask three to five Arabic content editors or proofreaders who have not used this interface. Use only synthetic articles and the built-in demonstration article. Record the role and device, not names or private writing. Do not coach during a task; ask what the participant expected after it.

## Tasks

1. Start from the empty page. Run the demonstration article, decide both proposed changes, inspect the source of one quotation, and copy the revised article.
2. Paste a short article containing a partial or uncertain quotation without a reference. Find the unresolved place, choose the intended verse if the evidence supports it, or leave it for manual review.
3. In a longer synthetic article, edit words next to a quotation after an audit, recheck, and explain whether the earlier decision still applies.

For each task, record completion, incorrect approvals, time from start to completion, requests for help, and the exact control or sentence that caused hesitation. Then ask the participant:

- which words come from the Quran source, and where that source is named;
- what the difference is between «مطابق للمصحف», «يحتاج تأكيدك» and «أبقيتَه كما كتبتَ» (a match found by the tool, a passage that may not be a quotation, and the writer's own decision);
- what the optional model contributes;
- what the final copy does **not** certify.

## Release decisions

Fix repeatable comprehension errors before polishing decoration. Keep the original observation and the change made in `docs/TEST_LOG.md`. If a participant cannot identify the source, mistakes a possible quotation for a confirmed one, reads a quotation kept as written as verified, or believes copying publishes the article, treat that as a release issue. Report the number of participants and outcomes plainly; do not call this a general accuracy or time-saving study.

## Separate AI evaluation

The product's runtime model is a different question from the coding model used to design this interface. Freeze a small independently reviewed set of difficult unmarked excerpts before running it. Compare the same articles with the optional model on and off; count genuinely added correct quotations, added false positives, errors and latency. Preserve failures and the provider outcome. Until this shows a repeatable gain, do not claim that the model improves detection.
