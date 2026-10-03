// Browser end-to-end check of the unmarked-phrase workflow (Playwright, Chromium). Two separate parts.
//
//   NODE_PATH=<scratch>/node_modules node scripts/ui_phrase_e2e.mjs [--shots DIR] [--python PATH]
//
// 1) DETERMINISTIC (default). Starts its OWN server with AI switched off (no Groq call possible; a server with AI is refused).
//    An article with (1) an unmarked distinctive quotation, (2) an unmarked slightly misquoted one and (3) a two-word phrase the
//    search does not report. The "possible" one is a question, never a verdict: «هل قصدتَ اقتباس هذه الآية؟» with the suggested
//    verse, and NO replacement text until the writer confirms; «ليس اقتباسًا» dismisses it reversibly (the reply draft, the final
//    check and the marks follow); «آية أخرى» lets the writer name another verse; a phrase the search missed is selected in the
//    article itself and checked; nothing in the article changes except by an approved change.
//      NODE_PATH=... node scripts/ui_phrase_e2e.mjs --server http://localhost:8011   # a server of yours (AI off)
// 2) LIVE AI (opt-in): ONE audit (one Groq call) on a server that has AI configured; checks only properties that must hold
//    whatever the model proposes. Exit 2 = the model did not answer (inconclusive, not a pass).
//      NODE_PATH=... node scripts/ui_phrase_e2e.mjs --live-ai https://quran-quote-auditor.onrender.com
import { chromium, check, norm, opt, testServer, openPage, failures } from "./_ui_common.mjs";

const article = "لا تجزع من الأزمات، والله يقول ادعوا ربكم تضرعا وخفية، وفي مواساة المصابين وبشر المؤمنين الذين إذا أصابتهم مصيبة قالوا إنا لله وإنا إليه راجعون رسالة أمل. وقال لهم كونوا مع الصابرين دائما.";
const POSSIBLE = "هل قصدتَ اقتباس هذه الآية؟";

async function deterministic(browser) {
  const server = await testServer();
  const { page, errors, shot, overflowX, audit } = await openPage(browser, server.base, { width: 1366, height: 900 }, false, "p-desktop");
  await page.goto(server.base);
  await page.evaluate(() => sessionStorage.clear());
  await audit(article);
  const rows = page.locator("#queue li");
  check((await rows.count()) === 2, `two quotations are listed (got ${await rows.count()})`);
  // both wait for the writer: #1 is an exact distinctive phrase whose end is not settled (a comma does not settle it), #2 is only possible
  check(norm(await page.textContent("#panel-progress")).startsWith("اقتباسان ينتظران قرارك"), "two quotations wait for a decision");
  let card = page.locator("#current article");
  check((await card.getAttribute("id")) === "finding-1" && (await card.locator(".ask.bounds").count()) === 1, "the panel starts with the first one in the article (#1: where does it end?)");
  await page.locator("#row-2").click();
  await page.waitForSelector("#current #finding-2");
  card = page.locator("#current article");
  check(norm(await card.locator(".f-head .state").textContent()) === "يحتاج تأكيدك", "its one state word is «يحتاج تأكيدك»");
  check(norm(await card.locator(".q-title").first().textContent()) === POSSIBLE, `it asks «${POSSIBLE}»`);
  check(norm(await card.locator(".choice").first().textContent()).includes("سورة البقرة") && norm(await card.locator(".choice .quran").first().textContent()).includes("المصابين") === false, "it names the likely surah and ayah and shows the verse's words");
  check((await card.locator(".choice a[href*='quranpedia']").count()) === 1, "the verse's source link is on the card");
  const btns = (await card.locator(".ask .actions-row button").allTextContents()).map(norm);
  check(btns.join("|") === "نعم، هذه الآية|آية أخرى|ليس اقتباسًا", `three plain actions (${btns.join(" | ")})`);
  check((await card.locator(".decide").count()) === 0 && (await card.locator(".delta").count()) === 0, "no replacement text before the writer confirms");
  check((await page.locator('#article-view mark[data-id="2"].need').count()) === 1, "the quotation is marked as waiting in the article");
  await shot("1-possible");
  await page.click(".reply-box summary");
  check(!(await page.inputValue("#reply-text")).includes("وبشر المؤمنين"), "the reply draft does not name the unconfirmed phrase");

  // «ليس اقتباسًا»: dismissed, reversible
  await card.locator(".not-quote").click();
  await page.waitForTimeout(600);
  check((await page.locator('#article-view mark[data-id="2"]').count()) === 0, "dismissed: the mark leaves the article");
  check(/استبعدتَ الاقتباس ٢/.test(norm(await page.textContent("#undo-line"))), "the page says what happened, with «تراجع»");
  check((await page.locator("#queue .q-group.off li").count()) === 1, "it is listed under «استبعدتَها»");
  check(norm(await page.textContent("#final-summary")).includes("واستبعدتَ مقطعًا واحدًا ليس اقتباسًا"), "the final check mentions it");
  check((await page.inputValue("#revised-text")) === article, "dismissing changes nothing in the article");
  await page.evaluate(() => window.dispatchEvent(new Event("beforeprint")));
  check(norm(await page.locator("#print-record").innerText()).includes("مقاطع استبعدها المحرر"), "the record lists what the writer dismissed");
  await shot("2-dismissed");
  await page.locator("#undo-line button").click();
  await page.waitForSelector('#current #finding-2');
  check((await page.locator('#article-view mark[data-id="2"]').count()) === 1 && (await page.locator("#queue .q-group.off").count()) === 0, "«تراجع»: the quotation is back, still waiting");
  // dismissing and restoring from the list
  await page.locator(".not-quote").click();
  await page.waitForTimeout(400);
  await page.locator("#queue .q-group.off .row").click();
  await page.waitForSelector("#current #finding-2");
  check(norm(await page.textContent("#undo-line")).includes("أعدتَ الاقتباس ٢"), "the list row of a dismissed item restores it");

  // «آية أخرى»: name a verse by hand
  await page.locator('[data-act="other-verse"]').click();
  check(await page.locator(".verse-form").isVisible(), "«آية أخرى» opens the verse form");
  await page.fill("#vf-a1", "999");
  await page.locator(".verse-form button[type=submit]").click();
  check(/خارج سورة/.test(norm(await page.textContent("#current .card-error"))), "an ayah number outside the surah is refused with a plain message");
  await page.locator('[data-act="other-verse"]').click();
  await page.selectOption("#vf-surah", "2");
  await page.fill("#vf-a1", "156");
  await page.locator(".verse-form button[type=submit]").click();
  await page.waitForFunction(() => document.querySelector("#current .decide, #current .ask.review, #current .okline"), null, { timeout: 30000 });
  check(norm(await page.textContent("#current .where")).includes("١٥٦"), "the check ran against the verse the writer named (البقرة ١٥٦)");
  await page.locator("#undo-line button").click();
  await page.waitForSelector("#current .choice");

  // confirm the suggested verse → only now a proposal appears
  await page.locator('[data-act="confirm-verse"]').click();
  await page.waitForSelector('#current .decide[data-change$="-wording"]', { timeout: 30000 });
  card = page.locator("#current article");
  check(norm(await card.locator(".q-title").first().textContent()).includes("هل تصحّح") || (await card.locator(".delta").count()) === 1, "after confirming, the exact change is shown before its buttons");
  const dd = [norm(await card.locator(".d-before").first().textContent()), norm(await card.locator(".d-after").first().textContent())];
  check(dd[0].includes("المؤمنين") && dd[1].includes("الصابرين"), `the proposal comes from the source: «${dd[0]}» → «${dd[1]}»`);
  check((await page.inputValue("#revised-text")) === article, "nothing changed before approval");
  await card.locator('button[data-act="approved"]').first().click();
  await page.waitForTimeout(500);
  check((await page.inputValue("#revised-text")) === article.replace("وبشر المؤمنين", "وبشر الصابرين"), "revised article = original with ONLY the quoted span corrected");
  await shot("3-confirmed");

  // a phrase the search does not report: selected in the article itself
  const found = await page.evaluate(() => {
    const ta = document.getElementById("article");
    const i = ta.value.indexOf("مع الصابرين");
    if (i < 0) return false;
    ta.focus();
    ta.setSelectionRange(i, i + "مع الصابرين".length);
    return true;
  });
  check(found, "test precondition: the two-word phrase is in the editor");
  await page.waitForSelector("#sel-bar:not([hidden])");
  check(norm(await page.textContent("#sel-text")).includes("مع الصابرين"), "the selection bar shows what was selected");
  await page.click("#phrase-btn");
  await page.waitForFunction(() => document.querySelectorAll("#queue .row").length === 3, null, { timeout: 30000 });
  card = page.locator("#current article");
  check(norm(await card.locator(".q-title").first().textContent()) === "أي آية قصدتَ؟", "a two-word phrase found in several verses asks «أي آية قصدتَ؟»");
  check((await card.locator(".choice").count()) >= 2 && (await card.locator(".decide").count()) === 0, "it lists the verses and proposes nothing yet");
  await shot("4-choices");
  const before = await page.inputValue("#revised-text");
  await card.locator('[data-act="choose-verse"]').first().click();
  await page.waitForFunction(() => document.querySelectorAll("#current .choice").length <= 1 && !document.querySelector('#current [data-act="choose-verse"]'), null, { timeout: 30000 });
  check((await page.inputValue("#revised-text")) === before, "choosing a verse does not change the article");
  check((await page.locator('#current .where a[href*="quranpedia"]').count()) === 1, "after choosing, the source link is shown");

  // the text changed after the audit → the stale note
  await page.fill("#article", article + " ");
  check(await page.locator("#stale-note").isVisible(), "an edit after the audit is flagged");
  await page.reload();
  await page.waitForSelector("#panel:not([hidden]) #current article");
  check((await page.locator("#queue .row").count()) === 3, "the findings (including the one selected by hand) survive a reload");

  // phone
  const m = await openPage(browser, server.base, { width: 390, height: 844 }, true, "p-phone");
  await m.page.goto(server.base);
  await m.audit(article);
  check((await m.overflowX()) <= 1, "phone: no horizontal scroll");
  check(await m.inView("#current .ask .actions-row"), "phone: the three actions are on screen");
  const hs = await m.page.$$eval("#current .ask .actions-row button", (b) => b.map((x) => Math.round(x.getBoundingClientRect().height)));
  check(hs.every((x) => x >= 44), `phone: the actions are at least 44 px high (${hs.join(", ")})`);
  await m.shot("1-possible");
  check(errors.length === 0 && m.errors.length === 0, `no console errors (${[...errors, ...m.errors].join(" | ")})`);
  server.stop();
}

// ---- live AI: properties that must hold whatever the model proposes (never a fixed number of findings)
async function liveAi(browser, base) {
  const health = await (await fetch(base + "/api/health")).json();
  check(health.mode === "ai" && health.ai_configured === true, `the server has AI configured (mode ${health.mode})`);
  if (!health.ai_configured) return "setup";
  const { page, errors, shot, ctx } = await openPage(browser, base, { width: 1366, height: 900 }, false, "ai");
  await page.goto(base);
  await page.fill("#article", article);
  const [resp] = await Promise.all([page.waitForResponse((r) => r.url().endsWith("/api/audit"), { timeout: 120000 }), page.click("#audit-btn")]);
  const data = await resp.json();
  const ai = data.ai || {};
  console.log(`INFO  audit status ${resp.status()}, mode ${data.mode}, ai ${JSON.stringify({ outcome: ai.outcome, http_status: ai.http_status, proposed: ai.proposed, located: ai.located, discarded: ai.discarded, added_only: ai.added_only, also_found: ai.also_found, ms: ai.elapsed_ms })}, findings ${data.findings.length}`);
  if (!(resp.ok() && ai.responded && ai.outcome === "ok")) {
    console.log(`INCONCLUSIVE  the model did not answer this audit (outcome ${ai.outcome}, http ${ai.http_status}); none of the AI assertions below were evaluated.`);
    await ctx.close();
    return "inconclusive";
  }
  await page.waitForSelector("#panel:not([hidden]) #current article", { timeout: 60000 });
  await shot("1-results");
  const cps = Array.from(article);
  const fs_ = data.findings;
  check(ai.proposed === ai.located + ai.discarded, `AI counters add up (proposed ${ai.proposed} = located ${ai.located} + discarded ${ai.discarded})`);
  check(fs_.every((f) => f.quote === cps.slice(f.start, f.end).join("")), "every finding's quote is exactly the article text at its offsets (nothing invented by the model)");
  const only = fs_.filter((f) => f.detected_by.length === 1 && f.detected_by[0] === "ai");
  const also = fs_.filter((f) => f.detected_by.includes("ai") && f.detected_by.length > 1);
  check(only.every((f) => f.detection.ai_role === "only") && also.every((f) => f.detection.ai_role === "also") && fs_.filter((f) => !f.detected_by.includes("ai")).every((f) => f.detection.ai_role == null), "provenance role matches detected_by on every finding");
  check(ai.added_only === only.length && ai.also_found === also.length, `AI counters match the findings (added_only ${ai.added_only} = ${only.length}, also_found ${ai.also_found} = ${also.length})`);
  for (const f of fs_) {
    await page.locator(`#row-${f.id}`).click();
    await page.waitForSelector(`#finding-${f.id}`);
    await page.locator(`#finding-${f.id} details.f-all > summary`).click();
    const how = norm(await page.locator(`#finding-${f.id} .f-detail`).textContent());
    const role = f.detection.ai_role;
    check(role === "only" ? how.includes("اقترحه الذكاء الاصطناعي وحده") : !how.includes("وحده"), `#${f.id} ${role === "only" ? "is labelled as found by the model alone" : 'never claims "the model alone"'}`);
    if (role === "also") check(how.includes("المقطع نفسه أيضًا"), `#${f.id} says the model only proposed the same span`);
    if (role == null) check(!how.includes("الذكاء الاصطناعي"), `#${f.id} makes no AI claim when the model took no part`);
  }
  const weak = fs_.filter((f) => f.detection.unconfirmed);
  for (const f of weak) {
    check(f.changes.length === 0 && f.correction.status === "unconfirmed", `#${f.id} (a possible quotation) offers no automatic correction`);
    await page.locator(`#row-${f.id}`).click();
    check((await page.locator(`#finding-${f.id} .decide`).count()) === 0 && (await page.locator(`#finding-${f.id} .state.done`).count()) === 0, `#${f.id} shows a question, no change and no «done» state`);
  }
  const prose = fs_.filter((f) => /^كونوا مع الصابرين$/.test(f.quote));
  console.log(`INFO  ordinary prose «كونوا مع الصابرين» ${prose.length ? `was reported (detected_by ${prose[0].detected_by.join("+")}, tier ${prose[0].detection.tier})` : "was not reported"}`);
  check(prose.every((f) => f.detection.unconfirmed && f.changes.length === 0), "ordinary prose is never an established quotation or an automatic correction (absent is also valid)");
  const over = (phrase) => { const a = cps.join("").indexOf(phrase); const s0 = Array.from(cps.join("").slice(0, a)).length, e0 = s0 + Array.from(phrase).length; return fs_.filter((f) => f.start < e0 && s0 < f.end); };
  const dist = over("ادعوا ربكم تضرعا وخفية"), appr = over("وبشر المؤمنين الذين إذا أصابتهم مصيبة قالوا إنا لله وإنا إليه راجعون");
  check(dist.length > 0 && dist.every((f) => !f.detection.unconfirmed), "the distinctive exact phrase is still reported, not downgraded to «maybe»");
  check(appr.length > 0 && appr.every((f) => f.detection.unconfirmed && f.changes.length === 0), "the slightly misquoted phrase is still only «maybe» with no change offered, whoever proposed it");
  check(errors.length === 0, `no console errors (${errors.join(" | ")})`);
  await ctx.close();
  return "done";
}

const browser = await chromium.launch();
let code;
try {
  const liveUrl = opt("--live-ai");
  if (liveUrl) {
    const r = await liveAi(browser, liveUrl.replace(/\/$/, ""));
    console.log(`\nlive AI assertions: failures ${failures}${r === "inconclusive" ? " (INCONCLUSIVE: the model did not respond)" : ""}`);
    code = failures ? 1 : r === "inconclusive" ? 2 : 0;
  } else {
    await deterministic(browser);
    console.log(failures ? `\nfailures: ${failures}` : "\nall checks passed");
    code = failures ? 1 : 0;
  }
} finally {
  await browser.close();
}
process.exit(code);
