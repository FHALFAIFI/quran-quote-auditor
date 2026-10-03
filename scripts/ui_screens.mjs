// Screenshots of every state a writer meets, at 1366, 390 and 320 px, for a before/after comparison of the interface.
// It checks nothing; it only photographs. A server of its own with the model off (no Groq call is possible). The three states that
// need a configured model (it failed, the article is over its limit, it answered) are SIMULATED by rewriting the audit answer in the
// browser, the same way ui_long_e2e.mjs tests them: the file names start with «sim-» so a picture is never mistaken for a live call.
//   NODE_PATH=<scratch>/node_modules node scripts/ui_screens.mjs --shots DIR [--server URL] [--python PATH]
import fs from "fs";
import path from "path";
import { chromium, root, shots, testServer } from "./_ui_common.mjs";

if (!shots) { console.log("usage: node scripts/ui_screens.mjs --shots DIR"); process.exit(2); }
const VPS = [["1366", { width: 1366, height: 860 }, false], ["390", { width: 390, height: 844 }, true], ["320", { width: 320, height: 640 }, true]];
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const longCase = JSON.parse(fs.readFileSync(path.join(root, "eval/articles_long_20261003.json"), "utf8")).cases[0].article;
const PHRASE = "لا تجزع من الأزمات، والله يقول ادعوا ربكم تضرعا وخفية، وفي مواساة المصابين وبشر المؤمنين الذين إذا أصابتهم مصيبة قالوا إنا لله وإنا إليه راجعون رسالة أمل. وقال لهم كونوا مع الصابرين دائما.";
const FAILED_NOTE = "تعذّر الاستخراج بالذكاء الاصطناعي في هذا التدقيق. عُرضت الاقتباسات المعلَّمة صراحةً والعبارات المطابقة لنص المصحف فقط؛ وقد تفوت الاقتباسات القصيرة غير المعلَّمة.";
const SIM = {
  failed: (j) => { j.mode = "ai_failed"; j.provider = "Groq (qwen/qwen3.8-27b)"; j.ai = { ...j.ai, configured: true, provider: "groq", model: "qwen/qwen3.8-27b", responded: false, outcome: "failed", error: "HTTP 429", http_status: 429, elapsed_ms: 240 }; j.notices = [{ level: "warning", text: FAILED_NOTE }, ...j.notices]; },
  length: (j) => { j.ai = { ...j.ai, configured: true, provider: "groq", model: "qwen/qwen3.8-27b", outcome: "skipped_length" }; j.notices = [{ level: "info", text: "لم يُستخدم الذكاء الاصطناعي لأن المقال أطول من 6000 حرف؛ فُحص المقال كاملًا بالعلامات وبالبحث في نص المصحف." }, ...j.notices]; },
  ok: (j) => { j.mode = "ai"; j.provider = "Groq (qwen/qwen3.8-27b)"; j.provider_model = "qwen/qwen3.8-27b"; j.ai = { ...j.ai, configured: true, provider: "groq", model: "qwen/qwen3.8-27b", responded: true, outcome: "ok", elapsed_ms: 900, proposed: 2, located: 2, discarded: 0, added_only: 0, also_found: 2, overlapped: 0 }; },
};
const SIM_HEALTH = { mode: "ai", ai_configured: true, provider: "Groq (qwen/qwen3.8-27b)", ai_last_call: { outcome: "failed", detail: "429", http_status: 429, cooldown_seconds: 0 } };

const server = await testServer();
const browser = await chromium.launch();

async function open(vp, mobile, sim) {
  const ctx = await browser.newContext({ viewport: vp, deviceScaleFactor: 1, locale: "ar", isMobile: mobile, hasTouch: mobile });
  const page = await ctx.newPage();
  if (sim) {
    await page.route("**/api/health", async (r) => { const res = await r.fetch(); r.fulfill({ response: res, json: { ...(await res.json()), ...SIM_HEALTH } }); });
    await page.route("**/api/audit", async (r) => { const res = await r.fetch(); const j = await res.json(); if (res.ok) SIM[sim](j); r.fulfill({ response: res, json: j }); });
  }
  await page.goto(server.base + "/");
  await page.evaluate(() => { sessionStorage.clear(); localStorage.clear(); });
  await page.reload();
  await page.waitForSelector("#article");
  await page.evaluate(() => document.fonts.ready);
  await sleep(500);
  return { ctx, page };
}
const waitCard = (page) => page.waitForSelector("#panel:not([hidden]) #current article", { timeout: 120000 }).then(() => sleep(1200));
const audit = async (page, text) => { await page.fill("#article", text); await page.click("#audit-btn"); await waitCard(page); };

for (const [tag, vp, mobile] of VPS) {
  const out = (n) => path.join(shots, `${tag}-${n}.png`);
  let { ctx, page } = await open(vp, mobile);
  await page.screenshot({ path: out("01-empty") });
  await page.screenshot({ path: out("01-empty-full"), fullPage: true });
  await page.click("#article");
  await page.keyboard.type("قال تعالى: وما خلقت الجن والإنس إلا", { delay: 5 });
  await page.waitForSelector("#suggest:not([hidden]) .sg-item", { timeout: 60000 }).catch(() => {});
  await sleep(500);
  await page.screenshot({ path: out("02-suggest") });
  await ctx.close();

  // 4 Oct: the first piece of a verse says where it stops; after accepting it the next piece is offered
  ({ ctx, page } = await open(vp, mobile));
  await page.click("#article");
  await page.keyboard.type("قال تعالى: إن الله يأمركم أن تؤدوا الأمانات", { delay: 5 });
  await page.waitForSelector("#suggest:not([hidden]) .sg-item", { timeout: 60000 }).catch(() => {});
  await sleep(500);
  await page.screenshot({ path: out("02b-suggest-piece") });
  if (mobile) await page.locator("#suggest .sg-accept").first().tap(); else await page.keyboard.press("Tab");
  await page.waitForSelector("#suggest:not([hidden]) .sg-item", { timeout: 60000 }).catch(() => {});
  await sleep(500);
  await page.screenshot({ path: out("02c-next-piece") });
  await ctx.close();

  ({ ctx, page } = await open(vp, mobile));
  await page.click("#demo-btn");
  await waitCard(page);
  await page.screenshot({ path: out("03-first-correction") });
  await page.screenshot({ path: out("03-first-correction-full"), fullPage: true });
  await page.click('[data-change="3-wording"] button[data-act="approved"]');
  await page.waitForSelector('[data-change="4-reference"]', { timeout: 15000 });
  await sleep(900);
  await page.screenshot({ path: out("05-last-decision") });
  // the approved correction drawn in the box (4 Oct)
  await page.evaluate(() => document.querySelector("#article-view .fix")?.scrollIntoView({ block: "center" }));
  await sleep(500);
  await page.screenshot({ path: out("05b-approved-in-box") });
  await page.click('[data-change="4-reference"] button[data-act="approved"]');
  await sleep(900);
  await page.evaluate(() => document.getElementById("final").scrollIntoView({ block: "start" }));
  await sleep(600);
  await page.screenshot({ path: out("06-final") });
  await ctx.close();

  ({ ctx, page } = await open(vp, mobile));
  await audit(page, PHRASE);
  await page.evaluate(() => { const d = document.getElementById("row-2")?.closest("details"); if (d) d.open = true; });
  await page.locator("#row-2").click();
  await sleep(900);
  await page.screenshot({ path: out("04-uncertain") });
  await ctx.close();

  for (const sim of ["failed", "length", "ok"]) {
    ({ ctx, page } = await open(vp, mobile, sim));
    await audit(page, sim === "length" ? longCase : await (await fetch(server.base + "/static/samples/sample-demo.txt")).text());
    await page.evaluate(() => scrollTo(0, 0));
    await sleep(400);
    await page.screenshot({ path: out(`sim-${sim === "length" ? "07-long-over-ai-limit" : sim === "failed" ? "08-ai-failed" : "09-ai-answered"}`) });
    if (sim === "length") { await waitCard(page); await page.screenshot({ path: out("sim-07-long-at-first-card"), fullPage: false }); }
    await ctx.close();
  }

  // a long article opened on its first concrete decision, and its phrases to confirm (4 Oct; no simulation)
  ({ ctx, page } = await open(vp, mobile));
  await audit(page, longCase);
  await page.screenshot({ path: out("11-long-first-card") });
  await page.evaluate(() => { const g = document.querySelector("#queue .q-group.maybe"); if (g) { g.open = true; g.scrollIntoView({ block: "center" }); } });
  await sleep(500);
  await page.screenshot({ path: out("12-long-phrases-to-confirm") });
  await ctx.close();

  // an edit inside the approved quotation: the mark and the decision fall, the quotation is stale (4 Oct)
  ({ ctx, page } = await open(vp, mobile));
  await audit(page, await (await fetch(server.base + "/static/samples/sample-demo.txt")).text());
  await page.click('[data-change="3-wording"] button[data-act="approved"]');
  await sleep(700);
  await page.evaluate(() => { const ta = document.getElementById("article"); const i = ta.value.indexOf("الصابرون") + 3; ta.focus(); ta.setSelectionRange(i, i); });
  await page.keyboard.type("ـ");
  await sleep(600);
  await page.evaluate(() => document.querySelector("#article-view mark.stale")?.scrollIntoView({ block: "center" }));
  await sleep(400);
  await page.screenshot({ path: out("13-edited-after-approval") });
  await ctx.close();

  for (const doc of ["sources", "privacy", "limitations"]) {
    ({ ctx, page } = await open(vp, mobile));
    await page.goto(`${server.base}/${doc}`);
    await page.evaluate(() => document.fonts.ready);
    await sleep(300);
    await page.screenshot({ path: out(`10-${doc}`) });
    await ctx.close();
  }
  console.log(`done ${tag}`);
}
await browser.close();
server.stop();
