// Browser end-to-end check of the editor workflow (Playwright, Chromium).
//
//   NODE_PATH=<scratch>/node_modules node scripts/ui_e2e.mjs [--shots DIR] [--server URL] [--python PATH]
//
// Flow: sample 2 → audit → approve the reference fix for «الشرح: 6» → reject one optional formatting change → the revised article
// differs only in that span → the final check shows it in its sentence → copy → reply draft → print record → decisions survive a
// reload → markup pasted into the article is shown as text, never executed → phone layout. Starts its OWN AI-off server unless --server.
import { chromium, check, norm, readSample, testServer, openPage, openRow, finish } from "./_ui_common.mjs";

const server = await testServer();
const browser = await chromium.launch();
const { page, errors, shot, overflowX } = await openPage(browser, server.base, { width: 1440, height: 900 }, false, "e-desktop");
await page.goto(server.base);
await page.evaluate(() => sessionStorage.clear());
await page.reload();
await page.waitForSelector("#mode-banner", { state: "attached" });
await shot("01-home");

await page.selectOption("#sample-select", "sample-2");
await page.waitForFunction(() => document.getElementById("article").value.length > 100);
const original = (await page.inputValue("#article")).replace(/\r\n?/g, "\n");
check(original === readSample("sample-2"), "the sample loaded");
await page.click("#audit-btn");
await page.waitForSelector("#results:not([hidden]) #current article", { timeout: 60000 });
await page.waitForTimeout(600);
await shot("02-results");
check((await page.locator("#queue .row").count()) === 7, `sample 2 lists 7 quotations (got ${await page.locator("#queue .row").count()})`);
check((await page.inputValue("#revised-text")) === original, "revised article equals the original before any approval");
check(!(await page.textContent("#input-summary")).includes("null") && (await page.locator("#input-body").isHidden()), "after the audit the pasted text gives way to one summary line (the article is shown once)");

// find the finding with the wrong reference through the page's own state, open it from the list and approve
const target = await page.evaluate(() => { const f = lastResult.findings.find((x) => x.quote.includes("فإن مع العسر يسرا") && x.changes.some((c) => c.kind === "reference" && !c.optional)); return { id: f.id, change: f.changes.find((c) => c.kind === "reference" && !c.optional).id }; });
await openRow(page, target.id);
const dm = norm(await page.textContent(`[data-change="${target.change}"] .delta`));
check(dm.includes("الشرح") && dm.includes("٦") && dm.includes("٥"), `the reference change is shown exactly («${dm}»)`);
await page.locator(`[data-change="${target.change}"] button[data-act="approved"]`).click();
await page.waitForTimeout(500);
check(/اعتمدتَ تغيير «الشرح: ٦» إلى «الشرح: ٥»/.test(norm(await page.textContent("#undo-line"))), "the page says exactly what was approved");

// reject an optional formatting change (it sits in its own folded box, apart from the corrections)
const optId = await page.evaluate(() => lastResult.findings.flatMap((f) => f.changes).find((c) => c.optional && c.kind === "vocalize").id);
const optFinding = await page.evaluate((id) => lastResult.findings.find((f) => f.changes.some((c) => c.id === id)).id, optId);
await openRow(page, optFinding);
await page.locator(`#finding-${optFinding} details.f-all > summary`).click();
const opt = page.locator(`[data-change="${optId}"]`);
await opt.locator('button[data-act="rejected"]').click();
check((await page.locator(`[data-change="${optId}"] button[data-act="rejected"]`).getAttribute("aria-pressed")) === "true", "the optional change is marked as ignored");

const revised = await page.inputValue("#revised-text");
const expected = original.replace("{فإن مع العسر يسرا} [الشرح: 6]", "{فإن مع العسر يسرا} [الشرح: 5]");
check(expected !== original, "test precondition: the sample contains the wrong reference");
check(revised === expected, "revised article = original with ONLY «الشرح: 6» → «الشرح: 5»");
check(revised.split("\n").length === original.split("\n").length, "line breaks preserved");
await page.locator("#final").scrollIntoViewIfNeeded();
const fin = norm(await page.textContent("#final-changes"));
check((await page.locator("#final-changes del").allTextContents()).includes("الشرح: 6") && (await page.locator("#final-changes ins").allTextContents()).includes("الشرح: 5"), "the final check shows the change in its sentence (old struck, new marked)");
check(fin.includes("الاقتباس") && /الفقرة|السطر/.test(fin), "and says where it is");
await page.locator("#final details.full-text summary").click();
check((await page.locator("#preview-view del").allTextContents()).includes("الشرح: 6") && (await page.locator("#preview-view .unresolved").count()) >= 1, "the full before/after view marks the change and the quotations not settled");
await shot("03-final");

await page.click("#copy-btn");
const clip = await page.evaluate(() => navigator.clipboard.readText().catch(() => null));
check(clip === null || clip.replace(/\r\n?/g, "\n") === revised, "the copy button puts the revised article on the clipboard");
check(clip === null || /تم النسخ/.test(await page.locator("#copy-btn").innerText()), "the copy button confirms the copy on the button itself");
check(clip === null || (await page.locator("#copy-note").innerText()).includes("نُسخ المقال المعدّل"), "a note beside the copy button confirms the copy");

await page.click(".reply-box summary");
const reply = await page.inputValue("#reply-text");
check(reply.includes("«الشرح: 6» ← الصواب «الشرح: 5»") && reply.includes("وليس حكمًا على المنشور كله"), "the reply draft lists the approved fix and the scope disclaimer");
check(!reply.includes("155-156"), "the reply draft omits corrections that were not approved");

await page.evaluate(() => window.dispatchEvent(new Event("beforeprint")));
const rec = await page.locator("#print-record").innerText();
check(rec.includes("سجل مراجعة الاقتباسات") && rec.includes("ليست شهادة"), "the record has a title and says it is not a certificate");
check(rec.includes("الشرح: 5") && rec.includes("الشرح: 6") && rec.includes("quranpedia"), "the record lists the approved change and the source link");
check(rec.includes("وقت جلب المصدر") && rec.includes("هل عمل الاستخراج بالذكاء الاصطناعي") && rec.includes("غير محسومة"), "the record states the source time, whether AI ran, and the unresolved items");
await page.emulateMedia({ media: "print" });
await shot("04-print-record", true);
await page.emulateMedia({ media: "screen" });

await page.reload();
await page.waitForSelector("#results:not([hidden]) #current article");
check((await page.inputValue("#revised-text")) === expected, "decisions survive a reload (sessionStorage)");

// markup in the article is shown as text, never parsed
await page.click("#edit-btn");
await page.click("#clear-btn");
await page.fill("#article", '<img src=x onerror="window.__pwned=1"> قال تعالى: ﴿اقرأ باسم ربك الذي خلق﴾ [العلق: 2] <script>window.__pwned=2</script>');
await page.click("#audit-btn");
await page.waitForSelector("#results:not([hidden]) #current article");
const fix = await page.evaluate(() => lastResult.findings.flatMap((f) => f.changes).find((c) => c.kind === "reference" && !c.optional)?.id);
if (fix) { await page.locator(`[data-change="${fix}"] button[data-act="approved"]`).click(); }
check(await page.evaluate(() => window.__pwned === undefined), "no script executed from article text");
check((await page.locator("#article-view img, #preview-view img, #current img, #article-view script").count()) === 0, "no injected elements in the page");
check((await page.inputValue("#revised-text")).includes('<img src=x onerror="window.__pwned=1">'), "markup preserved verbatim as text in the revised article");

const m = await openPage(browser, server.base, { width: 390, height: 844 }, true, "e-phone");
await m.page.goto(server.base);
await m.page.selectOption("#sample-select", "sample-2");
await m.page.waitForFunction(() => document.getElementById("article").value.length > 100);
await m.page.click("#audit-btn");
await m.page.waitForSelector("#results:not([hidden]) #current article", { timeout: 60000 });
check((await m.overflowX()) <= 1, `phone: no horizontal scroll (overflow ${await m.overflowX()}px)`);
await m.shot("06-top");
check(errors.length === 0 && m.errors.length === 0, `no console errors (${[...errors, ...m.errors].join(" | ")})`);
finish(server, browser);
