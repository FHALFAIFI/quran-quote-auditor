// Internal inspection (NOT a user study): the seven tasks of docs/WRITER_PILOT.md performed by a script, with a screenshot at each step,
// so that a person (or the assistant, labelled as such) can look at what a first-time writer would see. AI-off local server; no model call.
//   NODE_PATH=<scratch>/node_modules node scripts/walkthrough_shots.mjs --shots DIR [--phone]
import fs from "fs";
import path from "path";
import { chromium, testServer, root, shots, argv } from "./_ui_common.mjs";

const phone = argv.includes("--phone");
const vp = phone ? { width: 390, height: 844 } : { width: 1366, height: 900 };
const tag = phone ? "phone" : "desktop";
const server = await testServer();
const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: vp, locale: "ar", isMobile: phone, hasTouch: phone, permissions: ["clipboard-read", "clipboard-write"] });
const page = await ctx.newPage();
const log = [];
const note = (s) => { log.push(s); console.log(s); };
const shot = async (name, full = false) => { await page.screenshot({ path: path.join(shots, `${tag}-${name}.png`), fullPage: full }); note(`shot ${tag}-${name}`); };
const LA03 = JSON.parse(fs.readFileSync(path.join(root, "eval/articles_long_20261003.json"), "utf8")).cases.find((c) => c.id.startsWith("LA03")).article;

await page.goto(server.base + "/");
await page.waitForSelector("#article");
await shot("t0-empty");

// Task 1 — start an article
await page.click("#article");
await page.keyboard.type("الصبر خلق عظيم، وقد أكثر القرآن من ذكره. ", { delay: 5 });
await shot("t1-typed");

// Task 2 — insert a verse suggestion
await page.keyboard.type("قال تعالى: إن مع العسر", { delay: 30 });
await page.waitForTimeout(1500);
await shot("t2-suggestion");
await page.keyboard.press("Tab");
await page.waitForTimeout(600);
await shot("t2-inserted");
note(`editor after Tab: «${(await page.inputValue("#article")).slice(-80)}»`);

// Task 3 — audit a long article (14,700 characters: the model would be skipped anyway on the live service)
await page.fill("#article", LA03);
const t0 = Date.now();
await page.click("#audit-btn");
await page.waitForSelector("#current article", { timeout: 90000 });
note(`time to first decision card (local, AI off): ${((Date.now() - t0) / 1000).toFixed(1)} s`);
await page.waitForTimeout(400);
await shot("t3-after-audit");
note(`verdict: «${(await page.textContent("#verdict")).replace(/\s+/g, " ").trim().slice(0, 200)}»`);
note(`panel: «${(await page.textContent("#panel-progress")).replace(/\s+/g, " ").trim()}»`);

// Task 4 — settle an uncertain quotation: find a card with a verse question or a boundary question
const ids = await page.$$eval("#queue li button", (bs) => bs.map((b) => b.id));
let found = false;
for (const id of ids.slice(0, 30)) {
  await page.click(`#${id}`);
  await page.waitForTimeout(150);
  const kind = await page.evaluate(() => { const c = document.querySelector("#current article"); return c ? (c.querySelector(".ask.bounds") ? "bounds" : c.querySelector(".ask") ? "verse" : "") : ""; });
  if (kind) { note(`task 4 card: ${kind} (${id})`); await shot(`t4-${kind}`); found = true; break; }
}
if (!found) note("task 4: no uncertain card in the first 30 items");

// Task 5 — approve a correction, then undo it (demonstration article)
await page.selectOption("#sample-select", "sample-demo").catch(() => {});
await page.waitForTimeout(300);
if (await page.isVisible("#audit-btn")) await page.click("#audit-btn");
await page.waitForSelector("#current article", { timeout: 60000 });
await page.waitForTimeout(400);
await shot("t5-first-correction");
const approve = page.locator("#current article button.approve").first();
if (await approve.count()) {
  await approve.click();
  await page.waitForTimeout(500);
  await shot("t5-approved");
  const undo = page.locator("#undo-line button").first();
  if (await undo.count()) { await undo.click(); await page.waitForTimeout(400); await shot("t5-undone"); note("undo via the undo line"); }
}

// Task 6 — inspect the final article
await page.locator("#current article button.approve").first().click().catch(() => {});
await page.waitForTimeout(300);
await page.locator("#final").scrollIntoViewIfNeeded();
await page.waitForTimeout(300);
await shot("t6-final");
note(`final summary: «${(await page.textContent("#final-summary")).replace(/\s+/g, " ").trim().slice(0, 240)}»`);

// Task 7 — copy
await page.click("#copy-btn");
await page.waitForTimeout(300);
const clip = await page.evaluate(() => navigator.clipboard.readText()).catch(() => "");
note(`clipboard: ${clip.length} chars; contains «يوفى»: ${clip.includes("يوفى")}`);
await shot("t7-copied");

fs.writeFileSync(path.join(shots, `${tag}-log.txt`), log.join("\n") + "\n");
await browser.close();
server.stop();
