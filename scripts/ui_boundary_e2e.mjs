// Browser check of the uncertain-boundary question (Playwright, Chromium).
//
//   NODE_PATH=<scratch>/node_modules node scripts/ui_boundary_e2e.mjs [--shots DIR] [--server URL] [--python PATH]
//
// A quotation written straight after an ordinary word («فتذكر ومن يتق الله يجعل له مخرجا،») matches the verse, but nothing says whether
// the word before it belongs to the quotation. The card must not call it «matched»; it must ask where the quotation begins, show the
// word in the article and the word in the verse, and settle it in one step: confirm the span as it is, take the neighbouring word into
// the quotation, or choose the words by hand. Each step is reversible. Whatever is chosen, nothing in the article changes.
import { chromium, check, norm, testServer, openPage, finish } from "./_ui_common.mjs";

const quote = "ومن يتق الله يجعل له مخرجا";
const article = `إذا ضاقت بك السبل فتذكر ${quote}، واطلب المزيد.`;
const server = await testServer();
const browser = await chromium.launch();
for (const [name, vp, mobile] of [["desktop", { width: 1280, height: 900 }, false], ["phone", { width: 390, height: 844 }, true]]) {
  console.log(`\n== ${name}`);
  const { page, errors, shot, overflowX, audit } = await openPage(browser, server.base, vp, mobile, `b-${name}`);
  await page.goto(server.base);
  await page.evaluate(() => sessionStorage.clear());
  await audit(article);
  const card = page.locator("#current article");
  check((await page.locator("#queue li").count()) === 1, "one quotation");
  check(norm(await card.locator(".f-head .state").textContent()).includes("حدود الاقتباس غير محسومة"), "the single state word says the boundary is not settled");
  check((await card.locator(".state.done").count()) === 0 && !norm(await card.locator(".f-head").textContent()).includes("مطابق"), "the card's state does not say «matched»");
  const ask = card.locator(".ask.bounds");
  check(norm(await ask.locator(".q-title").textContent()) === "أين يبدأ الاقتباس؟", "the question is «أين يبدأ الاقتباس؟»");
  const text = norm(await ask.textContent());
  check(text.includes("فتذكر") && /وفي الآية: الآخر/.test(text), "it shows the word in the article and the word in the verse");
  const btns = await ask.locator("button").allTextContents();
  check(btns.map(norm).join("|") === "«فتذكر» من الاقتباس|نعم، هذا هو الاقتباس كاملًا|حدّد الكلمات بنفسك|ليس اقتباسًا", `the choices are plain (${btns.map(norm).join(" | ")})`);
  check(norm(await card.locator(".ctx").first().textContent()).includes("فتذكر " + quote), "the quoted words are shown in the sentence");
  check((await card.locator(".where a").first().getAttribute("href")).includes("quranpedia"), "the verse's source link is on the card");
  await shot("1-uncertain");

  // by hand: the span editor, one tap on the word before
  await ask.locator('[data-act="adjust-bounds"]').click();
  check((await page.locator(".span-editor .w.in").count()) === 6 && (await page.locator(".span-editor .w.out").count()) > 0, "the editor lists the words around the span; six are inside");
  await page.locator(".span-editor .w", { hasText: "فتذكر" }).click();
  check((await page.locator(".span-editor .w.in").count()) === 7, "tapping the word before adds it");
  await page.locator(".span-editor .w", { hasText: "فتذكر" }).click();
  check((await page.locator(".span-editor .w.in").count()) === 6, "tapping the first word inside takes it out again");
  await shot("2-editor");
  await page.locator(".span-editor .w", { hasText: "فتذكر" }).click();
  await page.click('[data-act="check-span"]');
  await page.waitForFunction(() => document.querySelector("#current .ctx mark")?.textContent.startsWith("فتذكر"), null, { timeout: 30000 });
  check((await page.locator("#current .ask.bounds").count()) === 0, "a span chosen by hand raises no boundary question");
  check(/ثبّتَّ حدود الاقتباس/.test(norm(await page.textContent("#undo-line"))), "the page says the boundary was fixed, with «تراجع»");
  check((await page.inputValue("#revised-text")) === article, "nothing in the article changed");
  await shot("3-after-editor");
  await page.locator("#undo-line button").click();
  await page.waitForSelector("#current .ask.bounds");
  check(norm(await page.textContent("#current .ask.bounds .q-title")) === "أين يبدأ الاقتباس؟", "«تراجع» brings the original question back");

  // one tap: «فتذكر» is part of the quotation
  await page.locator('[data-act="extend-start"]').click();
  await page.waitForFunction(() => document.querySelector("#current .ctx mark")?.textContent.startsWith("فتذكر"), null, { timeout: 30000 });
  check((await page.locator("#current .ask.bounds").count()) === 0, "«فتذكر» من الاقتباس: the span now includes the word and the question is gone");
  await page.locator("#undo-line button").click();
  await page.waitForSelector("#current .ask.bounds");

  // confirm as it is
  await page.locator('[data-act="confirm-bounds"]').click();
  await page.waitForSelector("#current .ask.bounds", { state: "detached", timeout: 30000 });
  const done = page.locator("#current article");
  check(norm(await done.locator(".f-head .state").textContent()).includes("مطابق للمصحف"), "after «نعم، هذا هو الاقتباس كاملًا» the wording reads matched");
  check(norm(await done.locator(".ctx mark").textContent()) === quote, "the span itself is unchanged");
  check(/ثبّتَّ حدود الاقتباس/.test(norm(await page.textContent("#undo-line"))), "this too can be taken back");
  check(norm(await page.textContent("#final-summary")).includes("لم تعتمد أي تغيير"), "the final check says the article is copied as written");
  check((await page.inputValue("#revised-text")) === article, "the article is unchanged");
  await shot("4-confirmed");
  check((await overflowX()) <= 1, "no horizontal overflow");
  check(errors.length === 0, `no page errors${errors.length ? ": " + errors.join(" | ") : ""}`);
}
finish(server, browser);
