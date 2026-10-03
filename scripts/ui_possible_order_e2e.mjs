// A phrase that may be a quotation does not lead the queue (4 Oct). In the long article LA01 («العلم الذي ينفع») the first open item was the
// ordinary prose «في كل عام» (an exact but common phrase, tier «possible», code «common»). Such phrases stay marked, listed and reachable; they
// wait behind the concrete decisions under their own name, and the headline does not count them as quotations found. Detection is unchanged.
// AI-off server: no model call.
//   NODE_PATH=<scratch>/node_modules node scripts/ui_possible_order_e2e.mjs [--shots DIR] [--server URL] [--python PATH]
import fs from "fs";
import path from "path";
import { chromium, check, norm, root, testServer, openPage, finish } from "./_ui_common.mjs";

const server = await testServer();
const browser = await chromium.launch();
const LA01 = JSON.parse(fs.readFileSync(path.join(root, "eval/articles_long_20261003.json"), "utf8")).cases[0].article;

for (const [name, vp, mobile] of [["desktop", { width: 1366, height: 900 }, false], ["phone", { width: 390, height: 844 }, true]]) {
  console.log(`\n== ${name} ${vp.width}x${vp.height}: possible phrases after the decisions`);
  const { page, errors, shot, overflowX, audit } = await openPage(browser, server.base, vp, mobile, `PO-${name}`);
  await page.goto(server.base);
  await page.evaluate(() => { sessionStorage.clear(); localStorage.clear(); });
  await page.reload();
  await audit(LA01);
  await page.waitForTimeout(600);

  const verdict = norm(await page.textContent("#verdict"));
  check(/وجدنا ٢٠ اقتباسًا؛ تحتاج ١٠ منها إلى قرارك/.test(verdict), `the headline counts the 20 quotations, not the 7 phrases («${verdict.slice(0, 60)}»)`);
  check(/و٧ عبارات تشبه آيات ولم نتأكد أنها اقتباسات، تنتظر تأكيدك/.test(verdict), "and says the 7 phrases apart, unconfirmed");
  const progress = norm(await page.textContent("#panel-progress"));
  check(progress.startsWith("١٠ اقتباسات تنتظر قرارك، و٧ عبارات للتأكيد"), `the panel says the same («${progress}»)`);
  check(/ — [٠-٩]+ من [٠-٩]+$/.test(progress) && !/·/.test(progress), "the position is set off by a dash, not a middle dot (which reads as an Arabic zero beside a digit)");

  const first = await page.evaluate(() => { const c = document.querySelector("#current article"); return { id: c.id, quote: c.querySelector(".q-hit")?.textContent, state: c.querySelector(".f-head .state")?.textContent }; });
  check(first.quote !== "في كل عام" && first.state !== "يحتاج تأكيدك", `the first card is a concrete decision, not «في كل عام» (${first.id}: ${first.state})`);
  await shot("1-first");

  // still there: the mark in the text, the row in its own group, the state word of a possible quotation
  check((await page.locator('#article-view mark[data-id="1"].need.possible').count()) === 1, "«في كل عام» is still marked in the article (dotted, «possible»)");
  const groups = await page.$$eval("#queue summary", (n) => n.map((x) => x.textContent.trim()));
  check(groups.includes("عبارات للتأكيد: قد تكون اقتباسات (٧)"), `it is listed in its own group (${groups.join(" | ")})`);
  check(norm(await page.textContent(".q-group.maybe #row-1")).includes("يحتاج تأكيدك"), "its row says «يحتاج تأكيدك»");
  check((await page.locator("#queue li").count()) === 27, "all 27 findings are still listed");

  // «التالي» walks the ten decisions first, then reaches the phrases
  const seen = [];
  for (let i = 0; i < 10; i++) {
    seen.push(await page.evaluate(() => document.querySelector("#current article").id));
    await page.locator(mobile ? "#dock-next" : "#next-btn").click();
    await page.waitForTimeout(250);
  }
  const weakIds = await page.$$eval(".q-group.maybe li button", (b) => b.map((x) => `finding-${x.id.slice(4)}`));
  check(new Set(seen).size === 10 && !seen.some((id) => weakIds.includes(id)), `«التالي» visits the ten decisions, none of the phrases (${seen.join(",")})`);
  const eleventh = await page.evaluate(() => document.querySelector("#current article").id);
  check(eleventh === seen[0], "after the tenth it comes back round to the first decision while decisions remain");
  // once no decision is left, the phrases come next: dismiss / keep the ten here by deciding through the page state
  await page.evaluate(() => {
    for (const f of activeFindings()) if (pendingKind(f) && !weakPending(f)) {
      if (requiredOf(f).length) requiredOf(f).forEach((c) => { decisions[c.id] = "rejected"; });
      else dismissed[f.id] = true;
    }
    renderAll();
  });
  await page.locator(mobile ? "#dock-next" : "#next-btn").click().catch(() => {});
  await page.waitForTimeout(300);
  const cur = await page.evaluate(() => { const c = document.querySelector("#current article"); return { id: c.id, state: c.querySelector(".f-head .state")?.textContent }; });
  check(weakIds.includes(cur.id) && cur.state === "يحتاج تأكيدك", `with the decisions done, «التالي» goes to the phrases (${cur.id})`);
  check(norm(await page.textContent("#panel-progress")).startsWith("٧ عبارات للتأكيد"), "the panel now names only the phrases");
  if (mobile) check(norm(await page.textContent("#dock-text")) === "٧ عبارات للتأكيد", "and so does the bottom bar");
  const head = norm(await page.textContent("#final-pending h3"));
  check(head.startsWith("٧ عبارات للتأكيد — وسيبقى كما كتبتَه"), `the final review lists them as unconfirmed, copied as written («${head}»)`);
  check(await page.evaluate(() => document.getElementById("copy-btn").classList.contains("ready")), "copying is ready: nothing in the phrases changes the text unless the writer confirms one");
  // settling a phrase updates the headline too (it counted 7)
  await page.locator("#current .not-quote").first().click();
  await page.waitForTimeout(500);
  check(/و٦ عبارات تشبه آيات/.test(norm(await page.textContent("#verdict"))), `after dismissing one phrase the headline says 6 («${norm(await page.textContent("#verdict")).slice(0, 90)}»)`);
  // with one phrase left «التالي» would only reopen it: it is not offered
  await page.evaluate(() => { const w = weakPendingList(); for (const f of w.slice(0, w.length - 2)) dismissed[f.id] = true; renderAll(); goTo(weakPendingList()[0].id, { scroll: null }); });
  check(!(await page.isHidden("#panel-nav")), "with two phrases left «التالي» is offered");
  await page.evaluate(() => { dismissed[weakPendingList()[1].id] = true; renderAll(); goTo(weakPendingList()[0].id, { scroll: null }); });
  check(await page.isHidden("#panel-nav"), "with only the open one left, «التالي» and «السابق» are not shown (they would reopen it)");
  await page.evaluate(() => { delete dismissed[allFindings().filter((f) => dismissed[f.id] && isWeak(f)).pop().id]; renderAll(); });
  await page.evaluate(() => copyRevised());
  await page.waitForTimeout(400);
  check(/وعبارتان للتأكيد نُسختا كما كتبتَهما/.test(norm(await page.textContent("#copy-note"))), `the copy note says two phrases in the dual («${norm(await page.textContent("#copy-note")).slice(0, 80)}»)`);
  const rec = await page.evaluate(() => { window.dispatchEvent(new Event("beforeprint")); const t = document.getElementById("print-record").innerText;
    const n = R.unresolvedFindings(activeFindings(), decisions).filter((f) => !weakPending(f)).length; return { t, n, all: R.unresolvedFindings(activeFindings(), decisions).length }; });
  check(/عبارات تشبه آيات لم يؤكّدها المحرر \(لم يتغيّر فيها شيء\)/.test(rec.t) && rec.t.includes(`غير محسومة ${rec.n} `) && rec.n < rec.all, `the record lists the phrases on their own and counts ${rec.n} unresolved quotations, not ${rec.all}`);
  await shot("2-phrases");
  check((await overflowX()) <= 1, "no sideways scroll");
  check(errors.length === 0, `no console errors ${errors.join(" | ")}`);
}
finish(server, browser);
