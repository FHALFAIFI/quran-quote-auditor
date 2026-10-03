// A phrase check may finish after the writer opens another quotation. Its
// response must update the earlier finding without taking focus away.
// NODE_PATH=<scratch>/node_modules node scripts/ui_async_navigation_e2e.mjs [--server URL]
import fs from "fs";
import path from "path";
import { chromium, check, root, testServer, openPage, finish } from "./_ui_common.mjs";

const article = JSON.parse(fs.readFileSync(path.join(root, "eval/articles_frozen.json"), "utf8"))
  .cases.find((c) => c.id.startsWith("L1-")).article;
const server = await testServer();
const browser = await chromium.launch();
const { page, errors, audit } = await openPage(browser, server.base, { width: 1366, height: 900 }, false, "async-nav");
await page.goto(server.base);
await audit(article);

let release, intercepted;
const barrier = new Promise((resolve) => { release = resolve; });
const started = new Promise((resolve) => { intercepted = resolve; });
await page.route("**/api/phrase", async (route) => {
  intercepted();
  await barrier;
  await route.continue();
});
const pendingBefore = await page.evaluate(() => pendingList().length);
await page.click('#current [data-act="confirm-bounds"]');
await started;
await page.click("#next-btn");
const opened = await page.locator("#current article").getAttribute("id");
check(opened === "finding-3", "the writer can open the next quotation while a check is pending");
release();
await page.waitForFunction(() => document.querySelector("#undo-line")?.textContent.includes("ثبّتَّ حدود"), null, { timeout: 30000 });
check((await page.locator("#current article").getAttribute("id")) === opened,
  "the completed response does not pull the writer back to the previous quotation");
// (until 4 Oct this read «٧ اقتباسات» in the progress line; two exact-but-common phrases are now counted apart there, so the state is checked)
check(await page.evaluate((n) => pendingList().length === n - 1, pendingBefore),
  "the earlier quotation was still updated (one fewer open item)");
check(errors.length === 0, `no page errors ${errors.join(" | ")}`);
finish(server, browser);
