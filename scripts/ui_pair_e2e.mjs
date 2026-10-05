// An unmarked two-word quotation (5 Oct, app/phrases.find_pairs) is offered as an optional confirmation: listed apart from the decisions,
// no replacement and no change before the writer picks the verse; everyday pairs in the same article («حياة طيبة», «جملة واحدة») are not listed.
// AI-off server: no model call.
//   NODE_PATH=<scratch>/node_modules node scripts/ui_pair_e2e.mjs [--shots DIR] [--server URL] [--python PATH]
import { chromium, check, norm, testServer, openPage, openRow, finish, VIEWPORTS } from "./_ui_common.mjs";

const article = "في زحمة الحياة ننسى أحيانًا ما يهم. فاستبقوا الخيرات قبل أن يفوت الوقت، وكونوا لأهلكم سندًا. ونتمنى للجميع حياة طيبة، "
  + "وتكفي جملة واحدة صادقة لتصلح يومًا كاملًا.\n\nقال تعالى: ﴿إن الله مع الصابرين﴾ [البقرة: 153].";
const server = await testServer();
const browser = await chromium.launch();
for (const [name, vp, mobile] of VIEWPORTS) {
  console.log(`\n== ${name} ${vp.width}x${vp.height}`);
  const { page, ctx, errors, shot, overflowX, audit } = await openPage(browser, server.base, vp, mobile, `PAIR-${name}`);
  await page.goto(server.base);
  await page.evaluate(() => { sessionStorage.clear(); localStorage.clear(); });
  await page.reload();
  await audit(article);
  const rows = await page.$$eval("#queue li", (n) => n.map((x) => x.textContent.replace(/\s+/g, " ").trim()));
  check(rows.length === 2, `two findings: the marked verse and the pair (${rows.join(" | ")})`);
  check(!rows.some((r) => /حياة طيبة|جملة واحدة/.test(r)), "the everyday pairs are not listed");
  const groups = await page.$$eval("#queue summary", (n) => n.map((x) => x.textContent.trim()));
  check(groups.some((g) => /^عبارات للتأكيد \(اختياري\)/.test(g)), `the pair is in the optional group (${groups.join(" | ")})`);
  const pairId = await page.evaluate(() => lastResult.findings.find((f) => (f.detection.codes || []).includes("pair"))?.id);
  check(!!pairId, "the audit marks the finding with the code «pair»");
  await openRow(page, pairId);
  await page.waitForTimeout(300);
  const card = page.locator(`#finding-${pairId}`);
  const text = norm(await card.innerText());
  check(/تأكيد اختياري/.test(text) && /كلمتان توافقان لفظ آية، وقد تكون كلامًا عاديًا/.test(text), `the card says it is optional and may be ordinary prose («${text.slice(0, 90)}…»)`);
  check((await card.locator('[data-act="approved"]').count()) === 0, "no replacement is offered before the verse is confirmed");
  const places = await card.locator(".choice-place b").allInnerTexts();
  check(places.length === 2 && places.some((p) => /البقرة، الآية ١٤٨/.test(p)) && places.some((p) => /المائدة، الآية ٤٨/.test(p)), `both verses are offered, none chosen for the writer (${places.join(" | ")})`);
  await card.locator("details.ch-more > summary", { hasText: "لماذا ظهرت؟" }).click();
  check(/نادرة في الكلام العادي/.test(await card.innerText()), "«لماذا ظهرت؟» gives the reason");
  check((await overflowX()) <= 1, "no sideways scroll");
  await shot("1-card");
  await card.locator('[data-act="choose-verse"]').first().click();
  await page.waitForTimeout(1500);
  const after = await page.evaluate((id) => { const f = findingById(id); return f && { wording: f.wording?.status, required: requiredOf(f).length, optional: (f.changes || []).map((c) => c.kind) }; }, pairId);
  check(after && after.wording === "matched" && after.required === 0 && after.optional.every((k) => k === "vocalize" || k === "reference_add"),
    `after picking the verse the words match; only the usual optional extras are offered (${JSON.stringify(after)})`);
  check(await page.inputValue("#article") === article, "the draft is untouched");
  await shot("2-confirmed");
  check(errors.length === 0, `no page error (${errors.slice(0, 2).join(" | ")})`);
  await ctx.close();
}
finish(server, browser);
