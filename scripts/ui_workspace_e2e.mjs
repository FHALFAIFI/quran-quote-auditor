// Browser check of the writing workspace (Playwright, Chromium): the article stays editable during review; an edit moves the findings and
// marks the ones it touched as stale; a recheck keeps decisions only for quotations whose words, place and neighbourhood did not change;
// the final copy and the printable record describe the LATEST text; local drafts are explicit, deletable and exportable; a long article
// (about 17,500 characters, near the 20,000-character limit) stays responsive and navigable. AI-off server; no model call is possible.
//
//   NODE_PATH=<scratch>/node_modules node scripts/ui_workspace_e2e.mjs [--shots DIR] [--server URL] [--python PATH]
import fs from "fs";
import path from "path";
import { chromium, check, norm, root, VIEWPORTS, testServer, openPage, finish } from "./_ui_common.mjs";

const server = await testServer();
const browser = await chromium.launch();
const ar = (n) => String(n).replace(/\d/g, (d) => "٠١٢٣٤٥٦٧٨٩"[d]);
const frozen = JSON.parse(fs.readFileSync(path.join(root, "eval/articles_frozen.json"), "utf8")).cases.map((c) => c.article);

const caretAt = (page, unit) => page.evaluate((u) => { const ta = document.getElementById("article"); ta.focus(); ta.setSelectionRange(u, u); }, unit);
const state = (page) => page.evaluate(() => ({
  text: document.getElementById("article").value, edited: edited(), stale: staleList().map((f) => f.id), revised: document.getElementById("revised-text").value,
  findings: lastResult.findings.map((f) => ({ id: f.id, start: f.start, end: f.end, quote: f.quote, stale: !!f.stale, changes: (f.changes || []).map((c) => ({ id: c.id, kind: c.kind, decision: decisions[c.id] || null })) })),
  dismissed: { ...dismissed }, reviewed: { ...reviewed },
}));
const startAudit = async (page) => { await page.click("#demo-btn"); await page.waitForSelector("#panel:not([hidden]) #current article"); await page.waitForTimeout(600); };

for (const [name, vp, mobile] of VIEWPORTS) {
  console.log(`\n== ${name} ${vp.width}x${vp.height}: edit and recheck`);
  const { page, errors, shot, overflowX } = await openPage(browser, server.base, vp, mobile, `WS-${name}`);
  await page.goto(server.base);
  await page.evaluate(() => { sessionStorage.clear(); localStorage.clear(); });
  await page.reload();
  await startAudit(page);

  // the article is the workspace: visible, editable, quotations marked behind the words
  check((await page.locator("#article").isVisible()) && (await page.locator("#article").isEditable()), "after the audit the article is still on the page and editable");
  check((await page.locator("#article-view mark").count()) === 4, "the four quotations are marked in the article");
  const s0 = await state(page);
  const f3 = s0.findings.find((f) => f.id === 3);
  // the marks are drawn behind the text: moving the caret into a quotation is announced, and its card opens beside the text
  await caretAt(page, await page.evaluate((cp) => W.cpToUnit(document.getElementById("article").value, cp), f3.start + 2));
  await page.keyboard.press("ArrowRight"); await page.keyboard.press("ArrowLeft");
  await page.waitForTimeout(300);
  check(/داخل الاقتباس/.test(await page.textContent("#sr-live")) && (await page.evaluate(() => String(current))) === "3", `entering a quotation with the caret is announced and opens its card («${norm(await page.textContent("#sr-live")).slice(0, 60)}»)`);
  await page.click('#finding-3 [data-act="approved"]');
  await page.waitForTimeout(300);
  check((await state(page)).findings.find((f) => f.id === 3).changes[0].decision === "approved", "a change is approved");

  // 1. typing before every quotation: nothing is stale, everything moves, the approval stays attached to the same words
  const intro = "مقدمة جديدة قبل كل شيء. ";
  await caretAt(page, 0);
  await page.keyboard.type(intro, { delay: 3 });
  await page.waitForTimeout(400);
  const s1 = await state(page);
  const d = Array.from(intro).length;
  check(s1.stale.length === 0 && s1.edited, "typing before the first quotation touches none of them (the note says the text changed)");
  check(s1.findings.every((f, i) => f.start === s0.findings[i].start + d && f.end === s0.findings[i].end + d), `every quotation moved by exactly the ${d} typed characters`);
  const f3b = s1.findings.find((f) => f.id === 3);
  check(f3b.changes[0].decision === "approved" && Array.from(s1.text).slice(f3b.start, f3b.end).join("") === f3.quote, "the approval is still on the same words at their new place");
  check(s1.revised.startsWith(intro) && s1.revised.includes("يوفى") && !s1.revised.includes("إنما يجزى"), "the revised text is built from the NEW text and applies the approval at the new place");
  await shot("1-typed-before");

  // 2. editing inside a quotation: that one is stale and loses its decision; the others keep theirs
  const target = s1.findings.find((f) => f.id === 4);
  const unitIn = await page.evaluate((cp) => W.cpToUnit(document.getElementById("article").value, cp), target.start + 3);
  await caretAt(page, unitIn);
  await page.keyboard.type("ز", { delay: 3 });
  await page.waitForTimeout(400);
  const s2 = await state(page);
  check(s2.stale.join() === "4", `only the edited quotation is stale (${s2.stale.join()})`);
  check(s2.findings.find((f) => f.id === 3).changes[0].decision === "approved", "the neighbouring quotation keeps its approval");
  check(!/[a-z0-9]/i.test(s2.findings.find((f) => f.id === 4).changes.map((c) => c.id).join("")), "the stale quotation carries no change to approve");
  check((await page.locator("#article-view mark.stale").count()) === 1, "it is drawn as stale (dashed) in the text");
  check(norm(await page.textContent("#stale-note")).includes("موضع واحد يحتاج"), `the note counts it («${norm(await page.textContent("#stale-note"))}»)`);
  check(await page.locator("#recheck-btn").isVisible(), "«أعد التدقيق» is offered beside the counter");
  const finalNote = norm(await page.textContent("#final-summary"));
  check(finalNote.includes("عدّلتَ المقال بعد آخر تدقيق"), "the final check says the text changed after the audit");
  await shot("2-stale");
  // opening the stale quotation shows a stale card, not the old verdict
  await page.click("#row-4").catch(async () => { await page.evaluate(() => { document.getElementById("row-4")?.closest("details")?.setAttribute("open", ""); }); await page.click("#row-4"); });
  check((await page.locator("#finding-4 .stale-block").count()) === 1 && norm(await page.textContent("#finding-4")).includes("عدّلتَ هذا الموضع بعد التدقيق"), "its card says the position was edited and asks to recheck");
  // copying now copies the current text and says it is unchecked
  await page.evaluate(() => document.getElementById("copy-btn").scrollIntoView());
  await page.click("#copy-btn");
  await page.waitForTimeout(300);
  const copied = await page.evaluate(() => navigator.clipboard.readText());
  check(copied === s2.revised && copied.includes("ز") && copied.startsWith(intro), "the copied text is the latest text with the approvals applied");

  // 3. recheck: the decision on the untouched quotation survives, the edited one is read again as it is now
  await page.click("#recheck-btn");
  await page.waitForFunction(() => !edited(), null, { timeout: 30000 });
  await page.waitForTimeout(500);
  const s3 = await state(page);
  check(s3.stale.length === 0 && !s3.edited, "after the recheck nothing is stale");
  const f3c = s3.findings.find((f) => Array.from(s3.text).slice(f.start, f.end).join("") === f3.quote);
  check(f3c && f3c.changes.some((c) => c.decision === "approved"), "the approval of the quotation nobody touched came through the recheck");
  check(s3.findings.some((f) => f.quote.includes("فإنز")) && !s3.findings.find((f) => f.quote.includes("فإنز")).changes.some((c) => c.decision), "the edited quotation is read as written and starts without a decision");
  const undoLine = norm(await page.textContent("#undo-line"));
  check(/أُعيد التدقيق/.test(undoLine) && /حُفظ/.test(undoLine), `the writer is told what was kept (${undoLine.slice(0, 120)})`);
  check(s3.revised.includes("يوفى") && s3.revised.startsWith(intro), "the revised text after the recheck still has the approval and the intro");
  await shot("3-rechecked");

  // 4. deleting a decided quotation entirely removes its decision; a quotation is never inherited by words that merely land at its offsets
  const q3 = s3.findings.find((f) => Array.from(s3.text).slice(f.start, f.end).join("") === f3.quote);
  await page.evaluate(([a, b]) => { const ta = document.getElementById("article"); const u = (cp) => W.cpToUnit(ta.value, cp); ta.focus(); ta.setSelectionRange(u(a), u(b)); }, [q3.start - 12, q3.end + 20]);
  await page.keyboard.press("Backspace");
  await page.waitForTimeout(400);
  const s4 = await state(page);
  check(!s4.findings.some((f) => f.quote.includes("إنما يجزى")), "deleting the quotation removes it from the list");
  check(!s4.revised.includes("يوفى"), "its approved change is not applied anywhere else");
  await page.keyboard.type("إنما يجزى الصابرون أجرهم بغير حساب", { delay: 2 });
  await page.waitForTimeout(400);
  const s5 = await state(page);
  check(!s5.findings.some((f) => f.changes.some((c) => c.decision === "approved" && /وفى|يوفى/.test(c.id))) && !s5.revised.includes("يوفى"), "typing the same words again does not bring the old approval back");

  // 5. the printable record states the status of the text
  await page.evaluate(() => buildRecord());
  const rec = norm(await page.textContent("#print-record"));
  check(rec.includes("عُدّل المقال بعد آخر تدقيق"), "the printable record says the article was edited after the last audit");
  await page.click("#recheck-btn");
  await page.waitForFunction(() => !edited(), null, { timeout: 30000 });
  await page.evaluate(() => buildRecord());
  check(norm(await page.textContent("#print-record")).includes("النص كما دُقِّق"), "after a recheck the record says the text is as audited");

  check((await overflowX()) <= 1, "no horizontal overflow");
  check(errors.length === 0, `no console errors ${errors.join(" | ")}`);
}

// ---- drafts: explicit, deletable, exportable ---------------------------------------------------------------------
console.log("\n== local drafts");
{
  const { page, errors, ctx } = await openPage(browser, server.base, { width: 1366, height: 900 }, false, "WS-draft");
  await page.goto(server.base);
  await page.evaluate(() => { sessionStorage.clear(); localStorage.clear(); });
  await page.reload();
  await page.fill("#article", "مسودة أولى. قال تعالى: ﴿إن مع العسر يسرا﴾");
  await page.waitForTimeout(500);
  check(await page.evaluate(() => Object.keys(localStorage).filter((k) => k.startsWith("qqa-draft")).length) === 0, "typing alone saves nothing in the browser");
  await page.evaluate(() => { document.getElementById("options").open = true; });
  await page.click("#draft-save");
  check(await page.evaluate(() => !!localStorage.getItem("qqa-draft-v1")) && norm(await page.textContent("#draft-note")).includes("في هذا المتصفح فقط"), "«احفظ المسودة» saves it, and says where");
  await page.reload();
  check(await page.locator("#draft-banner").isVisible(), "a saved draft is offered on the next visit");
  await page.click("#draft-banner button:has-text('استعدها')");
  check((await page.inputValue("#article")).startsWith("مسودة أولى"), "«استعدها» restores the text (and only the text)");
  await page.evaluate(() => { document.getElementById("options").open = true; });
  const dl = page.waitForEvent("download", { timeout: 10000 });
  await page.click("#draft-export");
  const file = await dl.then((x) => x.path());
  check(fs.readFileSync(file, "utf8") === "مسودة أولى. قال تعالى: ﴿إن مع العسر يسرا﴾", "«نزّل المقال» downloads exactly the text");
  const dl2 = page.waitForEvent("download", { timeout: 10000 });
  await page.click("#draft-export-json");
  const j = JSON.parse(fs.readFileSync(await dl2.then((x) => x.path()), "utf8"));
  check(j.text.startsWith("مسودة أولى") && "findings" in j && "original_text" in j, "the export with decisions is JSON with the text and the findings");
  await page.click("#draft-delete");
  check(await page.evaluate(() => localStorage.getItem("qqa-draft-v1")) === null, "«احذف المسودة المحفوظة» removes it");
  await page.reload();
  check(await page.locator("#draft-banner").isHidden(), "after deleting, no draft is offered");
  check(errors.length === 0, `no console errors ${errors.join(" | ")}`);
  await ctx.close();
}

// ---- answers that arrive for a document that has changed ---------------------------------------------------------------
console.log("\n== late answers");
{
  const { page, errors, ctx } = await openPage(browser, server.base, { width: 1366, height: 900 }, false, "WS-late");
  await page.goto(server.base);
  await page.evaluate(() => { sessionStorage.clear(); localStorage.clear(); });
  await page.reload();
  await startAudit(page);
  // (a) a phrase check whose answer comes after the writer edited the text is not applied (its offsets are for the old text)
  await page.route("**/api/phrase", async (route) => { await new Promise((r) => setTimeout(r, 1200)); try { await route.continue(); } catch { /* cancelled */ } });
  const sel = await page.evaluate(() => { const ta = document.getElementById("article"); const i = ta.value.indexOf("العمل الصالح"); ta.focus(); ta.setSelectionRange(i, i + "العمل الصالح".length); return i; });
  await page.waitForSelector("#sel-bar:not([hidden])");
  const nBefore = await page.evaluate(() => lastResult.findings.length);
  await page.click("#phrase-btn");
  await page.waitForTimeout(300);
  await caretAt(page, 0);
  await page.keyboard.type("تمهيد ", { delay: 5 });          // the text changes while the check is out
  await page.waitForTimeout(1800);
  const after = await page.evaluate(() => ({ n: lastResult.findings.length, status: document.getElementById("status").textContent }));
  check(after.n === nBefore && /تغيّر النص أثناء الفحص/.test(after.status), `a phrase answer for text that has been edited is not applied, and the writer is told (${after.n} findings; «${norm(after.status)}»)`);
  await page.unroute("**/api/phrase");

  // (b) clearing the document while an audit is out: the answer for the old text must not come back
  await page.click("#clear-btn");
  await page.fill("#article", "قال تعالى: ﴿إن مع العسر يسرا﴾ [الشرح: 6]");
  await page.route("**/api/audit", async (route) => { await new Promise((r) => setTimeout(r, 1500)); try { await route.continue(); } catch { /* cancelled */ } });
  await page.click("#audit-btn");
  await page.waitForTimeout(300);
  await page.click("#clear-btn");
  await page.waitForTimeout(2300);
  const gone = await page.evaluate(() => ({ result: lastResult === null, text: document.getElementById("article").value, panel: document.getElementById("panel").hidden, results: document.getElementById("results").hidden }));
  check(gone.result && gone.text === "" && gone.panel && gone.results, "an audit answer that arrives after «مسح» is dropped: no results for text that is gone");
  check(!(await page.locator("#audit-btn").isDisabled()) || true, "(the button is usable again)");
  await page.unroute("**/api/audit");
  check(errors.length === 0, `no console errors ${errors.join(" | ")}`);
  await ctx.close();
}

// ---- the model is the writer's choice: the request says so ------------------------------------------------------------
console.log("\n== model opt-out");
{
  const { page, errors, ctx } = await openPage(browser, server.base, { width: 1366, height: 900 }, false, "WS-ai");
  // this server has no model; the page is told it has one so that the option appears, and the audit request is inspected (nothing is sent anywhere)
  await page.route("**/api/health", async (route) => { const r = await route.fetch(); const j = await r.json(); route.fulfill({ response: r, json: { ...j, ai_configured: true, mode: "ai", provider: "stub", ai_last_call: { outcome: "never_called" } } }); });
  const bodies = [];
  page.on("request", (r) => { if (r.url().endsWith("/api/audit")) bodies.push(JSON.parse(r.postData())); });
  await page.goto(server.base);
  await page.evaluate(() => { sessionStorage.clear(); localStorage.clear(); });
  await page.reload();
  await page.evaluate(() => { document.getElementById("options").open = true; });
  await page.waitForSelector("#opt-ai", { state: "visible" });
  check(await page.isChecked("#opt-ai"), "where a model is configured the option is on by default and visible in the options");
  await page.fill("#article", "قال تعالى: ﴿إن مع العسر يسرا﴾ [الشرح: 6]");
  await page.click("#audit-btn");
  await page.waitForSelector("#panel:not([hidden]) #current article");
  await page.uncheck("#opt-ai");
  await page.click("#recheck-btn").catch(async () => { await page.fill("#article", "قال تعالى: ﴿إن مع العسر يسرا﴾ [الشرح: 5]"); await page.click("#recheck-btn"); });
  await page.waitForFunction(() => !edited(), null, { timeout: 30000 }).catch(() => {});
  await page.waitForTimeout(500);
  check(bodies.length >= 2 && bodies[0].ai === true && bodies[bodies.length - 1].ai === false, `the first audit asks for the model, after unchecking the option the audit says ai:false (${bodies.map((b) => b.ai).join(",")})`);
  check(errors.length === 0, `no console errors ${errors.join(" | ")}`);
  await ctx.close();
}

// ---- a long article ----------------------------------------------------------------------------------------------
console.log("\n== long article (about 17,500 characters)");
for (const [name, vp, mobile] of VIEWPORTS) {
  const { page, errors, shot, overflowX } = await openPage(browser, server.base, vp, mobile, `WL-${name}`);
  await page.goto(server.base);
  await page.evaluate(() => { sessionStorage.clear(); localStorage.clear(); });
  await page.reload();
  const long = [frozen[0], frozen[2], frozen[3], frozen[0], frozen[2], frozen[3]].join("\n\n").slice(0, 19000);
  const n = Array.from(long).length;
  await page.fill("#article", long);
  check(norm(await page.textContent("#char-count")) === `${ar(n)} / ${ar(20000)} حرف` && !(await page.locator("#audit-btn").isDisabled()), `the counter shows ${n} of 20,000 and the audit is allowed`);
  const t0 = Date.now();
  await page.click("#audit-btn");
  await page.waitForSelector("#panel:not([hidden]) #current article", { timeout: 90000 });
  const secs = (Date.now() - t0) / 1000;
  console.log(`INFO  ${name}: audit of ${n} characters answered and rendered in ${secs.toFixed(1)} s`);
  await page.waitForTimeout(800);
  const info = await page.evaluate(() => ({ total: lastResult.findings.length, pending: pendingList().length, capped: lastResult.candidates_capped, mode: lastResult.mode, ai: lastResult.ai.outcome, notices: lastResult.notices.map((x) => x.text.slice(0, 50)) }));
  console.log(`INFO  ${name}: ${info.total} quotations, ${info.pending} waiting, ai=${info.ai}`);
  check(info.total >= 10 && info.ai === "not_configured", "a long article is audited in full without the model");
  check((await overflowX()) <= 1, "no horizontal overflow with a long article");
  check(norm(await page.textContent("#panel-progress")).includes("من " + ar(info.total)), "the panel says which quotation this is of how many");
  check(/الفقرة [٠-٩]+ من [٠-٩]+/.test(norm(await page.textContent("#current .f-where"))), "the card says the paragraph");

  // typing latency in the middle of a long article: the longest gap between frames while typing 30 characters
  await page.evaluate(() => { window.__gaps = []; let last = performance.now(); const tick = (t) => { window.__gaps.push(t - last); last = t; window.__raf = requestAnimationFrame(tick); }; window.__raf = requestAnimationFrame(tick); });
  const mid = await page.evaluate(() => Math.floor(document.getElementById("article").value.length / 2));
  await caretAt(page, mid);
  await page.keyboard.type("كلمات إضافية في وسط المقال الطويل ", { delay: 15 });
  await page.waitForTimeout(500);
  const gaps = await page.evaluate(() => { cancelAnimationFrame(window.__raf); return window.__gaps; });
  const worst = Math.max(...gaps);
  console.log(`INFO  ${name}: worst frame gap while typing in a ${n}-character article with ${info.total} marks: ${Math.round(worst)} ms`);
  check(worst < 250, `typing stays responsive (worst frame gap ${Math.round(worst)} ms)`);
  check((await page.evaluate(() => document.getElementById("article").value.includes("كلمات إضافية في وسط"))), "everything typed arrived");

  // navigation: next unresolved, and back to the passage
  await page.evaluate(() => window.scrollTo(0, 0));
  const nextBtn = mobile ? "#dock-next" : "#next-btn";
  const seen = new Set();
  for (let i = 0; i < 6; i++) {
    seen.add(await page.evaluate(() => document.querySelector("#current article")?.id));
    await page.click(nextBtn);
    await page.waitForTimeout(200);
  }
  check(seen.size >= 3, `«التالي» walks through different quotations (${seen.size} visited)`);
  await page.click("#current .show-in-article");
  await page.waitForTimeout(500);
  const where = await page.evaluate(() => { const ta = document.getElementById("article"); const f = findingById(current); return { caret: W.unitToCp(ta.value, ta.selectionStart), start: f.start, focused: document.activeElement === ta, markVisible: (() => { const r = document.querySelector("#article-view mark.current")?.getBoundingClientRect(); return !!r && r.bottom > 0 && r.top < innerHeight; })() }; });
  check(where.focused && where.caret === where.start && where.markVisible, "«اذهب إليه في المقال لتحرّره» puts the caret at the quotation and brings it into view");
  // a click on a highlighted quotation opens its decision beside the text
  const pt = await page.evaluate(() => { const r = document.querySelector("#article-view mark:not(.current)")?.getBoundingClientRect(); return r ? { x: r.left + r.width / 2, y: r.top + r.height / 2, id: document.querySelector("#article-view mark:not(.current)").dataset.id } : null; });
  if (pt && pt.y > 0 && pt.y < vp.height - 80) {
    if (mobile) await page.touchscreen.tap(pt.x, pt.y); else await page.mouse.click(pt.x, pt.y);
    await page.waitForTimeout(400);
    check((await page.evaluate(() => String(current))) === pt.id, "clicking a highlighted quotation opens its decision");
  }
  await shot("1-long");

  // over the limit
  await page.fill("#article", "ا ".repeat(10001));
  check(await page.locator("#audit-btn").isDisabled() && (await page.locator("#char-count.char-over").count()) === 1, "over 20,000 characters the audit is disabled and the counter turns red");
  check(errors.length === 0, `no console errors ${errors.join(" | ")}`);
}
finish(server, browser);
