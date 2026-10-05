// A referenced quotation with both a wrong word and an omitted word must offer a source-backed correction.
// Runs on its own AI-off server; no Groq call is possible.
import { chromium, check, testServer, openPage, VIEWPORTS, finish, norm } from "./_ui_common.mjs";

const article = "وقال جل شأنه: ﴿إنما يجزى الصابرون بغير حساب﴾ [الزمر: 10]";
const corrected = article.replace("إنما يجزى الصابرون بغير حساب", "إنما يوفى الصابرون أجرهم بغير حساب");
const server = await testServer();
const browser = await chromium.launch();
for (const [name, viewport, mobile] of VIEWPORTS) {
  const { page, ctx, errors, audit } = await openPage(browser, server.base, viewport, mobile, `FEEDBACK-${name}`);
  await page.goto(server.base + "/");
  await audit(article);
  const card = page.locator("#finding-1");
  check(await card.locator('[data-change="1-wording"] button[data-act="approved"]').count() === 1,
    `${name}: the referenced two-edit quotation offers an approval decision`);
  check(/الزمر.*١٠/.test(norm(await card.innerText())), `${name}: the source verse is identified`);
  const choices = await card.locator('[data-change="1-wording"] .actions-row button').allInnerTexts();
  check(choices.join("|") === "غيّر إلى «يوفى الصابرون أجرهم»|أبقِ «يجزى الصابرون»",
    `${name}: the two choices name the proposed correction (${choices.join(" | ")})`);
  await card.locator('[data-change="1-wording"] button[data-act="approved"]').click();
  check(await page.inputValue("#article") === article, `${name}: approval preserves the draft`);
  await page.evaluate(() => { document.querySelector("#final").hidden = false; });
  await page.click("#copy-btn");
  const copied = await page.evaluate(() => navigator.clipboard.readText());
  check(copied === corrected, `${name}: the copied text has exactly the source-backed replacement and missing word`);
  check(errors.length === 0, `${name}: no page error (${errors.slice(0, 2).join(" | ")})`);
  await ctx.close();
}
finish(server, browser);
