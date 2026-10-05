// The pilot writer's journey on a DEPLOYED instance (scripts/ui_pilot_journey_e2e.mjs is the local version).
// Makes ONE audit at 1366 px (on a service with a model configured: ONE Groq call; its ai.outcome is printed, never assumed), then
// REPLAYS that answer at 390 and 320 px: no further audit request reaches the server. No recheck is made live (it would be a second
// model call); the recheck is covered locally. Findings are found by their words, not their number, since a model may add items.
//   NODE_PATH=<scratch>/node_modules node scripts/live_pilot.mjs https://quran-quote-auditor.onrender.com [--shots DIR] [--build SHA]
import { chromium, check, norm, openPage, finish, opt } from "./_ui_common.mjs";

const base = (process.argv[2] || "").replace(/\/$/, "");
if (!/^https?:/.test(base)) { console.log("usage: node scripts/live_pilot.mjs URL [--shots DIR] [--build SHA]"); process.exit(2); }
const ARTICLE = [
  "الصبر في حياة الكاتب.",
  "قال تعالى: ﴿يا أيها الذين آمنوا استعينوا بالصبر والصلاة إن الله مع الصابرين﴾ [البقرة: 153]",
  "وقال سبحانه: ﴿وأطيعوا الله ورسوله ولا تختلفوا فتفشلوا وتذهب ريحكم﴾ [الأنفال: 46]",
  "وقال عز وجل: ﴿واعتصموا بحبل الله ولا تفرقوا﴾ [آل عمران: 103]",
  "وقال: ﴿قل هو الله أحد﴾ [الإخلاص: 2]",
  "ويسأل القارئ نفسه: هل يستوي الذين يعلمون والذين لا يعلمون في الصبر على الطلب؟",
  "في كل عام نجتمع مع الأهل ونتحدث عن أيامنا الماضية.",
].join("\n\n");
const ADDED = "\n\nفقرة أضفتها بعد التدقيق.";
const revised = (t) => t.replace("ولا تختلفوا فتفشلوا", "ولا تنازعوا فتفشلوا").replace("بحبل الله ولا تفرقوا", "بحبل الله جميعا ولا تفرقوا").replace("[الإخلاص: 2]", "[الإخلاص: 1]");
const REPORT = "https://github.com/FHALFAIFI/quran-quote-auditor/issues/new?template=pilot_report.yml";

const health = await (await fetch(base + "/api/health")).json();
console.log(`INFO  build ${health.build}  provider ${health.provider}  ai_configured ${health.ai_configured}  ai_max_completion_tokens ${health.ai_max_completion_tokens}`);
if (opt("--build")) check(health.build === opt("--build"), `the deployed build is ${opt("--build")}`);

const browser = await chromium.launch();
let saved = null;
const typeAtEnd = async (page, text) => {
  await page.locator("#article").focus();
  await page.evaluate(() => { const t = document.querySelector("#article"); t.setSelectionRange(t.value.length, t.value.length); });
  await page.keyboard.type(text, { delay: 5 });
  await page.waitForTimeout(450);
};
const copyNow = async (page) => {
  await page.evaluate(() => navigator.clipboard.writeText(""));
  await page.click("#copy-btn");
  await page.waitForTimeout(200);
  return page.evaluate(() => navigator.clipboard.readText());
};
for (const [name, vp, mobile] of [["1366", { width: 1366, height: 900 }, false], ["390", { width: 390, height: 844 }, true], ["320", { width: 320, height: 640 }, true]]) {
  console.log(`\n== ${name}${saved ? " (REPLAYED audit answer: no audit request reaches the server)" : " (ONE live audit)"}`);
  const { page, ctx, errors, shot, overflowX } = await openPage(browser, base, vp, mobile, `LIVE-PILOT-${name}`);
  page.setDefaultTimeout(60000);
  let audits = 0;
  await page.route("**/api/audit", async (route) => {
    audits++;
    if (saved) return route.fulfill({ status: 200, contentType: "application/json", body: saved });
    const res = await route.fetch({ timeout: 120000 });
    saved = await res.text();
    return route.fulfill({ response: res, body: saved });
  });
  await page.goto(base + "/");
  await page.evaluate(() => { sessionStorage.clear(); localStorage.clear(); });
  await page.reload();
  // a typed text survives a reload (no request)
  await typeAtEnd(page, "مسودة كتبتها للتو ولم أدققها بعد");
  await page.reload();
  await page.waitForTimeout(500);
  check(await page.inputValue("#article") === "مسودة كتبتها للتو ولم أدققها بعد", `${name}: a typed, un-audited text survives a reload`);
  await page.click("#clear-btn");
  // a verse suggestion (no model; a local text lookup on the server)
  await typeAtEnd(page, "قال تعالى: ﴿هل يستوي الذين يعلمون");
  const sg = await page.waitForSelector("#suggest:not([hidden]) .sg-accept", { timeout: 20000 }).then(() => true).catch(() => false);
  check(sg && /الزمر/.test(norm(await page.locator("#suggest").innerText())), `${name}: a verse suggestion names الزمر`);
  await page.click("#clear-btn");
  // TXT import (read in the browser)
  await page.setInputFiles("#import-file", { name: "pilot.txt", mimeType: "text/plain", buffer: Buffer.from(ARTICLE, "utf8") });
  await page.waitForFunction(() => document.querySelector("#article").value.length > 0, null, { timeout: 15000 });
  check(await page.inputValue("#article") === ARTICLE, `${name}: the imported TXT is the article code point for code point`);
  // the audit
  await page.click("#audit-btn");
  await page.waitForSelector("#panel:not([hidden]) #current article", { timeout: 120000 });
  await page.waitForTimeout(1000);
  const ai = await page.evaluate(() => lastResult.ai);
  if (!mobile) console.log(`INFO  ai.outcome=${ai?.outcome} http=${ai?.http_status ?? "-"} proposed=${ai?.proposed ?? "-"} located=${ai?.located ?? "-"} added_only=${ai?.added_only ?? "-"} elapsed_ms=${ai?.elapsed_ms ?? "-"}`);
  check(audits === 1, `${name}: exactly one audit request (${audits})`);
  const notice = norm(await page.locator("#notices").innerText());
  console.log(`INFO  ${name} notice: ${notice.slice(0, 220)}`);
  check(notice.length > 0, `${name}: the result says what the model did`);
  check(await copyNow(page) === ARTICLE, `${name}: before any decision the copy is the writer's text unchanged`);
  const fs = await page.evaluate(() => lastResult.findings.map((f) => ({ id: f.id, text: lastArticle.slice(f.start, f.end), changes: (f.changes || []).map((c) => c.kind + ":" + c.replacement), role: f.detection?.ai_role || null })));
  console.log(`INFO  ${name} findings: ${fs.map((f) => `${f.id} «${f.text}» ${f.role ? "[ai " + f.role + "]" : ""}`).join(" | ")}`);
  const byText = (w) => fs.find((f) => f.text.includes(w));
  const open = async (f) => { await page.evaluate((id) => { const d = document.getElementById(`row-${id}`)?.closest("details"); if (d) d.open = true; }, f.id); await page.locator(`#row-${f.id}`).click(); await page.waitForSelector(`#finding-${f.id}`); return page.locator(`#finding-${f.id}`); };
  const f1 = byText("استعينوا"), f2 = byText("تختلفوا"), f3 = byText("واعتصموا"), f4 = byText("قل هو الله"), f5 = byText("هل يستوي");
  check(f1 && f2 && f3 && f4 && f5, `${name}: the five quotations are listed`);
  const c1 = await open(f1);
  check(/مطابق للمصحف/.test(norm(await c1.innerText())) && /quranpedia\.net/.test(await c1.locator('a[href*="quranpedia.net"]').first().getAttribute("href")), `${name}: the correct verse is «مطابق للمصحف» with its Quranpedia link`);
  const c5 = await open(f5);
  check(!/مطابق للمصحف/.test(norm(await c5.innerText())) && await c5.locator('[data-change$="-wording"]').count() === 0, `${name}: the unmarked quotation is not «مطابق» and offers no wording change`);
  check(!fs.some((f) => /نجتمع/.test(f.text)) || !(await page.locator("#queue").innerText()).match(/في كل عام[^\n]*مطابق/), `${name}: prose is never listed as matched`);
  for (const [f, label] of [[f2, "غيّر إلى «تنازعوا»"], [f3, "أضف «جميعا»"]]) {
    const c = await open(f);
    check(norm(await c.innerText()).includes(label), `${name}: «${label}» is offered`);
    await c.locator('[data-change$="-wording"] button[data-act="approved"]').click();
  }
  const c4 = await open(f4);
  await c4.locator('[data-change$="-reference"] button[data-act="approved"]').click();
  check(await page.inputValue("#article") === ARTICLE, `${name}: decisions leave the writer's text as written`);
  await shot("1-decided", true);
  check(await copyNow(page) === revised(ARTICLE), `${name}: the copy has exactly the three approved source corrections`);
  await typeAtEnd(page, ADDED);
  await page.reload();
  await page.waitForTimeout(800);
  check(await page.inputValue("#article") === ARTICLE + ADDED, `${name}: an edit after the audit survives a reload`);
  check(await copyNow(page) === revised(ARTICLE + ADDED), `${name}: after the reload the copy keeps the corrections and the new paragraph`);
  check(audits === 1, `${name}: still one audit request (${audits})`);
  check((await overflowX()) <= 1, `${name}: no sideways scroll`);
  for (const p of ["/sources", "/privacy", "/limitations", "/roadmap"]) {
    const res = await page.goto(base + p);
    check(res.status() === 200 && await page.locator(".site-footer a", { hasText: "أبلغ عن مشكلة" }).getAttribute("href") === REPORT, `${name}: ${p} answers 200 with the report link`);
    check((await overflowX()) <= 1, `${name}: ${p} has no sideways scroll`);
  }
  check(/حدود التجربة/.test(await page.textContent("main")), `${name}: /roadmap shows the pilot's limits`);
  check(errors.length === 0, `${name}: no page error (${errors.slice(0, 2).join(" | ")})`);
  await ctx.close();
}
const after = await (await fetch(base + "/api/health")).json();
console.log(`INFO  health after: source_ok=${after.source_ok} ayahs=${after.source?.ayahs} stale=${after.source?.stale} ai_last_call=${JSON.stringify(after.ai_last_call)} ai_recent=${JSON.stringify(after.ai_recent)}`);
check(after.source_ok === true && after.source?.ayahs === 6236, "the live Quran text is loaded (6236 verses) and current");
finish(null, browser);
