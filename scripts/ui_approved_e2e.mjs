// What a writer sees when they approve a correction (4 Oct). The box keeps their own text (undo, edit tracking and the recheck rely on it); the
// approved word is drawn small above theirs, like a proofreader's mark, and the copied text carries the change. Checked before approval, after it,
// after «تراجع», after editing that quotation and after a recheck, at 1366, 390 and 320 px. AI-off server: no model call.
//   NODE_PATH=<scratch>/node_modules node scripts/ui_approved_e2e.mjs [--shots DIR] [--server URL] [--python PATH]
import { chromium, check, norm, readSample, VIEWPORTS, testServer, openPage, openRow, finish } from "./_ui_common.mjs";

const server = await testServer();
const browser = await chromium.launch();
const demo = readSample("sample-demo");

const fixes = (page) => page.evaluate(() => [...document.querySelectorAll("#article-view .fix")].map((n) => {
  const r = n.getBoundingClientRect(), ed = document.getElementById("editor").getBoundingClientRect();
  const ps = getComputedStyle(n, "::before"), em = parseFloat(getComputedStyle(n).fontSize);
  const top = r.top + 0.32 * em - parseFloat(ps.height);          // bottom: calc(100% - .32em)
  return { under: n.textContent, to: n.dataset.to, content: ps.content, shown: ps.display !== "none" && ps.color !== "rgba(0, 0, 0, 0)",
    // the label starts at the span's right edge (RTL) and runs left for its own width
    inside: top >= ed.top - 1 && r.right <= ed.right + 1 && r.right - parseFloat(ps.width) >= ed.left - 1, above: top < r.top };
}));
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
  check(/عند الاعتماد يظهر «يوفى» فوق ما كتبتَه في المربع، ويُكتب مكانه في النسخة التي تنسخها/.test(note), `the card says where «يوفى» will appear («${note}»)`);
  check(await page.evaluate(() => { const b = document.querySelector('#finding-3 [data-act="approved"]'); const id = b.getAttribute("aria-describedby"); return !!id && !!document.getElementById(id); }), "the approve button is described by that note (screen readers hear it)");
  check(/يجزى/.test(await revised(page)), "the copy still says «يجزى»");
  await shot("1-before");

  // after: the box keeps «يجزى», «يوفى» is drawn above it, the copy says «يوفى», and the next card does not repeat the note
  await tap('#finding-3 [data-act="approved"]');
  await page.waitForTimeout(900);
  check((await page.inputValue("#article")) === demo, "approving does not change the text in the box");
  let fx = await fixes(page);
  check(fx.length === 1 && fx[0].under === "يجزى" && fx[0].to === "يوفى" && /يوفى/.test(fx[0].content) && fx[0].shown, `«يوفى» is drawn over «يجزى» in the box (${JSON.stringify(fx[0] || {})})`);
  check(fx[0]?.above && fx[0]?.inside, "the mark sits above the word and inside the box (not clipped)");
  const undoLine = norm(await page.textContent("#undo-line"));
  check(/اعتمدتَ تغيير «يجزى» إلى «يوفى» \(الاقتباس ٣\)\. يظهر «يوفى» فوق ما كتبتَه في المربع، ويُكتب مكانه في النسخة التي تنسخها/.test(undoLine), `right after, the line above the card says where the change is («${undoLine.slice(0, 70)}…»)`);
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
  check(fx.length === 2 && fx.some((x) => x.under === "الشرح: 6" && x.to === "الشرح: ٥"), `the approved reference «الشرح: ٥» is drawn over «الشرح: 6» (${fx.map((x) => x.to).join(", ")})`);
  check((await overflowX()) <= 1, "no sideways scroll");

  // undo: the mark goes, the copy goes back, the box is still the writer's text
  await page.evaluate(() => document.getElementById("undo-line").scrollIntoView({ block: "center" }));
  await tap("#undo-line button");
  await page.waitForTimeout(900);
  fx = await fixes(page);
  check(fx.length === 1 && fx[0].to === "يوفى", "«تراجع» removes the mark of the change it undid, and only that one");
  check(/\[الشرح: 6\]/.test(await revised(page)) && (await page.inputValue("#article")) === demo, "the copy is back to «الشرح: 6»; the box never changed");

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
  check(/عند الاعتماد يظهر «رب» فوق ما كتبتَه/.test(norm(await page.textContent("#current .fix-note").catch(() => ""))), "the card says where «رب» will appear");
  await tap('#current [data-act="approved"]');
  await page.waitForTimeout(700);
  fx = await fixes(page);
  check(fx.length === 1 && fx[0].under === "" && fx[0].to === "+ رب" && fx[0].shown && fx[0].inside, `the added word is drawn at its place as «+ رب» (${JSON.stringify(fx[0] || {})})`);
  check((await page.inputValue("#article")) === ADD && /الحمد لله رب العالمين/.test(await revised(page)), "the box is unchanged and the copy has «الحمد لله رب العالمين»");
  check(errors.length === 0, `no console errors ${errors.join(" | ")}`);
}
finish(server, browser);
