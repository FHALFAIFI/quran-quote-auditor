// Browser check of a long article (5,809 of 6,000 characters), the review sequence, keyboard focus against the bottom bar, 320 px reflow,
// mixed-direction text, a slow or failing server, the no-findings state and the model-failed state (Playwright, Chromium).
//
//   NODE_PATH=<scratch>/node_modules node scripts/ui_long_e2e.mjs [--shots DIR] [--server URL] [--python PATH]
//
// Starts its OWN AI-off server unless --server is given. The articles are cases of eval/articles_frozen.json (L1 patience, near the
// limit; L3 a social post with a URL and a Latin reference; L5 ordinary prose with no quotation). What is asserted about L1 is
// structural (the order of the sequence, what is on screen, what is covered), never how many quotations the search finds.
import fs from "fs";
import path from "path";
import { chromium, check, norm, root, VIEWPORTS, testServer, openPage, openRow, finish } from "./_ui_common.mjs";

const cases = Object.fromEntries(JSON.parse(fs.readFileSync(path.join(root, "eval/articles_frozen.json"), "utf8")).cases.map((c) => [c.id.split("-")[0], c.article]));
const server = await testServer();
const browser = await chromium.launch();

for (const [name, vp, mobile] of VIEWPORTS) {
  console.log(`\n== ${name} ${vp.width}x${vp.height}: long article`);
  const { page, errors, shot, inView, overflowX, audit } = await openPage(browser, server.base, vp, mobile, `L-${name}`);
  await page.goto(server.base);
  await page.evaluate(() => sessionStorage.clear());
  await page.fill("#article", cases.L1);
  check(Array.from(cases.L1).length > 5700 && Array.from(cases.L1).length <= 6000, `the article has ${Array.from(cases.L1).length} characters (limit 6000)`);
  check(norm(await page.textContent("#char-count")) === "٥٨٠٩ / ٦٠٠٠ حرف" && !(await page.locator("#audit-btn").isDisabled()), "the counter shows the length against the limit and the audit is allowed");
  await audit(cases.L1);
  await page.waitForTimeout(600);
  check((await overflowX()) <= 1, "results: no horizontal overflow");
  const state = await page.evaluate(() => ({ total: lastResult.findings.length, pending: lastResult.findings.filter((f) => pendingKind(f)).map((f) => f.id), start: Object.fromEntries(lastResult.findings.map((f) => [f.id, f.start])) }));
  console.log(`INFO  ${state.total} quotations, ${state.pending.length} waiting`);
  check(state.pending.length >= 3, "the article has several quotations waiting for the writer");
  check(norm(await page.textContent("#panel-progress")).includes(" من " + (state.total).toLocaleString("ar-EG")), `the panel says which of ${state.total} this is`);
  check(/الفقرة [٠-٩]+ من [٠-٩]+/.test(norm(await page.textContent("#current .f-where"))), "the card says where in the article (paragraph number)");
  check(state.pending.every((id, i, a) => i === 0 || state.start[id] > state.start[a[i - 1]]), "the pending list is in the order of the article");

  // the sequence: «التالي» visits every waiting quotation once, in article order, and comes back to the first
  const seen = [];
  const nextBtn = mobile ? "#dock-next" : "#next-btn";
  for (let i = 0; i < state.pending.length + 1; i++) {
    seen.push(await page.evaluate(() => Number(document.querySelector("#current article").id.replace("finding-", ""))));
    await page.click(nextBtn);
    await page.waitForTimeout(250);
  }
  check(seen.slice(0, state.pending.length).join() === state.pending.join() && seen[state.pending.length] === state.pending[0], `«التالي» walks the waiting quotations in order and wraps (${seen.join("→")})`);
  if (!mobile) {
    const vis = await page.evaluate(() => { const m = document.querySelector("#article-view mark.current"), v = document.getElementById("article-view"); if (!m) return false; const a = m.getBoundingClientRect(), b = v.getBoundingClientRect(); return a.top >= b.top - 1 && a.bottom <= b.bottom + 1; });
    check(vis, "wide screen: the quotation in the card is outlined and in view in the article beside it");
    const both = await page.evaluate(() => { document.getElementById("workbench").scrollIntoView({ block: "start" }); const p = document.getElementById("panel").getBoundingClientRect(), a = document.getElementById("article-col").getBoundingClientRect(); return p.top >= 0 && p.bottom <= innerHeight + 1 && a.top >= 0 && a.bottom <= innerHeight + 1; });
    check(both, "wide screen: the decision panel and the article column each fit the screen, side by side (the article scrolls inside its column)");
    await page.evaluate(() => window.scrollTo(0, 0));
  }

  // a decision moves on by itself; the list shows the open ones first and keeps unresolved items visible
  const first = state.pending[0];
  await openRow(page, first);
  check((await page.locator("#queue .q-group.need li").count()) === state.pending.length, "the list keeps every waiting quotation visible");
  await shot("1-long");

  // keyboard focus must never be left behind the bottom bar (WCAG 2.2 SC 2.4.11, failure F110)
  const covered = async (limit) => page.evaluate((lim) => {
    const dock = document.getElementById("review-dock");
    const dr = dock.hidden || getComputedStyle(dock).display === "none" ? null : dock.getBoundingClientRect();
    const sel = 'a[href], button:not([disabled]), input:not([type=hidden]), select, textarea, summary, [tabindex="0"], mark[tabindex]';
    const items = [...document.querySelectorAll(sel)].filter((e) => { const r = e.getBoundingClientRect(); const cs = getComputedStyle(e); return r.width > 0 && r.height > 0 && cs.visibility !== "hidden" && !e.closest("[hidden]") && !e.closest("details:not([open]) > :not(summary)"); });
    const bad = [];
    for (const e of items.slice(0, lim)) {
      e.focus({ preventScroll: false });
      const r = e.getBoundingClientRect();
      // a control taller than most of the screen cannot avoid the bar; every other control must be wholly clear of it
      if (dr && r.height < innerHeight * 0.6 && r.bottom > dr.top + 0.5 && r.top < dr.bottom - 0.5) bad.push((e.id || e.className || e.tagName) + ":" + (e.textContent || "").trim().slice(0, 20));
    }
    return { checked: Math.min(items.length, lim), bad, dock: !!dr };
  }, limit);
  const cv = await covered(150);
  check(cv.dock === mobile && cv.bad.length === 0, `no focused control is hidden behind the bottom bar (${cv.checked} controls focused, bar ${cv.dock ? "on" : "off"}${cv.bad.length ? "; covered: " + cv.bad.slice(0, 4).join(", ") : ""})`);
  // and a real Tab sweep through the first controls
  await page.evaluate(() => { window.scrollTo(0, 0); document.activeElement?.blur(); });
  let hidden = 0, pressed = 0;
  for (let i = 0; i < 70; i++) {
    await page.keyboard.press("Tab"); pressed++;
    hidden += await page.evaluate(() => { const dock = document.getElementById("review-dock"); const e = document.activeElement; if (!e || dock.hidden || getComputedStyle(dock).display === "none" || dock.contains(e)) return 0; const r = e.getBoundingClientRect(), d = dock.getBoundingClientRect(); return r.height < innerHeight * 0.6 && r.bottom > d.top + 0.5 && r.top < d.bottom - 0.5 ? 1 : 0; });
  }
  check(hidden === 0, `${pressed} real Tab presses: the focused control is never under the bar`);
  const pad = await page.evaluate(() => ({ h: getComputedStyle(document.documentElement).getPropertyValue("--dock-h").trim(), sp: getComputedStyle(document.documentElement).scrollPaddingBottom }));
  check(mobile ? parseInt(pad.h) > 30 && parseInt(pad.sp) >= parseInt(pad.h) : pad.h === "0px", `the bar's height is reserved as scroll padding (${pad.h} / ${pad.sp})`);
  if (mobile) {
    const dockH = await page.evaluate(() => Math.round(document.getElementById("review-dock").getBoundingClientRect().height));
    check(dockH <= vp.height * 0.16, `the bar takes at most 16% of the screen height (${dockH} of ${vp.height} px)`);
    const t = await page.$$eval(".panel .btn, #dock-next, .row", (b) => b.filter((x) => x.getBoundingClientRect().width).map((x) => Math.round(x.getBoundingClientRect().height)));
    check(t.every((h) => h >= 44), `panel buttons and list rows are at least 44 px high (${[...new Set(t)].join(", ")})`);
  }
  check(errors.length === 0, `no console errors ${errors.join(" | ")}`);
}

// ---- mixed direction (W3C: Structural markup and right-to-left text in HTML; Inline markup and bidirectional text in HTML)
console.log("\n== mixed-direction text");
{
  const { page, errors, shot, audit, overflowX } = await openPage(browser, server.base, { width: 390, height: 844 }, true, "L-bidi");
  await page.goto(server.base);
  await page.evaluate(() => sessionStorage.clear());
  await audit(cases.L3);
  const runs = await page.$$eval("#article-view bdi", (b) => b.map((x) => ({ text: x.textContent, dir: x.getAttribute("dir"), ub: getComputedStyle(x).unicodeBidi })));
  const url = runs.find((r) => r.text.startsWith("https://"));
  check(url && url.text === "https://example.org/athkar?id=153" && url.dir === "ltr" && url.ub === "isolate", `the URL is an isolated left-to-right run without the sentence's full stop (${url?.text})`);
  check(runs.some((r) => r.text === "Al-Baqarah 2:186" && r.dir === "ltr"), "the Latin reference «Al-Baqarah 2:186» is an isolated left-to-right run");
  check(runs.some((r) => r.text === "example.org") === false, "no run is split in the middle of the URL");
  const dirs = await page.evaluate(() => ({ html: document.documentElement.dir, lang: document.documentElement.lang, view: document.getElementById("article-view").dir, ta: document.getElementById("article").dir }));
  check(dirs.html === "rtl" && dirs.lang === "ar" && dirs.view === "rtl" && dirs.ta === "rtl", "the page, the article view and the text box declare Arabic and right-to-left");
  check((await page.inputValue("#revised-text")) === cases.L3, "the characters themselves are unchanged by the isolation");
  const overlap = await page.evaluate(() => { const b = document.querySelector("#article-view bdi.ltr"), r = b.getBoundingClientRect(); return r.right <= innerWidth + 1 && r.left >= -1; });
  check(overlap && (await overflowX()) <= 1, "the long URL stays inside the screen (no horizontal scroll)");
  await shot("1-url");
  check(errors.length === 0, `no console errors ${errors.join(" | ")}`);
}

// ---- a slow server, then a failing one: the article stays, the writer is told, one button retries
console.log("\n== slow and failing server");
{
  const { page, errors, shot } = await openPage(browser, server.base, { width: 390, height: 844 }, true, "L-slow");
  await page.goto(server.base);
  await page.evaluate(() => sessionStorage.clear());
  let calls = 0;
  await page.route("**/api/audit", async (route) => {
    calls++;
    if (calls === 1) { await new Promise((r) => setTimeout(r, 9000)); return route.abort("failed"); }
    return route.continue();
  });
  await page.fill("#article", cases.L5);
  await page.click("#audit-btn");
  await page.waitForTimeout(8200);
  check(norm(await page.textContent("#status")).includes("الخادم المجاني يستيقظ") && (await page.locator("#status .spinner").count()) === 1, "after a few seconds the writer is told the free server may need a minute to wake");
  check(await page.locator("#audit-btn").isDisabled(), "the audit button is busy, not clickable twice");
  await shot("1-waking");
  await page.waitForSelector("#status .btn", { timeout: 20000 });
  check(norm(await page.textContent("#status")).includes("مقالك ما زال في المربع"), "when the connection fails the status says the article is still in the box");
  check((await page.inputValue("#article")) === cases.L5, "the article text is untouched");
  await shot("2-failed");
  await page.click("#status .btn");
  await page.waitForSelector("#results:not([hidden])", { timeout: 30000 });
  check(calls === 2 && norm(await page.textContent("#verdict-title")) === "لم نجد اقتباسات قرآنية في النص", "«أعد المحاولة» audits again and the page recovers");
  check(errors.filter((e) => !/Failed to load resource|net::ERR/.test(e)).length === 0, `no page errors ${errors.join(" | ")}`);
}

// ---- no findings, and the model failing: still usable
for (const [name, vp, mobile] of VIEWPORTS) {
  console.log(`\n== ${name}: no findings / model failed`);
  const { page, errors, shot, audit, overflowX } = await openPage(browser, server.base, vp, mobile, `S-${name}`);
  await page.goto(server.base);
  await page.evaluate(() => sessionStorage.clear());
  await audit(cases.L5).catch(() => {});
  await page.waitForSelector("#results:not([hidden])");
  check(norm(await page.textContent("#verdict-title")) === "لم نجد اقتباسات قرآنية في النص", "no findings: the verdict says so");
  const vt = norm(await page.textContent("#verdict"));
  check(!vt.includes("null") && vt.includes("ليس حكمًا على المقال كله") && vt.includes("افحص المحدَّد"), "no findings: it says it is not a judgement of the article and how to check a missed phrase");
  check(!/\bnull\b|undefined|\[object/.test(await page.evaluate(() => document.body.innerText)), "no findings: no stray «null» text");
  check(await page.locator("#panel").isHidden() && (await page.locator("#review-dock").isHidden()) && await page.locator("#article-view").isVisible(), "no findings: no empty decision panel or bar; the article is shown for selecting");
  check(norm(await page.textContent("#final")) === "" || await page.locator("#final").isHidden(), "no findings: no final check to fill in");
  check((await overflowX()) <= 1, "no findings: no horizontal overflow");
  await shot("1-no-findings", true);
  // a phrase the search missed can still be selected in the article
  const ok = await page.evaluate(() => { const w = document.createTreeWalker(document.getElementById("article-view"), NodeFilter.SHOW_TEXT); for (let n = w.nextNode(); n; n = w.nextNode()) { const i = n.textContent.indexOf("الوقت كالسيف"); if (i >= 0) { const r = document.createRange(); r.setStart(n, i); r.setEnd(n, i + 12); const s = getSelection(); s.removeAllRanges(); s.addRange(r); return true; } } return false; });
  await page.waitForTimeout(200);
  check(ok && await page.locator("#sel-bar").isVisible() && (await page.inputValue("#article")) === cases.L5, "a selection in the article offers «افحص المحدَّد»");
  check(errors.length === 0, `no console errors ${errors.join(" | ")}`);

  // the model failed (a 429): what the writer sees
  const f = await openPage(browser, server.base, vp, mobile, `F-${name}`);
  await f.page.goto(server.base);
  await f.page.evaluate(() => sessionStorage.clear());
  await f.page.route("**/api/audit", async (r) => {
    const res = await r.fetch(); const j = await res.json();
    j.mode = "ai_failed"; j.provider = "Groq (qwen/qwen3.8-27b)"; j.ai = { ...j.ai, configured: true, provider: "groq", responded: false, outcome: "failed", error: "HTTP 429" };
    j.notices = [{ level: "warning", text: "تعذّر الاستخراج بالذكاء الاصطناعي في هذا التدقيق. عُرضت الاقتباسات المعلَّمة صراحةً والعبارات المطابقة لنص المصحف فقط؛ وقد تفوت الاقتباسات القصيرة غير المعلَّمة." }, ...j.notices];
    r.fulfill({ response: res, json: j });
  });
  await f.audit(readQuotes());
  const meta = norm(await f.page.textContent("#notices"));
  check(meta.includes("تعذّر اقتراح الذكاء الاصطناعي هذه المرة") && meta.includes("حدّدها في المقال"), "model failed: one plain line says so and what to do about a missed phrase");
  check(!(await f.page.locator("#notices .notice").allTextContents()).some((t) => /تعذّر الاستخراج/.test(t)), "model failed: the server's warning is not repeated as a second banner");
  check((await f.page.locator("#current article").count()) === 1 && (await f.overflowX()) <= 1, "model failed: the review is complete and usable");
  await f.shot("1-ai-failed");
  check(f.errors.length === 0, `no console errors ${f.errors.join(" | ")}`);
}
function readQuotes() { return cases.L1.slice(0, 2400); }
finish(server, browser);
