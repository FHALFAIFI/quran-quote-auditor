// Browser check of verse suggestion while writing (Playwright, Chromium): when it speaks, explicit acceptance (Tab, click, tap), dismissal,
// the probable correction «لعبادتي ← ليعبدون», several choices, stale answers, insertion boundaries in right-to-left text, Ctrl+Z, the
// «أكمل من المصحف» action, composition, and the same at 390 and 320 px. The server is AI-off; no suggestion ever involves a model.
//
//   NODE_PATH=<scratch>/node_modules node scripts/ui_suggest_e2e.mjs [--shots DIR] [--server URL] [--python PATH]
import { chromium, check, norm, VIEWPORTS, testServer, openPage, finish } from "./_ui_common.mjs";

const server = await testServer();
const browser = await chromium.launch();
const LEAD = "الصبر خلق عظيم. قال تعالى: ";
const SIX = "وما خلقت الجن والإنس إلا";

// Type into the editor like a writer (key events, not fill) and wait for the debounce + answer.
const typeText = async (page, text) => { await page.keyboard.type(text, { delay: 4 }); };
const boxState = (page) => page.evaluate(() => {
  const b = document.getElementById("suggest");
  if (!b || b.hidden) return null;
  return { text: b.innerText.replace(/\s+/g, " ").trim(), items: b.querySelectorAll(".sg-item").length, selected: b.querySelectorAll(".sg-item.sel").length, rect: b.getBoundingClientRect().toJSON() };
});
// resolves when an answer is on screen (the «searching» line of an explicit request is not an answer)
const waitBox = (page, timeout = 4000) => page.waitForFunction(() => { const b = document.getElementById("suggest"); return b && !b.hidden && (b.querySelector(".sg-item") || (b.querySelector(".sg-msg") && !/جارٍ البحث/.test(b.textContent))); }, null, { timeout }).then(() => true).catch(() => false);
const value = (page) => page.inputValue("#article");
const reset = async (page) => { await page.evaluate(() => { sessionStorage.clear(); localStorage.clear(); }); await page.reload(); await page.click("#article"); };

for (const [name, vp, mobile] of VIEWPORTS) {
  console.log(`\n== ${name} ${vp.width}x${vp.height}: suggestions`);
  const { page, errors, shot, overflowX } = await openPage(browser, server.base, vp, mobile, `SG-${name}`);
  const requests = [];
  page.on("request", (r) => { if (r.url().endsWith("/api/suggest")) requests.push(JSON.parse(r.postData() || "{}")); });
  await page.goto(server.base);
  await reset(page);

  // 1. the example of the brief: after a lead-in the next word is offered, with its place, and nothing is inserted yet
  await typeText(page, LEAD + SIX);
  check(await waitBox(page), "after «قال تعالى» and the beginning of a verse a suggestion appears");
  let st = await boxState(page);
  check(st && st.text.includes("ليعبدون") && /الذاريات/.test(st.text) && /٥٦/.test(st.text), `it offers «ليعبدون» with the surah and ayah (${st?.text.slice(0, 90)})`);
  check(st && /من نص قرآنبيديا/.test(st.text), "it says where the words come from");
  check((await value(page)) === LEAD + SIX, "nothing is inserted until the writer accepts");
  check(st && st.rect.left >= -1 && st.rect.right <= vp.width + 1 && (await overflowX()) <= 1, "the box stays inside the screen");
  await shot("1-offer");
  // the suggestion box is announced and reachable without taking the caret away
  check(await page.evaluate(() => document.activeElement.id === "article"), "the caret stays in the text");
  await page.waitForFunction(() => /اقتراح من المصحف/.test(document.getElementById("sr-live").textContent), null, { timeout: 2000 }).catch(() => {});
  const live = await page.evaluate(() => document.getElementById("sr-live").textContent);
  check(/اقتراح من المصحف/.test(live) && /Tab/.test(live), `it is announced to screen readers with the keys («${live.slice(0, 60)}»)`);

  // 2. Tab inserts it, exactly once, at the caret; Ctrl+Z takes it back
  await page.keyboard.press("Tab");
  await page.waitForTimeout(150);
  check((await value(page)) === LEAD + SIX + " ليعبدون", `Tab inserts the word at the caret (${await value(page)})`);
  check((await boxState(page)) === null, "the box closes after accepting");
  check(await page.evaluate(() => document.activeElement.id === "article"), "the caret is still in the text after accepting");
  await page.keyboard.press(process.platform === "darwin" ? "Meta+z" : "Control+z");
  await page.waitForTimeout(150);
  check((await value(page)) === LEAD + SIX, "Ctrl/Cmd+Z takes the insertion back in one step");

  // 3. Escape dismisses and the text is untouched; the same suggestion does not come straight back
  await page.keyboard.press("End");
  await page.keyboard.type(" ", { delay: 4 }); await page.keyboard.press("Backspace");
  await waitBox(page);
  await page.keyboard.press("Escape");
  check((await boxState(page)) === null && (await value(page)) === LEAD + SIX, "Escape dismisses the suggestion and leaves the text as it was");
  await page.waitForTimeout(500);
  check((await boxState(page)) === null, "a dismissed suggestion does not reappear on its own");

  // 4. typing on dismisses
  await page.keyboard.type(" ل", { delay: 4 });
  check((await boxState(page)) === null || /ليعبدون/.test((await boxState(page)).text), "typing on removes the old suggestion at once (a new one may follow)");
  await page.keyboard.press("Escape");

  // 5. the probable correction, never silently applied
  await reset(page);
  await typeText(page, LEAD + SIX + " لعبادتي");
  check(await waitBox(page), "a wrong last word gets a suggestion");
  st = await boxState(page);
  check(st && /لعبادتي/.test(st.text) && /ليعبدون/.test(st.text) && /احتمال/.test(st.text), `it is shown as «لعبادتي ← ليعبدون», a possibility (${st?.text.slice(0, 100)})`);
  check((await value(page)) === LEAD + SIX + " لعبادتي", "the correction is not applied by itself");
  await page.keyboard.press("Tab");
  await page.waitForTimeout(150);
  check((await value(page)) === LEAD + SIX + " ليعبدون", `accepting replaces only the wrong word (${await value(page)})`);

  // 6. several verses: nothing preselected, arrows choose, Tab does nothing until a choice
  await reset(page);
  await typeText(page, LEAD + "يا أيها الذين آمنوا كتب");
  check(await waitBox(page), "ambiguous words give choices");
  st = await boxState(page);
  check(st && st.items >= 2 && st.selected === 0 && /أكثر من آية/.test(st.text), `two or more verses are listed and none is preselected (${st?.items} items)`);
  const before6 = await value(page);
  await page.keyboard.press("Tab");
  await page.waitForTimeout(150);
  check((await value(page)) === before6, "Tab on an unchosen list inserts nothing (focus moves on as usual)");
  await reset(page);
  await typeText(page, LEAD + "يا أيها الذين آمنوا كتب");
  await waitBox(page);
  await page.keyboard.press("ArrowDown");
  st = await boxState(page);
  check(st && st.selected === 1, "ArrowDown selects the first verse and shows it");
  await shot("2-choices");
  await page.keyboard.press("Tab");
  await page.waitForTimeout(150);
  const v6 = await value(page);
  check(v6.startsWith(LEAD + "يا أيها الذين آمنوا كتب ") && v6.length > (LEAD + "يا أيها الذين آمنوا كتب ").length + 3, `Tab then inserts the chosen verse's next words only (${v6.slice(-40)})`);
  check(Array.from(v6.slice((LEAD + "يا أيها الذين آمنوا كتب ").length).trim().split(/\s+/)).length <= 5, "a short excerpt, not the whole verse");

  // 7. ordinary prose: nothing is asked of the server and nothing shown
  await reset(page);
  const n0 = requests.length;
  await typeText(page, "الحمد لله رب العالمين، ونحن نعمل على أن يكون الصبر على الأذى طريقًا إلى الخير");
  await page.waitForTimeout(700);
  check(requests.length === n0 && (await boxState(page)) === null, "ordinary prose with common Quran words sends nothing to the server and shows nothing");
  // a hadith cue: asked for nothing (no Quran cue in the sentence)
  await reset(page);
  const n1 = requests.length;
  await typeText(page, "قال رسول الله ﷺ: " + SIX);
  await page.waitForTimeout(700);
  check(requests.length === n1 && (await boxState(page)) === null, "after a hadith cue nothing is sent or shown");

  // 8. a slow answer for text that has since changed is never shown; the old request is cancelled
  await reset(page);
  let held = 0, aborted = 0;
  page.on("requestfailed", (r) => { if (r.url().endsWith("/api/suggest")) aborted++; });
  await page.route("**/api/suggest", async (route) => { if (++held === 1) { await new Promise((r) => setTimeout(r, 1500)); } try { await route.continue(); } catch { /* the page cancelled it */ } });
  await typeText(page, LEAD + SIX);
  await page.waitForFunction(() => true);
  await page.waitForTimeout(450);                 // the debounce has fired: request 1 is out and held
  await page.keyboard.type(" و", { delay: 4 });  // the text changes; the verse is no longer being continued
  await page.waitForTimeout(2300);                // request 1 would have been answered by now
  check((await boxState(page)) === null || !/ليعبدون/.test((await boxState(page)).text), "the late answer for older text is not shown");
  check(aborted >= 1, `the superseded request was cancelled (${aborted} cancelled)`);
  await page.unroute("**/api/suggest");
  await reset(page);
  await typeText(page, LEAD + SIX);
  await waitBox(page);
  await page.keyboard.press("ArrowRight");   // right-to-left: ArrowRight moves back (ArrowLeft at the end of the text would not move)
  await page.waitForTimeout(150);
  check((await boxState(page)) === null, "moving the caret closes the suggestion");

  // 9. insertion in the middle of a text, RTL: what follows the caret is untouched
  await reset(page);
  const tail = " وهذه جملة بعدها.";
  await page.fill("#article", LEAD + SIX + tail);
  await page.evaluate((n) => { const ta = document.getElementById("article"); ta.focus(); ta.setSelectionRange(n, n); }, (LEAD + SIX).length);
  await page.click("#complete-btn");
  check(await waitBox(page), "«أكمل من المصحف» works with text after the caret");
  await page.keyboard.press("Tab");
  await page.waitForTimeout(200);
  check((await value(page)) === LEAD + SIX + " ليعبدون" + tail, `the insertion keeps the text after the caret exactly (${(await value(page)).slice(-30)})`);

  // 10. the explicit action explains itself when it has nothing, and works without a cue
  await reset(page);
  await page.fill("#article", "نقرأ في المصحف آية بدايتها لقد جاءكم ");
  await page.evaluate(() => { const ta = document.getElementById("article"); ta.focus(); ta.setSelectionRange(ta.value.length, ta.value.length); });
  await page.click("#complete-btn");
  check(await waitBox(page), "«أكمل من المصحف» answers without any lead-in");
  st = await boxState(page);
  check(st && /رسول من أنفسكم|التوبة/.test(st.text), `it offers the next words of the verse (${st?.text.slice(0, 70)})`);
  await page.keyboard.press("Escape");
  await page.fill("#article", "الذين ");
  await page.evaluate(() => { const ta = document.getElementById("article"); ta.focus(); ta.setSelectionRange(ta.value.length, ta.value.length); });
  await page.click("#complete-btn");
  await waitBox(page);
  st = await boxState(page);
  check(st && /اكتب كلمتين|شائعة|كلمة/.test(st.text) && st.items === 0, `with one word it says what to add instead of guessing (${st?.text.slice(0, 60)})`);

  // 11. the option to switch it off, and a composition in progress
  await reset(page);
  await page.evaluate(() => { document.getElementById("options").open = true; });
  await page.uncheck("#opt-suggest");
  const n2 = requests.length;
  await typeText(page, LEAD + SIX);
  await page.waitForTimeout(700);
  check(requests.length === n2 && (await boxState(page)) === null, "with suggestions switched off nothing is sent while typing");
  await page.click("#complete-btn");
  check(await waitBox(page), "the explicit action still works when automatic suggestions are off");
  await page.check("#opt-suggest");

  // 11a. «auto off» means nothing is sent while typing, even if the opt-in «distinct» box was ticked before
  await reset(page);
  await page.evaluate(() => { document.getElementById("options").open = true; });
  await page.check("#opt-distinct");
  await page.uncheck("#opt-suggest");
  const n4 = requests.length;
  await typeText(page, "وما خلقت الجن والإنس إلا");
  await typeText(page, " " + LEAD + SIX);
  await page.waitForTimeout(800);
  check(requests.length === n4 && (await boxState(page)) === null, "with automatic suggestions off nothing is sent while typing, even with «العبارة المميزة» ticked");
  await page.uncheck("#opt-distinct");
  await page.check("#opt-suggest");

  // 11c. the «searching» line does not outlive an answer that is dropped because the caret moved
  await reset(page);
  await page.route("**/api/suggest", async (route) => { await new Promise((r) => setTimeout(r, 1500)); try { await route.continue(); } catch { /* cancelled */ } });
  await page.fill("#article", LEAD + SIX);
  await page.evaluate(() => { const ta = document.getElementById("article"); ta.focus(); ta.setSelectionRange(ta.value.length, ta.value.length); });
  await page.click("#complete-btn");
  await page.waitForTimeout(300);
  check((await boxState(page))?.text.includes("جارٍ البحث"), "an explicit request shows that it is searching");
  await page.waitForTimeout(500);
  check((await boxState(page))?.text.includes("جارٍ البحث"), "the «searching» line stays while a slow answer is awaited (it is not hidden by the focus going back to the text)");
  check(await waitBox(page, 5000) && (await boxState(page)).items >= 1, "and the slow answer is shown when it arrives");
  await page.keyboard.press("Escape");
  await page.click("#complete-btn");
  await page.waitForTimeout(200);
  await page.keyboard.press("ArrowRight");
  await page.waitForTimeout(2200);
  check((await boxState(page)) === null, "the «searching» line is gone once the caret has moved and the answer was dropped");
  await page.unroute("**/api/suggest");

  // 11b. an input-method composition in progress is left alone, and answered once it ends
  await reset(page);
  const n3 = requests.length;
  await page.evaluate(() => document.getElementById("article").dispatchEvent(new CompositionEvent("compositionstart", { bubbles: true })));
  await page.keyboard.insertText(LEAD + SIX);
  await page.waitForTimeout(700);
  check(requests.length === n3 && (await boxState(page)) === null, "while a composition is in progress nothing is sent and nothing is shown");
  await page.evaluate(() => document.getElementById("article").dispatchEvent(new CompositionEvent("compositionend", { bubbles: true })));
  check(await waitBox(page), "when the composition ends the suggestion is asked for and shown");

  // 12. touch: tapping «أدرج» inserts, the keyboard stays up (the button never takes focus)
  if (mobile) {
    await reset(page);
    await typeText(page, LEAD + SIX);
    await waitBox(page);
    const btn = page.locator("#suggest .sg-accept").first();
    const bb = await btn.boundingBox();
    check(bb && bb.height >= 44 && bb.width >= 44, `the accept button is at least 44 px (${Math.round(bb?.width)}×${Math.round(bb?.height)})`);
    await shot("3-touch");
    await btn.tap();
    await page.waitForTimeout(200);
    check((await value(page)) === LEAD + SIX + " ليعبدون" && (await page.evaluate(() => document.activeElement.id)) === "article", "a tap inserts the word and leaves the caret in the text");
  } else {
    await reset(page);
    await typeText(page, LEAD + SIX);
    await waitBox(page);
    await page.locator("#suggest .sg-accept").first().click();
    await page.waitForTimeout(200);
    check((await value(page)) === LEAD + SIX + " ليعبدون", "a click on «أدرج» inserts the word");
  }

  // 13. (4 Oct) the first insertion stops before the next clause; the rest of the verse stays one action away
  const accept = async () => { if (mobile) await page.locator("#suggest .sg-accept").first().tap(); else await page.keyboard.press("Tab"); await page.waitForTimeout(200); };
  const AMANAT = "إن الله يأمركم أن تؤدوا الأمانات";
  await reset(page);
  await typeText(page, LEAD + AMANAT);
  check(await waitBox(page), "4:58: a suggestion appears after «… أن تؤدوا الأمانات»");
  st = await boxState(page);
  const added = await page.evaluate(() => [...document.querySelectorAll("#suggest .w-add")].map((n) => n.textContent).join(" "));
  check(st && /إلى أهلها/.test(st.text) && !/وإذا حكمتم ب?/.test(st.text.split("النساء")[0]), `it offers «إلى أهلها», not «إلى أهلها وإذا حكمتم» (${st?.text.slice(0, 60)})`);
  check(added === "إِلَىٰ أَهْلِهَا", `the verse line marks exactly the two words to be inserted («${added}»)`);
  check(st && /يُدرَج حتى «أهلها»، ثم نقترح ما يليه من الآية/.test(st.text), "before accepting, the box says where the insertion stops and that the rest follows");
  await shot("4-short-piece");
  await accept();
  check((await value(page)) === LEAD + AMANAT + " إلى أهلها", `${mobile ? "a tap" : "Tab"} inserts «إلى أهلها» and nothing after it (${(await value(page)).slice(-30)})`);
  check(await page.evaluate(() => document.activeElement.id === "article"), "the caret stays in the text");
  check(await waitBox(page), "the next piece of the verse is offered at once");
  st = await boxState(page);
  check(st && /وإذا حكمتم بين الناس/.test(st.text) && /حتى «الناس»/.test(st.text), `the next piece is «وإذا حكمتم بين الناس» (${st?.text.slice(0, 60)})`);
  await page.keyboard.press("Escape");
  check((await boxState(page)) === null && (await value(page)) === LEAD + AMANAT + " إلى أهلها", "Escape stops there: the writer keeps exactly «… إلى أهلها»");
  // the whole verse on request
  await reset(page);
  await typeText(page, LEAD + AMANAT);
  await waitBox(page);
  if (mobile) await page.locator("#suggest .sg-extend").first().tap(); else await page.locator("#suggest .sg-extend").first().click();
  await page.waitForTimeout(200);
  check((await value(page)).endsWith(" إلى أهلها وإذا حكمتم بين الناس أن تحكموا بالعدل إن الله نعما يعظكم به إن الله كان سميعا بصيرا"), "«إلى نهاية الآية» inserts the rest of the verse, from the source");
  await page.waitForTimeout(500);
  check((await boxState(page)) === null, "after the verse end nothing more is offered");
  // the explicit action without a cue: the follow-up comes quietly, as the writer asked for the first piece
  await reset(page);
  await typeText(page, AMANAT);
  await page.waitForTimeout(400);
  check((await boxState(page)) === null, "without a cue nothing is offered while typing");
  await page.locator("#complete-btn").click();
  check(await waitBox(page), "«أكمل من المصحف» offers the first piece");
  await accept();
  check((await value(page)) === AMANAT + " إلى أهلها", `the explicit request inserts the same short piece (${(await value(page)).slice(-20)})`);
  check(await waitBox(page) && /وإذا حكمتم/.test((await boxState(page))?.text || ""), "and the next piece follows without another request");
  // an ambiguous beginning: each verse's own short piece, nothing chosen for the writer
  await reset(page);
  await typeText(page, LEAD + "﴿إن الله يأمركم");
  await waitBox(page);
  st = await boxState(page);
  check(st && st.items === 2 && st.selected === 0 && /أن تذبحوا بقرة/.test(st.text) && /أن تؤدوا الأمانات/.test(st.text) && !/بقرة قالوا/.test(st.text) && !/الأمانات إلى/.test(st.text),
    `«﴿إن الله يأمركم»: two verses, none preselected, each piece short (${st?.text.slice(0, 120)})`);
  if (!mobile) {
    await page.keyboard.press("ArrowDown");   // (Tab with nothing chosen inserts nothing: section 6)
    await page.keyboard.press("Tab");
  } else {
    await page.locator("#suggest .sg-item").first().getByRole("button", { name: "اعرض الآية" }).tap();
    await page.waitForTimeout(150);
    await page.locator("#suggest .sg-accept").first().tap();
  }
  await page.waitForTimeout(200);
  check((await value(page)) === LEAD + "﴿إن الله يأمركم أن تذبحوا بقرة", `the chosen verse's piece is inserted, ending before «قالوا» (${(await value(page)).slice(-25)})`);
  // punctuation: inside «…» and after a comma the piece is the same, with one space before it
  for (const typed of ["«" + AMANAT, AMANAT + "،"]) {
    await reset(page);
    await typeText(page, LEAD + typed);
    await waitBox(page);
    await accept();
    check((await value(page)) === LEAD + typed + " إلى أهلها", `after «${typed.slice(0, 2)}…${typed.slice(-3)}» the piece is inserted with one space`);
  }
  // a short verse: the rest is the verse end, and the box promises nothing more
  await reset(page);
  await typeText(page, LEAD + "إنا أعطيناك");
  await waitBox(page);
  st = await boxState(page);
  check(st && /الكوثر/.test(st.text) && !(await page.$("#suggest .sg-extend")) && !(await page.$("#sg-next")), "«إنا أعطيناك»: «الكوثر» alone, no «إلى نهاية الآية» and no «ثم نقترح»");
  await accept();
  check((await value(page)) === LEAD + "إنا أعطيناك الكوثر", "it is inserted, and nothing follows");
  check(errors.length === 0, `no console errors ${errors.join(" | ")}`);
}
finish(server, browser);
