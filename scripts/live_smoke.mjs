// One focused end-to-end journey of the demonstration article against a running instance (live or local).
//
//   NODE_PATH=<dir with playwright>/node_modules node scripts/live_smoke.mjs https://quran-quote-auditor.onrender.com [screenshot-dir]
//
// Makes ONE audit (so, on a live instance with a model configured, ONE Groq call). Flow: pick the demo article → audit → the four
// quotations and two required changes → open «تفاصيل هذا التدقيق» (model outcome is recorded, not asserted) → approve both required
// changes → the revised text equals the article with exactly «يجزى»→«يوفى» and «الشرح: 6»→«الشرح: 5» → copy → the clipboard holds it.
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
const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1366, height: 900 }, locale: "ar", acceptDownloads: false });
await ctx.grantPermissions(["clipboard-read", "clipboard-write"], { origin: base });
const page = await ctx.newPage();
const errors = [];
page.on("pageerror", (e) => errors.push(String(e)));
page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
const t0 = Date.now();
await page.goto(base, { waitUntil: "load", timeout: 120000 });
console.log(`INFO  page loaded in ${((Date.now() - t0) / 1000).toFixed(1)} s`);
const health = await (await page.request.get(`${base}/api/health`)).json();
console.log(`INFO  health: mode=${health.mode} provider=${health.provider} build=${health.build}`);

await page.selectOption("#sample-select", "sample-demo");
await page.waitForFunction(() => document.getElementById("article").value.length > 100);
const article = (await page.inputValue("#article")).replace(/\r\n?/g, "\n");
check((await page.textContent("#status")).includes("مقال تجريبي"), "loading the demo says it is an example with two deliberate misquotations");
const t1 = Date.now();
await page.click("#audit-btn");
await page.waitForSelector("#results:not([hidden])", { timeout: 90000 });
console.log(`INFO  audit answered in ${((Date.now() - t1) / 1000).toFixed(1)} s (wall)`);
await page.waitForTimeout(800);
if (shots) await page.screenshot({ path: path.join(shots, "1-results.png") });

check((await page.locator("ol.findings > li").count()) === 4, "four quotations found");
const tiles = (await page.textContent("#summary .stats")).replace(/\s+/g, " ");
check(/٢\s*تحتاج مراجعة/.test(tiles) && /٢\s*تصحيحات مقترحة/.test(tiles) && /٤\s*اقتباسات مرصودة/.test(tiles), `tiles: ${tiles.trim()}`);
check((await page.locator(".change:not(.optional)").count()) === 2, "two required changes (one word, one reference)");
const chips = await page.locator("ol.findings > li").evaluateAll((els) => els.map((e) => e.textContent.replace(/\s+/g, " ").slice(0, 400)));
check(chips[0].includes("رسم عثماني") && chips[0].includes("إحالة مطابقة"), "1: Uthmani-script quotation matched, reference matched");
check(chips[1].includes("مطابق") && chips[1].includes("إحالة مطابقة"), "2: ordinary-script quotation matched, reference matched");
check(chips[2].includes("اختلاف"), "3: the wrong word is a difference");
check(chips[3].includes("إحالة خاطئة"), "4: the wrong reference is flagged");
check(await page.locator("#notices .audit-meta").count() === 1 && (await page.locator("#notices .notice").count()) <= 1, "one quiet status line (details folded), at most one warning");
await page.locator("#notices .audit-meta summary").click().catch(() => {});
const meta = (await page.textContent("#notices")).replace(/\s+/g, " ").trim();
console.log(`INFO  status line + details: ${meta}`);
if (shots) await page.screenshot({ path: path.join(shots, "2-status-details.png") });

// nothing changes before approval
await page.click("#tab-text");
check((await page.inputValue("#revised-text")).replace(/\r\n?/g, "\n") === article, "before any decision the revised text equals the article");
for (const b of await page.locator(".change:not(.optional) button.approve").all()) await b.click();
await page.waitForTimeout(300);
const revised = (await page.inputValue("#revised-text")).replace(/\r\n?/g, "\n");
const expected = article.replace("يجزى", "يوفى").replace("[الشرح: 6]", "[الشرح: 5]");
check(revised === expected && revised !== article, "after approving both: exactly «يجزى»→«يوفى» and «الشرح: 6»→«الشرح: 5», nothing else changed");
await page.click("#tab-preview");
if (shots) await page.screenshot({ path: path.join(shots, "3-approved-preview.png") });
await page.click("#copy-btn");
await page.waitForTimeout(500);
const clip = (await page.evaluate(() => navigator.clipboard.readText())).replace(/\r\n?/g, "\n");
check(clip === expected, "the clipboard holds the revised article");
check(!(await page.textContent("#copy-note")).includes("تحقق من المقال كله"), "no claim that the whole article is verified");
check(errors.length === 0, `no console/page errors ${errors.join(" | ")}`);
await browser.close();
console.log(failures ? `\nfailures: ${failures}` : "\nall checks passed");
process.exit(failures ? 1 : 0);
