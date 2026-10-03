// The phone's bottom bar (4 Oct): it names where the review stands and offers the next step that is not already on screen. It used to offer
// «المراجعة الأخيرة» while that review was the thing on screen, over its buttons. Checked at 390 and 320 px with touch, by scrolling, by
// tapping and with the keyboard. AI-off server: no model call.
//   NODE_PATH=<scratch>/node_modules node scripts/ui_dock_e2e.mjs [--shots DIR] [--server URL] [--python PATH]
import { chromium, check, readSample, testServer, openPage, finish } from "./_ui_common.mjs";

const server = await testServer();
const browser = await chromium.launch();
const demo = readSample("sample-demo");

const dock = (page) => page.evaluate(() => {
  const d = document.getElementById("review-dock");
  const vis = !d.hidden && getComputedStyle(d).display !== "none";
  return { vis, text: vis ? d.innerText.replace(/\s+/g, " ").trim() : "", h: getComputedStyle(document.documentElement).getPropertyValue("--dock-h").trim(),
    top: vis ? d.getBoundingClientRect().top : innerHeight };
});
// the element at the centre of a control is the control itself (nothing covers it)
const uncovered = (page, sel) => page.evaluate((s) => {
  const n = document.querySelector(s); const r = n.getBoundingClientRect();
  if (r.bottom <= 0 || r.top >= innerHeight) return null;
  const hit = document.elementFromPoint(r.left + r.width / 2, Math.min(innerHeight - 2, r.top + r.height / 2));
  return n === hit || n.contains(hit);
}, sel);
const settle = (page, ms = 700) => page.waitForTimeout(ms);
const scrollToSel = (page, sel, block = "start") => page.evaluate(([s, b]) => document.querySelector(s).scrollIntoView({ block: b, behavior: "instant" }), [sel, block]);

for (const [name, vp] of [["phone", { width: 390, height: 844 }], ["narrow", { width: 320, height: 640 }]]) {
  console.log(`\n== ${name} ${vp.width}x${vp.height}: the bottom bar`);
  const { page, errors, shot, overflowX } = await openPage(browser, server.base, vp, true, `DOCK-${name}`);
  await page.goto(server.base);
  await page.evaluate(() => { sessionStorage.clear(); localStorage.clear(); });
  await page.reload();
  await page.waitForSelector("#article");
  check(!(await dock(page)).vis, "no bar before an audit");
  await page.fill("#article", demo);
  await page.click("#audit-btn");
  await page.waitForSelector("#panel:not([hidden]) #current article", { timeout: 60000 });
  await settle(page);

  // two decisions wait: the bar names them and offers «التالي», also when the writer scrolls down to the final review
  let d = await dock(page);
  check(d.vis && /اقتباسان ينتظران قرارك/.test(d.text) && /التالي/.test(d.text), `with two decisions open the bar says so and offers «التالي» («${d.text}»)`);
  await scrollToSel(page, "#final");
  await settle(page);
  d = await dock(page);
  check(d.vis && /التالي/.test(d.text) && !/المراجعة الأخيرة/.test(d.text), `in the final review, with decisions open, the bar still leads back to them («${d.text}»)`);
  await shot("1-final-with-pending");
  await page.locator("#dock-next").tap();
  await settle(page, 900);
  check(await page.evaluate(() => { const r = document.getElementById("panel").getBoundingClientRect(); return r.top < innerHeight && r.bottom > 0; }), "«التالي» brings the decision back into view");

  // decide both: the bar offers the final review while the writer is elsewhere
  for (let i = 0; i < 2; i++) {   // whichever quotation «التالي» opened first, then the other
    await page.locator('#current button[data-act="approved"]').first().tap();
    await settle(page);
  }
  await scrollToSel(page, "#panel");
  await settle(page);
  d = await dock(page);
  check(d.vis && /حسمتَ كل ما يحتاج قرارك/.test(d.text) && /المراجعة الأخيرة/.test(d.text), `away from the review, with nothing open, the bar offers «المراجعة الأخيرة» («${d.text}»)`);

  // tapping it: the review comes into view and the bar goes away instead of offering it again
  await page.locator("#dock-next").tap();
  await settle(page, 1200);
  d = await dock(page);
  check(!d.vis && d.h === "0px", `with the final review on screen the bar is gone and reserves no space (visible=${d.vis}, --dock-h=${d.h})`);
  check(await page.evaluate(() => document.activeElement?.id === "final-title"), "focus is on the review's heading");
  await shot("2-final-no-bar");
  for (const sel of ["#copy-btn", "#print-btn", "#reset-btn"]) {
    await scrollToSel(page, sel, "end");
    await settle(page, 300);
    check(await uncovered(page, sel), `${sel} at the bottom of the screen is not covered`);
  }
  check((await overflowX()) <= 1, "no sideways scroll");

  // scrolling back up to the decisions brings the bar back; down again hides it; no flicker at the edge
  await scrollToSel(page, "#article-col");
  await settle(page);
  d = await dock(page);
  check(d.vis && /المراجعة الأخيرة/.test(d.text), "scrolling back up to the article brings the bar back");
  const seen = [];
  for (let y = 0; y <= 14; y++) {
    await page.evaluate((k) => { const f = document.getElementById("final"); const top = scrollY + f.getBoundingClientRect().top; scrollTo({ top: top - innerHeight * (0.9 - k * 0.04), behavior: "instant" }); }, y);
    await settle(page, 120);
    seen.push((await dock(page)).vis ? 1 : 0);
  }
  const flips = seen.slice(1).filter((v, i) => v !== seen[i]).length;
  check(flips === 1 && seen[0] === 1 && seen[seen.length - 1] === 0, `scrolling into the review hides the bar once, without flicker (${seen.join("")})`);

  // the keyboard: the bar's own button, pressed with Enter, leaves focus on the review, never on a hidden button
  await scrollToSel(page, "#article-col");
  await settle(page);
  await page.focus("#dock-next");
  await page.keyboard.press("Enter");
  await settle(page, 1200);
  const f = await page.evaluate(() => ({ id: document.activeElement?.id, inDock: !!document.activeElement?.closest("#review-dock"), body: document.activeElement === document.body }));
  check(f.id === "final-title" && !f.inDock && !f.body, `Enter on the bar's button moves focus to the review heading (${JSON.stringify(f)})`);
  // Tab through the review: no focused control is under the bar (it is hidden here) or off screen
  let hidden = 0;
  for (let i = 0; i < 8; i++) {
    await page.keyboard.press("Tab");
    await settle(page, 120);
    const r = await page.evaluate(() => { const a = document.activeElement; const b = a.getBoundingClientRect(); const dk = document.getElementById("review-dock"); const dt = dk.hidden || getComputedStyle(dk).display === "none" ? innerHeight : dk.getBoundingClientRect().top; return { ok: b.bottom <= dt + 1 && b.top >= -1, id: a.id || a.textContent.slice(0, 20) }; });
    if (!r.ok) hidden++;
  }
  check(hidden === 0, `tabbing through the review never puts focus under the bar (${hidden} hidden)`);

  // undoing a decision from the review reopens it: the bar comes back with «التالي»
  await scrollToSel(page, "#final");
  await settle(page);
  await page.locator("#reset-btn").tap();
  await settle(page);
  d = await dock(page);
  check(d.vis && /التالي/.test(d.text), `after «إلغاء كل القرارات» in the review the bar returns with «التالي» («${d.text}»)`);
  await shot("3-after-reset");
  check(errors.length === 0, `no console errors ${errors.join(" | ")}`);
}
finish(server, browser);
