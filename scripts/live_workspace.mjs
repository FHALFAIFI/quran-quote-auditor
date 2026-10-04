// Live journey of the writing workspace on a DEPLOYED instance (Playwright, Chromium).
// WARNING: on a service with a model configured, short audit requests in this script attempt real model calls.
//
//   NODE_PATH=<scratch>/node_modules node scripts/live_workspace.mjs https://quran-quote-auditor.onrender.com [--shots DIR]
//
// Checks: the served build, the three trust pages and their links, verse suggestion (accept with Tab, the correction «لعبادتي ← ليعبدون»),
// the demonstration article, an edit that makes a quotation stale, a recheck that keeps the other decision, and an article of about
// 17,000 characters (time to the audit's answer; the window in which the server may have to wake is reported separately).
import fs from "fs";
import path from "path";
import { createRequire } from "module";

const require = createRequire(import.meta.url);
const { chromium } = require("playwright");
const base = (process.argv[2] || "").replace(/\/$/, "");
if (!base.startsWith("http")) { console.log("usage: live_workspace.mjs <https://host> [--shots DIR]"); process.exit(2); }
const shotsDir = process.argv.includes("--shots") ? process.argv[process.argv.indexOf("--shots") + 1] : null;
if (shotsDir) fs.mkdirSync(shotsDir, { recursive: true });
const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..");
let failures = 0;
const check = (ok, msg) => { console.log(`${ok ? "PASS" : "FAIL"}  ${msg}`); if (!ok) failures++; };
const norm = (t) => (t || "").replace(/\s+/g, " ").trim();
const ar = (n) => String(n).replace(/\d/g, (d) => "٠١٢٣٤٥٦٧٨٩"[d]);
const arN = (n) => ar(String(n).replace(/\B(?=(\d{3})+(?!\d))/g, "٬"));   // a character count, with the Arabic thousands separator
const frozen = JSON.parse(fs.readFileSync(path.join(root, "eval/articles_frozen.json"), "utf8")).cases.map((c) => c.article);

// wake the server without a model call (/api/health does not load the text; /api/phrase never calls a model)
const t0 = Date.now();
let health = null;
for (let i = 0; i < 6 && !health; i++) { try { health = await (await fetch(base + "/api/health", { signal: AbortSignal.timeout(90000) })).json(); } catch { /* waking */ } }
console.log(`INFO  health answered after ${((Date.now() - t0) / 1000).toFixed(1)} s: build ${health?.build}, mode ${health?.mode}, max_chars ${health?.max_chars}, ai_max_chars ${health?.ai_max_chars}, ai_last_call ${JSON.stringify(health?.ai_last_call?.outcome)}`);
check(!!health && health.status === "ok", "the service answers");
await fetch(base + "/api/phrase", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ article: "اقرأ باسم ربك الذي خلق", start: 0, end: 22 }), signal: AbortSignal.timeout(120000) }).catch(() => {});

const browser = await chromium.launch();
const audits = [];
for (const [name, vp, mobile] of [["desktop", { width: 1366, height: 900 }, false], ["phone", { width: 390, height: 844 }, true]]) {
  console.log(`\n== ${name}`);
  const ctx = await browser.newContext({ viewport: vp, locale: "ar", isMobile: mobile, hasTouch: mobile });
  await ctx.grantPermissions(["clipboard-read", "clipboard-write"], { origin: base });
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  page.on("response", async (r) => { if (r.url().endsWith("/api/audit") && r.request().method() === "POST") { try { const j = await r.json(); audits.push({ name, status: r.status(), mode: j.mode, ai: j.ai?.outcome, findings: j.findings?.length, ms: j.elapsed_ms, capped: j.candidates_capped }); } catch { /* ignore */ } } });
  const shot = async (n) => { if (shotsDir) await page.screenshot({ path: path.join(shotsDir, `live-${name}-${n}.png`) }); };
  await page.goto(base + "/", { timeout: 120000 });
  await page.evaluate(() => { sessionStorage.clear(); localStorage.clear(); });
  await page.reload();
  await page.waitForSelector("#article");
  await page.evaluate(() => { document.getElementById("options").open = true; });
  check((await page.locator("#opt-ai").count()) === 0, "there is no per-audit model switch");
  check(norm(await page.textContent("#limit-note")) === arN(health.max_chars), `the page states the limit (${await page.textContent("#limit-note")})`);
  for (const [href, h1] of [["/sources", "المصادر وطريقة التحقق"], ["/privacy", "الخصوصية"], ["/limitations", "الحدود"]]) {
    check((await page.locator(`.site-footer a[href="${href}"]`).count()) === 1 && (await page.locator(`.site-nav a[href="${href}"]`).count()) === 1, `${href} is linked from the header and the footer`);
  }
  check((await page.locator('#editor-hint a[href="/privacy"]').count()) === 1, "the paste box links to the privacy page");

  // verse suggestion
  await page.click("#article");
  await page.keyboard.type("الصبر خلق عظيم. قال تعالى: وما خلقت الجن والإنس إلا", { delay: 5 });
  const got = await page.waitForSelector("#suggest:not([hidden]) .sg-item", { timeout: 60000 }).then(() => true).catch(() => false);
  check(got && /ليعبدون/.test(await page.textContent("#suggest")) && /الذاريات/.test(await page.textContent("#suggest")), "a suggestion appears: ليعبدون, الذاريات");
  await shot("1-suggest");
  if (mobile) await page.locator("#suggest .sg-accept").first().tap(); else await page.keyboard.press("Tab");
  await page.waitForTimeout(300);
  check((await page.inputValue("#article")).endsWith("إلا ليعبدون"), "accepting inserts the word");
  await page.evaluate(() => document.getElementById("clear-btn").click());
  await page.click("#article");
  await page.keyboard.type("قال تعالى: وما خلقت الجن والإنس إلا لعبادتي", { delay: 5 });
  await page.waitForSelector("#suggest:not([hidden]) .sg-item", { timeout: 60000 }).catch(() => {});
  const corr = norm(await page.textContent("#suggest"));
  check(/لعبادتي/.test(corr) && /ليعبدون/.test(corr) && /احتمال/.test(corr), "the wrong word is offered as a possible correction «لعبادتي ← ليعبدون»");
  check((await page.inputValue("#article")).endsWith("لعبادتي"), "it was not applied by itself");
  await shot("2-correction");
  await page.keyboard.press("Escape");

  // the demonstration article, an edit, a recheck
  await page.click("#clear-btn");
  await page.click("#demo-btn");
  await page.waitForSelector("#panel:not([hidden]) #current article", { timeout: 120000 });
  await page.waitForTimeout(800);
  check(norm(await page.textContent("#verdict-title")) === "وجدنا ٤ اقتباسات؛ يحتاج اثنان إلى قرارك", "the demonstration article: 4 quotations, 2 need a decision");
  await page.click('#finding-3 [data-act="approved"]');
  await page.evaluate(() => { const ta = document.getElementById("article"); const f = lastResult.findings[3]; const u = W.cpToUnit(ta.value, f.start + 3); ta.focus(); ta.setSelectionRange(u, u); });
  await page.keyboard.type("ز", { delay: 3 });
  await page.waitForTimeout(500);
  check((await page.locator("#article-view mark.stale").count()) === 1, "an edit inside a quotation marks it stale");
  await shot("3-stale");
  await page.click("#recheck-btn");
  await page.waitForFunction(() => !edited(), null, { timeout: 120000 });
  await page.waitForTimeout(500);
  const kept = await page.evaluate(() => Object.values(decisions).filter((d) => d === "approved").length);
  check(kept === 1, `after the recheck the untouched quotation keeps its approval (${kept})`);
  check((await page.inputValue("#revised-text")).includes("يوفى"), "the revised text applies it");
  await shot("4-rechecked");

  // a long article (17,500 characters of the older frozen articles; above the model's size limit)
  await page.click("#clear-btn");
  const long = [frozen[0], frozen[2], frozen[3], frozen[0], frozen[2], frozen[3]].join("\n\n").slice(0, 19000);
  await page.fill("#article", long);
  const t1 = Date.now();
  await page.click("#audit-btn");
  await page.waitForSelector("#panel:not([hidden]) #current article", { timeout: 180000 });
  const secs = (Date.now() - t1) / 1000;
  console.log(`INFO  ${name}: ${Array.from(long).length}-character audit answered and rendered in ${secs.toFixed(1)} s`);
  check(secs < 60, `the long article is audited in ${secs.toFixed(1)} s`);
  await shot("5-long");
  check(errors.filter((e) => !/Failed to load resource.*(fonts|gstatic)/i.test(e)).length === 0, `no console errors ${errors.join(" | ")}`);
  await ctx.close();
}
await browser.close();
console.log("\nINFO  audit responses:", JSON.stringify(audits));
check(audits.length > 0 && audits.every((a) => a.status === 200 && ["ok", "failed", "not_configured", "skipped_length", "skipped_cooldown"].includes(a.ai)), "audits report whether the model answered, failed, or was unavailable for this article");
const h2 = await (await fetch(base + "/api/health")).json();
check(!health.ai_configured || ["ok", "failed"].includes(h2.ai_last_call?.outcome), `the configured model was attempted (${JSON.stringify(h2.ai_last_call?.outcome)})`);
console.log(failures ? `\nfailures: ${failures}` : "\nall checks passed");
process.exit(failures ? 1 : 0);
