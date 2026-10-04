// The writing workspace in Firefox and WebKit (Playwright's builds of the Safari engine), as well as Chromium: verse suggestion with Tab and with a
// tap/click, the probable correction, the demonstration audit, an edit that makes a quotation stale, a recheck, and that the highlight layer sits
// exactly under the words of the text box (the same wrapped height, and a mark's box covers the words of its quotation).
// WebKit is NOT Safari itself (no macOS system integration, no real iOS keyboard); this narrows the "Chromium only" limit, it does not remove it.
//
//   NODE_PATH=<scratch>/node_modules node scripts/ui_crossbrowser.mjs [--server URL] [--only firefox|webkit|chromium]
import { createRequire } from "module";
import { check, norm, readSample, testServer, opt, finish } from "./_ui_common.mjs";

const require = createRequire(import.meta.url);
const pw = require("playwright");
const server = await testServer();
const only = opt("--only");
const LEAD = "الصبر خلق عظيم. قال تعالى: ";
const SIX = "وما خلقت الجن والإنس إلا";
const waitBox = (page) => page.waitForFunction(() => { const b = document.getElementById("suggest"); return b && !b.hidden && b.querySelector(".sg-item"); }, null, { timeout: 15000 }).then(() => true).catch(() => false);

for (const name of ["chromium", "firefox", "webkit"]) {
  if (only && only !== name) continue;
  let browser;
  // Playwright finds its own build of each engine; when only another revision of Firefox is cached, FIREFOX_BIN may point at it
  const exe = name === "firefox" && process.env.FIREFOX_BIN ? { executablePath: process.env.FIREFOX_BIN } : {};
  try { browser = await pw[name].launch(exe); } catch (e) { console.log(`SKIP  ${name} is not installed here (${String(e).split("\n")[0].slice(0, 80)})`); continue; }
  for (const [label, vp, mobile] of [["desktop", { width: 1366, height: 900 }, false], ["phone", { width: 390, height: 844 }, true]]) {
    console.log(`\n== ${name} ${label}`);
    const ctx = await browser.newContext({ viewport: vp, locale: "ar", hasTouch: mobile, isMobile: mobile && name !== "firefox" });
    const page = await ctx.newPage();
    const errors = [];
    page.on("pageerror", (e) => errors.push(String(e)));
    await page.goto(server.base);
    await page.evaluate(() => { sessionStorage.clear(); localStorage.clear(); });
    await page.reload();
    await page.click("#article");
    await page.keyboard.type(LEAD + SIX, { delay: 6 });
    check(await waitBox(page) && /ليعبدون/.test(await page.textContent("#suggest")), "the suggestion appears");
    if (mobile) await page.locator("#suggest .sg-accept").first().tap(); else await page.keyboard.press("Tab");
    await page.waitForTimeout(250);
    check((await page.inputValue("#article")) === LEAD + SIX + " ليعبدون", `accepting inserts exactly the word (${(await page.inputValue("#article")).slice(-14)})`);
    await page.keyboard.press(process.platform === "darwin" ? "Meta+z" : "Control+z");
    await page.waitForTimeout(250);
    // the browser's own undo: Chromium takes back just the insertion, WebKit takes back the whole typing run with it; either way the word is gone
    check(!(await page.inputValue("#article")).endsWith("ليعبدون"), "undo takes the insertion back (the browser decides how much more it undoes)");
    await page.fill("#article", LEAD + SIX);
    await page.evaluate(() => { const ta = document.getElementById("article"); ta.focus(); ta.setSelectionRange(ta.value.length, ta.value.length); });
    await page.keyboard.type(" لعبادتي", { delay: 6 });
    check(await waitBox(page) && /لعبادتي/.test(await page.textContent("#suggest")) && /ليعبدون/.test(await page.textContent("#suggest")), "the wrong word is offered as a possible correction");
    await page.keyboard.press("Escape");
    check((await page.inputValue("#article")).endsWith("لعبادتي"), "dismissing leaves the text alone");
    // 4 Oct: the first piece of 4:58 stops at «أهلها», by Tab or by a tap, and the next piece follows
    await page.fill("#article", "");
    await page.keyboard.type(LEAD + "إن الله يأمركم أن تؤدوا الأمانات", { delay: 6 });
    check(await waitBox(page) && /يُدرَج حتى «أهلها»/.test(await page.textContent("#suggest")), "4:58: the box says the insertion stops at «أهلها»");
    if (mobile) await page.locator("#suggest .sg-accept").first().tap(); else await page.keyboard.press("Tab");
    await page.waitForTimeout(250);
    check((await page.inputValue("#article")).endsWith("الأمانات إلى أهلها"), `4:58: ${mobile ? "a tap" : "Tab"} inserts «إلى أهلها» and nothing after it`);
    check(await waitBox(page) && /وإذا حكمتم بين الناس/.test(await page.textContent("#suggest")), "4:58: the next piece is offered");
    await page.keyboard.press("Escape");

    // audit, mark alignment, edit, recheck
    await page.click("#clear-btn");
    await page.fill("#article", readSample("sample-demo"));
    await page.click("#audit-btn");
    await page.waitForSelector("#panel:not([hidden]) #current article", { timeout: 60000 });
    await page.waitForTimeout(700);
    const align = await page.evaluate(() => {
      const ta = document.getElementById("article"), v = document.getElementById("article-view");
      const keep = [v.style.height, v.style.position, v.style.inset];
      v.style.height = "auto"; v.style.position = "relative"; v.style.inset = "auto";
      const heights = { ta: ta.scrollHeight, view: v.scrollHeight };
      [v.style.height, v.style.position, v.style.inset] = keep;
      // the first line of text in the text box and the first mark: the mark must start on a line the text box really has
      const taTop = ta.getBoundingClientRect().top + parseFloat(getComputedStyle(ta).paddingTop);
      const m = document.querySelector("#article-view mark").getBoundingClientRect();
      return { ...heights, markInside: m.top >= taTop - 2 && m.bottom <= ta.getBoundingClientRect().bottom + 2 };
    });
    check(Math.abs(align.ta - align.view) <= 3 && align.markInside, `the highlight layer wraps like the text box (${align.ta} / ${align.view} px)`);
    check((await page.locator("#article-view mark").count()) === 4, "four quotations are marked");
    await page.click('#finding-3 [data-act="approved"]');
    await page.waitForTimeout(400);
    const fx = await page.evaluate(() => { const v = document.getElementById("article-view"), n = v.querySelector(".fix"), l = v.querySelector(".fix-to"); if (!n || !l) return null; const r = n.getClientRects()[0], lr = l.getBoundingClientRect(), vr = v.getBoundingClientRect(); return { under: n.textContent, struck: n.querySelector(".fix-del")?.textContent, label: l.textContent, h: Math.round(lr.height), above: lr.top < r.top, inside: lr.left >= vr.left - 1 && lr.right <= vr.right + 1 }; });
    check(fx && fx.under === "يجزى" && fx.struck === "يجزى" && fx.label === "يوفى" && fx.h > 8 && fx.above && fx.inside && (await page.inputValue("#article")) === readSample("sample-demo"), `an approved «يوفى» is drawn over the struck «يجزى», inside the box, and the box is unchanged (${JSON.stringify(fx)})`);
    await page.evaluate(() => { const ta = document.getElementById("article"); const f = lastResult.findings[3]; const u = W.cpToUnit(ta.value, f.start + 3); ta.focus(); ta.setSelectionRange(u, u); });
    await page.keyboard.type("ز", { delay: 6 });
    await page.waitForTimeout(500);
    check((await page.locator("#article-view mark.stale").count()) === 1 && norm(await page.textContent("#stale-note")).includes("موضع واحد"), "an edit inside a quotation makes it stale");
    await page.click("#recheck-btn");
    await page.waitForFunction(() => !edited(), null, { timeout: 30000 });
    await page.waitForTimeout(400);
    check((await page.inputValue("#revised-text")).includes("يوفى"), "after the recheck the approval of the untouched quotation is still applied");
    if (mobile) {
      // with nothing left to decide, the bar offers the final review and is gone once that review is on screen
      const left = await page.evaluate(() => pendingList().map((f) => `${f.id}:${pendingKind(f)}`));
      // what the recheck asks again (the edited quotation) is settled through the page state; the bar is what is checked here
      await page.evaluate(() => { for (const f of pendingList()) { if (requiredOf(f).length) requiredOf(f).forEach((c) => { decisions[c.id] = "rejected"; }); else reviewed[f.id] = true; } renderAll(); });
      await page.evaluate(() => document.getElementById("final").scrollIntoView({ block: "start" }));
      await page.waitForTimeout(800);
      check(await page.evaluate(() => !pendingList().length && document.getElementById("review-dock").hidden), `phone: with nothing left (was ${left.join(",") || "none"}), the bottom bar is gone while the final review is on screen`);
    }
    check(errors.length === 0, `no page errors ${errors.join(" | ")}`);
    await ctx.close();
  }
  await browser.close();
}
finish(server, null);
