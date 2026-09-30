// Browser end-to-end check of the unmarked-phrase workflow (Playwright, Chromium).
//
//   npm i playwright            # in any scratch directory; not a project dependency
//   AI_PROVIDER=none uvicorn app.main:app --port 8011      # no Groq calls; needs the Quran text (live or cached)
//   NODE_PATH=<scratch>/node_modules node scripts/ui_phrase_e2e.mjs http://localhost:8011 [screenshot-dir]
//
// Flow: an article with (1) an unmarked distinctive quotation, (2) an unmarked slightly misquoted one and
// (3) a two-word phrase the search does not report → audit → the candidate and the "maybe" are labelled
// differently; the "maybe" offers no replacement text → confirm its verse → only then a proposal appears →
// approve it → the revised article differs from the original ONLY in the quoted span → highlight the
// two-word phrase by hand, choose its verse → check the reply draft never names an unconfirmed phrase.
import { createRequire } from "module";
import fs from "fs";
import path from "path";

const require = createRequire(import.meta.url);
const { chromium } = require("playwright");
const base = (process.argv[2] || "http://localhost:8011").replace(/\/$/, "");
const shots = process.argv[3] || null;
if (shots) fs.mkdirSync(shots, { recursive: true });

let failures = 0;
const check = (cond, msg) => { console.log(`${cond ? "PASS" : "FAIL"}  ${msg}`); if (!cond) failures++; };
const shot = async (page, name, opts = {}) => { if (shots) await page.screenshot({ path: path.join(shots, name), ...opts }); };

const MAYBE = "قد يكون اقتباسًا قرآنيًا — يحتاج مراجعة";
const article = "لا تجزع من الأزمات، والله يقول ادعوا ربكم تضرعا وخفية، وفي مواساة المصابين وبشر المؤمنين الذين إذا أصابتهم مصيبة قالوا إنا لله وإنا إليه راجعون رسالة أمل. وقال لهم كونوا مع الصابرين دائما.";

const browser = await chromium.launch();
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
await browser.close();
console.log(`\nfailures: ${failures}`);
process.exit(failures ? 1 : 0);
