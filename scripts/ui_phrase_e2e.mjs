// Browser end-to-end check of the unmarked-phrase workflow (Playwright, Chromium). Two separate parts.
//
//   npm i playwright            # in any scratch directory; not a project dependency
//
// 1) DETERMINISTIC (default). Starts its OWN server on a free port with AI switched off (AI_PROVIDER=none, no API key in
//    its environment, a high rate limit), so the tier assertions cannot be changed by a model and no Groq call is possible.
//    It refuses to run if that server reports AI as configured. Needs the Quran text (live fetch or the local cache).
//      NODE_PATH=<scratch>/node_modules node scripts/ui_phrase_e2e.mjs [--shots DIR] [--python PATH]
//    To use a server you started yourself instead (it must have AI off; the check is made, not assumed):
//      NODE_PATH=... node scripts/ui_phrase_e2e.mjs --server http://localhost:8011 [--shots DIR]
//
// 2) LIVE AI (opt-in). Runs against a server that HAS AI configured (for example the Render service) and makes ONE audit,
//    i.e. one Groq call. It does not assume how many findings the model produces; it checks properties that must hold
//    whatever the model proposes (see liveAi()). If the model did not respond, it says so and exits 2: that is
//    "inconclusive", not a pass.
//      NODE_PATH=... node scripts/ui_phrase_e2e.mjs --live-ai https://quran-quote-auditor.onrender.com [--shots DIR]
//
// Deterministic flow: an article with (1) an unmarked distinctive quotation, (2) an unmarked slightly misquoted one and
// (3) a two-word phrase the search does not report → audit → the candidate and the "maybe" are labelled
// differently; the "maybe" offers no replacement text → confirm its verse → only then a proposal appears →
// approve it → the revised article differs from the original ONLY in the quoted span → highlight the
// two-word phrase by hand, choose its verse → check the reply draft never names an unconfirmed phrase.
import { createRequire } from "module";
import { spawn } from "child_process";
import net from "net";
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const require = createRequire(import.meta.url);
const { chromium } = require("playwright");

// ---- arguments (a bare URL is still accepted as --server, a second bare argument as the screenshot directory)
const argv = process.argv.slice(2);
const opt = (name) => { const i = argv.indexOf(name); return i >= 0 ? argv[i + 1] : null; };
const bare = argv.filter((x, i) => !x.startsWith("--") && !argv[i - 1]?.startsWith("--"));
const liveUrl = opt("--live-ai");
const serverArg = opt("--server") || bare.find((x) => /^https?:/.test(x)) || null;
const shots = opt("--shots") || bare.find((x) => !/^https?:/.test(x)) || null;
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const python = opt("--python") || process.env.PYTHON || (fs.existsSync(path.join(root, ".venv/bin/python")) ? path.join(root, ".venv/bin/python") : "python3");
if (shots) fs.mkdirSync(shots, { recursive: true });

let failures = 0;
const check = (cond, msg) => { console.log(`${cond ? "PASS" : "FAIL"}  ${msg}`); if (!cond) failures++; };
const shot = async (page, name, opts = {}) => { if (shots) await page.screenshot({ path: path.join(shots, name), ...opts }); };
const health = async (base) => (await fetch(base + "/api/health")).json();

// A server of our own: AI off in its environment, so nothing outside this process can turn it on.
async function startIsolatedServer() {
  const port = await new Promise((res, rej) => { const s = net.createServer(); s.listen(0, "127.0.0.1", () => { const p = s.address().port; s.close(() => res(p)); }); s.on("error", rej); });
  const env = { ...process.env, AI_PROVIDER: "none", RATE_LIMIT_PER_MINUTE: "1000" };
  for (const k of Object.keys(env)) if (/^(GROQ|GEMINI|GOOGLE)_|API_KEY/i.test(k)) delete env[k];
  const child = spawn(python, ["-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", String(port)], { cwd: root, env, stdio: ["ignore", "pipe", "pipe"] });
  let log = "";
  child.stdout.on("data", (d) => (log += d)); child.stderr.on("data", (d) => (log += d));
  const base = `http://127.0.0.1:${port}`;
  for (let i = 0; i < 100; i++) {
    if (child.exitCode !== null) throw new Error(`test server exited early:\n${log.slice(-1500)}`);
    try { if ((await fetch(base + "/api/health")).ok) return { base, stop: () => child.kill() }; } catch { /* not up yet */ }
    await new Promise((r) => setTimeout(r, 200));
  }
  child.kill();
  throw new Error(`test server did not start:\n${log.slice(-1500)}`);
}

const MAYBE = "قد يكون اقتباسًا قرآنيًا — يحتاج مراجعة";
const article = "لا تجزع من الأزمات، والله يقول ادعوا ربكم تضرعا وخفية، وفي مواساة المصابين وبشر المؤمنين الذين إذا أصابتهم مصيبة قالوا إنا لله وإنا إليه راجعون رسالة أمل. وقال لهم كونوا مع الصابرين دائما.";

async function deterministic(browser, base) {
  const h = await health(base);
  check(h.mode === "reduced" && h.ai_configured === false, `the server under test has AI off (mode ${h.mode}, ai_configured ${h.ai_configured})`);
  if (h.ai_configured) { console.log("FAIL  refusing to run the deterministic tier checks against a server with AI on; run without --server, or use --live-ai for that server."); return; }
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: "ar" });
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });

  await page.goto(base + "/");
  await page.fill("#article", article);
  check(await page.locator("#phrase-btn").isDisabled(), "manual-check button is disabled before an audit");
  await page.click("#audit-btn");
  await page.waitForSelector("#results:not([hidden]) .finding", { timeout: 60000 });
  await shot(page, "p1-results.png");

  const cards = page.locator(".finding");
  check((await cards.count()) === 2, `two findings are listed (got ${await cards.count()})`);
  const cand = cards.filter({ hasText: "ادعوا ربكم تضرعا وخفية" });
  const maybe = cards.filter({ hasText: "وبشر المؤمنين" });
  check((await cand.locator(".f-head .chip.cand").innerText()) === "مرشَّح لاقتباس قرآني", "distinctive exact phrase is labelled as a candidate");
  check((await maybe.locator(".f-head .chip.maybe").innerText()) === MAYBE, "approximate phrase says «قد يكون اقتباسًا قرآنيًا — يحتاج مراجعة»");
  check((await maybe.locator(".f-head .chip.ok").count()) === 0, "the maybe-card shows no green «matched» chip");
  check((await maybe.locator(".change").count()) === 0 && (await maybe.locator(".confirm-box").count()) === 1, "the maybe-card offers no replacement text, only «confirm»");
  check((await page.locator("#article-view mark.s-possible").count()) === 1, "the maybe is highlighted differently in the article");
  await page.click("#summary .more-stats summary");  // the secondary counts are on demand
  check((await page.locator("#summary .tile").filter({ hasText: "قد تكون اقتباسًا" }).locator(".n").innerText()) === "١", "summary counts one possible quotation");

  // the reply draft for a social post must not name a phrase that may not be a quotation
  await page.click(".reply-box summary");
  const reply0 = await page.inputValue("#reply-text");
  check(!reply0.includes("وبشر المؤمنين"), "reply draft does not name the unconfirmed phrase");

  // confirm the verse → only now a proposal appears
  await maybe.locator(".confirm-box button").first().click();
  await page.waitForSelector('.finding .change[data-change$="-wording"]', { timeout: 20000 });
  const confirmed = page.locator(".finding").filter({ hasText: "وبشر المؤمنين" });
  check((await confirmed.locator(".f-head .chip.manual").count()) === 1, "confirmed phrase is now marked «حدّدتَ هذا المقطع بنفسك»");
  const change = confirmed.locator('.change[data-change$="-wording"]').first();
  check((await change.locator(".ch-after").innerText()).includes("وبشر الصابرين"), "proposal comes from the source: «المؤمنين» → «الصابرين»");
  check((await page.inputValue("#revised-text")) === article, "nothing changed before approval");
  await change.locator('button[data-act="approved"]').click();
  const revised = await page.inputValue("#revised-text");
  check(revised === article.replace("وبشر المؤمنين", "وبشر الصابرين"), "revised article = original with ONLY the quoted span corrected");
  await shot(page, "p2-confirmed.png");

  // manual selection of a two-word phrase that the search does not report
  const sel = await page.evaluate(() => {
    const ta = document.getElementById("article");
    const a = ta.value.indexOf("مع الصابرين");
    ta.focus();
    ta.setSelectionRange(a, a + "مع الصابرين".length);
    return [a, a + "مع الصابرين".length];
  });
  await page.waitForFunction(() => !document.getElementById("phrase-btn").disabled);
  await page.click("#phrase-btn");
  await page.waitForFunction(() => document.querySelectorAll(".finding").length === 3, null, { timeout: 20000 });
  const manual = page.locator(".finding").filter({ has: page.locator(".quote-text", { hasText: /^مع الصابرين$/ }) }).first();
  check((await manual.locator(".confirm-box .choice").count()) >= 2, "a two-word phrase that occurs in several verses lists the choices");
  check((await manual.locator(".change").count()) === 0, "no proposal before a verse is chosen");
  await shot(page, "p3-manual-choices.png");
  check((await page.locator(".finding").count()) === 3, "the manual phrase is added as a third finding");
  await manual.locator(".confirm-box .choice button").first().click();
  await page.waitForFunction(() => document.querySelectorAll(".finding .confirm-box").length === 0, null, { timeout: 20000 });
  const chosen = page.locator(".finding").filter({ has: page.locator(".quote-text", { hasText: /^مع الصابرين$/ }) }).first();
  check((await chosen.locator(".source-box").count()) === 1, "after choosing a verse the source text is shown");
  check((await page.inputValue("#revised-text")) === revised, "choosing a verse does not change the article");

  // the text changed after the audit → the button is disabled again
  await page.fill("#article", article + " ");
  check(await page.locator("#phrase-btn").isDisabled(), "button disabled when the text changed after the audit");

  // the choice survives a reload (sessionStorage)
  await page.reload();
  await page.waitForSelector("#results:not([hidden]) .finding");
  check((await page.locator(".finding").count()) === 3, "findings (including the manual one) survive a reload");

  // mobile
  const m = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true, locale: "ar" });
  const mp = await m.newPage();
  await mp.goto(base + "/");
  await mp.fill("#article", article);
  await mp.click("#audit-btn");
  await mp.waitForSelector("#results:not([hidden]) .finding", { timeout: 60000 });
  const overflow = await mp.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  check(overflow <= 1, `mobile: no horizontal scroll (overflow ${overflow}px)`);
  await mp.locator(".confirm-box").first().scrollIntoViewIfNeeded();
  await shot(mp, "p4-mobile-confirm.png");
  await m.close();

  check(errors.length === 0, `no console errors (${errors.join(" | ")})`);

}

// ---- live AI: properties that must hold whatever the model proposes (never a fixed number of findings)
async function liveAi(browser, base) {
  const h = await health(base);
  check(h.mode === "ai" && h.ai_configured === true, `the server has AI configured (mode ${h.mode}, ai_configured ${h.ai_configured})`);
  if (!h.ai_configured) return "setup";
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: "ar" });
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  await page.goto(base + "/");
  await page.fill("#article", article);
  const [resp] = await Promise.all([page.waitForResponse((r) => r.url().endsWith("/api/audit")), page.click("#audit-btn")]);
  const data = await resp.json();
  const ai = data.ai || {};
  console.log(`INFO  audit status ${resp.status()}, mode ${data.mode}, ai ${JSON.stringify({ outcome: ai.outcome, http_status: ai.http_status, proposed: ai.proposed, located: ai.located, discarded: ai.discarded, added_only: ai.added_only, also_found: ai.also_found, ms: ai.elapsed_ms })}, findings ${data.findings.length}`);
  if (!(resp.ok() && ai.responded && ai.outcome === "ok")) {
    console.log(`INCONCLUSIVE  the model did not answer this audit (outcome ${ai.outcome}, http ${ai.http_status}); none of the AI assertions below were evaluated.`);
    await ctx.close();
    return "inconclusive";
  }
  await page.waitForSelector("#results:not([hidden]) .finding", { timeout: 60000 });
  await shot(page, "ai1-results.png");
  const cps = Array.from(article);
  const fs_ = data.findings;
  const card = (f) => page.locator(`#finding-${f.id}`);

  check(ai.proposed === ai.located + ai.discarded, `AI counters add up (proposed ${ai.proposed} = located ${ai.located} + discarded ${ai.discarded})`);
  check(fs_.every((f) => f.quote === cps.slice(f.start, f.end).join("")), "every finding's quote is exactly the article text at its offsets (nothing invented by the model)");
  check(fs_.every((f) => Array.isArray(f.detected_by) && f.detected_by.length > 0), "every finding says how it was found");
  const only = fs_.filter((f) => f.detected_by.length === 1 && f.detected_by[0] === "ai");
  const also = fs_.filter((f) => f.detected_by.includes("ai") && f.detected_by.length > 1);
  check(only.every((f) => f.detection.ai_role === "only") && also.every((f) => f.detection.ai_role === "also") && fs_.filter((f) => !f.detected_by.includes("ai")).every((f) => f.detection.ai_role == null), "provenance role matches detected_by on every finding");
  check(ai.added_only === only.length && ai.also_found === also.length, `AI counters match the findings (added_only ${ai.added_only} = ${only.length}, also_found ${ai.also_found} = ${also.length})`);
  for (const f of fs_) {
    const chips = (await card(f).locator(".source-meta .chip").allInnerTexts()).join(" | ");
    const role = f.detection.ai_role;
    check(role === "only" ? chips.includes("وحده") : !chips.includes("وحده"), `#${f.id} («${f.quote.slice(0, 24)}…») ${role === "only" ? "is labelled as found by the model alone" : 'never claims "the model alone"'}`);
    if (role === "also") check(chips.includes("المقطع نفسه أيضًا"), `#${f.id} says the model only proposed the same span`);
    if (role == null) check(!chips.includes("الذكاء الاصطناعي"), `#${f.id} makes no AI claim when the model took no part`);
  }
  const weak = fs_.filter((f) => f.detection.unconfirmed);
  for (const f of weak) {
    check(f.changes.length === 0 && f.correction.status === "unconfirmed", `#${f.id} (a possible quotation) offers no automatic correction`);
    check((await card(f).locator(".chip.maybe").count()) === 1 && (await card(f).locator(".chip.ok").count()) === 0 && (await card(f).locator(".change").count()) === 0, `#${f.id} shows the «maybe» chip, no green chip, no change`);
  }
  check((await page.locator("#article-view mark.s-possible").count()) === weak.length, "highlighting: one «possible» mark per possible quotation");
  const tile = page.locator("#summary .tile").filter({ hasText: "قد تكون اقتباسًا" });
  check(weak.length === 0 ? (await tile.count()) === 0 || (await tile.locator(".n").innerText()) === "٠" : (await tile.locator(".n").innerText()) === weak.length.toLocaleString("ar-EG"), `summary counts ${weak.length} possible quotation(s)`);

  // Ordinary prose of the article: if the model proposed it, it must not be presented as an established quotation.
  const prose = fs_.filter((f) => /^كونوا مع الصابرين$/.test(f.quote));
  console.log(`INFO  ordinary prose «كونوا مع الصابرين» ${prose.length ? `was reported (detected_by ${prose[0].detected_by.join("+")}, tier ${prose[0].detection.tier})` : "was not reported"}`);
  check(prose.every((f) => f.detection.unconfirmed && f.changes.length === 0), "ordinary prose is never an established quotation or an automatic correction (absent is also valid)");
  // The deterministic findings are still there with their deterministic tiers; the model can add, not upgrade.
  // (By offsets, not by text: if the model proposes a shorter or longer span the finding's own bounds may differ.)
  const over = (phrase) => { const a = cps.join("").indexOf(phrase); const s0 = Array.from(cps.join("").slice(0, a)).length, e0 = s0 + Array.from(phrase).length; return fs_.filter((f) => f.start < e0 && s0 < f.end); };
  const dist = over("ادعوا ربكم تضرعا وخفية"), appr = over("وبشر المؤمنين الذين إذا أصابتهم مصيبة قالوا إنا لله وإنا إليه راجعون");
  check(dist.length > 0 && dist.every((f) => !f.detection.unconfirmed), "the distinctive exact phrase is still reported, not downgraded to «maybe»");
  check(appr.length > 0 && appr.every((f) => f.detection.unconfirmed && f.changes.length === 0), "the slightly misquoted phrase is still only «maybe» with no change offered, whoever proposed it");

  // A possible quotation can still be confirmed by the editor (no model involved: /api/phrase).
  const target = weak.find((f) => (f.choices || []).length > 0);
  if (target) {
    await card(target).locator(".confirm-box .choice button").first().click();
    await page.waitForFunction((id) => document.querySelectorAll(`#finding-${id} .confirm-box`).length === 0 || !!document.querySelector(".finding .chip.manual"), target.id, { timeout: 20000 });
    check((await page.locator(".finding .chip.manual").count()) >= 1, `confirming the verse of #${target.id} turns it into «حدّدتَ هذا المقطع بنفسك»`);
  } else console.log("INFO  no possible quotation with verse choices to confirm in this audit");
  check(errors.length === 0, `no console errors (${errors.join(" | ")})`);
  await ctx.close();
  return "done";
}

// ---- main
const browser = await chromium.launch();
let isolated = null, code;
try {
  if (liveUrl) {
    const r = await liveAi(browser, liveUrl.replace(/\/$/, ""));
    console.log(`\nlive AI assertions: failures ${failures}${r === "inconclusive" ? " (INCONCLUSIVE: the model did not respond)" : ""}`);
    code = failures ? 1 : r === "inconclusive" ? 2 : 0;
  } else {
    isolated = serverArg ? null : await startIsolatedServer();
    await deterministic(browser, isolated ? isolated.base : serverArg.replace(/\/$/, ""));
    console.log(`\nfailures: ${failures}`);
    code = failures ? 1 : 0;
  }
} finally {
  await browser.close();
  isolated?.stop();
}
process.exit(code);
