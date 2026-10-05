// Browser end-to-end check of the writer's first journey at a desktop (1366), a phone (390) and a narrow phone (320) width.
//
//   NODE_PATH=<scratch>/node_modules node scripts/ui_journey_e2e.mjs [--shots DIR] [--python PATH]
//   NODE_PATH=... node scripts/ui_journey_e2e.mjs --server http://localhost:8011 [--shots DIR]   # a server you started (AI off)
//
// Starts its OWN server with AI switched off (no Groq call is possible) unless --server is given; a server with AI is refused.
// Journey, per viewport: empty page (the demo action on the first screen, a short box, no audit button to press) → one click loads AND
// audits → the verdict → the decision panel shows item 3 with the exact change («يجزى ← يوفى»), why it is uncertain, where it is in
// the Quran, the source link and two plainly worded buttons → the verse and technical notes are folded → item 3 approved by keyboard →
// the panel moves on by itself to item 4 and says what was done (with undo) → item 4 left as written → the final check lists the
// change in context and the open item → a changed mind → the clipboard holds the article with exactly the two approved changes.
import { chromium, check, norm, readSample, VIEWPORTS, testServer, openPage, finish } from "./_ui_common.mjs";

const demo = readSample("sample-demo");
const expected = demo.replace("يجزى", "يوفى").replace("[الشرح: 6]", "[الشرح: 5]");
const server = await testServer();
const browser = await chromium.launch();
for (const [name, vp, mobile] of VIEWPORTS) {
  console.log(`\n== ${name} ${vp.width}x${vp.height}`);
  const { page, errors, shot, inView, overflowX } = await openPage(browser, server.base, vp, mobile, name);
  await page.goto(server.base, { waitUntil: "load" });
  await page.evaluate(() => sessionStorage.clear());
  await page.reload({ waitUntil: "load" });

  // ---- 1. the empty page
  await page.waitForSelector("#demo-btn");
  check(norm(await page.textContent("#demo-btn")) === "جرّب المقال التجريبي", "the demo action is named «جرّب المقال التجريبي»");
  check(await inView("#demo-btn"), "the demo action is on the first screen without scrolling");
  const taH = await page.evaluate(() => document.getElementById("article").getBoundingClientRect().height);
  check(taH <= vp.height * 0.3, `the empty box is short (${Math.round(taH)} px of ${vp.height})`);
  check(await page.locator("#audit-btn").isDisabled(), "«دقّق الاقتباسات» waits for some text");
  check((await overflowX()) <= 1, "empty page: no horizontal overflow");
  await shot("0-empty");

  // ---- 2. one click: load + audit
  await page.click("#demo-btn");
  await page.waitForSelector("#panel:not([hidden]) #finding-3", { timeout: 60000 });
  await page.waitForTimeout(1500);
  check((await page.inputValue("#article")).replace(/\r\n?/g, "\n") === demo, "one click loaded the demonstration article");
  check(norm(await page.textContent("#verdict-title")) === "وجدنا ٤ اقتباسات؛ يحتاج اثنان إلى قرارك", "the verdict: «وجدنا ٤ اقتباسات؛ يحتاج اثنان إلى قرارك»");
  check((await page.textContent("#verdict")).includes("مقال تجريبي كُتب لهذا العرض"), "the verdict says the two mistakes are deliberate (a demo article)");
  check((await page.textContent("#verdict")).includes("فحصنا الاقتباسات المرصودة فقط"), "the verdict limits its claim to quotations found");
  check(!(await page.textContent("#verdict")).includes("null"), "no stray «null» in the verdict");
  check(await page.evaluate(() => document.activeElement?.id === "finding-3"), "focus is on the first quotation that needs a decision (#3)");
  check(norm(await page.textContent("#panel-progress")).startsWith("اقتباسان ينتظران قرارك"), `the panel says what is pending («${norm(await page.textContent("#panel-progress"))}»)`);
  check(await inView("#finding-3 .delta"), "the exact change is on screen");
  check(await inView('[data-change="3-wording"] button[data-act="approved"]'), "its approve button is on screen");
  check(await inView('[data-change="3-wording"] button[data-act="rejected"]'), "its keep-as-written button is on screen");
  if (!mobile) {
    check(await inView("#verdict-title"), "wide screen: the verdict and the decision share the first screen");
    const markIn = await page.evaluate(() => { const m = document.querySelector('#article-view mark[data-id="3"]').getBoundingClientRect(), v = document.getElementById("article-view").getBoundingClientRect(); return m.top >= v.top && m.bottom <= v.bottom; });
    check(markIn && (await page.locator('#article-view mark[data-id="3"].current').count()) === 1, "wide screen: the quotation being decided is outlined and in view in the article beside the card");
  } else {
    check(await inView("#review-dock"), "phone: the bottom bar is on screen");
    check(norm(await page.textContent("#dock-text")).startsWith("اقتباسان ينتظران قرارك"), "phone: the bar repeats how many wait");
  }
  await shot("1-landing");

  // ---- 3. the card: change first, then why, where, source; plain buttons
  const d3 = [norm(await page.textContent("#finding-3 .d-before")), norm(await page.textContent("#finding-3 .d-after"))];
  check(d3[0] === "يجزى" && d3[1] === "يوفى", `item 3: «${d3[0]}» ← «${d3[1]}»`);
  check(await page.evaluate(() => { const b = document.querySelector("#finding-3 .d-before").getBoundingClientRect(), a = document.querySelector("#finding-3 .d-after").getBoundingClientRect(); return b.left > a.left; }), "RTL: the old word is on the right, the new on the left, with the arrow between");
  const labels3 = await page.$$eval('#finding-3 [data-change="3-wording"] button[data-act]', (b) => b.map((x) => x.textContent.trim()));
  check(labels3.join("|") === "غيّر إلى «يوفى»|أبقِ «يجزى»", `item 3 buttons name the exact result (${labels3.join(" | ")})`);
  const ctx3 = norm(await page.textContent("#finding-3 .f-ctx"));
  check(ctx3.includes("وقال جل شأنه") && ctx3.includes("إنما يجزى الصابرون أجرهم بغير حساب"), "the quoted words are shown in their sentence");
  check(norm(await page.textContent("#finding-3 .where")).includes("سورة الزمر، الآية ١٠"), "the likely surah and ayah are named");
  check(await page.locator('#finding-3 .where a[href*="quranpedia"]').first().isVisible(), "the source link is visible");
  check(/مطابقة تقريبية/.test(await page.textContent("#finding-3 .ch-lead")), "the uncertainty warning stays in view");
  const labels4 = await page.$$eval('#row-4 ~ *, [data-change="4-reference"]', () => []).catch(() => []);
  void labels4;
  check(!(await page.locator("#finding-3 details.f-all").evaluate((d) => d.open)), "the full verse and technical details are folded");
  check(!(await page.locator("#finding-3 .source-box").isVisible()), "the full verse is not on the card until asked for");
  check(!(await page.locator("#finding-3 .statuses").isVisible()), "the similarity percentage is folded");
  const notices = await page.evaluate(() => { const n = document.getElementById("notices"); return { open: [...n.querySelectorAll("details")].filter((d) => d.open).length, text: n.innerText.replace(/\s+/g, " ").trim() }; });
  const sourceStale = notices.text.includes("استُخدمت نسخة مخبأة");
  check(notices.open === 0 && notices.text.length <= (sourceStale ? 200 : 140), `the audit-method notice stays compact, including a source-cache warning when needed («${notices.text}»)`);
  await page.locator("#finding-3 details.f-all > summary").click();
  check(await page.locator("#finding-3 .source-box").isVisible() && /نسبة التشابه: ٨٣٪/.test(await page.locator("#finding-3 .statuses").innerText()), "opened: the full verse and the similarity (٨٣٪) appear");
  check(await page.locator('#finding-3 .source-box a[href*="/v1/mushafs/"]').first().isVisible(), "opened: the API record link appears");
  await shot("2-details-open");
  await page.locator("#finding-3 details.f-all > summary").click();

  // ---- 4. decide: item 3 by keyboard
  const approve3 = page.locator('[data-change="3-wording"] button[data-act="approved"]');
  await page.locator("#finding-3").focus();
  let reached = false;
  for (let i = 0; i < 8 && !reached; i++) { await page.keyboard.press("Tab"); reached = await approve3.evaluate((b) => b === document.activeElement); }
  check(reached, "Tab from the focused card reaches «غيّر إلى «يوفى»» within a few presses");
  await page.keyboard.press("Enter");
  await page.waitForTimeout(1200);
  check(await page.evaluate(() => document.activeElement?.id === "finding-4"), "after the decision the panel moves on to item 4 and focus follows");
  check(/اعتمدتَ «يوفى» مكان «يجزى»/.test(norm(await page.textContent("#undo-line"))) && (await page.locator("#undo-line button").count()) === 1, "it says what was done, with «تراجع»");
  check(norm(await page.textContent("#panel-progress")).startsWith("اقتباس واحد ينتظر قرارك"), "one quotation is left");
  check((await page.inputValue("#revised-text")).replace(/\r\n?/g, "\n") === demo.replace("يجزى", "يوفى"), "after one decision only «يجزى»→«يوفى» changed");
  const d4 = await page.evaluate(() => ["#finding-4 .d-pre", "#finding-4 .d-before", "#finding-4 .d-after"].map((s) => document.querySelector(s)?.textContent.trim()));
  check(d4[0] === "الشرح:" && d4.join(" ").includes("٦") && d4.join(" ").includes("٥"), `item 4 shows the reference change «${d4.join(" ")}»`);
  check(await inView('[data-change="4-reference"] button[data-act="rejected"]'), "item 4's buttons are on screen");
  await page.locator('[data-change="4-reference"] button[data-act="rejected"]').click();
  await page.waitForTimeout(900);
  check(norm(await page.textContent("#panel-title")) === "اكتملت قراراتك" || norm(await page.textContent("#panel-progress")).startsWith("حسمتَ كل ما يحتاج قرارك"), "nothing is left waiting");
  check((await page.inputValue("#revised-text")).replace(/\r\n?/g, "\n") === demo.replace("يجزى", "يوفى"), "leaving #4 as written keeps «الشرح: 6»");

  // ---- 5. the final check
  if (mobile) {
    check(norm(await page.textContent("#dock-text")) === "حسمتَ كل ما يحتاج قرارك" && norm(await page.textContent("#dock-next")) === "المراجعة الأخيرة", "phone: the bar now offers «المراجعة الأخيرة», not a copy button");
    await page.click("#dock-next");
    await page.waitForTimeout(900);
    check(await page.evaluate(() => document.activeElement?.id === "final-title"), "the bar leads to the final check and focuses its heading");
  } else {
    await page.locator("#final").scrollIntoViewIfNeeded();
  }
  const fin = norm(await page.textContent("#final"));
  check(fin.includes("سيُنسخ مقالك بعد تغيير واحد اعتمدتَه، وأبقيتَ موضعًا واحدًا كما كتبتَه.") && !/[٠-٩] تغيير/.test(fin), "the final check states what will be copied and what was left as written");
  check(norm(await page.textContent("#final-changes")).includes("إنما") && (await page.locator("#final-changes del").count()) === 1 && (await page.locator("#final-changes ins").count()) === 1, "the change is shown in its sentence (old struck, new marked)");
  check(norm(await page.textContent("#final-pending")).includes("فإن مع العسر يسرا") && norm(await page.textContent("#final-pending")).includes("لم تحسمه الأداة"), "the quotation whose wrong reference was left stays listed as not settled");
  check(fin.includes("ليس شهادة بأن المقال كله متحقق منه"), "the final check says it does not certify the whole article");
  await shot("3-final");
  check(!/\bnull\b|undefined|\[object/.test(await page.evaluate(() => document.body.innerText)), "no stray «null», «undefined» or «[object …]» text anywhere on the page");
  // a changed mind: reopen #4 from the list and approve
  await page.locator("#final-pending button", { hasText: "راجع" }).click();
  await page.waitForTimeout(700);
  await page.locator('[data-change="4-reference"] button[data-act="approved"]').click();
  await page.waitForTimeout(500);
  check(norm(await page.textContent("#final-summary")).startsWith("سيُنسخ مقالك بعد تغييرين اعتمدتَهما."), "changing a decision updates the final check («بعد تغييرين», no numeral)");
  await page.locator("#final").scrollIntoViewIfNeeded();
  await page.click("#copy-btn");
  await page.waitForTimeout(500);
  const clip = (await page.evaluate(() => navigator.clipboard.readText())).replace(/\r\n?/g, "\n");
  check(clip === expected && clip !== demo, "the clipboard holds the article with exactly «يجزى»→«يوفى» and «الشرح: 6»→«الشرح: 5»");
  check(/الاقتباسات القرآنية التي رُصدت فقط/.test(await page.textContent("#copy-note")), "after copying, a note says only the quotations found were checked");
  await shot("4-copied");
  check(!/\bnull\b|undefined|\[object/.test(await page.evaluate(() => document.body.innerText)) && (await page.locator("#final-pending").innerText()).trim() === "", "with everything decided the final check lists nothing open and prints no stray text");

  // ---- 6. layout, touch targets, reload, clear
  check((await overflowX()) <= 1, "results: no horizontal overflow");
  if (mobile) {
    const hs = await page.$$eval("#final-pending .link-btn, #copy-btn, #dock-next, .row", (b) => b.map((x) => Math.round(x.getBoundingClientRect().height)));
    check(hs.length > 0 && hs.filter((x) => x > 0).every((x) => x >= 24), "small links are at least 24 px (WCAG 2.2 target size, minimum)");
    const big = await page.$$eval("#copy-btn, #dock-next, .btn.approve", (b) => b.filter((x) => x.getBoundingClientRect().width).map((x) => Math.round(x.getBoundingClientRect().height)));
    check(big.every((x) => x >= 44), `buttons are at least 44 px (${[...new Set(big)].join(", ")})`);
  }
  await page.reload({ waitUntil: "load" });
  await page.waitForSelector("#panel:not([hidden]) #current article");
  check(norm(await page.textContent("#final-summary")).startsWith("سيُنسخ مقالك بعد تغييرين اعتمدتَهما."), "after a reload the decisions are restored");
  await page.click("#clear-btn");
  check(await page.locator("#demo-hero").isVisible() && await page.locator("#results").isHidden(), "clearing brings the demo action back and hides the results");
  await page.evaluate(() => window.dispatchEvent(new Event("beforeprint")));
  check(!/\bnull\b|undefined|\[object/.test(await page.evaluate(() => document.getElementById("print-record").innerText)), "no stray «null» text in the printable record");
  check(errors.length === 0, `no console/page errors ${errors.join(" | ")}`);
}
finish(server, browser);
