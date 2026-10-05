// The pilot writer's whole journey, at 1366, 390 and 320 px, on its own AI-off server (no Groq call is possible):
// empty page → demonstration article; a typed text survives a reload before any audit; a verse suggestion; TXT and DOCX import;
// an audit of a synthetic article with a correct verse, a wrong word, an omitted word, a wrong reference, an unmarked quotation and
// ordinary prose; approve, reject, undo; an edit after the audit survives a reload; recheck keeps the decisions; final review; the
// copied text is exactly the writer's text plus the approved source corrections; the writer's text in the editor is never changed;
// the trust pages and the «report a problem» link; sideways scroll, decision-button size and names, CSP and other hosts.
//
// Every verse used here is in tests/fixtures/hafs_subset.json, so the suite gives the same answers on a server that loaded only
// that 36-verse excerpt (CI: scripts/ci_fixture_cache.py) as on one with the whole Quranpedia text.
//   NODE_PATH=<scratch>/node_modules node scripts/ui_pilot_journey_e2e.mjs [--server URL] [--shots DIR]
import { chromium, check, norm, testServer, openPage, openRow, VIEWPORTS, finish } from "./_ui_common.mjs";
import { docx, docXml } from "../tests/fixtures/import/fixtures.mjs";

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
// what the copy must hold once the three source corrections are approved (and nothing else changed)
const revised = (t) => t.replace("ولا تختلفوا فتفشلوا", "ولا تنازعوا فتفشلوا").replace("بحبل الله ولا تفرقوا", "بحبل الله جميعا ولا تفرقوا").replace("[الإخلاص: 2]", "[الإخلاص: 1]");
const REPORT = "https://github.com/FHALFAIFI/quran-quote-auditor/issues/new?template=pilot_report.yml";

const docxBytes = Buffer.from(docx(docXml(ARTICLE.split("\n").map((p) => `<w:p><w:pPr><w:bidi/></w:pPr><w:r><w:rPr><w:rtl/></w:rPr><w:t xml:space="preserve">${p}</w:t></w:r></w:p>`).join(""))));
const FILES = [
  { name: "pilot.txt", mimeType: "text/plain", buffer: Buffer.from(ARTICLE, "utf8") },
  { name: "pilot.docx", mimeType: "application/vnd.openxmlformats-officedocument.wordprocessingml.document", buffer: docxBytes },
];

const server = await testServer();
const browser = await chromium.launch();
const copyNow = async (page) => {
  await page.evaluate(() => navigator.clipboard.writeText(""));
  await page.click("#copy-btn");
  await page.waitForTimeout(200);
  return page.evaluate(() => navigator.clipboard.readText());
};
// the caret is put at the end by the page itself (a phone has no Ctrl+End), then the text is typed as keystrokes
const typeAtEnd = async (page, text) => {
  await page.locator("#article").focus();
  await page.evaluate(() => { const t = document.querySelector("#article"); t.setSelectionRange(t.value.length, t.value.length); });
  await page.keyboard.type(text, { delay: 5 });
  await page.waitForTimeout(450);  // the tab's session copy is written 250 ms after the last keystroke
};

for (const [name, viewport, mobile] of VIEWPORTS) {
  const { ctx, page, errors, shot, overflowX, audit } = await openPage(browser, server.base, viewport, mobile, `PILOT-${name}`);
  page.setDefaultTimeout(30000);
  const tag = `${name}`;
  await page.goto(server.base + "/");

  // 1. empty page → demonstration article
  check(await page.inputValue("#article") === "" && await page.locator("#demo-btn").isVisible(), `${tag}: the first screen is empty and offers the demonstration article`);
  await page.waitForFunction(() => /لا نموذج لغوي/.test(document.querySelector("#send-note").textContent));
  check(/لا يُرسَل مقالك عند التدقيق إلى جهة خارجية/.test(norm(await page.locator("#send-note").innerText())), `${tag}: beside the editor, the page says this server sends the article to no model`);
  await page.click("#demo-btn");
  await page.waitForSelector("#panel:not([hidden]) #current article", { timeout: 60000 });
  check(/مقال تجريبي/.test(norm(await page.locator("#verdict").innerText())), `${tag}: the demonstration verdict says its mistakes are deliberate`);
  check(await overflowX() <= 0, `${tag}: no sideways scroll after the demonstration audit`);
  await shot("demo");

  // 2. a text typed and not audited survives a reload (regression: it was lost); «مسح» is respected
  await page.click("#clear-btn");
  const typed = "مسودة كتبتها للتو ولم أدققها بعد";
  await typeAtEnd(page, typed);
  await page.reload();
  await page.waitForSelector("#article");
  await page.waitForTimeout(300);
  check(await page.inputValue("#article") === typed, `${tag}: a typed, un-audited text is still in the editor after a reload`);
  check(/لم يُدقَّق بعد/.test(norm(await page.locator("#status").innerText())), `${tag}: the page says the restored text has not been audited`);
  check(await page.locator("#panel").isHidden(), `${tag}: restoring the text does not start an audit`);
  await page.click("#clear-btn");
  await page.reload();
  await page.waitForTimeout(300);
  check(await page.inputValue("#article") === "", `${tag}: after «مسح» a reload brings nothing back`);

  // 3. a verse suggestion while writing, inserted from the source text, not covering the line being written
  await typeAtEnd(page, "قال تعالى: ﴿هل يستوي الذين يعلمون");
  let suggested = false;
  try { await page.waitForSelector("#suggest:not([hidden]) .sg-accept", { timeout: 10000 }); suggested = true; } catch { /* checked below */ }
  check(suggested && /الزمر/.test(norm(await page.locator("#suggest").innerText())), `${tag}: a suggestion names الزمر after «قال تعالى: ﴿هل يستوي الذين يعلمون»`);
  if (suggested) {
    // the caret's line, measured as the page measures it (a hidden copy of the text up to the caret; scripts/ui_suggest_place_e2e.mjs)
    const cover = await page.evaluate(() => {
      const ta = document.getElementById("article"), ed = document.getElementById("editor");
      const m = document.createElement("div"); m.className = "caret-mirror ed-text"; ed.append(m);
      m.style.width = ta.clientWidth + "px"; m.textContent = ta.value.slice(0, ta.selectionEnd);
      const p = document.createElement("span"); p.textContent = "\u200b"; m.append(p);
      const er = ed.getBoundingClientRect(), top = er.top + p.offsetTop, bottom = top + p.offsetHeight; m.remove();
      const b = document.getElementById("suggest").getBoundingClientRect();
      return !(b.bottom <= top + 1 || b.top >= bottom - 1);
    });
    check(!cover, `${tag}: the suggestion box does not cover the line being written`);
    await shot("suggest");
    await page.locator("#suggest .sg-accept").first().click();
    await page.waitForTimeout(300);
    check(/هل يستوي الذين يعلمون والذين لا يعلمون/.test(await page.inputValue("#article")), `${tag}: the inserted words come from the verse («والذين لا يعلمون»)`);
  }

  // 4. TXT and DOCX import: the exact text, nothing audited until asked
  for (const f of FILES) {
    await page.click("#clear-btn");
    await page.setInputFiles("#import-file", f);
    await page.waitForFunction(() => document.querySelector("#article").value.length > 0, null, { timeout: 15000 });
    check(await page.inputValue("#article") === ARTICLE, `${tag}: ${f.name} gives the article code point for code point`);
    check(await page.locator("#panel").isHidden(), `${tag}: ${f.name} is not audited until the writer asks`);
  }

  // 5. the audit of the imported article
  await page.click("#audit-btn");
  await page.waitForSelector("#panel:not([hidden]) #current article", { timeout: 60000 });
  await page.waitForTimeout(600);
  await shot("audit", true);
  check(/دون ذكاء اصطناعي/.test(norm(await page.locator("#notices").innerText())), `${tag}: the result says the audit ran without a model`);
  check(await copyNow(page) === ARTICLE, `${tag}: before any decision the copy is the writer's text unchanged (no automatic change)`);
  await openRow(page, 1);
  const c1 = page.locator("#finding-1");
  check(/مطابق للمصحف/.test(norm(await c1.innerText())), `${tag}: the correct verse is «مطابق للمصحف»`);
  const link = await c1.locator('a[href*="quranpedia.net"]').first().getAttribute("href");
  check(/quranpedia\.net/.test(link || "") && /153/.test(link || ""), `${tag}: the card links to the verse at Quranpedia (${link})`);
  await openRow(page, 2);
  check(/غيّر إلى «تنازعوا»/.test(norm(await page.locator("#finding-2").innerText())), `${tag}: the wrong word is offered «غيّر إلى «تنازعوا»» and waits for a decision`);
  await openRow(page, 3);
  check(/أضف «جميعا»/.test(norm(await page.locator("#finding-3").innerText())), `${tag}: the omitted word is offered «أضف «جميعا»»`);
  await openRow(page, 4);
  check(/الإخلاص/.test(norm(await page.locator("#finding-4").innerText())) && /خاطئة/.test(norm(await page.locator("#finding-4").innerText())), `${tag}: the wrong reference is called wrong and الإخلاص ١ is proposed`);
  await openRow(page, 5);
  const c5 = norm(await page.locator("#finding-5").innerText());
  check(!/مطابق للمصحف/.test(c5) && await page.locator('#finding-5 [data-change="5-wording"]').count() === 0, `${tag}: the unmarked quotation is not «مطابق» and has nothing to approve before the writer settles it`);
  const prose = await page.evaluate(() => [...document.querySelectorAll("#queue li, #queue a, #queue button")].map((n) => n.textContent).filter((t) => /نجتمع|في كل عام/.test(t)));
  const proseCards = await page.locator("#queue").innerText();
  check(!/في كل عام[^\n]*مطابق/.test(proseCards), `${tag}: ordinary prose is never listed as a matched quotation (${prose.length} optional row(s))`);

  // decision buttons: names, pressed state, at least 24 × 24 px (WCAG 2.2 target size)
  await openRow(page, 2);
  const btns = await page.locator('#finding-2 [data-change] button[data-act]').evaluateAll((bs) => bs.map((b) => ({ name: (b.getAttribute("aria-label") || b.textContent).trim(), pressed: b.getAttribute("aria-pressed"), w: b.getBoundingClientRect().width, h: b.getBoundingClientRect().height })));
  check(btns.length === 2 && btns.every((b) => b.name && b.pressed !== null && b.w >= 24 && b.h >= 24), `${tag}: both decision buttons have a name, a pressed state and a 24 px target (${JSON.stringify(btns.map((b) => [Math.round(b.w), Math.round(b.h)]))})`);

  // 6. approve, approve, reject, undo, approve
  await page.locator('#finding-2 [data-change] button[data-act="approved"]').first().click();
  await openRow(page, 3);
  await page.locator('#finding-3 [data-change] button[data-act="approved"]').first().click();
  await openRow(page, 4);
  const ref4 = page.locator('#finding-4 [data-change="4-reference"]');
  await ref4.locator('button[data-act="rejected"]').click();
  check(/أبقيتَ/.test(norm(await page.locator("#undo-line").innerText())), `${tag}: a rejection says what will be kept, with an undo`);
  await page.locator("#undo-line button").first().click();
  await openRow(page, 4);
  check(await ref4.locator('button[data-act="rejected"]').getAttribute("aria-pressed") === "false", `${tag}: undo takes the rejection back`);
  await ref4.locator('button[data-act="approved"]').click();
  check(await page.inputValue("#article") === ARTICLE, `${tag}: decisions never change the writer's text in the editor`);

  // 7. an edit after the audit survives a reload; the recheck keeps the decisions
  await typeAtEnd(page, ADDED);
  const edited = ARTICLE + ADDED;
  check(await page.inputValue("#article") === edited, `${tag}: the paragraph was typed at the end`);
  await page.reload();
  await page.waitForSelector("#panel:not([hidden])");
  await page.waitForTimeout(400);
  check(await page.inputValue("#article") === edited, `${tag}: the edit made after the audit is still there after a reload`);
  check(await copyNow(page) === revised(edited), `${tag}: after the reload the copy still holds the three approved corrections`);
  await page.click("#recheck-btn").catch(() => page.click("#audit-btn"));
  await page.waitForFunction(() => /حُفظ|حفظ/.test(document.querySelector("#status")?.textContent || "") || !document.querySelector("#stale-note") || document.querySelector("#stale-note").hidden, null, { timeout: 60000 });
  await page.waitForTimeout(800);

  // 8. final review and copy
  await page.evaluate(() => document.querySelector("#final").scrollIntoView());
  const summary = norm(await page.locator("#final-summary").innerText());
  check(/٣ تغييرات/.test(summary), `${tag}: the final review counts the three approved changes («${summary.slice(0, 60)}»)`);
  const copied = await copyNow(page);
  check(copied === revised(edited), `${tag}: the copied article is exactly the writer's text with the three approved source corrections`);
  check(await page.inputValue("#article") === edited, `${tag}: the writer's text in the editor is still as written after copying`);
  check(await overflowX() <= 0, `${tag}: no sideways scroll at the final review`);
  await shot("final", true);
  await page.reload();
  await page.waitForTimeout(500);
  check(await page.inputValue("#article") === edited && /استُعيدت/.test(norm(await page.locator("#status").innerText())), `${tag}: a reload after the review restores the text and the decisions`);

  // 9. the report link and the trust pages
  for (const p of ["/", "/sources", "/privacy", "/limitations", "/roadmap"]) {
    const res = await page.goto(server.base + p);
    check(res.status() === 200, `${tag}: ${p} answers 200`);
    const href = await page.locator(".site-footer a", { hasText: "أبلغ عن مشكلة" }).getAttribute("href").catch(() => null);
    check(href === REPORT, `${tag}: ${p} has «أبلغ عن مشكلة» pointing to the pilot report form`);
    check(await overflowX() <= 0, `${tag}: ${p} has no sideways scroll`);
  }
  check(/حدود التجربة/.test(norm(await page.locator("main").innerText())), `${tag}: /roadmap names the pilot's limits apart from what works and what is future work`);
  check(errors.length === 0, `${tag}: no page error (${errors.slice(0, 2).join(" | ")})`);
  await ctx.close();
}
finish(server, browser);
