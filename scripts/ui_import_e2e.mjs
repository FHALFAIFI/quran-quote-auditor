// Importing an article from a file (.txt, .docx), end to end in a real browser, at 1366, 390 and 320 px.
//
//   npm i playwright axe-core   # in any scratch directory; not project dependencies
//   NODE_PATH=<scratch>/node_modules node scripts/ui_import_e2e.mjs [--server URL] [--python PATH] [--browser chromium|firefox|webkit] [--shots DIR]
//
// Every fixture of tests/fixtures/import/fixtures.mjs goes through the page's real file input. For each: the editor's text equals the
// expected text code point for code point (or the refusal message is shown and the editor is unchanged); the notice is shown; no audit
// starts; and NO network request at all is made from the moment the file is given until the text is in the editor (and for 1.5 s after).
// The worker's own script is fetched once when the import button is first used, before any file is chosen, and is counted separately.
// Also: keyboard-only use (Tab to the button, Enter / Space opens the chooser), the replace / cancel question when the editor has text
// (and when it holds an audit), the 10 s time limit (a worker that never answers is stopped), axe on each import state, no sideways scroll.
// Starts its OWN AI-off server unless --server is given.
import { createRequire } from "module";
import fs from "fs";
import { chromium, check, testServer, openPage, VIEWPORTS, finish, opt, shots } from "./_ui_common.mjs";
import { FIXTURES } from "../tests/fixtures/import/fixtures.mjs";

const require = createRequire(import.meta.url);
const I = require("../app/static/import.js");
const axeSource = fs.readFileSync(require.resolve("axe-core/axe.min.js"), "utf8");
const browserName = opt("--browser") || "chromium";
const engine = browserName === "chromium" ? chromium : require("playwright")[browserName];

const server = await testServer();
const browser = await engine.launch();
const MAX = server.health.max_chars;
check(MAX === 20000, `the server's article limit is 20,000 (got ${MAX})`);

const axe = async (page, label) => {
  await page.evaluate(axeSource);
  const res = await page.evaluate(() => axe.run(document, { runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa", "best-practice"] } }));
  const bad = res.violations.map((v) => `${v.id} (${v.impact}) ×${v.nodes.length}: ${v.nodes[0].target.join(" ")}`);
  check(bad.length === 0, `axe: ${label}: ${bad.length ? bad.join(" | ") : "0 violations"}`);
};
// Firefox and WebKit know no clipboard permission: their pages are opened here, the same way otherwise
async function open(vp, mobile, tag) {
  if (browserName === "chromium") return openPage(browser, server.base, vp, mobile, tag);
  const ctx = await browser.newContext({ viewport: vp, locale: "ar", hasTouch: mobile, isMobile: mobile && browserName !== "firefox" });
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  return { ctx, page, errors, shot: async () => {}, overflowX: () => page.evaluate(() => document.documentElement.scrollWidth - innerWidth) };
}
// WebKit on macOS moves focus to buttons with Option+Tab (Safari's default), the others with Tab
const TAB = browserName === "webkit" && process.platform === "darwin" ? "Alt+Tab" : "Tab";
// What happened on the wire between two marks. WebKit reads a File inside the worker by loading it as a blob: URL and reports that load
// as a request; a blob: URL is the browser's own memory (it cannot leave the machine), so it is listed apart, never as network.
let requests = [];
const network = (from) => requests.slice(from).filter((r) => !r.url.startsWith("blob:"));
const local = (from) => requests.slice(from).filter((r) => r.url.startsWith("blob:"));
const show = (list) => list.map((r) => r.method + " " + r.url).join(", ") || "none";
const fileOf = (f) => ({ name: f.name, mimeType: f.name.endsWith(".docx") ? "application/vnd.openxmlformats-officedocument.wordprocessingml.document" : "text/plain", buffer: Buffer.from(f.make()) });
const UNCHANGED = " لم يتغيّر شيء في المحرر.";

for (const [tag, vp, mobile] of VIEWPORTS) {
  console.log(`\n== ${browserName} ${tag} ${vp.width}px`);
  const { ctx, page, errors, shot, overflowX } = await open(vp, mobile, `imp-${tag}`);
  requests = [];
  page.on("request", (r) => requests.push({ method: r.method(), url: r.url().replace(server.base, "") }));
  await page.goto(server.base);
  await page.waitForFunction(() => document.getElementById("limit-note").textContent.trim() !== "");
  await page.waitForTimeout(400);

  // ---- the control: present, quiet, labelled, reachable with the keyboard
  const btn = page.locator("#import-btn");
  check(await btn.isVisible(), `${tag}: the import button is visible`);
  check((await btn.textContent()).trim() === "استورد نصًّا من ملف", `${tag}: the button is labelled in Arabic`);
  check(!(await btn.evaluate((b) => b.classList.contains("primary"))), `${tag}: the import button is not a primary action`);
  const box = await btn.boundingBox();
  check(box && box.height >= 44 && box.x >= 0 && box.x + box.width <= vp.width, `${tag}: the button is at least 44 px tall and inside the page (${box && Math.round(box.height)} px)`);
  check(await page.locator("#import-file").getAttribute("accept") === ".txt,.docx,text/plain,application/vnd.openxmlformats-officedocument.wordprocessingml.document", `${tag}: the chooser offers .txt and .docx only`);
  check(await overflowX() <= 0, `${tag}: no sideways scroll`);

  // keyboard only: Tab from the top of the page to the button; Enter opens the chooser (Space on the second try)
  await page.evaluate(() => { document.activeElement?.blur(); window.scrollTo(0, 0); });
  let reached = false;
  for (let i = 0; i < 40 && !reached; i++) { await page.keyboard.press(TAB); reached = await page.evaluate(() => document.activeElement?.id === "import-btn"); }
  check(reached, `${tag}: Tab reaches the import button`);
  const before = requests.length;
  const [chooser] = await Promise.all([page.waitForEvent("filechooser", { timeout: 10000 }), page.keyboard.press("Enter")]);
  check(!!chooser, `${tag}: Enter on the button opens the file chooser`);
  await page.waitForTimeout(600);   // the worker's script loads now, before a file is chosen
  const warm = requests.slice(before);
  check(warm.every((r) => r.method === "GET" && r.url === "/static/import.js") && warm.length <= 1, `${tag}: opening the chooser fetches only the worker's script (${warm.map((r) => r.method + " " + r.url).join(", ") || "from cache"})`);

  // the first file through the chooser itself, chosen with the keyboard
  const first = FIXTURES.find((f) => f.id === "docx-quran");
  let mark = requests.length;
  await chooser.setFiles(fileOf(first));
  await page.waitForFunction(() => /استُخرج النص/.test(document.getElementById("status").textContent), null, { timeout: 12000 });
  check(await page.inputValue("#article") === first.text, `${tag}: chosen with the keyboard, ${first.id}: the editor holds the expected text`);
  await page.waitForTimeout(1500);
  check(network(mark).length === 0 && local(mark).length <= 1, `${tag}: no network request while the file was read and for 1.5 s after (${show(network(mark))}; in-browser blob reads: ${local(mark).length})`);
  check(await page.evaluate(() => document.activeElement?.id === "article"), `${tag}: the editor has the focus after the import`);
  await shot("docx-imported");
  await axe(page, `${tag}: after an import`);

  // Space opens the chooser too (the editor is not empty now: cancel the question it brings)
  await page.focus("#import-btn");
  const [ch2] = await Promise.all([page.waitForEvent("filechooser", { timeout: 10000 }), page.keyboard.press(" ")]);
  check(!!ch2, `${tag}: Space on the button opens the file chooser`);
  await ch2.setFiles([]);
  await page.click("#clear-btn");

  // ---- every fixture through the real file input, on an empty editor
  for (const f of FIXTURES) {
    if (f.id === "zip-bomb" && tag !== "desktop") continue;   // 50 MB of zeros: once is enough (refused before inflating)
    await page.click("#clear-btn");
    await page.evaluate(() => { document.getElementById("status").replaceChildren(); document.getElementById("import-note").replaceChildren(); });
    mark = requests.length;
    const t0 = Date.now();
    await page.setInputFiles("#import-file", fileOf(f));
    if (f.code) {
      await page.waitForFunction(() => document.getElementById("import-note").classList.contains("error"), null, { timeout: 12000 });
      const want = await I.extract(f.make(), f.name, { maxChars: MAX });
      const note = (await page.textContent("#import-note")).trim();
      check(note === want.message + UNCHANGED, `${tag}: ${f.id}: refused with «${note.slice(0, 70)}…» in ${Date.now() - t0} ms`);
      check(await page.inputValue("#article") === "", `${tag}: ${f.id}: the editor is unchanged`);
    } else {
      await page.waitForFunction(() => /استُخرج النص/.test(document.getElementById("status").textContent), null, { timeout: 12000 });
      const got = await page.inputValue("#article");
      const same = got === f.text;
      let where = "";
      if (!same) { const a = Array.from(got), b = Array.from(f.text); let i = 0; while (a[i] === b[i]) i++; where = ` (differs at code point ${i}: ${JSON.stringify(a.slice(i, i + 10).join(""))} vs ${JSON.stringify(b.slice(i, i + 10).join(""))})`; }
      check(same, `${tag}: ${f.id}: the editor's text equals the expected text code point for code point (${Array.from(f.text).length} cp)${where}`);
      const status = await page.textContent("#status");
      check(status.includes(`استُخرج النص من الملف «\u2068${f.name}\u2069»؛ راجعه قبل التدقيق.`), `${tag}: ${f.id}: the notice is shown`);
      if (f.notes?.presentation) check(status.includes("من أشكال الحروف العربية المعروضة"), `${tag}: ${f.id}: the notice says presentation forms were replaced`);
      if (f.notes?.tracked) check(status.includes("تعديلات متعقَّبة"), `${tag}: ${f.id}: the notice says tracked changes were present`);
      if (f.notes?.notes) check(status.includes("أُلحقت الحواشي"), `${tag}: ${f.id}: the notice says footnotes were appended`);
      const count = (await page.textContent("#char-count")).trim();
      check(count.startsWith(I.arNum(Array.from(f.text).length)), `${tag}: ${f.id}: the count shows the imported length (${count})`);
    }
    await page.waitForTimeout(f.code ? 200 : 1200);
    check(network(mark).length === 0 && local(mark).length <= 1, `${tag}: ${f.id}: no network request during the import (${show(network(mark))}; in-browser blob reads: ${local(mark).length})`);
    check(await page.locator("#results").isHidden() && await page.locator("#panel").isHidden(), `${tag}: ${f.id}: nothing was audited`);
    if (f.id === "txt-20001") { await shot("refused-long"); await axe(page, `${tag}: a refusal shown`); }
  }

  // ---- the editor already has text: the question, then cancel (Escape) and replace (keyboard)
  await page.click("#clear-btn");
  await page.fill("#article", "نص كتبه الكاتب ولا يُمحى دون سؤاله.");
  const docx = FIXTURES.find((f) => f.id === "docx-footnotes");
  mark = requests.length;
  await page.setInputFiles("#import-file", fileOf(docx));
  await page.waitForSelector("#import-ask:not([hidden])", { timeout: 12000 });
  const ask = (await page.textContent("#import-ask-text")).trim();
  check(ask.startsWith("في المحرر نص الآن.") && ask.includes("«\u2068footnotes.docx\u2069»"), `${tag}: the editor has text: asked first («${ask.slice(0, 60)}…»)`);
  check(await page.evaluate(() => document.activeElement?.id === "import-ask-text"), `${tag}: the question has the focus`);
  check(await page.inputValue("#article") === "نص كتبه الكاتب ولا يُمحى دون سؤاله.", `${tag}: the editor is unchanged while asking`);
  check(await page.locator("#import-ask .btn.primary").count() === 0, `${tag}: no primary button in the question («دقّق الاقتباسات» stays the one primary action)`);
  check(await overflowX() <= 0, `${tag}: no sideways scroll with the question open`);
  await shot("ask");
  const markAxe = requests.length;
  await axe(page, `${tag}: the replace question`);
  requests.splice(markAxe);   // axe itself fetches the page's stylesheets (fonts.googleapis.com, blocked by connect-src): not the import's
  await page.focus("#import-ask-text");
  await page.keyboard.press("Escape");
  check(await page.locator("#import-ask").isHidden(), `${tag}: Escape cancels the question`);
  check(await page.inputValue("#article") === "نص كتبه الكاتب ولا يُمحى دون سؤاله.", `${tag}: cancelled: the editor is unchanged`);
  check(await page.evaluate(() => document.activeElement?.id === "import-btn"), `${tag}: cancelled: the focus is back on the import button`);
  await page.setInputFiles("#import-file", fileOf(docx));
  await page.waitForSelector("#import-ask:not([hidden])", { timeout: 12000 });
  await page.keyboard.press(TAB);
  check(await page.evaluate(() => document.activeElement?.id === "import-replace"), `${tag}: Tab from the question reaches «استبدل النص»`);
  await page.keyboard.press("Enter");
  await page.waitForFunction(() => /استُخرج النص/.test(document.getElementById("status").textContent), null, { timeout: 5000 });
  check(await page.inputValue("#article") === docx.text, `${tag}: replaced with the keyboard: the editor holds the file's text`);
  await page.waitForTimeout(1200);
  check(network(mark).length === 0, `${tag}: no network request during the question and the replacement (${show(network(mark))})`);

  // ---- the editor holds an audit: the question says so; replacing clears the audit, and no new audit starts
  await page.click("#clear-btn");
  await page.fill("#article", "قال تعالى: ﴿إِنَّ اللَّهَ مَعَ الصَّابِرِينَ﴾ [البقرة: 153]");
  await page.click("#audit-btn");
  await page.waitForSelector("#results:not([hidden])", { timeout: 60000 });
  await page.waitForTimeout(1500);   // the test's own typing may still ask for a verse suggestion: let it finish before the import
  mark = requests.length;
  const txt = FIXTURES.find((f) => f.id === "txt-arabic");
  await page.setInputFiles("#import-file", fileOf(txt));
  await page.waitForSelector("#import-ask:not([hidden])", { timeout: 12000 });
  check((await page.textContent("#import-ask-text")).includes("ومعه نتيجة تدقيق وقراراتك"), `${tag}: with an audit: the question says the audit and decisions go too`);
  await page.click("#import-replace");
  await page.waitForTimeout(1500);
  check(await page.inputValue("#article") === txt.text, `${tag}: with an audit: replaced`);
  check(await page.locator("#results").isHidden() && await page.locator("#panel").isHidden(), `${tag}: with an audit: the old result is gone and no new audit started`);
  check(network(mark).length === 0, `${tag}: no network request from choosing the file to 1.5 s after replacing (${show(network(mark))})`);
  check(await page.locator("#audit-btn").evaluate((b) => b.classList.contains("primary") && !b.disabled), `${tag}: «دقّق الاقتباسات» is the primary action, ready for the writer`);

  // axe reads the page's stylesheets with fetch(), which the page's CSP (connect-src 'self') blocks for fonts.googleapis.com: axe's message, not the page's
  const own = errors.filter((e) => !/fonts\.googleapis\.com.*connect-src/.test(e));
  check(own.length === 0, `${tag}: no console errors (${own.slice(0, 2).join(" | ")})`);
  const posts = requests.filter((r) => r.method === "POST").map((r) => r.url);
  check(posts.every((u) => u === "/api/audit" || u === "/api/suggest"), `${tag}: the only POSTs in the run are the ones the test's own typing and audit made (${[...new Set(posts)].join(", ")})`);
  await ctx.close();
}

// ---- the time limit: a worker that never answers is stopped after 10 s, and the next import works with a new worker
{
  console.log(`\n== ${browserName} time limit`);
  const { ctx, page, errors } = await open({ width: 1366, height: 900 }, false, "imp-timeout");
  let stuck = true;
  await ctx.route("**/static/import.js", (route) => (stuck ? route.fulfill({ status: 200, contentType: "text/javascript", body: "self.onmessage = () => {};" }) : route.continue()));
  await page.goto(server.base);
  await page.waitForFunction(() => document.getElementById("limit-note").textContent.trim() !== "");
  const f = FIXTURES.find((x) => x.id === "txt-arabic");
  const t0 = Date.now();
  await page.click("#import-btn").catch(() => {});
  await page.setInputFiles("#import-file", fileOf(f));
  await page.waitForFunction(() => document.getElementById("import-note").classList.contains("error"), null, { timeout: 15000 });
  const ms = Date.now() - t0;
  const note = (await page.textContent("#import-note")).trim();
  check(note === "استغرقت قراءة الملف أكثر من ١٠ ثوانٍ فأُوقفت." + UNCHANGED, `a worker that never answers: stopped with «${note}» after ${ms} ms`);
  check(ms >= 9500 && ms < 13000, `the limit is 10 s (${ms} ms)`);
  check(await page.inputValue("#article") === "", "the editor is unchanged after the time limit");
  stuck = false;
  await page.setInputFiles("#import-file", fileOf(f));
  await page.waitForFunction(() => /استُخرج النص/.test(document.getElementById("status").textContent), null, { timeout: 12000 });
  check(await page.inputValue("#article") === f.text, "after a stopped worker, the next import works (a new worker)");
  check(errors.length === 0, `no console errors (${errors.slice(0, 2).join(" | ")})`);
  await ctx.close();
}

if (shots) console.log(`INFO  screenshots in ${shots}`);
finish(server, browser);
