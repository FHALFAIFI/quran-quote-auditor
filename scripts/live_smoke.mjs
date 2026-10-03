// One focused end-to-end journey of the demonstration article against a running instance (live or local).
//
//   NODE_PATH=<dir with playwright>/node_modules node scripts/live_smoke.mjs https://quran-quote-auditor.onrender.com [screenshot-dir] [--phone]
//
// Makes ONE audit (so, on a live instance with a model configured, ONE Groq call). Flow: the empty page offers
// «جرّب المقال التجريبي» → one click loads and audits the demonstration article → the verdict, and the first decision on screen with
// «يجزى ← يوفى» and its two buttons → the audit-method notice is folded (what shows is measured and printed) → the first decision is
// approved, the panel moves on to the second, which is approved too → the final check lists both changes in their sentences → copy →
// the clipboard holds the article with exactly «يجزى»→«يوفى» and «الشرح: 6»→«الشرح: 5». --phone runs it at 390x844 with touch.
// Prints the deployed build (/api/health "build") so the run can be tied to a commit.
import { createRequire } from "module";
import fs from "fs";
import path from "path";
const require = createRequire(import.meta.url);
const { chromium } = require("playwright");
const args = process.argv.slice(2).filter((a) => !a.startsWith("--"));
const phone = process.argv.includes("--phone");
const base = (args[0] || "http://localhost:8000").replace(/\/$/, "");
const shots = args[1] || null;
if (shots) fs.mkdirSync(shots, { recursive: true });
let failures = 0;
const check = (cond, msg) => { console.log(`${cond ? "PASS" : "FAIL"}  ${msg}`); if (!cond) failures++; };
const norm = (t) => (t || "").replace(/\s+/g, " ").trim();
const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: phone ? { width: 390, height: 844 } : { width: 1366, height: 900 }, locale: "ar", isMobile: phone, hasTouch: phone, acceptDownloads: false });
await ctx.grantPermissions(["clipboard-read", "clipboard-write"], { origin: base });
const page = await ctx.newPage();
const errors = [];
page.on("pageerror", (e) => errors.push(String(e)));
page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
let auditData = null;
page.on("response", async (r) => { if (r.url().endsWith("/api/audit") && r.request().method() === "POST") auditData = await r.json().catch(() => null); });
const shot = async (n) => { if (shots) await page.screenshot({ path: path.join(shots, `${phone ? "phone" : "desktop"}-${n}.png`) }); };
const inView = (sel) => page.evaluate((s) => { const r = document.querySelector(s)?.getBoundingClientRect(); return !!r && r.top >= 0 && r.bottom <= innerHeight + 1 && r.width > 0; }, sel);
const t0 = Date.now();
await page.goto(base, { waitUntil: "load", timeout: 120000 });
console.log(`INFO  page loaded in ${((Date.now() - t0) / 1000).toFixed(1)} s (${phone ? "phone" : "desktop"})`);
const health = await (await page.request.get(`${base}/api/health`)).json();
console.log(`INFO  health: mode=${health.mode} provider=${health.provider} build=${health.build}`);

check(norm(await page.textContent("#demo-btn")) === "جرّب المقال التجريبي" && await inView("#demo-btn"), "the empty page shows «جرّب المقال التجريبي» on the first screen");
await shot("0-empty");
const t1 = Date.now();
await page.click("#demo-btn");
await page.waitForSelector("#panel:not([hidden]) #finding-3", { timeout: 90000 });
console.log(`INFO  load + audit answered in ${((Date.now() - t1) / 1000).toFixed(1)} s (wall)`);
await page.waitForTimeout(1800);
const article = (await page.inputValue("#article")).replace(/\r\n?/g, "\n");
await shot("1-landing");

check(norm(await page.textContent("#verdict-title")) === "وجدنا ٤ اقتباسات؛ يحتاج اثنان إلى قرارك", "the verdict: «وجدنا ٤ اقتباسات؛ يحتاج اثنان إلى قرارك»");
check((await page.textContent("#verdict")).includes("مقال تجريبي كُتب لهذا العرض"), "the page says the two mistakes in the demo are deliberate");
check(await page.evaluate(() => document.activeElement?.id === "finding-3") && await inView("#finding-3 .delta"), "the first decision is on screen and focused");
const delta = norm(await page.textContent("#finding-3 .d-before")) + " ← " + norm(await page.textContent("#finding-3 .d-after"));
check(delta === "يجزى ← يوفى", `its exact change: ${delta}`);
check(await inView('[data-change="3-wording"] button[data-act="approved"]'), "its buttons are on screen");
check((await page.locator("#queue .row").count()) === 4, "four quotations found");
const rows = await page.locator("#queue .row").evaluateAll((els) => els.map((e) => e.textContent.replace(/\s+/g, " ")));
check(rows.filter((r) => r.includes("مطابق للمصحف")).length === 2, "1 and 2 (the Uthmani and the ordinary-script quotations) are matched and need nothing");
check((await page.locator("#queue .row.need").count()) === 2, "3 (wrong word) and 4 (wrong reference) wait for the writer");

const n = await page.evaluate(() => { const e = document.getElementById("notices"); return { open: [...e.querySelectorAll("details")].filter((d) => d.open).length, text: e.innerText.replace(/\s+/g, " ").trim(), h: Math.round(e.getBoundingClientRect().height) }; });
console.log(`INFO  notices region: ${n.h}px high, visible text: «${n.text}»`);
check(n.open === 0, "the audit-method notice is folded");
// What is visible depends on what THIS audit did (the server's own `mode`), not on what /api/health says is configured:
//   ai          the model answered: one quiet folded line («كيف جرى هذا التدقيق؟…»)          <= 70 characters
//   reduced     no model configured: the one-line caveat stays in view                       <= 140
//   ai_failed   a model is configured but did not answer (e.g. Groq 429): the visible model-failure warning, which must say so
//               plainly and say what was still done; it is longer by design, so its length is bounded (<= 200), not waived.
const mode = auditData?.mode;
console.log(`INFO  audit mode: ${mode}${mode === "ai_failed" ? ` (ai.http_status ${auditData.ai?.http_status}, outcome ${auditData.ai?.outcome})` : ""}`);
check(["ai", "reduced", "ai_failed"].includes(mode), `the audit response reported a known mode («${mode}»)`);
if (mode === "ai_failed") {
  const warn = norm(await page.textContent("#notices .audit-meta.limited .am-line").catch(() => ""));
  check(warn.startsWith("تعذّر اقتراح الذكاء الاصطناعي هذه المرة") && warn.includes("فُحص المقال بالعلامات وبالبحث في المصحف"), "the model-failure warning is visible and says the model gave no proposals and the audit used the markers and the Quran search");
  check(n.text.length <= 200, `the model-failure notice stays bounded (${n.text.length} characters)`);
  check(auditData.ai?.responded === false && auditData.ai?.proposed === 0 && auditData.ai?.added_only === 0, "the response agrees: model did not respond, no proposal, none added");
} else {
  check(mode === "ai" ? n.text.length <= 70 : n.text.length <= 140, "what is visible of it is one short line");
}
await page.locator("#notices details > summary").click().catch(() => {});
console.log(`INFO  opened: ${norm(await page.textContent("#notices"))}`);
await shot("2-notice-open");
await page.locator("#notices details > summary").click().catch(() => {});

check((await page.inputValue("#revised-text")).replace(/\r\n?/g, "\n") === article, "before any decision the revised text equals the article");
await page.locator('#current button[data-act="approved"]').first().click();
await page.waitForTimeout(900);
check(await page.evaluate(() => document.activeElement?.id === "finding-4"), "the panel moved on to the second decision by itself");
await page.locator('#current button[data-act="approved"]').first().click();
await page.waitForTimeout(700);
check(norm(await page.textContent("#panel-progress")).startsWith("حسمتَ كل ما يحتاج قرارك"), "nothing is left waiting");
await page.locator("#final").scrollIntoViewIfNeeded();
const fin = norm(await page.textContent("#final"));
check(/سيُنسخ مقالك بعد ٢ تغييرين اعتمدتَهما/.test(fin) && (await page.locator("#final-changes del").count()) === 2, "the final check lists both changes in their sentences");
check(fin.includes("ليس شهادة بأن المقال كله متحقق منه"), "and says it does not certify the whole article");
const revised = (await page.inputValue("#revised-text")).replace(/\r\n?/g, "\n");
const expected = article.replace("يجزى", "يوفى").replace("[الشرح: 6]", "[الشرح: 5]");
check(revised === expected && revised !== article, "exactly «يجزى»→«يوفى» and «الشرح: 6»→«الشرح: 5»; nothing else changed");
await shot("3-final");
await page.click("#copy-btn");
await page.waitForTimeout(500);
const clip = (await page.evaluate(() => navigator.clipboard.readText())).replace(/\r\n?/g, "\n");
check(clip === expected, "the clipboard holds the revised article");
check((await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)) <= 1, "no horizontal overflow");
check(errors.length === 0, `no console/page errors ${errors.join(" | ")}`);
await browser.close();
console.log(failures ? `\nfailures: ${failures}` : "\nall checks passed");
process.exit(failures ? 1 : 0);
