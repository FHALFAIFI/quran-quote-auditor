// Browser end-to-end check of the "uncertain boundary" workflow (Playwright, Chromium). No Groq call: run the server with AI_PROVIDER=none.
//
//   AI_PROVIDER=none uvicorn app.main:app --port 8011      # needs the Quran text (live or cached)
//   NODE_PATH=<dir with playwright>/node_modules node scripts/ui_boundary_e2e.mjs http://localhost:8011 [screenshot-dir]
//
// Flow: an article with an unmarked, CORRECT quotation that begins in the middle of a verse right after prose
// → audit → the card says «غير محسوم — حدود الاقتباس», explains what "uncertain" means, shows the verse's previous word beside the
// article's, and offers two buttons → «عدّل الحدود بنفسك» selects the span in the textarea and enables «افحص المقطع المحدَّد» →
// «حدود الاقتباس صحيحة» re-checks the same span as a manual highlight → wording becomes «مطابق» and the note disappears.
import { createRequire } from "module";
import fs from "fs";
import path from "path";

const require = createRequire(import.meta.url);
const { chromium } = require("playwright");
const base = (process.argv[2] || "http://localhost:8011").replace(/\/$/, "");
const shots = process.argv[3] || null;
if (shots) fs.mkdirSync(shots, { recursive: true });

let failures = 0;
const check = (cond, msg) => { console.log(`${cond ? "PASS" : "FAIL"}  ${msg}`); if (!cond) failures++; };
const shot = async (page, name) => { if (shots) await page.screenshot({ path: path.join(shots, name), fullPage: true }); };

const quote = "ومن يتق الله يجعل له مخرجا";
const article = `إذا ضاقت بك السبل فتذكر ${quote}، واطلب المزيد.`;

const browser = await chromium.launch();
const page = await (await browser.newContext({ viewport: { width: 1280, height: 900 }, locale: "ar" })).newPage();
const errors = [];
page.on("pageerror", (e) => errors.push(String(e)));
page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });

await page.goto(base + "/");
await page.fill("#article", article);
await page.click("#audit-btn");
await page.waitForSelector("#results:not([hidden]) .finding", { timeout: 60000 });
await shot(page, "b1-uncertain.png");

const card = page.locator(".finding").filter({ hasText: quote });
check((await page.locator(".finding").count()) === 1, "one finding");
check((await card.locator(".f-head .chip.warn").first().innerText()).includes("غير محسوم — حدود الاقتباس"), "the wording chip says «غير محسوم — حدود الاقتباس»");
check((await card.locator(".f-head .chip.review").count()) === 1, "the card carries «يحتاج مراجعة»");
check((await card.locator(".f-head .chip.ok").count()) === 0, "no green «matched» chip");
const box = card.locator(".boundary-box");
check((await box.count()) === 1, "the card has the boundary explanation box");
const boxText = await box.innerText();
check(boxText.includes("لا يعني أن الألفاظ خاطئة") && boxText.includes("حدود الاقتباس لم تتحدد"), "the box explains that «uncertain» means the boundary was not established, not that the wording is wrong");
check(boxText.includes("فتذكر") && boxText.includes("الآخر"), "the box shows the article's previous word and the Quran's previous word");
check((await page.locator("#boundary-note").isVisible()) && (await page.locator("#boundary-note").innerText()).includes("لأن حدودها لم تتحدد"), "the summary carries the explanation note");
check((await box.locator("button").count()) === 2, "two buttons: confirm and adjust");
await page.click("#summary .more-stats summary");  // the secondary counts are on demand
check((await page.locator("#summary .tile").filter({ hasText: "غير محسومة" }).locator(".n").innerText()) === "١", "summary counts one uncertain");

// adjust: the span is selected in the textarea, the check button is enabled
await box.locator('button[data-act="adjust-bounds"]').click();
const sel = await page.evaluate(() => { const t = document.getElementById("article"); return t.value.slice(t.selectionStart, t.selectionEnd); });
check(sel === quote, "«عدّل الحدود بنفسك» selects exactly the identified span in the article box");
check(!(await page.locator("#phrase-btn").isDisabled()), "«افحص المقطع المحدَّد» is enabled by that selection");
await shot(page, "b2-selected.png");

// the editor widens the selection by hand to take the previous word → manual boundaries are respected as given
await page.evaluate(() => { const t = document.getElementById("article"); t.setSelectionRange(t.selectionStart - "فتذكر ".length, t.selectionEnd); t.dispatchEvent(new Event("select")); });
await page.click("#phrase-btn");
await page.waitForFunction(() => document.querySelector(".finding .quote-text")?.textContent.startsWith("فتذكر"), null, { timeout: 30000 });
const manual = page.locator(".finding");
check((await manual.locator(".f-head .chip.manual").count()) === 1, "the manual highlight is labelled as the editor's own");
check((await manual.locator(".boundary-box").count()) === 0, "no boundary question for a manual highlight");
check((await manual.locator(".f-head .chip.warn").count()) === 0 || !(await manual.locator(".f-head .chip.warn").first().innerText()).includes("حدود"), "no «حدود الاقتباس» chip on a manual highlight");

// back to the original and confirm via the button
await page.click("#audit-btn");
await page.waitForSelector("#results:not([hidden]) .finding .boundary-box", { timeout: 60000 });
await page.locator('.finding button[data-act="confirm-bounds"]').click();
await page.waitForSelector(".finding .chip.manual", { timeout: 30000 });
const done = page.locator(".finding");
check((await done.locator(".boundary-box").count()) === 0, "after «حدود الاقتباس صحيحة» the boundary box is gone");
check((await done.locator(".f-head .chip.ok").count()) === 1, "the wording now reads «مطابق»");
check((await page.locator("#boundary-note").isHidden()), "the summary note is hidden when nothing is uncertain");
check((await done.locator(".quote-text").textContent()) === quote, "the span itself is unchanged");
await shot(page, "b3-confirmed.png");

check(errors.length === 0, `no page errors${errors.length ? ": " + errors.join(" | ") : ""}`);
await browser.close();
console.log(failures ? `${failures} FAILED` : "all checks passed");
process.exit(failures ? 1 : 0);
