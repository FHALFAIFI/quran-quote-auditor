// What a writer sees when they approve a correction (4 Oct). The box keeps their own text (undo, edit tracking and the recheck rely on it); the
// writer's words that change are struck through and the approved text is drawn small above where the change starts, like a proofreader's mark;
// the copied text carries the change. Checked before approval, after it, after «تراجع» (in the panel and in the final review), after editing that
// quotation and after a recheck, at 1366, 390 and 320 px; the label must clear the line above and stay inside the box. AI-off server: no model call.
//   NODE_PATH=<scratch>/node_modules node scripts/ui_approved_e2e.mjs [--shots DIR] [--server URL] [--python PATH]
import { chromium, check, norm, readSample, VIEWPORTS, testServer, openPage, openRow, finish } from "./_ui_common.mjs";

const server = await testServer();
const browser = await chromium.launch();
const demo = readSample("sample-demo");

// Each drawn correction: the writer's text under it, the struck words, and its label (.fix-to, in the same order as the .fix spans).
// clearPrev: the gap between the label and the type area of the line above (a negative number = the label overlaps that line).
const fixes = (page) => page.evaluate(() => {
  const view = document.getElementById("article-view"), vr = view.getBoundingClientRect();
  const rng = document.createRange(); rng.selectNodeContents(view);
  const lines = [...rng.getClientRects()].filter((x) => x.width > 1);
  const labels = [...view.querySelectorAll(".fix-to")];
  return [...view.querySelectorAll(".fix")].map((n, i) => {
    const r = n.getClientRects()[0] || n.getBoundingClientRect(), l = labels[i], lr = l?.getBoundingClientRect();
    const prev = lines.filter((x) => x.bottom < r.top - 2).reduce((a, x) => Math.max(a, x.bottom), -Infinity);
    return { under: n.textContent, to: n.dataset.to, label: l?.textContent, struck: [...n.querySelectorAll(".fix-del")].map((d) => d.textContent),
      shown: !!lr && lr.width > 8 && getComputedStyle(l).visibility !== "hidden", cut: !!l?.classList.contains("cut"),
      inside: !!lr && lr.left >= vr.left - 1 && lr.right <= vr.right + 1 && lr.top >= vr.top - 1, above: !!lr && lr.top < r.top && lr.bottom <= r.top + 0.3 * parseFloat(getComputedStyle(view).fontSize),
      startGap: lr ? Math.round(r.right - lr.right) : null, clearPrev: lr && prev > -Infinity ? Math.round(lr.top - prev) : null };
  });
});
const lineHeight = (page) => page.evaluate(() => [getComputedStyle(document.getElementById("article")).lineHeight, getComputedStyle(document.getElementById("article-view")).lineHeight]);
const revised = (page) => page.evaluate(() => { document.getElementById("final")?.querySelector("details.full-text")?.setAttribute("open", ""); return document.getElementById("revised-text").value; });

for (const [name, vp, mobile] of VIEWPORTS) {
  console.log(`\n== ${name} ${vp.width}x${vp.height}: an approved correction`);
  const { page, errors, shot, overflowX, audit } = await openPage(browser, server.base, vp, mobile, `FIX-${name}`);
  const tap = (sel) => (mobile ? page.locator(sel).first().tap() : page.locator(sel).first().click());
  await page.goto(server.base);
  await page.evaluate(() => { sessionStorage.clear(); localStorage.clear(); });
  await page.reload();
  await audit(demo);

  // before: nothing drawn, and the card says what the button will do
  check((await fixes(page)).length === 0, "before approval no correction is drawn in the box");
  const note = norm(await page.textContent("#finding-3 .fix-note").catch(() => ""));
  check(/نصّك في المربع كما هو؛ اعتماد التصحيح يغيّر النسخة المنسوخة فقط/.test(note), `the card distinguishes the original from the copy («${note}»)`);
  const lh0 = await lineHeight(page);
  check(await page.evaluate(() => { const b = document.querySelector('#finding-3 [data-act="approved"]'); const id = b.getAttribute("aria-describedby"); return !!id && !!document.getElementById(id); }), "the approve button is described by that note (screen readers hear it)");
  check(/يجزى/.test(await revised(page)), "the copy still says «يجزى»");
  await shot("1-before");

  // after: the box keeps «يجزى», «يوفى» is drawn above it, the copy says «يوفى», and the next card does not repeat the note
  await tap('#finding-3 [data-act="approved"]');
  await page.waitForTimeout(900);
  check((await page.inputValue("#article")) === demo, "approving does not change the text in the box");
  let fx = await fixes(page);
  check(fx.length === 1 && fx[0].under === "يجزى" && fx[0].label === "يوفى" && fx[0].shown && !fx[0].cut, `«يوفى» is drawn over «يجزى» in the box (${JSON.stringify(fx[0] || {})})`);
  check(fx[0]?.struck.join("|") === "يجزى", "the writer's «يجزى» is struck through (it is what the copy replaces); the box still holds it");
  check(fx[0]?.above && fx[0]?.inside && Math.abs(fx[0].startGap) <= 2, `the label sits above where the change starts, inside the box (${JSON.stringify(fx[0] || {})})`);
  const lh1 = await lineHeight(page);
  check(lh1[0] === lh1[1] && parseFloat(lh1[0]) > parseFloat(lh0[0]), `the lines open up while a correction is drawn, the text box and the marks alike (${lh0[0]} → ${lh1.join(" / ")})`);
  const undoLine = norm(await page.textContent("#undo-line"));
  check(/اعتمدتَ «يوفى» مكان «يجزى» \(الاقتباس ٣\) في النسخة التي تنسخها؛ نصّك في المربع لم يُمحَ/.test(undoLine), `right after, the line above the card says what is copied and that the box keeps the text («${undoLine.slice(0, 70)}…»)`);
  const r1 = await revised(page);
  check(/إنما يوفى الصابرون/.test(r1) && !/يجزى/.test(r1), "the text to copy carries «يوفى»");
  check((await page.locator("#current .fix-note").count()) === 0, "after the first approval the next card does not repeat the note");
  check(await page.evaluate(() => document.querySelector('#article-view mark[data-id="3"]')?.classList.contains("approved")), "the quotation is marked «اعتمدتَ التصحيح», not as a source match");
  await page.evaluate(() => document.querySelector("#article-view .fix").scrollIntoView({ block: "center" }));
  await page.waitForTimeout(300);
  await shot("2-after");
  // the caret in that quotation is announced with the correction (the marks are not read aloud)
  await page.evaluate(() => { const ta = document.getElementById("article"); const i = ta.value.indexOf("يجزى"); ta.focus(); ta.setSelectionRange(i + 2, i + 2); ta.dispatchEvent(new KeyboardEvent("keyup")); });
  await page.waitForFunction(() => /يُكتب «يوفى» في النسخة/.test(document.getElementById("sr-live").textContent), null, { timeout: 2000 }).catch(() => {});
  check(/داخل الاقتباس ٣.*يُكتب «يوفى» في النسخة التي تنسخها، ونصّك هنا كما كتبتَه/.test(await page.textContent("#sr-live")), "with the caret in it, a screen reader hears the approved word and that the box is unchanged");

  // a reference correction is drawn the same way
  await page.evaluate(() => document.getElementById("article").blur());
  await openRow(page, 4);   // the caret had opened quotation 3's card; the writer goes to 4 from the list
  await tap('#finding-4 [data-act="approved"]');
  await page.waitForTimeout(900);
  fx = await fixes(page);
  check(fx.length === 2 && fx.some((x) => x.under === "الشرح: 6" && x.label === "الشرح: ٥" && x.struck.join("|") === "6" && x.inside), `the approved reference «الشرح: ٥» is drawn over «الشرح: 6», only «6» struck (${JSON.stringify(fx.map((x) => [x.label, x.struck]))})`);
  check(fx.every((x) => x.clearPrev === null || x.clearPrev >= 1), `no label touches the line above (${fx.map((x) => x.clearPrev).join(", ")} px)`);
  // once approved, the card itself says which text is the writer's, which is copied, and how to take it back
  await openRow(page, 3);
  const approvedNote = norm(await page.textContent("#finding-3 .fix-note").catch(() => ""));
  check(/اعتمدتَه: يُكتب «يوفى» في النسخة المنسوخة؛ نصّك الأصلي باقٍ\. اضغط الزر ثانية للتراجع/.test(approvedNote), `the approved card says what is copied, what stays, and how to undo («${approvedNote}»)`);
  await openRow(page, 4);
  check((await overflowX()) <= 1, "no sideways scroll");

  // undo: the mark goes, the copy goes back, the box is still the writer's text
  await page.evaluate(() => document.getElementById("undo-line").scrollIntoView({ block: "center" }));
  await tap("#undo-line button");
  await page.waitForTimeout(900);
  fx = await fixes(page);
  check(fx.length === 1 && fx[0].to === "يوفى", "«تراجع» removes the mark of the change it undid, and only that one");
  check(/\[الشرح: 6\]/.test(await revised(page)) && (await page.inputValue("#article")) === demo, "the copy is back to «الشرح: 6»; the box never changed");
  check(parseFloat((await lineHeight(page))[0]) > parseFloat(lh0[0]), "with one correction still drawn, the lines stay open");

  // the final review lists each approved change with «تراجع عنه»: it takes the approval back where the writer is reading
  const undoBtn = page.locator('#final-changes [data-act="undo-approval"]');
  check((await undoBtn.count()) === 1 && /تراجع عن اعتماد «يوفى» في الاقتباس ٣/.test(await undoBtn.first().getAttribute("aria-label")), "the final review offers «تراجع عنه» on the approved change, named for screen readers");
  await undoBtn.first().scrollIntoViewIfNeeded();
  if (mobile) await undoBtn.first().tap(); else await undoBtn.first().click();
  await page.waitForTimeout(600);
  check((await fixes(page)).length === 0 && /إنما يجزى الصابرون/.test(await revised(page)), "after «تراجع عنه» nothing is drawn and the copy says «يجزى» again");
  check(await page.evaluate(() => !!document.activeElement?.closest("#final")), "focus stays in the final review");
  check(/تراجعتَ عن اعتماد «يوفى» \(الاقتباس ٣\)؛ سيُنسخ «يجزى» كما كتبتَه/.test(norm(await page.textContent("#undo-line"))), "the line says what was undone, with its own «تراجع»");
  check(parseFloat((await lineHeight(page))[0]) === parseFloat(lh0[0]), "with nothing drawn, the lines close again");
  await page.locator("#undo-line button").first().click();   // the undo of the undo: approved again
  await page.waitForTimeout(600);
  check((await fixes(page)).some((x) => x.label === "يوفى") && /إنما يوفى الصابرون/.test(await revised(page)), "«تراجع» on that line approves it again");

  // editing inside the approved quotation: the decision falls, the mark goes, the copy has the writer's new text
  const at = demo.indexOf("الصابرون") + 3;
  await page.evaluate((i) => { const ta = document.getElementById("article"); ta.focus(); ta.setSelectionRange(i, i); }, at);
  await page.keyboard.type("ـ");
  await page.waitForTimeout(500);
  fx = await fixes(page);
  check(!fx.some((x) => x.to === "يوفى"), "an edit inside that quotation removes «يوفى» from the box (its decision fell)");
  check(await page.evaluate(() => document.querySelector('#article-view mark[data-id="3"]')?.classList.contains("stale")), "the quotation is marked «عُدّل بعد التدقيق»");
  const r2 = await revised(page);
  check(/يجزى/.test(r2) && !/يوفى الصابرون/.test(r2), "the copy keeps the writer's edited text, with no change applied over it");
  await shot("3-edited");

  // recheck: the edited quotation is asked about again; no mark until the writer decides again
  await tap("#recheck-btn");
  await page.waitForSelector("#panel:not([hidden]) #current article", { timeout: 60000 });
  await page.waitForTimeout(900);
  fx = await fixes(page);
  check(!fx.some((x) => x.to === "يوفى"), "after the recheck nothing is drawn for that quotation until the writer decides again");
  check(await page.locator('#current [data-act="approved"]').count() > 0, "its decision is asked again");

  // a correction that adds a missing word has no characters under it: it is drawn at its place, marked «+»
  const ADD = "وفي فاتحة الكتاب: ﴿الحمد لله العالمين﴾ [الفاتحة: 2].";
  await page.goto(server.base); await page.evaluate(() => sessionStorage.clear()); await page.reload();
  await audit(ADD);
  const kind = await page.evaluate(() => { const c = requiredOf(findingById(current))[0]; return c && { len: c.end - c.start, rep: c.replacement }; });
  check(kind && kind.len === 0 && /رب/.test(kind.rep), `the missing «رب» is an insertion (${JSON.stringify(kind)})`);
  // an addition replaces nothing: «فوق موضعه، ويُضاف» (until 5 Oct the note said «فوقه، ويُكتب مكانه», as for a replaced word)
  check(/أضف «رب»/.test(await page.textContent('#current [data-act="approved"]')) && /نصّك في المربع كما هو؛ اعتماد التصحيح يغيّر النسخة المنسوخة فقط/.test(norm(await page.textContent("#current .fix-note").catch(() => ""))), "the button offers to add «رب», while the note says the original stays");
  await tap('#current [data-act="approved"]');
  await page.waitForTimeout(700);
  fx = await fixes(page);
  check(fx.length === 1 && fx[0].under === "" && fx[0].label === "+ رب" && fx[0].shown && fx[0].inside && fx[0].struck.length === 0, `the added word is drawn at its place as «+ رب», nothing struck (${JSON.stringify(fx[0] || {})})`);
  check((await page.inputValue("#article")) === ADD && /الحمد لله رب العالمين/.test(await revised(page)), "the box is unchanged and the copy has «الحمد لله رب العالمين»");

  // an optional addition (a missing reference) approved and then undone from the final review: nothing was written there, so nothing is «copied as written»
  const NOREF = "وقال جل شأنه: ﴿إنما يوفى الصابرون أجرهم بغير حساب﴾ وهذا وعد عظيم.";
  await page.goto(server.base); await page.evaluate(() => sessionStorage.clear()); await page.reload();
  await audit(NOREF);
  const opt = await page.evaluate(() => { const c = allChanges().find((x) => x.optional && x.kind === "reference_add"); if (!c) return null; decisions[c.id] = "approved"; saveSession(); renderAll(); return c.replacement; });
  check(!!opt, `the missing reference is offered as an optional addition (${opt})`);
  if (opt) {
    await page.evaluate(() => document.getElementById("final").scrollIntoView({ block: "start" }));
    const ub = page.locator('#final-changes [data-act="undo-approval"]').first();
    if (mobile) await ub.tap(); else await ub.click();
    await page.waitForTimeout(500);
    const line = norm(await page.textContent("#undo-line"));
    check(/تراجعتَ عن إضافة «.+» \(الاقتباس [٠-٩]+\)؛ لن تُضاف إلى النسخة المنسوخة/.test(line) && !/«—»/.test(line), `undoing an addition says it will not be added («${line.slice(0, 80)}»)`);
    check((await revised(page)) === NOREF, "and the copy is the article as written");
  }

  // a long correction wherever it falls on the line (start, middle, the left edge): one paragraph per position, every correction approved.
  // The label must stay inside the box (moved, or cut with «…» only if wider than the box) and must not touch the line above.
  const FILL = "وهذا كلام عادي في الصبر ".split(" ").filter(Boolean);
  const EDGE = Array.from({ length: 10 }, (_, k) => `${Array.from({ length: k }, (_, i) => FILL[i % FILL.length]).join(" ")} قال تعالى: ﴿واصبر وما صبرك إلا بالله ولا تحزن عليهم ولا تكن في ضيق مما يكيدون﴾ [النحل: 127]`.trim()).join("\n\n")
    + "\n\nوقال: ﴿إنما يجزى الصابرون أجرهم بغير حساب﴾ [الزمر: 10] و﴿فإن مع العسر يسرا﴾ [الشرح: 6]";   // a wording and a reference correction close together: their labels must not overlap
  await page.goto(server.base); await page.evaluate(() => sessionStorage.clear()); await page.reload();
  await audit(EDGE);
  for (let i = 0; i < 30; i++) {
    const b = page.locator('#current [data-act="approved"]');
    if (!(await b.count())) break;
    await tap('#current [data-act="approved"]');
    await page.waitForTimeout(350);
  }
  fx = await fixes(page);
  const long = fx.filter((x) => x.label === "تك في ضيق مما يمكرون");
  check(long.length === 10 && long.every((x) => x.struck.join("|") === "تكن|يكيدون"), `ten long corrections drawn, only «تكن» and «يكيدون» struck (${long.length}; ${JSON.stringify(long[0]?.struck)})`);
  check(fx.every((x) => x.inside && x.shown), `every label is inside the box (${fx.filter((x) => !x.inside).length} outside)`);
  check(fx.every((x) => x.clearPrev === null || x.clearPrev >= 1), `no label touches the line above (smallest gap ${Math.min(...fx.map((x) => x.clearPrev ?? 99))} px)`);
  check(fx.every((x) => x.above), "every label sits above its line");
  const overlaps = await page.evaluate(() => { const r = [...document.querySelectorAll("#article-view .fix-to")].map((l) => l.getBoundingClientRect()); let n = 0;
    for (let i = 0; i < r.length; i++) for (let j = i + 1; j < r.length; j++) if (r[i].left < r[j].right - 1 && r[j].left < r[i].right - 1 && r[i].top < r[j].bottom - 1 && r[j].top < r[i].bottom - 1) n++; return { n, total: r.length }; });
  check(overlaps.total === 12 && overlaps.n === 0, `no two labels overlap (${overlaps.n} overlapping pairs among ${overlaps.total})`);
  if (vp.width <= 390) check(long.some((x) => x.startGap <= -4), `at this width at least one label had to move inside the box (the edge case was exercised; shifts ${long.map((x) => x.startGap).join(", ")})`);
  check(long.every((x) => !x.cut), "the long label is shown whole (it is narrower than the box at this width)");
  await shot("4-edge");
  // «تراجع عنه» on the third approved change: focus goes to the change that is now third, not back to the first
  await page.evaluate(() => document.getElementById("final").scrollIntoView({ block: "start" }));
  const btns = page.locator('#final-changes [data-act="undo-approval"]');
  const n0 = await btns.count(), fourth = await btns.nth(3).getAttribute("data-change");
  if (mobile) await btns.nth(2).tap(); else await btns.nth(2).click();
  await page.waitForTimeout(500);
  check((await btns.count()) === n0 - 1 && await page.evaluate((id) => document.activeElement?.dataset?.change === id, fourth), `after undoing the third of ${n0}, focus is on the next change (${fourth}), still in the final review`);
  check((await overflowX()) <= 1, "no sideways scroll");
  check(errors.length === 0, `no console errors ${errors.join(" | ")}`);
}
finish(server, browser);
