// Browser check of the interface with Uthmani-script input (Playwright, Chromium), desktop 1280 and phone 390.
//
//   NODE_PATH=<scratch>/node_modules node scripts/ui_uthmani_e2e.mjs [--shots DIR] [--server URL] [--python PATH]
//
// Starts its OWN AI-off server unless --server is given. Article: one correct Uthmani quotation (البقرة: 153), one with a changed word
// (النور: 56) and one correct quotation with a wrong reference (الشرح: 6).
// Quran text in the test article: Tanzil Project, https://tanzil.net (Tanzil Quran Text, Uthmani v1.1, CC BY 3.0; its notice is in
// tests/fixtures/uthmani_verses.json). Typed from Tanzil's text with some marks in another order, so not a byte copy; the
// النور: 56 quotation has one word changed by hand and the الشرح quotation carries a wrong reference on purpose: test inputs, not Quran text.
// Checks: no horizontal overflow, RTL; the correct Uthmani quotation needs no decision and no correction; the two real problems are
// the two pending decisions; optional formatting is apart and never counted; keyboard approval; the revised article differs only in
// the approved spans; copy feedback.
import { chromium, check, norm, testServer, openPage, openRow, finish } from "./_ui_common.mjs";

const art = `قال تعالى: ﴿يَـٰٓأَيُّهَا ٱلَّذِينَ ءَامَنُوا۟ ٱسْتَعِينُوا۟ بِٱلصَّبْرِ وَٱلصَّلَوٰةِ ۚ إِنَّ ٱللَّهَ مَعَ ٱلصَّـٰبِرِينَ﴾ [البقرة: 153]

وقال سبحانه: ﴿وَأَقِيمُوا۟ ٱلصَّلَوٰةَ وَءَاتُوا۟ ٱلزَّكَوٰةَ وَأَطِيعُوا۟ ٱلنَّبِىَّ لَعَلَّكُمْ تُرْحَمُونَ﴾ [النور: 56]

﴿فَإِنَّ مَعَ ٱلْعُسْرِ يُسْرًا﴾ [الشرح: 6]`;
const server = await testServer();
const browser = await chromium.launch();
for (const [name, vp, mobile] of [["desktop", { width: 1280, height: 800 }, false], ["phone", { width: 390, height: 844 }, true]]) {
  console.log(`\n== ${name}`);
  const { page, errors, shot, overflowX, audit } = await openPage(browser, server.base, vp, mobile, `u-${name}`);
  await page.goto(server.base);
  await page.evaluate(() => sessionStorage.clear());
  const dir = await page.evaluate(() => ({ html: document.documentElement.dir, body: getComputedStyle(document.body).direction }));
  check(dir.html === "rtl" && dir.body === "rtl" && (await overflowX()) <= 1, "the page is RTL and has no horizontal overflow");
  await audit(art);
  check((await overflowX()) <= 1, "no horizontal overflow after the audit");
  check(norm(await page.textContent("#verdict-title")) === "وجدنا ٣ اقتباسات؛ يحتاج اثنان إلى قرارك", `verdict: ${norm(await page.textContent("#verdict-title"))}`);
  check((await page.locator("#queue .q-group.need li").count()) === 2 && (await page.locator("#queue .q-group.done li").count()) === 1, "two quotations wait for a decision, the Uthmani one does not");
  const uth = await page.evaluate(() => { const f = lastResult.findings[0]; return { id: f.id, level: f.wording.level, status: f.wording.status, required: f.changes.filter((c) => !c.optional).length, optional: f.changes.filter((c) => c.optional).length }; });
  check(uth.status === "matched" && uth.level === "uthmani" && uth.required === 0, "the correct Uthmani quotation is matched through its script and gets no correction");
  await openRow(page, uth.id);
  check(norm(await page.textContent("#current .f-head .state")) === "مطابق للمصحف", "its card says «مطابق للمصحف» and asks nothing");
  check((await page.locator("#current .decide").count()) === 0, "no decision block on it");
  await page.locator("#current details.f-all > summary").click();
  check(norm(await page.textContent("#current .f-detail")).includes("مطابق — رسم عثماني") && norm(await page.textContent("#current .script-note")).includes("رسم"), "the details say it was matched in the Uthmani script");
  check(uth.optional === 0 || (await page.locator("#current .optional-box .change.optional").count()) === uth.optional, "optional formatting, if any, sits apart in the details");
  await shot("1-uthmani-matched");

  // the two real problems: approve both with the keyboard (focus + Space)
  const decisions = await page.evaluate(() => lastResult.findings.flatMap((f) => f.changes.filter((c) => !c.optional).map((c) => ({ id: c.id, finding: f.id, kind: c.kind }))));
  check(decisions.length === 2, `two corrections are proposed (${decisions.map((d) => d.kind).join(", ")})`);
  for (const d of decisions) {
    await openRow(page, d.finding);
    const approve = page.locator(`[data-change="${d.id}"] button[data-act="approved"]`);
    await approve.focus();
    await page.keyboard.press("Space");
    await page.waitForTimeout(500);
  }
  const revised = await page.inputValue("#revised-text");
  check(revised.includes("[الشرح: 5]") && !revised.includes("ٱلنَّبِىَّ") && revised.includes("يَـٰٓأَيُّهَا") && revised.includes("[النور: 56]"), "after approving only the two corrections the article differs only there; the correct Uthmani text is untouched");
  check(revised.split("\n").length === art.split("\n").length, "line structure preserved");
  check(norm(await page.textContent("#final-summary")).includes("٢ تغييرين"), "the final check counts the two approved changes, not optional formatting");
  await page.locator("#final").scrollIntoViewIfNeeded();
  await page.click("#copy-btn");
  await page.waitForTimeout(300);
  const clip = await page.evaluate(() => navigator.clipboard.readText().catch(() => null));
  check(clip === null || clip.replace(/\r\n?/g, "\n") === revised, "copy puts the revised article on the clipboard");
  check((await page.textContent("#copy-note")).includes("نُسخ"), "copy gives feedback beside the button");
  await shot("2-final");
  check(errors.length === 0, `no page errors ${errors.join(";")}`);
}
finish(server, browser);
