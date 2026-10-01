// Browser end-to-end check of the editor workflow (Playwright, Chromium).
//
//   npm i playwright            # in any scratch directory; not a project dependency
//   NODE_PATH=<scratch>/node_modules node scripts/ui_e2e.mjs http://localhost:8000 [screenshot-dir]
//
// Flow: load sample 2 → audit → approve the reference fix for «الشرح: 6» → reject one
// optional change → check the revised article (only that span changed, all other
// characters identical) → review-only filter → print-record contents → mobile layout.
// Also pastes an article containing markup and checks that nothing is injected.
import { createRequire } from "module";
import fs from "fs";
import path from "path";

const require = createRequire(import.meta.url);
const { chromium } = require("playwright");
const base = (process.argv[2] || "http://localhost:8000").replace(/\/$/, "");
const shots = process.argv[3] || null;
if (shots) fs.mkdirSync(shots, { recursive: true });

let failures = 0;
const check = (cond, msg) => { console.log(`${cond ? "PASS" : "FAIL"}  ${msg}`); if (!cond) failures++; };
const shot = async (page, name, opts = {}) => { if (shots) await page.screenshot({ path: path.join(shots, name), ...opts }); };

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1, locale: "ar" });
await ctx.grantPermissions(["clipboard-read", "clipboard-write"], { origin: base });
const page = await ctx.newPage();
const errors = [];
page.on("pageerror", (e) => errors.push(String(e)));
page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });

await page.goto(base + "/");
await page.waitForSelector("#mode-banner:not([hidden])");
await shot(page, "01-home.png");

// sample 2
await page.selectOption("#sample-select", "sample-2");
await page.waitForFunction(() => document.getElementById("article").value.length > 100);
const original = await page.inputValue("#article");
await page.click("#audit-btn");
await page.waitForSelector("#results:not([hidden]) .finding", { timeout: 60000 });
await page.waitForTimeout(600);
await shot(page, "02-results.png");

const nFindings = await page.locator(".finding").count();
check(nFindings === 7, `sample 2 shows 7 findings (got ${nFindings})`);

// initially nothing approved: revised text identical to the original
check((await page.inputValue("#revised-text")) === original.replace(/\r\n?/g, "\n"), "revised article equals original before any approval");

// approve reference fix «الشرح: 6» → «الشرح: 5»
const refChange = page.locator('[data-change$="-reference"]').filter({ hasText: "الشرح" }).first();
await refChange.scrollIntoViewIfNeeded();
await refChange.locator('button[data-act="approved"]').click();
check(await refChange.evaluate((n) => n.classList.contains("approved")), "reference change marked approved");
await shot(page, "03-approved-change.png");

// reject an optional vocalization change
const optional = page.locator(".change.optional").first();
await optional.locator('button[data-act="rejected"]').click();
check(await optional.evaluate((n) => n.classList.contains("rejected")), "optional change marked rejected");

const revised = await page.inputValue("#revised-text");
const expected = original.replace("{فإن مع العسر يسرا} [الشرح: 6]", "{فإن مع العسر يسرا} [الشرح: 5]");
check(expected !== original, "test precondition: sample contains the wrong reference");
check(revised === expected, "revised article = original with ONLY «الشرح: 6» → «الشرح: 5»");
check(revised.split("\n").length === original.split("\n").length, "line breaks preserved");

// preview shows del/ins and unresolved marks
const del = await page.locator("#preview-view del").allTextContents();
const ins = await page.locator("#preview-view ins").allTextContents();
check(del.includes("الشرح: 6") && ins.includes("الشرح: 5"), `preview shows before/after (del=${JSON.stringify(del)} ins=${JSON.stringify(ins)})`);
check((await page.locator("#preview-view .unresolved").count()) >= 1, "unresolved quotations marked in preview");
await page.locator(".editor-card").scrollIntoViewIfNeeded();
await shot(page, "04-editor-preview.png");

// copy
await page.click("#copy-btn");
const clip = await page.evaluate(() => navigator.clipboard.readText().catch(() => null));
check(clip === null || clip === revised, "copy button puts the revised article on the clipboard");
// the confirmation must appear beside the button that was pressed, not only in the page-level status line
check(clip === null || /تم النسخ/.test(await page.locator("#copy-btn").innerText()), "copy button confirms the copy on the button itself");
check(clip === null || (await page.locator("#copy-note").innerText()).includes("نُسخ المقال المعدّل"), "a note beside the copy button confirms the copy");
// the nine summary tiles never leave a single orphan tile on a row (one row on wide screens, a 3 x 3 block below 1000 px)
const tileRows = await page.$$eval("#summary .tile", (t) => [...new Set(t.map((x) => Math.round(x.getBoundingClientRect().top)))].length);
check(tileRows === 1 || tileRows === 3, `summary tiles form ${tileRows} row(s) (1 or 3 expected, no orphan tile)`);

// reply draft for a social post: approved fix only, no claim about the whole post
await page.click(".reply-box summary");
const reply = await page.inputValue("#reply-text");
check(reply.includes("«الشرح: 6» ← الصواب «الشرح: 5»") && reply.includes("وليس حكمًا على المنشور كله"), "reply draft lists the approved fix and the scope disclaimer");
check(!reply.includes("155-156"), "reply draft omits corrections that were not approved");

// review-only filter
await page.check("#only-review");
const nFiltered = await page.locator(".finding").count();
check(nFiltered > 0 && nFiltered < nFindings, `review filter narrows the list (${nFiltered}/${nFindings})`);
await page.uncheck("#only-review");

// print record
await page.evaluate(() => window.dispatchEvent(new Event("beforeprint")));
const rec = await page.locator("#print-record").innerText();
check(rec.includes("سجل مراجعة الاقتباسات"), "record has a title");
check(rec.includes("ليست شهادة"), "record says it is not a certificate");
check(rec.includes("الشرح: 5") && rec.includes("الشرح: 6"), "record lists the approved change (original and replacement)");
check(rec.includes("quranpedia"), "record includes the source link");
check(rec.includes("وقت جلب المصدر"), "record includes source retrieval time");
check(rec.includes("هل عمل الاستخراج بالذكاء الاصطناعي"), "record states whether AI extraction ran");
check(rec.includes("غير محسومة"), "record lists unresolved items");
await page.emulateMedia({ media: "print" });
if (shots) await page.pdf({ path: path.join(shots, "review-record.pdf"), format: "A4", printBackground: true });
await shot(page, "05-print-record.png", { fullPage: true });
await page.emulateMedia({ media: "screen" });

// session persistence: reload keeps decisions
await page.reload();
await page.waitForSelector("#results:not([hidden]) .finding");
check((await page.inputValue("#revised-text")) === expected, "decisions survive a reload (sessionStorage)");

// XSS: markup in the article is shown as text, never parsed
await page.click("#clear-btn");
await page.fill("#article", '<img src=x onerror="window.__pwned=1"> قال تعالى: ﴿اقرأ باسم ربك الذي خلق﴾ [العلق: 2] <script>window.__pwned=2</script>');
await page.click("#audit-btn");
await page.waitForSelector("#results:not([hidden]) .finding");
const refFix = page.locator('[data-change$="-reference"]').first();
await refFix.locator('button[data-act="approved"]').click();
check(await page.evaluate(() => window.__pwned === undefined), "no script executed from article text");
check((await page.locator("#article-view img, #preview-view img, #findings img, #article-view script").count()) === 0, "no injected elements in the page");
check((await page.inputValue("#revised-text")).includes('<img src=x onerror="window.__pwned=1">'), "markup preserved verbatim as text in the revised article");

// mobile
const m = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true, locale: "ar" });
const mp = await m.newPage();
await mp.goto(base + "/");
await mp.selectOption("#sample-select", "sample-2");
await mp.waitForFunction(() => document.getElementById("article").value.length > 100);
await mp.click("#audit-btn");
await mp.waitForSelector("#results:not([hidden]) .finding", { timeout: 60000 });
const overflow = await mp.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
check(overflow <= 1, `mobile: no horizontal scroll (overflow ${overflow}px)`);
await shot(mp, "06-mobile-top.png");
await mp.locator(".change").first().scrollIntoViewIfNeeded();
await shot(mp, "07-mobile-change.png");
await m.close();

check(errors.length === 0, `no console errors (${errors.join(" | ")})`);
await browser.close();
console.log(`\nfailures: ${failures}`);
process.exit(failures ? 1 : 0);
