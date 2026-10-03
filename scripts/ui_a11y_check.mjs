// axe-core accessibility pass over the main states at 320, 390 and 1366 px (Playwright, Chromium + axe-core).
//
//   npm i playwright axe-core   # in any scratch directory; not project dependencies
//   NODE_PATH=<scratch>/node_modules node scripts/ui_a11y_check.mjs [--server URL] [--python PATH]
//
// Rules: WCAG 2.0/2.1/2.2 A and AA tags plus best-practice. States: empty, the demo's first decision, a boundary question with the span
// editor open, a possible quotation with the verse form open, the long article, the final check with every <details> opened, no findings,
// the model-failed state, a verse suggestion open (one verse; several verses), the stale state after an edit, and the three trust pages. Starts its OWN AI-off server unless --server is given.
import { createRequire } from "module";
import { chromium, check, readSample, testServer, openPage, openRow, finish } from "./_ui_common.mjs";
import fs from "fs";
import path from "path";
import { root } from "./_ui_common.mjs";

const require = createRequire(import.meta.url);
const axeSource = fs.readFileSync(require.resolve("axe-core/axe.min.js"), "utf8");
const cases = Object.fromEntries(JSON.parse(fs.readFileSync(path.join(root, "eval/articles_frozen.json"), "utf8")).cases.map((c) => [c.id.split("-")[0], c.article]));
const server = await testServer();
const browser = await chromium.launch();
const run = async (page, label) => {
  await page.evaluate(() => document.querySelectorAll("details").forEach((d) => (d.open = true)));
  await page.evaluate(axeSource);
  const res = await page.evaluate(() => axe.run(document, { runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa", "best-practice"] } }));
  const bad = res.violations.map((v) => `${v.id} (${v.impact}) ×${v.nodes.length}: ${v.nodes[0].target.join(" ")}`);
  check(bad.length === 0, `axe: ${label}: ${bad.length ? bad.join(" | ") : "0 violations"}`);
};
for (const [name, vp, mobile] of [["320", { width: 320, height: 640 }, true], ["390", { width: 390, height: 844 }, true], ["1366", { width: 1366, height: 900 }, false]]) {
  console.log(`\n== ${name}`);
  const { page, audit } = await openPage(browser, server.base, vp, mobile, `a-${name}`);
  const fresh = async () => { await page.goto(server.base); await page.evaluate(() => sessionStorage.clear()); await page.reload(); };
  await fresh(); await run(page, `${name}px empty`);
  await fresh(); await audit(readSample("sample-demo")); await run(page, `${name}px demo, first decision`);
  await page.evaluate(() => document.querySelectorAll("details").forEach((d) => (d.open = false)));
  await fresh(); await audit(cases.L3); await page.locator('[data-act="adjust-bounds"]').first().click(); await page.waitForTimeout(1500); /* the editor scrolls into view smoothly; measure after it settles */ await run(page, `${name}px boundary question with the span editor`);
  await fresh(); await audit(cases.L2); await openRow(page, 3); await page.locator('[data-act="other-verse"]').first().click(); await run(page, `${name}px possible quotation with the verse form`);
  await fresh(); await audit(cases.L1); await run(page, `${name}px long article`);
  await fresh(); await audit(readSample("sample-demo")); await page.locator('#current button[data-act="approved"]').first().click(); await page.waitForTimeout(500); await page.locator('#current button[data-act="rejected"]').first().click(); await page.waitForTimeout(500); await run(page, `${name}px final check, details open`);
  await fresh(); await audit(cases.L5).catch(() => {}); await page.waitForSelector("#results:not([hidden])"); await run(page, `${name}px no findings`);
  // verse suggestion while writing: the box with one verse, and with several verses (second one open)
  const typeAt = async (text) => { await page.click("#article"); await page.keyboard.type(text, { delay: 3 }); await page.waitForFunction(() => { const b = document.getElementById("suggest"); return b && !b.hidden && b.querySelector(".sg-item"); }, null, { timeout: 5000 }); };
  await fresh(); await typeAt("قال تعالى: وما خلقت الجن والإنس إلا"); await run(page, `${name}px verse suggestion (one verse)`);
  await fresh(); await typeAt("قال تعالى: وما خلقت الجن والإنس إلا لعبادتي"); await run(page, `${name}px probable correction`);
  await fresh(); await typeAt("قال تعالى: يا أيها الذين آمنوا كتب"); await page.keyboard.press("ArrowDown"); await run(page, `${name}px several verses, one open`);
  // the stale state: an edit inside a quotation after the audit
  await fresh(); await audit(readSample("sample-demo"));
  await page.evaluate(() => { const ta = document.getElementById("article"); const f = lastResult.findings[3]; const u = W.cpToUnit(ta.value, f.start + 3); ta.focus(); ta.setSelectionRange(u, u); });
  await page.keyboard.type("ز", { delay: 3 }); await page.waitForTimeout(500); await run(page, `${name}px stale quotation after an edit`);
  // the three trust pages
  for (const pg of ["/sources", "/privacy", "/limitations"]) { await page.goto(server.base + pg); await run(page, `${name}px ${pg}`); }
}
finish(server, browser);
