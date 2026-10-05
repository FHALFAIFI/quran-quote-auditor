// Self-hosted fonts and the strict Content-Security-Policy, in the browser (Chromium), at 1366 and 390 px.
//
//   NODE_PATH=<scratch>/node_modules node scripts/ui_selfhost_e2e.mjs [--shots DIR] [--python PATH] [--server URL]
//
// Per viewport: a full journey (load → the demonstration article, which audits → approve both changes → copy) and each trust page, with
// the network log and a securitypolicyviolation listener on every page. Checks: every request goes to the app's own origin (no Google
// Fonts, nothing else), 0 CSP violations, the response headers carry the strict policy, the three font families are loaded from
// /static/fonts/ (document.fonts: status «loaded» and document.fonts.check true for Arabic text), and the bytes of font files fetched.
import { chromium, check, norm, readSample, testServer, openPage, finish, watched } from "./_ui_common.mjs";

const demo = readSample("sample-demo");
const expected = demo.replace("يجزى", "يوفى").replace("[الشرح: 6]", "[الشرح: 5]");
const FAMILIES = ["Readex Pro", "Noto Naskh Arabic", "Amiri Quran"];
const server = await testServer();
const browser = await chromium.launch();

for (const [name, vp, mobile] of [["desktop", { width: 1366, height: 900 }, false], ["phone", { width: 390, height: 844 }, true]]) {
  console.log(`\n== ${name} ${vp.width}x${vp.height}`);
  const { page, errors, shot } = await openPage(browser, server.base, vp, mobile, `SH-${name}`);
  const requests = [];
  const fontBytes = {};
  page.on("request", (r) => requests.push(r.url()));
  page.on("response", async (r) => {
    if (r.url().includes("/static/fonts/")) { try { fontBytes[new URL(r.url()).pathname] = (await r.body()).length; } catch { /* navigation */ } }
  });
  const before = { csp: watched.csp.length, third: watched.thirdParty.length };

  const res = await page.goto(server.base, { waitUntil: "load" });
  const csp = res.headers()["content-security-policy"] || "";
  check(/default-src 'self'/.test(csp) && /style-src 'self';/.test(csp) && /font-src 'self';/.test(csp) && !/unsafe-inline|googleapis|gstatic/.test(csp), `the page is served with the strict policy (${csp.slice(0, 60)}…)`);
  check(res.headers()["permissions-policy"] === "camera=(), microphone=(), geolocation=()" && res.headers()["cross-origin-opener-policy"] === "same-origin", "Permissions-Policy and COOP headers are present");
  await page.evaluate(() => sessionStorage.clear());
  await page.reload({ waitUntil: "load" });

  // the demonstration article: one click loads and audits it
  await page.click("#demo-btn");
  await page.waitForSelector("#panel:not([hidden]) #finding-3", { timeout: 60000 });
  await page.waitForTimeout(1200);
  await page.evaluate(() => document.fonts.ready);
  const fonts = await page.evaluate((fams) => fams.map((f) => ({
    family: f,
    loaded: [...document.fonts].filter((x) => x.family.replace(/"/g, "") === f && x.status === "loaded").length,
    // A space requests the Latin subset too; the Arabic face alone is enough to render a Quran word.
    check: document.fonts.check(`20px "${f}"`, "قال"),
  })), FAMILIES);
  for (const f of fonts) check(f.loaded >= 1 && f.check, `${f.family}: loaded from this server (${f.loaded} face(s) loaded, fonts.check=${f.check})`);
  const used = await page.evaluate(() => ({ body: getComputedStyle(document.body).fontFamily, article: getComputedStyle(document.getElementById("article")).fontFamily }));
  check(/Readex Pro/.test(used.body) && /Noto Naskh Arabic/.test(used.article), `the interface uses Readex Pro and the article Noto Naskh Arabic (${used.body.slice(0, 30)} / ${used.article.slice(0, 30)})`);
  await shot("1-audited");

  // decide both changes and copy
  await page.locator('[data-change="3-wording"] button[data-act="approved"]').click();
  await page.waitForSelector('[data-change="4-reference"] button[data-act="approved"]', { timeout: 10000 });
  await page.waitForTimeout(600);
  await page.locator('[data-change="4-reference"] button[data-act="approved"]').click();
  await page.waitForTimeout(800);
  await page.locator("#copy-btn").scrollIntoViewIfNeeded();
  await page.click("#copy-btn");
  await page.waitForTimeout(500);
  const clip = (await page.evaluate(() => navigator.clipboard.readText())).replace(/\r\n?/g, "\n");
  check(clip === expected, "copy: the clipboard holds the article with the two approved changes");
  await shot("2-copied");

  // the trust pages
  for (const pg of ["/sources", "/privacy", "/limitations", "/roadmap"]) {
    const r = await page.goto(server.base + pg, { waitUntil: "load" });
    await page.evaluate(() => document.fonts.ready);
    check(r.headers()["content-security-policy"] === csp, `${pg}: same strict policy`);
    const ok = await page.evaluate(() => document.fonts.check('16px "Readex Pro"', "المصادر") && [...document.fonts].some((x) => x.family.replace(/"/g, "") === "Readex Pro" && x.status === "loaded"));
    check(ok, `${pg}: Readex Pro loaded from this server`);
    if (!mobile) {  // keyboard: the first Tab reaches a visible skip link; the next focused control draws a visible outline
      const html = await page.evaluate(() => [document.documentElement.lang, document.documentElement.dir]);
      await page.keyboard.press("Tab");
      const skip = await page.evaluate(() => { const a = document.activeElement, r = a.getBoundingClientRect(); return { cls: a.className, href: a.getAttribute("href"), shown: r.top >= 0 && r.height > 0, target: !!document.querySelector(a.getAttribute("href")) }; });
      await page.keyboard.press("Tab");
      const ring = await page.evaluate(() => { const cs = getComputedStyle(document.activeElement); return `${cs.outlineStyle} ${cs.outlineWidth}`; });
      check(html.join(" ") === "ar rtl" && skip.cls === "skip-link" && skip.shown && skip.target && /^solid [1-9]/.test(ring), `${pg}: lang=ar dir=rtl, the first Tab shows the skip link (→ ${skip.href}), the next focus has an outline (${ring})`);
    }
    if (pg === "/privacy") check(!/fonts\.googleapis|خطوط جوجل \(/.test(await page.textContent("main")) && /مستضافة/.test(await page.textContent("main")), "/privacy says the fonts are hosted on the tool's own server");
    if (pg === "/sources") check(/SIL/.test(await page.textContent("main")) && (await page.locator('a[href="/static/fonts/readex-pro/OFL.txt"]').count()) === 1, "/sources names the SIL licence and links each font's licence file");
    await shot(`3-${pg.slice(1)}`, true);
  }

  const origin = new URL(server.base).origin;
  const foreign = requests.filter((u) => /^https?:/.test(u) && new URL(u).origin !== origin);
  check(requests.length > 10 && foreign.length === 0, `network log: ${requests.length} requests, all to ${origin} (${foreign.length} to another host) ${foreign.slice(0, 3).join(" ")}`);
  check(watched.csp.length - before.csp === 0, `0 CSP violations during the journey and the trust pages`);
  const files = Object.keys(fontBytes).sort();
  const total = Object.values(fontBytes).reduce((a, b) => a + b, 0);
  console.log(`INFO  font files fetched: ${files.map((f) => `${f.split("/").pop()} ${fontBytes[f]}`).join(", ")}; total ${total} bytes`);
  check(files.length >= 3 && files.every((f) => f.startsWith("/static/fonts/")), `fonts came from /static/fonts/ (${files.length} files, ${total} bytes)`);
  check(errors.length === 0, `no console/page errors ${errors.join(" | ")}`);
  void norm;
}
// Control: the listener does fire. In a separate context (not counted above), an inline <style>, a style attribute set from markup and an
// external font must each be refused by the policy and reported; element.style (CSSOM), which the app uses, must not be.
{
  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  const seen = [];
  await ctx.addInitScript(() => document.addEventListener("securitypolicyviolation", (e) => console.log(`VIOLATION ${e.violatedDirective}`)));
  page.on("console", (m) => { if (m.text().startsWith("VIOLATION")) seen.push(m.text()); });
  await page.goto(server.base, { waitUntil: "load" });
  await page.evaluate(() => { document.getElementById("article").style.height = "300px"; });
  await page.waitForTimeout(300);
  const cssom = seen.length;
  await page.evaluate(() => {
    const st = document.createElement("style"); st.textContent = "body{color:red}"; document.head.append(st);
    document.body.insertAdjacentHTML("beforeend", '<p style="color:red">x</p>');
    const f = new FontFace("X", "url(https://fonts.gstatic.com/x.woff2)"); f.load().catch(() => {});
  });
  await page.waitForTimeout(800);
  check(cssom === 0, "control: element.style (CSSOM) is not a violation");
  check(seen.some((v) => /style-src/.test(v)) && seen.some((v) => /font-src/.test(v)), `control: an injected <style>, a style attribute and an external font are refused and reported (${seen.join(", ")})`);
  await ctx.close();
}
finish(server, browser);
