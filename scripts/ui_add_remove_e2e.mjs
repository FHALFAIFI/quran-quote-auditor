// A correction that adds a word the writer left out, or removes a word the writer added: the two choices and the line said after a
// decision name what happens («أضف «ورابطوا»» / «لا تُضِف شيئًا», «احذف «هو»» / «أبقِ «هو»»), never «أبقِ «—»» (internal inspection,
// 5 Oct 2026). The copied text carries exactly the approved change.
//
//   NODE_PATH=<scratch>/node_modules node scripts/ui_add_remove_e2e.mjs [--server URL] [--python PATH]
// Starts its OWN AI-off server unless --server is given (which must have AI off).
import { chromium, check, testServer, openPage, openRow, VIEWPORTS, finish, norm } from "./_ui_common.mjs";

const ARTICLE = "وقد جمع الله الوصية في آية واحدة: يا أيها الذين آمنوا اصبروا وصابروا واتقوا الله لعلكم تفلحون (آل عمران: 200).\n\n"
  + "وقال تعالى: ﴿إن الله هو مع الصابرين﴾ [البقرة: 153].";
const server = await testServer();
const browser = await chromium.launch();
for (const [name, viewport, mobile] of VIEWPORTS) {
  const { page, ctx, errors, audit } = await openPage(browser, server.base, viewport, mobile);
  await page.goto(server.base + "/");
  await audit(ARTICLE);
  const labels = async (id) => page.locator(`[data-change="${id}"] .actions-row button`).allInnerTexts();
  const add = await labels("1-wording");
  await openRow(page, 2);
  const del = await labels("2-wording");
  await openRow(page, 1);
  check(add.join("|") === "أضف «ورابطوا»|لا تُضِف شيئًا", `${name}: the omitted word is offered as an addition (${add.join(" | ")})`);
  check(del.join("|") === "احذف «هو»|أبقِ «هو»", `${name}: the extra word is offered as a removal (${del.join(" | ")})`);
  check(!/«—»/.test(await page.locator("#panel").innerText()), `${name}: no choice or line names «—»`);
  await page.locator('[data-change="1-wording"] button[data-act="approved"]').click();
  check(/^اعتمدتَ إضافة «ورابطوا» \(الاقتباس ١\)/.test(norm(await page.textContent("#undo-line"))), `${name}: the line says the word is added («${norm(await page.textContent("#undo-line")).slice(0, 40)}…»)`);
  await openRow(page, 2);
  await page.locator('[data-change="2-wording"] button[data-act="rejected"]').click();
  check(/^أبقيتَ «هو» كما كتبتَه \(الاقتباس ٢\)/.test(norm(await page.textContent("#undo-line"))), `${name}: keeping the extra word says so`);
  await page.locator('[data-change="2-wording"] button[data-act="approved"]').click();
  check(/^اعتمدتَ حذف «هو» \(الاقتباس ٢\)/.test(norm(await page.textContent("#undo-line"))), `${name}: the line says the word is removed`);
  const card2 = norm(await page.locator("#finding-2").innerText());
  check(/اعتمدتَه: تُحذف «هو» من النسخة المنسوخة/.test(card2) && !/«»/.test(card2), `${name}: the approved removal's note names the word, no empty «»`);
  check(await page.evaluate(() => [...document.querySelectorAll("#article-view .fix-to")].every((l) => l.textContent.trim() !== "")), `${name}: no empty label is drawn above the removed word`);
  // the caret inside the removal: the screen-reader line names what happens, with no empty «»
  await page.evaluate(() => { const t = document.querySelector("#article"); const i = t.value.indexOf("هو مع"); t.focus(); t.setSelectionRange(i + 1, i + 1); t.dispatchEvent(new Event("select")); document.dispatchEvent(new Event("selectionchange")); });
  await page.waitForTimeout(400);
  const said = await page.textContent("#sr-live");
  check(!/«»/.test(said || ""), `${name}: the caret announcement has no empty «» («${norm(said).slice(0, 90)}»)`);
  await page.evaluate(() => { document.querySelector("#final").hidden = false; });
  await page.click("#copy-btn");
  const copied = await page.evaluate(() => navigator.clipboard.readText());
  check(copied.includes("اصبروا وصابروا ورابطوا واتقوا الله") && copied.includes("﴿إن الله مع الصابرين﴾") && copied.includes("واحدة: يا أيها"),
    `${name}: the copy adds «ورابطوا» and removes «هو», nothing else`);
  check(errors.length === 0, `${name}: no page error (${errors.slice(0, 2).join(" | ")})`);
  await ctx.close();
}
finish(server, browser);
