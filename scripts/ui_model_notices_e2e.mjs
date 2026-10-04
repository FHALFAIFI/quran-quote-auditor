// What the page says about the language model, in each state (4 Oct). The server has NO model configured (no Groq call is possible). The states
// that need a configured model are SIMULATED by rewriting /api/health and /api/audit answers in the browser: they test the page's wording and
// layout only and prove nothing about a live model call. Every simulated check is printed with «SIMULATED».
//   NODE_PATH=<scratch>/node_modules node scripts/ui_model_notices_e2e.mjs [--shots DIR] [--server URL] [--python PATH]
import { chromium, check, norm, readSample, testServer, openPage, finish } from "./_ui_common.mjs";

const server = await testServer();
const browser = await chromium.launch();
const demo = readSample("sample-demo");
const long = (demo + "\n\n").repeat(Math.ceil(6400 / demo.length)).trim();   // over the model's 6,000-character limit, well under 20,000

const HEALTH = { mode: "ai", ai_configured: true, provider: "Groq (qwen/qwen3.8-27b)", ai_last_call: { outcome: "never_called", cooldown_seconds: 0 } };
const AI = { configured: true, provider: "groq", model: "qwen/qwen3.8-27b" };
const FAILED_NOTE = "تعذّر الاستخراج بالذكاء الاصطناعي في هذا التدقيق. عُرضت الاقتباسات المعلَّمة صراحةً والعبارات المطابقة لنص المصحف فقط؛ وقد تفوت الاقتباسات القصيرة غير المعلَّمة.";
// app/audit.py's own wording for an audit inside the cooldown that follows a failure (4 Oct): no request, mode "reduced"
const COOLDOWN_NOTE = (n) => `لم يُسأل الذكاء الاصطناعي في هذا التدقيق لأن استدعاءً سابقًا له تعذّر قبل قليل، ويُسأل من جديد بعد نحو ${n} ث؛ فُحص المقال كاملًا بالعلامات وبالبحث في نص المصحف.`;
const SIM = {
  timeout: (j) => { j.mode = "ai_failed"; j.provider = HEALTH.provider; j.ai = { ...j.ai, ...AI, responded: false, outcome: "failed", error: "انتهت مهلة خدمة الذكاء الاصطناعي", http_status: null, elapsed_ms: 12004 };
    j.notices = [{ level: "warning", text: FAILED_NOTE }, ...j.notices]; },
  cooldown: (j) => { j.mode = "reduced"; j.provider = null; j.provider_model = null; j.ai = { ...j.ai, ...AI, responded: false, outcome: "skipped_cooldown", http_status: null, elapsed_ms: null, error: null, cooldown_seconds: 117 };
    j.notices = [{ level: "info", text: COOLDOWN_NOTE(117) }, ...j.notices]; },
  over: (j) => { j.ai = { ...j.ai, ...AI, outcome: "skipped_length", responded: false };
    j.notices = [{ level: "info", text: "لم يُستخدم الذكاء الاصطناعي لأن المقال أطول من 6000 حرف؛ فُحص المقال كاملًا بالعلامات وبالبحث في نص المصحف." }, ...j.notices]; },   // the server's own wording (app/audit.py)
  failed: (j) => { j.mode = "ai_failed"; j.provider = HEALTH.provider; j.ai = { ...j.ai, ...AI, responded: false, outcome: "failed", error: "HTTP 429", http_status: 429, elapsed_ms: 230 };
    j.notices = [{ level: "warning", text: FAILED_NOTE }, ...j.notices]; },
  answered: (j) => { j.mode = "ai"; j.provider = HEALTH.provider; j.provider_model = AI.model; j.ai = { ...j.ai, ...AI, responded: true, outcome: "ok", elapsed_ms: 900, proposed: 2, located: 2, discarded: 0, added_only: 0, also_found: 2, overlapped: 0 }; },
  nothing: (j) => { j.mode = "ai"; j.provider = HEALTH.provider; j.provider_model = AI.model; j.ai = { ...j.ai, ...AI, responded: true, outcome: "ok", elapsed_ms: 700, proposed: 0, located: 0, discarded: 0, added_only: 0, also_found: 0, overlapped: 0 }; },
};

async function open(vp, mobile, sim) {
  const o = await openPage(browser, server.base, vp, mobile, `MN-${vp.width}-${sim || "none"}`);
  if (sim) {
    await o.page.route("**/api/health", async (r) => { const res = await r.fetch(); r.fulfill({ response: res, json: { ...(await res.json()), ...HEALTH } }); });
    await o.page.route("**/api/audit", async (r) => { const res = await r.fetch(); const j = await res.json(); if (res.ok) SIM[sim](j); r.fulfill({ response: res, json: j }); });
  }
  await o.page.goto(server.base);
  await o.page.evaluate(() => { sessionStorage.clear(); localStorage.clear(); });
  await o.page.reload();
  await o.page.waitForSelector("#article");
  await o.page.waitForTimeout(400);
  return o;
}
const meta = (page) => page.evaluate(() => {
  const m = document.querySelector("#notices .audit-meta");
  if (!m) return null;
  const d = m.querySelector("details");
  return { cls: m.className, line: m.querySelector(".am-line")?.textContent || "", lineVisible: !!m.querySelector(".am-line")?.checkVisibility(),
    detailsOpen: !!d?.open, detailsText: d?.textContent || "", errors: document.querySelectorAll("#notices .notice.error").length,
    visible: [...m.querySelectorAll("p")].filter((p) => p.checkVisibility()).map((p) => p.textContent).join(" ") };
});
const record = async (page) => { await page.evaluate(() => window.dispatchEvent(new Event("beforeprint"))); return norm(await page.locator("#print-record").innerText()); };

for (const [name, vp, mobile] of [["desktop", { width: 1366, height: 900 }, false], ["phone", { width: 390, height: 844 }, true]]) {
  console.log(`\n== ${name}: no model on this server (real server answer)`);
  let { page, errors, audit, shot } = await open(vp, mobile, null);
  const send = norm(await page.textContent("#send-note"));
  check(/لا نموذج لغوي مهيّأ على هذا الخادم، فلا يُرسَل مقالك عند التدقيق إلى جهة خارجية، ولا يُحفظ على خادمنا/.test(send), `before sending, the page says nothing goes to a third party («${send.slice(0, 50)}…»)`);
  check((await page.locator('#editor-hint a[href="/privacy"]').count()) === 1, "the privacy details are linked beside the editor, before any audit");
  await audit(demo);
  let m = await meta(page);
  check(m && /limited/.test(m.cls) && m.lineVisible && /^دون ذكاء اصطناعي: قد تفوت عبارة قصيرة بلا علامات؛ حدّدها في المقال لتفحصها\.$/.test(m.line), `after the audit, one calm visible line names the limit («${m?.line}»)`);
  check(m && m.errors === 0 && !/استجاب|اقترح نموذج/.test(m.visible), "no error styling, and nothing says a model answered");
  check(/لم يُستخدم الذكاء الاصطناعي \(وضع مخفّض\)/.test(await record(page)), "the printed record says the model was not used");
  check(errors.length === 0, `no console errors ${errors.join(" | ")}`);
  await shot("unconfigured");
  await page.context().close();

  console.log(`\n== ${name}: SIMULATED configured model, article over its limit`);
  ({ page, errors, audit, shot } = await open(vp, mobile, "over"));
  check(/عند التدقيق يُرسَل المقال إلى Groq إن كان النموذج متاحًا والمقال لا يتجاوز ٦٬٠٠٠ حرف/.test(norm(await page.textContent("#send-note"))), "SIMULATED: before sending, the page names Groq and the 6,000-character limit");
  await page.fill("#article", long);
  await page.waitForTimeout(200);
  const pre = norm(await page.textContent("#ai-limit-note"));
  check(await page.isVisible("#ai-limit-note") && pre === "أطول من ٦٬٠٠٠ حرف: يُدقَّق كاملًا دون النموذج اللغوي", `SIMULATED: before the audit, a long article is told it goes without the model («${pre}»)`);
  await page.click("#audit-btn");
  await page.waitForSelector("#panel:not([hidden]) #current article", { timeout: 60000 });
  await page.waitForTimeout(600);
  m = await meta(page);
  check(m && m.lineVisible && /^المقال أطول من ٦٬٠٠٠ حرف، فلم يُسأل النموذج اللغوي\. فُحص كله بالعلامات وبالبحث في المصحف/.test(m.line), `SIMULATED: after it, the line says why the model was not asked («${m?.line.slice(0, 50)}…»)`);
  check(m && !/استجاب|اقترح نموذج/.test(m.visible) && m.errors === 0, "SIMULATED: nothing says the model answered; no error styling");
  check(m && !/٦٠٠٠|6000/.test(m.detailsText + m.visible) && (m.detailsText.match(/أطول من/g) || []).length === 0, "SIMULATED: the server's own over-limit notice is not repeated in the details (nor its ungrouped «٦٠٠٠»)");
  check(/لم يُستدعَ النموذج لأن المقال أطول من ٦٬٠٠٠ حرف/.test(await record(page)), "SIMULATED: the record says the model was not called, and why");
  check(errors.length === 0, `no console errors ${errors.join(" | ")}`);
  await shot("over-limit");
  await page.context().close();

  console.log(`\n== ${name}: SIMULATED configured model that failed (HTTP 429)`);
  ({ page, errors, audit, shot } = await open(vp, mobile, "failed"));
  await audit(demo);
  m = await meta(page);
  check(m && m.lineVisible && /^تعذّر اقتراح الذكاء الاصطناعي هذه المرة\. فُحص المقال بالعلامات وبالبحث في المصحف، وقد تفوت عبارة قصيرة بلا علامات؛ حدّدها في المقال لتفحصها، أو أعد التدقيق لاحقًا\.$/.test(m.line), `SIMULATED: one calm line: the source-based result stands, try again later («${m?.line.slice(0, 40)}…»)`);
  check(m && !m.detailsOpen && /سبب التعذّر: HTTP 429/.test(m.detailsText) && !/HTTP 429/.test(m.visible), "SIMULATED: the HTTP status is behind «تفاصيل هذا التدقيق», not on the page");
  check(m && m.errors === 0 && (await page.locator("#notices .notice").count()) === 0, "SIMULATED: no red error and the server's warning is not repeated as a second banner");
  check(m && !/استجاب|اقترح نموذج/.test(m.visible + m.detailsText), "SIMULATED: nowhere does it say the model answered");
  check((await page.locator("#queue li").count()) === 4 && (await page.locator("#current article").count()) === 1, "SIMULATED: the source-based review is complete and usable");
  check(/لا — كان .* مُعَدًّا لكنه لم يستجب في هذا التدقيق \(HTTP 429\)/.test(await record(page)), "SIMULATED: the record says «no», with the reason");
  check(errors.length === 0, `no console errors ${errors.join(" | ")}`);
  await shot("failed");
  await page.context().close();

  console.log(`\n== ${name}: SIMULATED configured model that timed out`);
  ({ page, errors, audit, shot } = await open(vp, mobile, "timeout"));
  await audit(demo);
  m = await meta(page);
  check(m && m.lineVisible && /^تعذّر اقتراح الذكاء الاصطناعي هذه المرة\. فُحص المقال بالعلامات وبالبحث في المصحف/.test(m.line), `SIMULATED: a timeout gets the same calm failure line («${m?.line.slice(0, 40)}…»)`);
  check(m && !m.detailsOpen && /سبب التعذّر: انتهت مهلة خدمة الذكاء الاصطناعي/.test(m.detailsText) && m.errors === 0, "SIMULATED: the reason (timeout) is behind the details; no red error");
  check((await page.locator("#queue li").count()) === 4, "SIMULATED: the source-based review is complete");
  check(/لا — كان .* مُعَدًّا لكنه لم يستجب في هذا التدقيق \(انتهت مهلة/.test(await record(page)), "SIMULATED: the record says «no», with the timeout");
  check(errors.length === 0, `no console errors ${errors.join(" | ")}`);
  await page.context().close();

  console.log(`\n== ${name}: SIMULATED model skipped during the cooldown after a failure (no request in this audit)`);
  ({ page, errors, audit, shot } = await open(vp, mobile, "cooldown"));
  await audit(demo);
  m = await meta(page);
  check(m && /limited/.test(m.cls) && m.lineVisible && m.line === "لم يُسأل النموذج اللغوي هذه المرة لأنه تعذّر قبل قليل. فُحص المقال بالعلامات وبالبحث في المصحف، وقد تفوت عبارة قصيرة بلا علامات؛ حدّدها في المقال لتفحصها.", `SIMULATED: one calm line says the model was not asked, and why («${m?.line.slice(0, 45)}…»)`);
  check(m && !/^تعذّر اقتراح/.test(m.line) && !/سبب التعذّر|HTTP|429/.test(m.detailsText + m.visible), "SIMULATED: it does not claim this audit failed, and shows no status code of the earlier call");
  check(m && !m.detailsOpen && /يُسأل النموذج من جديد بعد نحو ١١٧ ث/.test(m.detailsText) && (m.detailsText.match(/لم يُسأل الذكاء الاصطناعي/g) || []).length === 0, "SIMULATED: the wait is behind the details, and the server's notice is not repeated there");
  check(m && m.errors === 0 && (await page.locator("#notices .notice").count()) === 0 && !/استجاب|اقترح نموذج/.test(m.visible + m.detailsText), "SIMULATED: no red error, no second banner, nothing says a model answered");
  check((await page.locator("#queue li").count()) === 4 && (await page.locator("#current article").count()) === 1, "SIMULATED: the source-based review is complete and usable");
  check(/لا — لم يُسأل groq في هذا التدقيق لأن استدعاءً سابقًا له تعذّر قبل قليل/.test(await record(page)), "SIMULATED: the printed record says the model was not asked, and why");
  const visibleLen = norm(await page.evaluate(() => document.getElementById("notices").innerText)).length;   // what is rendered, as live_smoke.mjs counts it
  check(visibleLen <= 200, `SIMULATED: the notice region stays bounded like the failure line (${visibleLen} characters)`);
  check(errors.length === 0, `no console errors ${errors.join(" | ")}`);
  await shot("cooldown");
  await page.context().close();

  console.log(`\n== ${name}: SIMULATED configured model that answered`);
  ({ page, errors, audit, shot } = await open(vp, mobile, "answered"));
  await audit(demo);
  m = await meta(page);
  check(m && !/limited/.test(m.cls) && !m.detailsOpen && /اقترح نموذج ذكاء اصطناعي مواضع الاقتباس فقط، والحكم على كل اقتباس من نص قرآنبيديا وحده/.test(m.detailsText), "SIMULATED: what the model did is one click away, and says it only proposed places");
  check(m && /اقترح مقطعين، وُجد منها في المقال ٢/.test(m.detailsText) && /ومن النتائج 0 لم يجدها غير النموذج|ومن النتائج ٠ لم يجدها غير النموذج/.test(m.detailsText), "SIMULATED: the details say how many it proposed and that it added none");
  check(/نعم — استجاب النموذج qwen\/qwen3\.8-27b/.test(await record(page)), "SIMULATED: the record says the model answered (in this simulation)");
  check(errors.length === 0, `no console errors ${errors.join(" | ")}`);
  await shot("answered");
  await page.context().close();

  console.log(`\n== ${name}: SIMULATED configured model that answered with nothing`);
  ({ page, errors, audit } = await open(vp, mobile, "nothing"));
  await audit(demo);
  m = await meta(page);
  check(m && /ولم يقترح هذه المرة أي مقطع/.test(m.detailsText) && /لم يقترح أي مقطع، فاعتمد الرصد على العلامات والبحث الآلي في المصحف/.test(m.detailsText), "SIMULATED: an empty answer is said as such, and the detection rests on the source search");
  check(errors.length === 0, `no console errors ${errors.join(" | ")}`);
  await page.context().close();
}
finish(server, browser);
