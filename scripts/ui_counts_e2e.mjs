// Browser check of the Arabic counts in the final check before copying: one and two are said without a numeral («تغيير واحد»,
// «تغييرين»), 3–10 take the plural («٣ تغييرات»), 11 and above the singular in the accusative («١١ تغييرًا»), for the approved
// changes, the places kept as written and the passages dismissed (Playwright, Chromium, desktop width).
//
//   NODE_PATH=<scratch>/node_modules node scripts/ui_counts_e2e.mjs [--server URL] [--python PATH]
//
// Starts its OWN AI-off server unless --server is given. The article quotes Az-Zumar 10 twelve times with «يجزى» for «يوفى», so each
// quotation carries one required change. Decisions are set in the page state and the final check redrawn (renderFinal), so every
// count from 1 to 12 is reached without clicking through twelve cards; the clicked journey is ui_journey_e2e.mjs.
import { chromium, check, norm, VIEWPORTS, testServer, openPage, finish } from "./_ui_common.mjs";

const N = 12;
const article = ["الصبر في القرآن."].concat(Array.from({ length: N }, (_, i) => `الموضع ${i + 1}: قال تعالى: ﴿إنما يجزى الصابرون أجرهم بغير حساب﴾ [الزمر: 10]`)).join("\n\n");
const server = await testServer();
const browser = await chromium.launch();
const [, vp, mobile] = VIEWPORTS[0];
const { page, errors, audit } = await openPage(browser, server.base, vp, mobile, "counts");
await page.goto(server.base);
await page.evaluate(() => sessionStorage.clear());
await audit(article);
const ids = await page.evaluate(() => activeFindings().map((f) => requiredOf(f).map((c) => c.id)));
check(ids.length === N && ids.every((r) => r.length === 1), `the article gives ${N} quotations with one required change each (${ids.map((r) => r.length).join(",")})`);

// approve the first `a` changes, keep the next `k` as written, dismiss the last `d` quotations; return the sentence
const state = (a, k, d) => page.evaluate(([a, k, d, n]) => {
  for (const key of Object.keys(decisions)) delete decisions[key];
  for (const key of Object.keys(dismissed)) delete dismissed[key];
  const fs = allFindings();
  fs.forEach((f, i) => {
    const c = requiredOf(f)[0];
    if (i < a) decisions[c.id] = "approved";
    else if (i < a + k) decisions[c.id] = "rejected";
    if (i >= n - d) dismissed[f.id] = true;
  });
  renderFinal();
  return document.querySelector("#final-summary .final-sentence").textContent;
}, [a, k, d, N]).then(norm);

const cases = [
  [[1, 0, 0], "سيُنسخ مقالك بعد تغيير واحد اعتمدتَه."],
  [[2, 0, 0], "سيُنسخ مقالك بعد تغييرين اعتمدتَهما."],
  [[3, 0, 0], "سيُنسخ مقالك بعد ٣ تغييرات اعتمدتَها."],
  [[10, 0, 0], "سيُنسخ مقالك بعد ١٠ تغييرات اعتمدتَها."],
  [[11, 0, 0], "سيُنسخ مقالك بعد ١١ تغييرًا اعتمدتَها."],
  [[12, 0, 0], "سيُنسخ مقالك بعد ١٢ تغييرًا اعتمدتَها."],
  [[0, 1, 0], "لم تعتمد أي تغيير؛ سيُنسخ مقالك كما كتبتَه، وأبقيتَ موضعًا واحدًا كما كتبتَه."],
  [[1, 2, 0], "سيُنسخ مقالك بعد تغيير واحد اعتمدتَه، وأبقيتَ موضعين كما كتبتَهما."],
  [[2, 3, 0], "سيُنسخ مقالك بعد تغييرين اعتمدتَهما، وأبقيتَ ٣ مواضع كما كتبتَها."],
  [[0, 10, 0], "لم تعتمد أي تغيير؛ سيُنسخ مقالك كما كتبتَه، وأبقيتَ ١٠ مواضع كما كتبتَها."],
  [[1, 11, 0], "سيُنسخ مقالك بعد تغيير واحد اعتمدتَه، وأبقيتَ ١١ موضعًا كما كتبتَها."],
  [[0, 0, 1], "لم تعتمد أي تغيير؛ سيُنسخ مقالك كما كتبتَه، واستبعدتَ مقطعًا واحدًا ليس اقتباسًا."],
  [[0, 0, 2], "لم تعتمد أي تغيير؛ سيُنسخ مقالك كما كتبتَه، واستبعدتَ مقطعين ليسا اقتباسين."],
  [[3, 0, 3], "سيُنسخ مقالك بعد ٣ تغييرات اعتمدتَها، واستبعدتَ ٣ مقاطع ليست اقتباسات."],
  [[1, 0, 11], "سيُنسخ مقالك بعد تغيير واحد اعتمدتَه، واستبعدتَ ١١ مقطعًا ليست اقتباسات."],
];
for (const [[a, k, d], want] of cases) {
  const got = await state(a, k, d);
  check(got === want, `${a} approved, ${k} kept, ${d} dismissed: «${got}»${got === want ? "" : ` (expected «${want}»)`}`);
}
check(!errors.length, `no page errors (${errors.join(" | ")})`);
finish(server, browser);
