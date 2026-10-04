// Where the verse suggestion box goes (4 Oct): the line being typed must stay in sight beside it, and «أدرج» must be on screen, wherever the
// caret is (near the top, the middle or the bottom of the screen; at the start of a line or at its left edge; a short and a long article) and on
// screens made short the way a phone's keyboard makes them (390×450, 320×360, 320×300). The box keeps its full verse when there is room and
// drops it (the words, the reference and the buttons stay) only when there is not. AI-off server: no model call.
//   NODE_PATH=<scratch>/node_modules node scripts/ui_suggest_place_e2e.mjs [--server URL] [--python PATH]
import { chromium, check, testServer, finish } from "./_ui_common.mjs";

const server = await testServer();
const browser = await chromium.launch();
const FILL = "الصبر والعمل الصالح مفتاح الفرج، وقد تحدث العلماء عن ذلك كثيرا في كتبهم ومجالسهم. ";
const TYPED = "قال تعالى: إن الله يأمركم أن تؤدوا الأمانات";
const SCREENS = [["390×844", 390, 844, true], ["390×450 (keyboard)", 390, 450, true], ["320×640", 320, 640, true], ["320×360 (keyboard)", 320, 360, true], ["320×300 (keyboard)", 320, 300, true], ["1366×860", 1366, 860, false]];
const PLACES = ["top", "middle", "bottom", "short"];

// the caret's line, measured the way the page measures it (a hidden copy of the text up to the caret)
const measure = (page) => page.evaluate(() => {
  const ta = document.getElementById("article"), box = document.getElementById("suggest"), ed = document.getElementById("editor");
  const m = document.createElement("div"); m.className = "caret-mirror ed-text"; ed.append(m);
  m.style.width = ta.clientWidth + "px"; m.textContent = ta.value.slice(0, ta.selectionEnd);
  const p = document.createElement("span"); p.textContent = "​"; m.append(p);
  const er = ed.getBoundingClientRect(), line = { top: er.top + p.offsetTop, bottom: er.top + p.offsetTop + p.offsetHeight }; m.remove();
  const b = box.getBoundingClientRect(), a = box.querySelector(".sg-accept")?.getBoundingClientRect();
  const vh = window.visualViewport ? window.visualViewport.height : innerHeight;
  return { vh, line: [Math.round(line.top), Math.round(line.bottom)], box: [Math.round(b.top), Math.round(b.bottom)],
    overlap: !(b.bottom <= line.top + 1 || b.top >= line.bottom - 1), lineSeen: line.top >= 0 && line.bottom <= vh,
    gap: Math.round(b.top >= line.bottom - 1 ? b.top - line.bottom : line.top - b.bottom),
    accept: !!a && a.top >= 0 && a.bottom <= vh && a.bottom <= b.bottom + 1, compact: box.classList.contains("sg-compact"),
    verse: !!box.querySelector(".sg-verse") && getComputedStyle(box.querySelector(".sg-verse")).display !== "none" };
});

for (const [name, w, h, mobile] of SCREENS) {
  console.log(`\n== ${name}`);
  for (const place of PLACES) for (const edge of [false, true]) {
    const ctx = await browser.newContext({ viewport: { width: w, height: h }, locale: "ar", isMobile: mobile, hasTouch: mobile });
    const page = await ctx.newPage();
    await page.goto(server.base);
    await page.evaluate(() => { localStorage.clear(); sessionStorage.clear(); });
    await page.reload();
    await page.evaluate(() => document.fonts.ready);
    const paras = Array.from({ length: 12 }, () => FILL.repeat(3).trim());
    const lead = edge ? FILL + "وفي هذا المعنى " : "";   // «edge»: the typed words run to the left end of a line and wrap
    const pre = place === "short" ? lead : paras.slice(0, 6).join("\n\n") + "\n\n" + lead;
    const post = place === "short" ? "" : "\n\n" + paras.slice(6).join("\n\n");
    await page.evaluate(([pre, post, place]) => {
      const ta = document.getElementById("article"); ta.value = pre + post; ta.dispatchEvent(new Event("input", { bubbles: true }));
      ta.focus(); ta.setSelectionRange(pre.length, pre.length);
      const m = document.createElement("div"); m.className = "caret-mirror ed-text"; document.getElementById("editor").append(m);
      m.style.width = ta.clientWidth + "px"; m.textContent = pre; const p = document.createElement("span"); p.textContent = "​"; m.append(p);
      const y = ta.getBoundingClientRect().top + scrollY + p.offsetTop; m.remove();
      scrollTo(0, y - innerHeight * ({ top: 0.12, middle: 0.5, bottom: 0.85, short: 0.1 })[place]);
    }, [pre, post, place]);
    await page.waitForTimeout(150);
    await page.keyboard.type(TYPED, { delay: 3 });
    const shown = await page.waitForSelector("#suggest:not([hidden]) .sg-item", { timeout: 15000 }).then(() => true).catch(() => false);
    await page.waitForTimeout(300);
    const m = await measure(page);
    const tag = `${place}${edge ? ", left edge" : ""}`;
    check(shown && !m.overlap && m.lineSeen && m.accept && m.gap >= 0 && m.gap <= 12,
      `${tag}: the typed line stays in sight beside the box, «أدرج» on screen (line ${m.line}, box ${m.box}, gap ${m.gap}, screen ${m.vh}${m.compact ? ", short box" : ""})`);
    if (h >= 640) check(!m.compact && m.verse, `${tag}: with room on screen the box shows the whole verse`);
    // the writer can still insert: the piece goes in where the caret is
    if (place === "middle" && !edge) {
      if (mobile) await page.locator("#suggest .sg-accept").first().tap(); else await page.keyboard.press("Tab");
      await page.waitForTimeout(300);
      check(await page.evaluate((t) => document.getElementById("article").value.includes(t + " إلى أهلها"), TYPED), `${tag}: «أدرج» inserts «إلى أهلها» after the typed words`);
    }
    await ctx.close();
  }
}
// after an audit on a phone the bottom bar is on screen: the box must stay clear of it too, with the typed line in sight
for (const [name, w, h] of [["390×844 after an audit", 390, 844], ["320×640 after an audit", 320, 640]]) {
  console.log(`\n== ${name}`);
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, locale: "ar", isMobile: true, hasTouch: true });
  const page = await ctx.newPage();
  await page.goto(server.base);
  await page.evaluate(() => { localStorage.clear(); sessionStorage.clear(); });
  await page.reload();
  await page.locator("#demo-btn").tap();
  await page.waitForSelector("#panel:not([hidden]) #current article", { timeout: 60000 });
  await page.waitForTimeout(800);
  // the caret at the end of the second paragraph, that line low on the screen, just above the bar
  await page.evaluate(() => {
    const ta = document.getElementById("article"); const i = ta.value.indexOf("\n\n", ta.value.indexOf("\n\n") + 2);
    ta.focus(); ta.setSelectionRange(i, i);
    const m = document.createElement("div"); m.className = "caret-mirror ed-text"; document.getElementById("editor").append(m);
    m.style.width = ta.clientWidth + "px"; m.textContent = ta.value.slice(0, i); const p = document.createElement("span"); p.textContent = "\u200b"; m.append(p);
    const y = ta.getBoundingClientRect().top + scrollY + p.offsetTop; m.remove();
    scrollTo(0, y - innerHeight * 0.78);
  });
  await page.waitForTimeout(200);
  await page.keyboard.type(" قال تعالى: إن الله يأمركم أن تؤدوا الأمانات", { delay: 3 });
  const shown = await page.waitForSelector("#suggest:not([hidden]) .sg-item", { timeout: 15000 }).then(() => true).catch(() => false);
  await page.waitForTimeout(300);
  const m = await measure(page);
  const dock = await page.evaluate(() => { const d = document.getElementById("review-dock"); const r = d.getBoundingClientRect(); return { shown: !d.hidden && r.height > 0 && r.top < innerHeight, top: Math.round(r.top) }; });
  check(shown && dock.shown && m.box[1] <= dock.top && !m.overlap && m.lineSeen && m.accept, `the box stays above the bottom bar and beside the typed line (box ${m.box}, bar top ${dock.top}, line ${m.line})`);
  await ctx.close();
}
finish(server, browser);
