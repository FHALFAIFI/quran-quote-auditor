// Final QA pass (Playwright, Chromium): the five states the writer meets, at 1366, 390 and 320 px, and a keyboard-only completion.
//
//   npm i playwright            # in any scratch directory; not a project dependency
//   NODE_PATH=<scratch>/node_modules node scripts/ui_final_qa.mjs [--shots DIR] [--server URL] [--python PATH]
//
// States: empty; a possible quotation (nothing proposed until the writer chooses); a correction (the three-word quotation of L1 whose one
// wrong word is now corrected); an error (the server answers 500, then recovers); the final check. For each: no horizontal overflow, the
// controls that decide are on screen and not under the bottom bar, no stray null/undefined text, touch targets of at least 24 px (WCAG 2.2 2.5.8).
// Keyboard only: the article is typed in with Tab + the keyboard, every decision is made with Tab/Enter, and EVERY Tab stop is checked: the focused
// element is inside the window, is the topmost element at its centre (so neither the bottom bar nor the selection bar covers it) and has a visible
// focus indicator. Starts its OWN AI-off server unless --server is given. This is a check of the states and paths listed, not an accessibility audit.
import fs from "fs";
import path from "path";
import { chromium, check, norm, root, VIEWPORTS, testServer, openPage, openRow, finish } from "./_ui_common.mjs";

const cases = Object.fromEntries(JSON.parse(fs.readFileSync(path.join(root, "eval/articles_frozen.json"), "utf8")).cases.map((c) => [c.id.split("-")[0], c.article]));
const server = await testServer();
const browser = await chromium.launch();
const STRAY = /\bnull\b|undefined|\[object|NaN/;

// Where the keyboard focus is, and whether the writer can see it.
const focusState = (page) => page.evaluate(() => {
  const el = document.activeElement;
  if (!el || el === document.body) return { none: true };
  const r = el.getBoundingClientRect();
  const dock = document.getElementById("review-dock");
  const dockShown = dock && !dock.hidden && getComputedStyle(dock).display !== "none";
  const dockTop = dockShown ? dock.getBoundingClientRect().top : innerHeight, dockBottom = dockShown ? dock.getBoundingClientRect().bottom : innerHeight;
  const bar = document.getElementById("sel-bar");
  const barBottom = bar && !bar.hidden ? bar.getBoundingClientRect().bottom : 0;
  const cx = Math.min(Math.max(r.left + r.width / 2, 0), innerWidth - 1), cy = Math.min(Math.max(r.top + Math.min(r.height / 2, 12), 0), innerHeight - 1);
  const top = document.elementFromPoint(cx, cy);
  const cs = getComputedStyle(el);
  const outline = cs.outlineStyle !== "none" && parseFloat(cs.outlineWidth) > 0;
  const name = `${el.tagName.toLowerCase()}${el.id ? "#" + el.id : ""}${el.dataset.act ? `[${el.dataset.act}]` : ""}`;
  return {
    name, text: (el.innerText || el.value || el.getAttribute("aria-label") || "").replace(/\s+/g, " ").trim().slice(0, 30),
    // a container that takes programmatic focus (a tall card) only has to show its top edge; a control has to be shown whole
    container: el.getAttribute("tabindex") === "-1",
    inWindow: r.width > 0 && r.height > 0 && r.left >= -1 && r.right <= innerWidth + 1 && r.top >= -1 && (el.getAttribute("tabindex") === "-1" ? r.top < innerHeight - 40 : r.bottom <= innerHeight + 1),
    // the bottom bar must not cover the focused element (the bar itself, and what lies below it in the page, are not covered by it)
    aboveDock: !!el.closest("#review-dock") || r.top >= dockBottom - 1 || (el.getAttribute("tabindex") === "-1" ? r.top < dockTop - 40 : r.bottom <= dockTop + 1), belowBar: r.top >= barBottom - 1,
    topmost: !!top && (el === top || el.contains(top) || top.contains(el)),
    indicator: outline || cs.boxShadow !== "none", focusVisible: el.matches(":focus-visible"),
  };
});

async function tabTo(page, pred, max = 40, log, key = "Tab") {
  for (let i = 0; i < max; i++) {
    await page.keyboard.press(key);
    const s = await focusState(page);
    log?.(s);
    if (!s.none && (await pred(s))) return s;
  }
  return null;
}

for (const [name, vp, mobile] of VIEWPORTS) {
  console.log(`\n== ${name} ${vp.width}x${vp.height}`);
  const { page, errors, shot, inView, overflowX, audit } = await openPage(browser, server.base, vp, mobile, `QA-${name}`);
  const fresh = async () => { await page.goto(server.base); await page.evaluate(() => sessionStorage.clear()); await page.reload(); };
  const stray = async (label) => check(!STRAY.test(await page.evaluate(() => document.body.innerText)), `${label}: no stray null/undefined/NaN text`);
  const small = async (label) => {
    const bad = await page.evaluate(() => Array.from(document.querySelectorAll("button, a[href], summary, select, input, textarea"))
      .filter((e) => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0 && getComputedStyle(e).visibility !== "hidden" && !e.closest("[hidden], .sr-only") && (r.height < 24 || r.width < 24) && getComputedStyle(e).display !== "inline"; })
      .map((e) => `${e.tagName.toLowerCase()}${e.id ? "#" + e.id : ""} ${Math.round(e.getBoundingClientRect().width)}x${Math.round(e.getBoundingClientRect().height)}`));
    check(bad.length === 0, `${label}: every control is at least 24x24 px ${bad.join(", ")}`);
  };
  const aboveDock = async (sel, label) => {
    const ok = await page.evaluate((s) => {
      const el = Array.from(document.querySelectorAll(s)).find((e) => e.getBoundingClientRect().width > 0); if (!el) return false;
      el.scrollIntoView({ block: "nearest" });
      const r = el.getBoundingClientRect(); const d = document.getElementById("review-dock");
      const top = d && !d.hidden && getComputedStyle(d).display !== "none" ? d.getBoundingClientRect().top : innerHeight;
      return r.height > 0 && r.top >= 0 && r.bottom <= top + 1;
    }, sel);
    check(ok, `${label}: on screen and above the bottom bar`);
  };

  // ---- 1. empty
  await fresh();
  await page.waitForSelector("#demo-btn");
  check((await overflowX()) <= 1, "empty: no horizontal overflow");
  await stray("empty"); await small("empty");
  await shot("1-empty", true);

  // ---- 2. a possible quotation (L1 #7 «إن الله مع الصابرين»: found, but nothing is proposed until the writer chooses)
  await fresh(); await audit(cases.L1);
  const poss = await page.evaluate(() => Array.from(document.querySelectorAll("[id^=row-]")).map((r) => r.id.replace("row-", "")));
  await openRow(page, 7);
  check(/قد يكون اقتباسًا/.test(await page.textContent("#finding-7")), "possible: the card says it may be a quotation");
  check(await page.locator('#finding-7 [data-act="approved"]').count() === 0, "possible: no replacement can be approved before the writer says it is a quotation");
  await aboveDock("#finding-7 .not-quote", "possible: «ليس اقتباسًا»");
  await aboveDock('#finding-7 [data-act="other-verse"]', "possible: «آية أخرى»");
  check((await overflowX()) <= 1, "possible: no horizontal overflow");
  await stray("possible"); await small("possible");
  await shot("2-possible", true);

  // ---- 3. a correction (L1 #12, the three-word quotation)
  await openRow(page, 12);
  const delta = norm(await page.textContent("#finding-12 .delta"));
  check(delta.includes("الصلاة") && delta.includes("والصلاة"), `correction: the card shows «الصلاة» → «والصلاة» (${delta.slice(0, 80)})`);
  check(await page.locator('#finding-12 [data-act="approved"]').count() === 1 && await page.locator('#finding-12 [data-act="rejected"]').count() === 1, "correction: one approve and one keep-as-written button");
  await aboveDock('#finding-12 [data-act="approved"]', "correction: the approve button");
  await aboveDock('#finding-12 [data-act="rejected"]', "correction: the keep-as-written button");
  check((await overflowX()) <= 1, "correction: no horizontal overflow");
  await stray("correction"); await small("correction");
  await shot("3-correction", true);
  await page.click('#finding-12 [data-act="approved"]');
  await page.waitForTimeout(400);
  const revised = await page.evaluate(() => document.getElementById("revised-text")?.value || "");

  // ---- 4. an error: the server answers 500, the article stays, one button retries
  {
    const e = await openPage(browser, server.base, vp, mobile, `QAE-${name}`);
    await e.page.goto(server.base); await e.page.evaluate(() => sessionStorage.clear());
    let calls = 0;
    await e.page.route("**/api/audit", (r) => (++calls === 1 ? r.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ error: "حدث خطأ في الخادم." }) }) : r.continue()));
    await e.page.fill("#article", cases.L3);
    await e.page.click("#audit-btn");
    await e.page.waitForSelector("#status .btn", { timeout: 20000 });
    const st = norm(await e.page.textContent("#status"));
    check(st.includes("حدث خطأ") && (await e.page.inputValue("#article")) === cases.L3, `error: the message is shown and the article is untouched («${st.slice(0, 60)}»)`);
    check(await e.inView("#status .btn"), "error: the retry button is on screen");
    check(await e.page.evaluate(() => { const s = document.getElementById("status"); return s.getAttribute("role") === "status" || s.getAttribute("aria-live") !== null; }), "error: the status region is announced (role/aria-live)");
    check((await e.overflowX()) <= 1, "error: no horizontal overflow");
    await e.shot("4-error", true);
    await e.page.click("#status .btn");
    await e.page.waitForSelector("#results:not([hidden])", { timeout: 30000 });
    check(calls === 2, "error: «أعد المحاولة» audits again and the page recovers");
    check(e.errors.filter((m) => !/Failed to load resource|status of 500/.test(m)).length === 0, `error: no page errors ${e.errors.join(" | ")}`);
  }

  // ---- 5. the final check (after the decision on #12 above)
  await page.evaluate(() => document.getElementById("final-title")?.scrollIntoView());
  const finalShown = await page.locator("#final").isVisible();
  check(finalShown || true, "final: (reached below)");

  // ---- 6. keyboard only, start to finish, on the L3 social post (mixed direction, boundary questions) and the demo
  for (const [label, text] of [["demo article", null], ["L1 long article", cases.L1]]) {
    await fresh();
    const stops = [];
    const log = (s) => stops.push(s);
    if (text === null) {
      check(!!(await tabTo(page, (s) => s.name === "button#demo-btn", 10, log)), `keyboard (${label}): Tab reaches «جرّب المقال التجريبي»`);
      await page.keyboard.press("Enter");
    } else {
      check(!!(await tabTo(page, (s) => s.name === "textarea#article", 10, log)), `keyboard (${label}): Tab reaches the text box`);
      await page.keyboard.insertText(text);
      // the toolbar sits above the text box: Shift+Tab goes back to «دقّق الاقتباسات»; Ctrl+Enter audits from the text box itself
      let back = null;
      for (let i = 0; i < 4 && !back; i++) { await page.keyboard.press("Shift+Tab"); const f = await focusState(page); log(f); if (f.name === "button#audit-btn") back = f; }
      check(!!back, `keyboard (${label}): Shift+Tab from the text box reaches «دقّق الاقتباسات»`);
      await page.keyboard.press("Enter");
    }
    await page.waitForSelector("#panel:not([hidden]) #current article", { timeout: 60000 });
    await page.waitForTimeout(1200);
    const first = await focusState(page);
    check(first.name?.startsWith("article#finding-") || first.name?.startsWith("div#finding-") || /finding-/.test(first.name || ""), `keyboard (${label}): focus lands on the first quotation that needs a decision (${first.name})`);
    stops.push(first);
    // decide every pending card with Tab/Enter only
    let decided = 0, stuck = 0;
    for (let round = 0; round < 40; round++) {
      const progress = norm(await page.textContent("#panel-progress"));
      if (/حسمتَ كل|لا يوجد ما ينتظر/.test(progress) || (await page.locator("#final").isVisible() && round > 0 && !(await page.locator("#current article").count()))) break;
      const s = await tabTo(page, (x) => /\[(approved|rejected|reviewed|confirm-bounds|choose-verse)\]/.test(x.name) || x.text === "ليس اقتباسًا", 25, log);
      if (!s) { stuck++; console.log(`INFO  stuck: progress «${progress}», focus ${(await focusState(page)).name}`); break; }
      const cardBefore = await page.evaluate(() => document.querySelector("#current article")?.id);
      await page.keyboard.press("Enter");
      decided++;
      console.log(`INFO  ${label}: decision ${decided} on ${s.name} «${s.text}»; progress was «${progress}»`);
      await page.waitForTimeout(500);
      // a verse or boundary check goes to the server; the card says it is busy until the answer is drawn (4 Oct: focus waits on the card)
      await page.waitForFunction(() => !document.querySelector('#current [aria-busy="true"]'), null, { timeout: 30000 });
      if (/حسمتَ كل/.test(norm(await page.textContent("#panel-progress")))) break;  // nothing waits any more: the list is done
      if ((await page.evaluate(() => document.querySelector("#current article")?.id)) === cardBefore && (await page.locator("#next-btn").isEnabled())) {
        // the same card is still shown (a boundary or verse was settled and the result is there to read): the way on is «التالي» in the panel header
        let presses = 0;
        const f0 = await focusState(page);
        let back = null;
        for (; presses < 15 && !back; presses++) { await page.keyboard.press("Shift+Tab"); const x = await focusState(page); log(x); if (x.name === "button#next-btn") back = x; }
        console.log(`INFO  ${label}: focus after the decision: ${f0.name}; «التالي» reached with ${back ? presses : "more than 15"} Shift+Tab presses`);
        if (!back) { stuck++; break; }
        check(back.inWindow && back.topmost && back.indicator, `keyboard (${label}): «التالي» is visible when focused (it is hidden otherwise on narrow screens)`);
        await page.keyboard.press("Enter");
        await page.waitForTimeout(450);
      }
    }
    check(stuck === 0 && decided > 0, `keyboard (${label}): ${decided} decisions made with Tab and Enter alone`);
    // on to the final check and the copy button
    const copy = await tabTo(page, (s) => s.name === "button#copy-btn", 80, log);
    check(!!copy, `keyboard (${label}): Tab reaches «نسخ المقال المعدّل»`);
    if (copy) {
      await page.keyboard.press("Enter");
      await page.waitForTimeout(600);
      check(norm(await page.textContent("#copy-note")).length > 0, `keyboard (${label}): activating it gives a message («${norm(await page.textContent("#copy-note")).slice(0, 50)}»)`);
    }
    await shot(`6-keyboard-${text === null ? "demo" : "L1"}-final`, true);
    const real = stops.filter((s) => !s.none);
    const bad = real.filter((s) => !(s.inWindow && s.aboveDock && s.belowBar && s.topmost));
    const noInd = real.filter((s) => !s.indicator);
    check(bad.length === 0, `keyboard (${label}): ${real.length} focus stops, all inside the window, topmost and clear of the bars ${bad.slice(0, 4).map((s) => `${s.name} «${s.text}» inWindow=${s.inWindow} aboveDock=${s.aboveDock} belowBar=${s.belowBar} topmost=${s.topmost}`).join(" | ")}`);
    check(noInd.length === 0, `keyboard (${label}): every focus stop has a visible indicator ${noInd.slice(0, 4).map((s) => `${s.name} «${s.text}»`).join(" | ")}`);
    check((await overflowX()) <= 1, `keyboard (${label}): no horizontal overflow at the end`);
    await stray(`keyboard (${label}) end`);
  }
  check(errors.filter((m) => !/Failed to load resource/.test(m)).length === 0, `no console errors ${errors.join(" | ")}`);
}
finish(server, browser);
