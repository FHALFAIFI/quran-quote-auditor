// The 5 Oct writer-feedback journey on a DEPLOYED instance: the screenshot case «إنما يجزى الصابرون بغير حساب» [الزمر: 10] gets a
// reviewable correction, an unmarked «فاستبقوا الخيرات» is an optional confirmation, «حياة طيبة» is not listed, /roadmap is linked.
// Makes ONE audit at 1366 px (on a service with a model configured: ONE Groq call; its ai.outcome is printed, never assumed), then
// REPLAYS that answer at 390 and 320 px: no further audit request reaches the server.
//   NODE_PATH=<scratch>/node_modules node scripts/live_feedback.mjs https://quran-quote-auditor.onrender.com [--shots DIR] [--build SHA]
import { chromium, check, norm, openPage, finish, opt } from "./_ui_common.mjs";

const base = (process.argv[2] || "").replace(/\/$/, "");
if (!/^https?:/.test(base)) { console.log("usage: node scripts/live_feedback.mjs URL [--shots DIR] [--build SHA]"); process.exit(2); }
const quote = "إنما يجزى الصابرون بغير حساب";
const article = `وقال جل شأنه: ﴿${quote}﴾ [الزمر: 10]\n\nفي زحمة الحياة ننسى ما يهم، فاستبقوا الخيرات قبل أن يفوت الوقت، ونتمنى للجميع حياة طيبة.`;
const corrected = article.replace(quote, "إنما يوفى الصابرون أجرهم بغير حساب");

const health = await (await fetch(base + "/api/health")).json();
console.log(`INFO  build ${health.build}  provider ${health.provider}  ai_configured ${health.ai_configured}`);
if (opt("--build")) check(health.build === opt("--build"), `the deployed build is ${opt("--build")}`);

const browser = await chromium.launch();
let saved = null;
for (const [name, vp, mobile] of [["1366", { width: 1366, height: 900 }, false], ["390", { width: 390, height: 844 }, true], ["320", { width: 320, height: 640 }, true]]) {
  console.log(`\n== ${name}${saved ? " (REPLAYED audit answer: no request to the server)" : " (ONE live audit)"}`);
  const { page, ctx, errors, shot, overflowX } = await openPage(browser, base, vp, mobile, `LIVE-FB-${name}`);
  let audits = 0;
  await page.route("**/api/audit", async (route) => {
    audits++;
    if (saved) return route.fulfill({ status: 200, contentType: "application/json", body: saved });
    const res = await route.fetch();
    saved = await res.text();
    return route.fulfill({ response: res, body: saved });
  });
  await page.goto(base + "/");
  await page.evaluate(() => { sessionStorage.clear(); localStorage.clear(); });
  await page.reload();
  check((await page.locator('.site-nav a[href="/roadmap"]').count()) === 1, `${name}: «القادم» (/roadmap) is in the header`);
  await page.fill("#article", article);
  await page.click("#audit-btn");
  await page.waitForSelector("#panel:not([hidden]) #current article", { timeout: 120000 });
  await page.waitForTimeout(1000);
  const ai = await page.evaluate(() => lastResult.ai);
  if (!mobile) console.log(`INFO  ai.outcome=${ai?.outcome} http=${ai?.http_status ?? "-"} proposed=${ai?.proposed ?? "-"} located=${ai?.located ?? "-"} added_only=${ai?.added_only ?? "-"} elapsed_ms=${ai?.elapsed_ms ?? "-"}`);
  check(audits === 1, `${name}: exactly one audit request (${audits})`);
  const fs = await page.evaluate(() => lastResult.findings.map((f) => ({ id: f.id, text: lastArticle.slice(f.start, f.end), codes: f.detection.codes || [] })));
  const q = fs.find((f) => f.text.includes("يجزى"));
  const pair = fs.find((f) => f.text.includes("فاستبقوا"));
  check(!!q && !!pair && !fs.some((f) => f.text.includes("حياة طيبة")), `${name}: the quotation and the pair are listed, «حياة طيبة» is not (${fs.map((f) => f.text).join(" | ")})`);
  check(pair && pair.codes.includes("pair"), `${name}: «فاستبقوا الخيرات» is an optional pair (${pair?.codes})`);
  await page.evaluate((id) => { const d = document.getElementById(`row-${id}`)?.closest("details"); if (d) d.open = true; }, q.id);
  await page.locator(`#row-${q.id}`).click();
  const card = page.locator(`#finding-${q.id}`);
  const choices = await card.locator('[data-change$="-wording"] .actions-row button').allInnerTexts();
  check(choices.join("|") === "غيّر إلى «يوفى الصابرون أجرهم»|أبقِ «يجزى الصابرون»", `${name}: the correction is offered for review (${choices.join(" | ")})`);
  check(/الزمر.*١٠/.test(norm(await card.innerText())), `${name}: the verse is named`);
  check((await overflowX()) <= 1, `${name}: no sideways scroll`);
  await shot("1-correction");
  await card.locator('[data-change$="-wording"] button[data-act="approved"]').click();
  await page.waitForTimeout(500);
  check(await page.inputValue("#article") === article, `${name}: approving leaves the draft as written`);
  await page.evaluate(() => { document.querySelector("#final").hidden = false; });
  await page.click("#copy-btn");
  const copied = await page.evaluate(() => navigator.clipboard.readText());
  check(copied === corrected, `${name}: the copy has exactly the source correction and nothing else changed`);
  await shot("2-approved");
  check(errors.length === 0, `${name}: no page error (${errors.slice(0, 2).join(" | ")})`);
  await ctx.close();
}
const page = await (await browser.newContext()).newPage();
await page.goto(base + "/roadmap");
check(norm(await page.textContent("h1")) === "ما نعمل عليه" && /qwen\/qwen3\.8-27b/.test(await page.textContent("main")), "/roadmap is served and names the model");
await page.goto(base + "/sources");
check(/٩ من ١٩٥/.test(await page.textContent("main")), "/sources gives the failed calls (٩ من ١٩٥)");
finish(null, browser);
