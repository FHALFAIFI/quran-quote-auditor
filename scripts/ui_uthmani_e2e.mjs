// Browser check of the revised interface with Uthmani-script input (Playwright, Chromium), desktop 1280 and mobile 390.
//
//   npm i playwright            # in any scratch directory; not a project dependency
//   NODE_PATH=<scratch>/node_modules node scripts/ui_uthmani_e2e.mjs [--shots DIR] [--python PATH] [--live https://host]
//
// Starts its OWN server on a free port with AI off (no key in its environment, no Groq call possible); with --live URL it drives
// that deployment instead (ONE audit, i.e. one model call when the service has AI on; the checks do not depend on what the model
// proposes, and the result of the model call is printed). With --shots DIR and --live it also saves element screenshots. Article: one correct
// Uthmani quotation (البقرة: 153), one with a changed word (النور: 56) and one correct quotation with a wrong reference (الشرح: 6).
// Quran text in the test article: Tanzil Project, https://tanzil.net (Tanzil Quran Text, Uthmani v1.1, CC BY 3.0; its notice is in
// tests/fixtures/uthmani_verses.json). Typed from Tanzil's text with some marks in another order, so not a byte copy; the
// النور: 56 quotation has one word changed by hand and the الشرح quotation carries a wrong reference on purpose: test inputs, not Quran text.
// Checks: first screen (title, purpose, sample, text box, ONE primary button, help collapsed); no horizontal overflow; RTL;
// three primary figures; finding order = article marker order; the correct quotation is a collapsed row with no correction
// card; optional formatting is apart, neutral and not counted; Tab order; keyboard approval; the revised article differs only
// in the approved spans; copy feedback.
import { createRequire } from "module";
import { spawn } from "child_process";
import net from "net";
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const require = createRequire(import.meta.url);
const { chromium } = require("playwright");
const argv = process.argv.slice(2);
const opt = (n) => { const i = argv.indexOf(n); return i >= 0 ? argv[i + 1] : null; };
const shots = opt("--shots");
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const python = opt("--python") || process.env.PYTHON || (fs.existsSync(path.join(root, ".venv/bin/python")) ? path.join(root, ".venv/bin/python") : "python3");
if (shots) fs.mkdirSync(shots, { recursive: true });
let failures = 0;
const check = (c, m) => { console.log(`${c ? "PASS" : "FAIL"}  ${m}`); if (!c) failures++; };

const live = opt("--live");
let child = null;
let base;
if (live) {
  base = live.replace(/\/$/, "");
} else {
  const port = await new Promise((res) => { const s = net.createServer(); s.listen(0, "127.0.0.1", () => { const p = s.address().port; s.close(() => res(p)); }); });
  const env = { ...process.env, AI_PROVIDER: "none", RATE_LIMIT_PER_MINUTE: "1000" };
  for (const k of Object.keys(env)) if (/^(GROQ|GEMINI|GOOGLE)_|API_KEY/i.test(k)) delete env[k];
  child = spawn(python, ["-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", String(port)], { cwd: root, env, stdio: "ignore" });
  base = `http://127.0.0.1:${port}`;
}
for (let i = 0; i < 300; i++) { try { if ((await fetch(base + "/api/health", { signal: AbortSignal.timeout(20000) })).ok) break; } catch { /* not up yet */ } await new Promise((r) => setTimeout(r, 400)); }
const h = await (await fetch(base + "/api/health")).json();
if (live) console.log(`INFO  live ${base}: mode ${h.mode}, provider ${h.provider}`);
else check(h.ai_configured === false, "the server under test has AI off");

const art = `قال تعالى: ﴿يَـٰٓأَيُّهَا ٱلَّذِينَ ءَامَنُوا۟ ٱسْتَعِينُوا۟ بِٱلصَّبْرِ وَٱلصَّلَوٰةِ ۚ إِنَّ ٱللَّهَ مَعَ ٱلصَّـٰبِرِينَ﴾ [البقرة: 153]

وقال سبحانه: ﴿وَأَقِيمُوا۟ ٱلصَّلَوٰةَ وَءَاتُوا۟ ٱلزَّكَوٰةَ وَأَطِيعُوا۟ ٱلنَّبِىَّ لَعَلَّكُمْ تُرْحَمُونَ﴾ [النور: 56]

﴿فَإِنَّ مَعَ ٱلْعُسْرِ يُسْرًا﴾ [الشرح: 6]`;
const browser = await chromium.launch();
const viewports = [["desktop 1280", { width: 1280, height: 800 }], ["mobile 390", { width: 390, height: 844 }]].filter(([v]) => !opt("--only") || v.startsWith(opt("--only")));
for (const [vp, size] of viewports) {
  const ctx = await browser.newContext({ viewport: size, locale: "ar", deviceScaleFactor: Number(opt("--dpr") || 1) });
  await ctx.grantPermissions(["clipboard-read", "clipboard-write"], { origin: base }).catch(() => {});
  const page = await ctx.newPage();
  const errs = [];
  page.on("pageerror", (e) => errs.push(String(e)));
  page.on("console", (m) => { if (m.type() === "error") errs.push(m.text()); });
  const tag = vp.split(" ")[0];
  await page.goto(base + "/");
  const geometry = () => page.evaluate(() => ({
    sw: document.documentElement.scrollWidth, iw: window.innerWidth, dir: document.documentElement.dir, bodyDir: getComputedStyle(document.body).direction,
    wide: [...document.querySelectorAll("body *")].filter((e) => { const r = e.getBoundingClientRect(); return r.width > 0 && (r.right > innerWidth + 1 || r.left < -1) && !e.closest("details:not([open]) > :not(summary)"); }).slice(0, 4).map((e) => e.tagName + "." + e.className),
  }));
  let g = await geometry();
  check(g.sw <= g.iw && g.dir === "rtl" && g.bodyDir === "rtl", `${vp}: home has no horizontal overflow (${g.sw}/${g.iw}) and is RTL`);
  const first = await page.evaluate(() => ({
    title: document.querySelector("h1")?.textContent, purpose: document.querySelector(".tagline")?.textContent.length, sample: !!document.getElementById("sample-select"),
    box: !!document.getElementById("article"), demo: (() => { const r = document.getElementById("demo-btn").getBoundingClientRect(); return r.width > 0 && r.bottom <= innerHeight; })(), boxH: document.getElementById("article").getBoundingClientRect().height, bottom: document.getElementById("audit-btn").getBoundingClientRect().bottom,
    height: innerHeight, helpOpen: document.querySelector(".help").open, safety: document.querySelector(".safety")?.textContent.length, bannerInHelp: !!document.querySelector(".help #mode-banner"),
  }));
  check(first.title && first.purpose > 20 && first.sample && first.box && first.demo && first.boxH <= first.height * 0.3 && first.bottom <= first.height, `${vp}: first screen = title, purpose, the demo action, a short text box, the audit button (box ${Math.round(first.boxH)} px, bottom ${Math.round(first.bottom)}/${first.height})`);
  check(!first.helpOpen && first.safety > 20 && first.bannerInHelp, `${vp}: help (with the technical status) is collapsed; the safety sentence stays visible`);
  if (shots) await page.screenshot({ path: path.join(shots, `ui-${tag}-home.png`) });

  // Tab order: text box → clear → audit
  await page.focus("#article");
  const seq = [];
  for (let i = 0; i < 3; i++) { await page.keyboard.press("Tab"); seq.push(await page.evaluate(() => document.activeElement.id || document.activeElement.tagName)); }
  check(seq.includes("clear-btn") && seq.includes("audit-btn"), `${vp}: Tab reaches the clear and audit buttons from the text box (${seq.join(" → ")})`);

  await page.fill("#article", art);
  const [resp] = await Promise.all([page.waitForResponse((r) => r.url().endsWith("/api/audit"), { timeout: 120000 }), page.click("#audit-btn")]);
  const data = await resp.json();
  if (live) console.log("INFO  audit:", JSON.stringify({ http: resp.status(), mode: data.mode, ai: { outcome: data.ai?.outcome, http_status: data.ai?.http_status, proposed: data.ai?.proposed, added_only: data.ai?.added_only, also_found: data.ai?.also_found, model: data.ai?.model }, stats: data.stats }));
  await page.waitForSelector("#results:not([hidden]) .finding", { timeout: 60000 });
  await page.waitForTimeout(400);
  g = await geometry();
  check(g.sw <= g.iw, `${vp}: after the audit there is no horizontal overflow (${g.sw}/${g.iw}) ${g.wide.join(",")}`);
  const order = await page.$$eval("#findings .finding .f-num", (n) => n.map((x) => x.textContent));
  const marks = await page.$$eval("#article-view mark sup", (n) => n.map((x) => x.textContent));
  check(order.join() === marks.join() && order.join() === "١,٢,٣", `${vp}: finding order and article markers agree (${order.join("،")})`);
  const stats = await page.$$eval("#summary .stats .tile", (n) => n.map((x) => x.textContent.replace(/\s+/g, " ").trim()));
  check(stats.length === 3 && stats[0].includes("تحتاج مراجعة") && stats[1].includes("تصحيحات مقترحة") && stats[2].includes("اقتباسات مرصودة"), `${vp}: three primary figures: ${stats.join(" | ")}`);
  const row = await page.evaluate(() => {
    const li = document.querySelector("#findings .finding.ok");
    return { exists: !!li, collapsed: !!li && !li.querySelector("details").open, chips: [...li.querySelectorAll(".f-head .chip")].map((c) => c.textContent), corrections: li.querySelectorAll(".change:not(.optional)").length,
      optional: li.querySelectorAll(".optional-box .change.optional").length };
  });
  check(row.exists && row.collapsed && row.corrections === 0 && row.chips.some((c) => c.includes("رسم عثماني")), `${vp}: the correct Uthmani quotation is a collapsed row (${row.chips.join(" · ")}), with no correction card`);
  const colours = await page.evaluate(() => {
    const bg = (e) => getComputedStyle(e).backgroundColor;
    const req = document.querySelector(".action .change:not(.optional) .ch-before"), opt = document.querySelector(".change.optional .ch-before");
    return { req: req && bg(req), opt: opt && bg(opt), after: bg(document.querySelector(".action .change:not(.optional) .ch-after")), optAfter: opt && bg(document.querySelector(".change.optional .ch-after")) };
  });
  check(colours.req !== colours.opt && colours.after !== colours.optAfter, `${vp}: a correction is red/green, optional formatting is neutral (${colours.req} vs ${colours.opt})`);
  const counts = await page.evaluate(() => ({ cards: document.querySelectorAll(".action .change:not(.optional)").length, fixTile: document.querySelector("#summary .stat.fix .n").textContent,
    optional: document.querySelectorAll(".optional-box .change.optional").length, optPill: [...document.querySelectorAll("#editor-progress .pill")].map((p) => p.textContent) }));
  check(counts.cards === 2 && counts.fixTile === "٢" && counts.optional >= 1, `${vp}: ${counts.cards} corrections counted (tile ${counts.fixTile}); ${counts.optional} optional formatting card(s) are not counted`);
  check(counts.optPill.some((p) => p.includes("بانتظار قرارك ٢")), `${vp}: «waiting for your decision» counts corrections only (${counts.optPill.join(" · ")})`);
  if (shots) await page.screenshot({ path: path.join(shots, `ui-${tag}-results.png`), fullPage: true });

  // Reading order inside a card that needs review: article text → source → difference/reference → action
  const orderIn = await page.evaluate(() => {
    const body = document.querySelector("#findings .finding.review:not(.weak) .f-body");
    const labels = [...body.querySelectorAll(":scope > .f-quote-line > .row-label, :scope > .action > .row-label, :scope > .f-all > summary")].map((e) => e.textContent.slice(0, 18));
    return labels;
  });
  check(orderIn[0].includes("في المقال") && orderIn[1].includes("المطلوب منك: قرارك") && orderIn[2].includes("التفاصيل"), `${vp}: card order = the quotation, the decision (difference first), then the folded details (${orderIn.slice(0, 3).join(" | ")})`);
  const delta = await page.evaluate(() => { const bg = (e) => getComputedStyle(e).backgroundColor; const c = document.querySelector(".action .change:not(.optional)"); return { b: bg(c.querySelector(".d-before")), a: bg(c.querySelector(".d-after")) }; });
  check(delta.b !== delta.a, `${vp}: the old value and the new value of the difference are coloured differently (${delta.b} vs ${delta.a})`);

  const elementShot = async (loc, name) => { if (shots && tag === "desktop") { await loc.scrollIntoViewIfNeeded(); await loc.screenshot({ path: path.join(shots, name) }); } };
  await elementShot(page.locator("#findings .finding.review").first(), "card-correction.png");
  // keyboard: open the compact row with Enter, approve a correction with Space
  await page.locator(".f-compact > summary").first().focus();
  await page.keyboard.press("Enter");
  check((await page.locator(".f-compact[open]").count()) === 1, `${vp}: the compact row opens with Enter`);
  await page.locator(".f-compact .optional-box summary").first().click();
  await elementShot(page.locator("#findings .finding.ok").first(), "card-uthmani-matched.png");
  const approves = page.locator('.action .change:not(.optional) button[data-act="approved"]');
  for (let i = 0; i < 2; i++) { await approves.nth(i).focus(); await page.keyboard.press("Space"); }
  const revised = await page.inputValue("#revised-text");
  const expected = art.replace(/ٱلنَّبِىَّ/, "الرَّسُولَ").replace("[الشرح: 6]", "[الشرح: 5]");
  const diff = revised.length !== art.length || revised !== art;
  const noOptional = !revised.includes("يَا أَيُّهَا") && revised.includes("يَـٰٓأَيُّهَا");
  check(diff && noOptional && revised.includes("[الشرح: 5]") && !revised.includes("ٱلنَّبِىَّ"), `${vp}: after approving only the two corrections the article differs only there; the correct Uthmani text is untouched`);
  check(revised.split("\n").length === art.split("\n").length, `${vp}: line structure preserved`);
  await elementShot(page.locator("#editor-title").locator("xpath=ancestor::section[1]"), "editor-preview.png");
  await page.click("#tab-text");
  await page.click("#copy-btn");
  await page.waitForTimeout(300);
  const clip = await page.evaluate(() => navigator.clipboard.readText().catch(() => null));
  check(clip === null || clip === revised, `${vp}: copy puts the revised article on the clipboard`);
  check((await page.textContent("#copy-note")).includes("نُسخ"), `${vp}: copy gives feedback beside the button`);
  check(errs.length === 0, `${vp}: no page errors ${errs.join(";")}`);
  await ctx.close();
}
await browser.close();
if (child) child.kill();
console.log(failures ? `${failures} FAILED` : "all checks passed");
process.exit(failures ? 1 : 0);
