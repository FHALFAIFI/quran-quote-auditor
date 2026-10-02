// One focused end-to-end journey of the demonstration article against a running instance (live or local).
//
//   NODE_PATH=<dir with playwright>/node_modules node scripts/live_smoke.mjs https://quran-quote-auditor.onrender.com [screenshot-dir] [--phone]
//
// Makes ONE audit (so, on a live instance with a model configured, ONE Groq call). Flow: the empty page offers
// «جرّب المقال التجريبي» → one click loads and audits the demonstration article → the verdict, and the first item needing the
// editor on screen with «يجزى ← يوفى» → the model/source notice above the findings is folded (what shows is measured and printed) →
// both required changes are approved (the second by «اعتماد التصحيح» too) → the dock offers «نسخ المقال المعدّل» → the revised text
// equals the article with exactly «يجزى»→«يوفى» and «الشرح: 6»→«الشرح: 5» → the clipboard holds it.
// --phone runs it at 390x844 with touch instead of 1366x900.
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
const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: phone ? { width: 390, height: 844 } : { width: 1366, height: 900 }, locale: "ar", isMobile: phone, hasTouch: phone, acceptDownloads: false });
await ctx.grantPermissions(["clipboard-read", "clipboard-write"], { origin: base });
const page = await ctx.newPage();
const errors = [];
page.on("pageerror", (e) => errors.push(String(e)));
page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
const shot = async (n) => { if (shots) await page.screenshot({ path: path.join(shots, `${phone ? "phone" : "desktop"}-${n}.png`) }); };
const inView = (sel) => page.evaluate((s) => { const r = document.querySelector(s)?.getBoundingClientRect(); return !!r && r.top >= 0 && r.bottom <= innerHeight + 1 && r.width > 0; }, sel);
const t0 = Date.now();
await page.goto(base, { waitUntil: "load", timeout: 120000 });
console.log(`INFO  page loaded in ${((Date.now() - t0) / 1000).toFixed(1)} s (${phone ? "phone" : "desktop"})`);
const health = await (await page.request.get(`${base}/api/health`)).json();
console.log(`INFO  health: mode=${health.mode} provider=${health.provider} build=${health.build}`);

check((await page.textContent("#demo-btn")).trim() === "جرّب المقال التجريبي" && await inView("#demo-btn"), "the empty page shows «جرّب المقال التجريبي» on the first screen");
await shot("0-empty");
const t1 = Date.now();
await page.click("#demo-btn");
await page.waitForSelector("#results:not([hidden]) #finding-3", { timeout: 90000 });
console.log(`INFO  load + audit answered in ${((Date.now() - t1) / 1000).toFixed(1)} s (wall)`);
await page.waitForTimeout(1800);
const article = (await page.inputValue("#article")).replace(/\r\n?/g, "\n");
await shot("1-landing");

check((await page.textContent("#verdict-title")).trim() === "وجدنا ٤ اقتباسات؛ يحتاج اثنان إلى قرارك", "the verdict: «وجدنا ٤ اقتباسات؛ يحتاج اثنان إلى قرارك»");
check((await page.textContent("#verdict")).includes("مقال تجريبي كُتب لهذا العرض"), "the page says the two mistakes in the demo are deliberate");
check(await page.evaluate(() => document.activeElement?.id === "finding-3") && await inView("#finding-3 .ch-delta"), "the first item needing review is on screen and focused");
const delta = (await page.textContent("#finding-3 .d-before")).trim() + " ← " + (await page.textContent("#finding-3 .d-after")).trim();
check(delta === "يجزى ← يوفى", `its decisive difference: ${delta}`);
check((await page.locator("ol.findings > li").count()) === 4, "four quotations found");
check((await page.locator(".change:not(.optional)").count()) === 2, "two required changes (one word, one reference)");
const chips = await page.locator("ol.findings > li").evaluateAll((els) => els.map((e) => e.textContent.replace(/\s+/g, " ").slice(0, 600)));
check(chips[0].includes("رسم عثماني") && chips[0].includes("إحالة مطابقة"), "1: Uthmani-script quotation matched, reference matched");
check(chips[1].includes("مطابق") && chips[1].includes("إحالة مطابقة"), "2: ordinary-script quotation matched, reference matched");
check(chips[2].includes("اختلاف") && chips[2].includes("مطابقة تقريبية"), "3: the wrong word is a difference, with the «approximate match» warning");
check(chips[3].includes("إحالة خاطئة") && chips[3].includes("٦") && chips[3].includes("٥"), "4: the wrong reference is flagged: ٦ ← ٥");

// the notice above the findings: measure what is actually visible
const n = await page.evaluate(() => { const e = document.getElementById("notices"); return { open: [...e.querySelectorAll("details")].filter((d) => d.open).length, text: e.innerText.replace(/\s+/g, " ").trim(), h: Math.round(e.getBoundingClientRect().height), notices: e.querySelectorAll(".notice").length }; });
console.log(`INFO  notices region: ${n.h}px high, ${n.notices} warning(s), visible text: «${n.text}»`);
check(n.open === 0, "model and source notices are folded (no <details> open)");
check(health.mode === "ai" ? n.text.length <= 60 : n.text.length <= 180, "what is visible of them is one short line");
await page.locator("#notices details > summary").click().catch(() => {});
console.log(`INFO  opened: ${(await page.textContent("#notices")).replace(/\s+/g, " ").trim()}`);
await shot("2-notice-open");
await page.locator("#notices details > summary").click().catch(() => {});

// nothing changes before approval
await page.click("#tab-text");
check((await page.inputValue("#revised-text")).replace(/\r\n?/g, "\n") === article, "before any decision the revised text equals the article");
check(!(await page.locator("#dock-copy").isVisible()), "the final action is not offered before both decisions");
for (const b of await page.locator(".change:not(.optional) button.approve").all()) await b.click();
await page.waitForTimeout(300);
check((await page.textContent("#dock-text")).includes("اكتملت قراراتك (٢ من ٢)"), "the dock says both decisions are made");
check(await page.locator("#dock-copy").isVisible() && await inView("#dock-copy"), "«نسخ المقال المعدّل» is the visible final action");
const revised = (await page.inputValue("#revised-text")).replace(/\r\n?/g, "\n");
const expected = article.replace("يجزى", "يوفى").replace("[الشرح: 6]", "[الشرح: 5]");
check(revised === expected && revised !== article, "after approving both: exactly «يجزى»→«يوفى» and «الشرح: 6»→«الشرح: 5», nothing else changed");
await page.click("#tab-preview");
await shot("3-approved");
await page.click("#dock-copy");
await page.waitForTimeout(500);
const clip = (await page.evaluate(() => navigator.clipboard.readText())).replace(/\r\n?/g, "\n");
check(clip === expected, "the clipboard holds the revised article");
check(!(await page.textContent("#dock-text")).includes("تحقق من المقال كله"), "no claim that the whole article is verified");
check((await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)) <= 1, "no horizontal overflow");
check(errors.length === 0, `no console/page errors ${errors.join(" | ")}`);
await browser.close();
console.log(failures ? `\nfailures: ${failures}` : "\nall checks passed");
process.exit(failures ? 1 : 0);
