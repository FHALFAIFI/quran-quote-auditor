// Browser end-to-end check of the judge's first journey, at a desktop (1366), a phone (390) and a narrow phone (320) width (Playwright, Chromium).
//
//   npm i playwright            # in any scratch directory; not a project dependency
//   NODE_PATH=<scratch>/node_modules node scripts/ui_journey_e2e.mjs [--shots DIR] [--python PATH]
//   NODE_PATH=... node scripts/ui_journey_e2e.mjs --server http://localhost:8011 [--shots DIR]   # a server you started (AI off)
//
// Starts its OWN server with AI switched off (no Groq call is possible) unless --server is given; with --server the check
// is made, not assumed: it refuses a server that reports AI as configured.
//
// Journey, per viewport: empty page → «جرّب المقال التجريبي» is visible without scrolling and the empty box is short →
// one click loads AND audits → the verdict «وجدنا ٤ اقتباسات؛ يحتاج اثنان إلى قرارك» → the first item needing review is on
// screen with its decisive difference («يجزى ← يوفى»), its uncertainty warning, its source link and both buttons → the verse,
// the similarity, the API links and the model/source notice are folded → both decisions (one by keyboard) → the dock turns
// into «نسخ المقال المعدّل» → the clipboard holds the article with exactly the two approved changes.
import { createRequire } from "module";
import { spawn } from "child_process";
import net from "net";
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const require = createRequire(import.meta.url);
const { chromium } = require("playwright");
const argv = process.argv.slice(2);
const opt = (name) => { const i = argv.indexOf(name); return i >= 0 ? argv[i + 1] : null; };
const shots = opt("--shots");
const serverArg = opt("--server");
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const python = opt("--python") || process.env.PYTHON || (fs.existsSync(path.join(root, ".venv/bin/python")) ? path.join(root, ".venv/bin/python") : "python3");
if (shots) fs.mkdirSync(shots, { recursive: true });

let failures = 0;
const check = (cond, msg) => { console.log(`${cond ? "PASS" : "FAIL"}  ${msg}`); if (!cond) failures++; };
const norm = (t) => t.replace(/\s+/g, " ").trim();

async function startIsolatedServer() {
  const port = await new Promise((res, rej) => { const s = net.createServer(); s.listen(0, "127.0.0.1", () => { const p = s.address().port; s.close(() => res(p)); }); s.on("error", rej); });
  const env = { ...process.env, AI_PROVIDER: "none", RATE_LIMIT_PER_MINUTE: "1000" };
  for (const k of Object.keys(env)) if (/^(GROQ|GEMINI|GOOGLE)_|API_KEY/i.test(k)) delete env[k];
  const child = spawn(python, ["-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", String(port)], { cwd: root, env, stdio: ["ignore", "pipe", "pipe"] });
  let log = "";
  child.stdout.on("data", (d) => (log += d)); child.stderr.on("data", (d) => (log += d));
  const base = `http://127.0.0.1:${port}`;
  for (let i = 0; i < 100; i++) {
    if (child.exitCode !== null) throw new Error(`test server exited early:\n${log.slice(-1500)}`);
    try { if ((await fetch(base + "/api/health")).ok) return { base, stop: () => child.kill() }; } catch { /* not up yet */ }
    await new Promise((r) => setTimeout(r, 300));
  }
  child.kill();
  throw new Error("test server did not start");
}

const demo = fs.readFileSync(path.join(root, "app/static/samples/sample-demo.txt"), "utf8").trim().replace(/\r\n?/g, "\n");
const expected = demo.replace("يجزى", "يوفى").replace("[الشرح: 6]", "[الشرح: 5]");

const server = serverArg ? { base: serverArg.replace(/\/$/, ""), stop: () => {} } : await startIsolatedServer();
const base = server.base;
const h = await (await fetch(base + "/api/health")).json();
if (h.ai_configured) { console.log("refusing to run: this server has AI configured (a Groq call would be made)"); server.stop(); process.exit(3); }
console.log(`INFO  server ${base} mode=${h.mode}`);

const browser = await chromium.launch();
for (const [name, vp, mobile] of [["desktop", { width: 1366, height: 900 }, false], ["phone", { width: 390, height: 844 }, true], ["narrow", { width: 320, height: 640 }, true]]) {
  console.log(`\n== ${name} ${vp.width}x${vp.height}`);
  const ctx = await browser.newContext({ viewport: vp, locale: "ar", isMobile: mobile, hasTouch: mobile });
  await ctx.grantPermissions(["clipboard-read", "clipboard-write"], { origin: base });
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  const shot = async (n) => { if (shots) await page.screenshot({ path: path.join(shots, `${name}-${n}.png`) }); };
  const inView = (sel, frac = 1) => page.evaluate(([s, f]) => { const r = document.querySelector(s)?.getBoundingClientRect(); return !!r && r.top >= 0 && r.bottom <= innerHeight * f + 1 && r.width > 0; }, [sel, frac]);
  const overflowX = () => page.evaluate(() => document.documentElement.scrollWidth - innerWidth);

  // ---- 1. the empty page
  await page.goto(base, { waitUntil: "load" });
  await page.waitForSelector("#demo-btn");
  check(norm(await page.textContent("#demo-btn")) === "جرّب المقال التجريبي", "the demo action is named «جرّب المقال التجريبي»");
  check(await inView("#demo-btn"), "the demo action is on the first screen without scrolling");
  const taH = await page.evaluate(() => document.getElementById("article").getBoundingClientRect().height);
  check(taH <= vp.height * 0.3, `the empty box is short (${Math.round(taH)} px of ${vp.height})`);
  if (vp.height >= 800) check(await inView("#audit-btn"), "the audit button is on the first screen too");  // not asked of a 640 px-high narrow phone: the demo action is the point there
  check((await overflowX()) <= 1, "empty page: no horizontal overflow");
  await shot("0-empty");

  // ---- 2. one click: load + audit
  await page.click("#demo-btn");
  await page.waitForSelector("#results:not([hidden]) #finding-3", { timeout: 60000 });
  await page.waitForTimeout(1500);  // smooth scroll + fonts settle
  check((await page.inputValue("#article")).replace(/\r\n?/g, "\n") === demo, "one click loaded the demonstration article");
  check((await page.locator("ol.findings > li").count()) === 4, "four quotations found");
  check(norm(await page.textContent("#verdict-title")) === "وجدنا ٤ اقتباسات؛ يحتاج اثنان إلى قرارك", "the verdict leads with «وجدنا ٤ اقتباسات؛ يحتاج اثنان إلى قرارك»");
  check((await page.textContent("#verdict")).includes("مقال تجريبي كُتب لهذا العرض"), "the verdict says the two mistakes are deliberate (a demo article)");
  check((await page.textContent("#verdict")).includes("ليس حكمًا على المقال كله"), "the verdict says it is not a judgement of the whole article");
  check(await page.evaluate(() => document.activeElement?.id === "finding-3"), "focus is on the first item needing review (#3)");
  check(await inView("#finding-3 .ch-delta"), "its decisive difference is on screen");
  check(await inView('[data-change="3-wording"] button[data-act="approved"]'), "its approve button is on screen");
  check(await inView("#review-dock"), "the dock is on screen");
  check(norm(await page.textContent("#dock-text")).startsWith("وجدنا ٤ اقتباسات؛ يحتاج اثنان إلى قرارك"), "the dock repeats the verdict while the page is scrolled to the item");
  await shot("1-landing");

  // ---- 3. the decisive difference, first
  const d3 = [norm(await page.textContent("#finding-3 .d-before")), norm(await page.textContent("#finding-3 .d-after"))];
  check(d3[0] === "يجزى" && d3[1] === "يوفى", `item 3: «${d3[0]}» ← «${d3[1]}»`);
  const order3 = await page.evaluate(() => { const b = document.querySelector("#finding-3 .d-before").getBoundingClientRect(), a = document.querySelector("#finding-3 .d-after").getBoundingClientRect(); return b.left > a.left; });
  check(order3, "RTL: the old word is on the right, the new on the left, with the arrow between");
  const ref = await page.evaluate(() => ["#finding-4 .d-prefix", "#finding-4 .d-before", "#finding-4 .d-after"].map((s) => document.querySelector(s)?.textContent.trim()));
  check(ref[0] === "الشرح:" && ref[1] === "٦" && ref[2] === "٥", `item 4: «${ref[0]} ${ref[1]} ← ${ref[2]}»`);
  for (const id of ["3", "4"]) {
    const labels = await page.$$eval(`#finding-${id} .change.decide button[data-act]`, (b) => b.map((x) => x.textContent.trim()));
    check(labels.join("|") === "اعتماد التصحيح|اترك كما هو", `item ${id}: buttons «اعتماد التصحيح» / «اترك كما هو»`);
  }
  const warn3 = norm(await page.textContent("#finding-3 .ch-lead").catch(() => ""));
  check(await page.locator("#finding-3 .ch-lead").first().isVisible() && /مطابقة تقريبية/.test(warn3), `item 3 keeps its uncertainty warning in view («${warn3}»)`);
  check((await page.locator("#finding-3 .f-head .chip.warn", { hasText: "إحالة غير محسومة" }).isVisible()), "item 3 keeps the chip «إحالة غير محسومة»");
  check(await page.locator('#finding-3 .ch-src a[href*="quranpedia"]').first().isVisible(), "item 3 shows its source link");

  // ---- 4. details are folded, then complete when opened
  for (const id of ["3", "4"]) {
    check(!(await page.locator(`#finding-${id} details.f-all`).evaluate((d) => d.open)), `item ${id}: details folded`);
    check(!(await page.locator(`#finding-${id} .source-box`).isVisible()), `item ${id}: the full verse is not on the card until asked for`);
  }
  check(!(await page.locator("#finding-3 .statuses").isVisible()), "item 3: the similarity percentage and the status boxes are folded");
  check(!(await page.locator('#finding-3 a[href*="/v1/mushafs/"]').first().isVisible()), "item 3: API links are folded");
  const notices = await page.evaluate(() => { const n = document.getElementById("notices"); return { open: [...n.querySelectorAll("details")].filter((d) => d.open).length, visible: n.innerText.replace(/\s+/g, " ").trim(), height: Math.round(n.getBoundingClientRect().height) }; });
  check(notices.open === 0, "the model/source notice is collapsed");
  // With a model the notice is one folded summary; without one (this server) the one-line caveat «قد تفوت عبارات قصيرة» stays in view by design.
  check(h.mode === "ai" ? notices.visible.length <= 60 : /دون ذكاء اصطناعي/.test(notices.visible) && notices.visible.length <= 180, `what shows of the notice is short («${notices.visible}»)`);
  check((await page.locator("#notices .notice").count()) <= 1, "at most one warning above the verdict's list");
  await page.locator("#finding-3 details.f-all > summary").click();
  check(await page.locator("#finding-3 .source-box").isVisible(), "opened: the full verse is shown");
  check(/نسبة التشابه: ٨٣٪/.test(await page.locator("#finding-3 .statuses").innerText()), "opened: the similarity percentage is shown (٨٣٪)");
  check(await page.locator('#finding-3 .source-box a[href*="/v1/mushafs/"]').first().isVisible(), "opened: the API link is shown");
  await shot("2-details-open");
  await page.locator("#finding-3 details.f-all > summary").click();
  await page.locator("#notices details > summary").click();
  check(/النموذج|المصحف|مصحف|قرآنبيديا/.test(await page.locator("#notices").innerText()), "the notice opens to the model/source details");
  await page.locator("#notices details > summary").click();

  // ---- 5. decisions: #3 by keyboard, #4 by pointer; the dock follows
  const approve3 = page.locator('[data-change="3-wording"] button[data-act="approved"]');
  await page.locator("#finding-3").focus();  // the clicks above moved focus; return to the item as the landing left it
  let reached = false;
  for (let i = 0; i < 6 && !reached; i++) { await page.keyboard.press("Tab"); reached = await approve3.evaluate((b) => b === document.activeElement); }
  check(reached, "Tab from the focused item reaches «اعتماد التصحيح» within a few presses");
  await page.keyboard.press("Enter");
  check((await approve3.getAttribute("aria-pressed")) === "true", "Enter approves (aria-pressed)");
  check(norm(await page.textContent("#dock-text")).includes("قراراتك: ١ من ٢"), "the dock now says «قراراتك: ١ من ٢»");
  check(!(await page.locator("#dock-copy").isVisible()), "the copy button waits for the second decision");
  const mid = await page.inputValue("#revised-text");
  check(mid.replace(/\r\n?/g, "\n") === demo.replace("يجزى", "يوفى"), "after one decision only «يجزى»→«يوفى» changed");
  await page.locator("#dock-next").click();
  await page.waitForTimeout(900);
  check(await page.evaluate(() => document.activeElement?.id === "finding-4"), "«التالي» goes to item 4");
  check(await inView('[data-change="4-reference"] button[data-act="approved"]'), "item 4's buttons are on screen");
  const leave4 = page.locator('[data-change="4-reference"] button[data-act="rejected"]');
  await leave4.click();
  check(norm(await page.textContent("#dock-text")).includes("اكتملت قراراتك (٢ من ٢)"), "the dock says «اكتملت قراراتك (٢ من ٢)»");
  check(await page.locator("#dock-copy").isVisible() && (await inView("#dock-copy")), "«نسخ المقال المعدّل» is now on screen in the dock");
  check(/ما زال .* غير محسوم/.test(await page.textContent("#dock-warn")) || !(await page.locator("#dock-warn").isVisible()), "an unresolved item, if any, is still warned about");
  check((await page.inputValue("#revised-text")).replace(/\r\n?/g, "\n") === demo.replace("يجزى", "يوفى"), "leaving #4 as it is keeps «الشرح: 6»");
  await page.locator('[data-change="4-reference"] button[data-act="approved"]').click();  // change of mind
  check(norm(await page.textContent("#dock-text")).includes("اعتمدتَ ٢"), "changing a decision updates the dock («اعتمدتَ ٢»)");
  check(await page.locator("#copy-btn.ready").count() === 1, "the editor's own copy button is highlighted as the final action");
  await shot("3-done");
  await page.click("#dock-copy");
  await page.waitForTimeout(500);
  const clip = (await page.evaluate(() => navigator.clipboard.readText())).replace(/\r\n?/g, "\n");
  check(clip === expected && clip !== demo, "the clipboard holds the article with exactly «يجزى»→«يوفى» and «الشرح: 6»→«الشرح: 5»");
  check(/فحصت الاقتباسات القرآنية فقط/.test(await page.textContent("#dock-text")), "after copying, the dock reminds that only the quotations were checked");
  check(!(await page.textContent("#dock-text")).includes("تحقق من المقال كله"), "no claim that the whole article is verified");
  await shot("4-copied");

  // ---- 6. layout, touch targets, reload
  check((await overflowX()) <= 1, "results: no horizontal overflow");
  if (mobile) {
    const hs = await page.$$eval("#finding-3 .ch-actions .btn, #dock-copy", (b) => b.map((x) => Math.round(x.getBoundingClientRect().height)));
    check(hs.every((x) => x >= 44), `touch targets are at least 44 px (${hs.join(", ")})`);
  }
  await page.reload({ waitUntil: "load" });
  await page.waitForSelector("#results:not([hidden]) #finding-3");
  check(norm(await page.textContent("#dock-text")).includes("اكتملت قراراتك"), "after a reload the decisions and the dock are restored");
  check(await page.locator("#demo-hero").isHidden(), "the demo action is hidden once the box holds text");
  await page.click("#clear-btn");
  check(await page.locator("#demo-hero").isVisible() && await page.locator("#review-dock").isHidden(), "clearing brings the demo action back and hides the dock");
  check(errors.length === 0, `no console/page errors ${errors.join(" | ")}`);
  await ctx.close();
}
await browser.close();
server.stop();
console.log(failures ? `\nfailures: ${failures}` : "\nall checks passed");
process.exit(failures ? 1 : 0);
