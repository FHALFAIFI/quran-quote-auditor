// Optional accounts (roadmap Stage 2) in the browser — AGAINST A LOCAL FAKE OF SUPABASE (scripts/fake_supabase.py); NOT THE REAL SERVICE.
//
//   NODE_PATH=<scratch>/node_modules node scripts/ui_account_e2e.mjs --python <venv with requirements.txt>/bin/python
//
// Starts: (1) an AI-off server with the flag OFF, to prove the guest page loads no account code and makes no auth request;
// (2) the fake Supabase Auth + PostgREST on 127.0.0.1; (3) an AI-off server with ACCOUNTS_ENABLED=true pointed at the fake.
// Then: the guest page with the flag on (no auth request until the writer asks for a link), sign-in by a fake magic link that
// opens in a second tab and hands the session back to the first, explicit save (nothing uploaded before «احفظ في حسابي»),
// list, open, rename, delete, export, the 409 choice with two pages, token expiry keeping the text, sign-out clearing the
// account's drafts while the guest draft in localStorage stays, account deletion, tokens never in localStorage /
// sessionStorage / cookies, axe on the account section and a keyboard-only run at 1366 / 390 / 320.
import { createRequire } from "module";
import { spawn } from "child_process";
import fs from "fs";
import path from "path";
import { chromium, check, finish, startIsolatedServer, python, root, norm } from "./_ui_common.mjs";

const require = createRequire(import.meta.url);
const axeSource = fs.readFileSync(require.resolve("axe-core/axe.min.js"), "utf8");
const cleanup = [];   // the fake and the servers are stopped even when a step throws
process.on("exit", () => cleanup.forEach((f) => { try { f(); } catch { /* already gone */ } }));
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const ANON = "fake-anon-key", SERVICE = "fake-service-role-key";
console.log("NOTE  everything below runs against a LOCAL FAKE of Supabase (scripts/fake_supabase.py), not the real service.");

// ------------------------------------------------------------------------------------------------ 0. the flag OFF
const off = await startIsolatedServer();
cleanup.push(off.stop);
const browser = await chromium.launch();
{
  console.log("\n== flag off (default)");
  const h = await (await fetch(off.base + "/api/health")).json();
  check(h.accounts_enabled === false, "flag off: /api/health says accounts_enabled false");
  check((await fetch(off.base + "/api/account/drafts")).status === 404 && (await fetch(off.base + "/api/account/config")).status === 404, "flag off: /api/account/* is 404");
  const ctx = await browser.newContext({ viewport: { width: 1366, height: 900 }, locale: "ar" });
  const page = await ctx.newPage();
  const urls = [];
  page.on("request", (r) => urls.push(r.url()));
  await page.goto(off.base);
  await page.waitForFunction(() => !document.getElementById("mode-banner").hidden);
  await page.click("#options > summary");
  await page.fill("#article", "قال تعالى: إن مع العسر يسرا");
  await page.click("#audit-btn");
  await page.waitForSelector("#results:not([hidden])", { timeout: 60000 });
  await sleep(500);
  check(!(await page.$("#account")), "flag off: no account section in the page");
  check(!urls.some((u) => /account|supabase|\/auth\/v1|\/rest\/v1/.test(u)), `flag off: network log has no account/auth request (${urls.filter((u) => u.startsWith(off.base)).length} same-origin requests)`);
  check(await page.evaluate(() => !window.QQAHost), "flag off: no account bridge object");
  await ctx.close();
}
off.stop();

// ------------------------------------------------------------------------------------------------ 1. the fake and the flag ON
const fake = await new Promise((resolve, reject) => {
  const child = spawn(python, [path.join(root, "scripts/fake_supabase.py"), "--port", "0", "--anon", ANON, "--service", SERVICE], { cwd: root, stdio: ["ignore", "pipe", "pipe"] });
  let out = "";
  child.stdout.on("data", (d) => { out += d; const m = out.match(/READY (\d+)/); if (m) resolve({ base: `http://127.0.0.1:${m[1]}`, stop: () => child.kill() }); });
  child.stderr.on("data", (d) => { out += d; });
  child.on("exit", (c) => reject(new Error(`fake exited ${c}: ${out}`)));
});
cleanup.push(fake.stop);
const F = (p, init) => fetch(fake.base + p, init).then((r) => r.json());
Object.assign(process.env, { ACCOUNTS_ENABLED: "true", SUPABASE_URL: fake.base, SUPABASE_ANON_KEY: ANON, SUPABASE_SERVICE_ROLE_KEY: SERVICE,
  ACCOUNT_TOKEN_LEEWAY_SECONDS: "0", ACCOUNT_RATE_LIMIT_PER_MINUTE: "5000" });
const server = await startIsolatedServer();
cleanup.push(server.stop);
const base = server.base;
const health = await (await fetch(base + "/api/health")).json();
check(health.accounts_enabled === true && !health.ai_configured, `flag on: health accounts_enabled true, AI off (fake at ${fake.base})`);
const csp = (await fetch(base + "/")).headers.get("content-security-policy");
check(csp.includes(`connect-src 'self' ${fake.base};`), "flag on: CSP connect-src adds only the configured Supabase origin");

const fakeRequests = async () => (await F("/__fake/requests")).requests;
const linkFor = async (email) => { for (let i = 0; i < 40; i++) { const r = await fetch(`${fake.base}/__fake/link?email=${encodeURIComponent(email)}`); if (r.ok) return (await r.json()).link; await sleep(100); } throw new Error("no link"); };
const noTokensStored = (page) => page.evaluate(() => {
  const all = JSON.stringify({ ...localStorage }) + JSON.stringify({ ...sessionStorage }) + document.cookie;
  return !/eyJ[A-Za-z0-9_-]{10,}/.test(all) && !/access_token|refresh_token/.test(all);
});
const note = (page) => page.$eval("#account-note", (n) => n.textContent);
const listTitles = (page) => page.$$eval("#account-list .account-draft-title", (ns) => ns.map((n) => n.textContent));
async function openOptions(page) { await page.evaluate(() => { document.getElementById("options").open = true; }); await page.waitForSelector("#account", { state: "attached" }); }
async function requestLink(page, email) {
  await openOptions(page);
  await page.fill("#account-email", email);
  await page.click("#account-form button[type=submit]");
  await page.waitForFunction(() => /أرسلنا رابط دخول/.test(document.getElementById("account-note").textContent));
  return linkFor(email);
}
// The writer opens the link in a new tab of the same browser: that tab signs in and hands the session to the asking tab.
async function followLink(ctx, link) {
  const tab = await ctx.newPage();
  await tab.goto(link);
  await tab.waitForSelector("#account-in:not([hidden])");
  return tab;
}
const signedIn = (page) => page.waitForSelector("#account-in:not([hidden])", { timeout: 10000 });
async function axeAccount(page, label) {
  await page.evaluate(axeSource);
  const res = await page.evaluate(() => axe.run({ include: [["#account"]] }, { runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa", "best-practice"] } }));
  const bad = res.violations.map((v) => `${v.id} (${v.impact}) ×${v.nodes.length}: ${v.nodes[0].target.join(" ")}`);
  check(bad.length === 0, `axe #account: ${label}: ${bad.length ? bad.join(" | ") : "0 violations"}`);
}

// ------------------------------------------------------------------------------------------------ 2. guest with the flag on
console.log("\n== flag on, guest (no sign-in)");
const ctxA = await browser.newContext({ viewport: { width: 1366, height: 900 }, locale: "ar", acceptDownloads: true });
const A = await ctxA.newPage();
const reqA = [];
A.on("request", (r) => reqA.push({ url: r.url(), method: r.method(), auth: r.headers().authorization || null }));
const errors = [];
A.on("pageerror", (e) => errors.push(String(e)));
await A.goto(base);
await A.waitForSelector("#account", { state: "attached" });
const GUEST = "مسودة الضيف في هذا المتصفح: قال تعالى: إن مع العسر يسرا";
await A.fill("#article", GUEST);
await openOptions(A);
await A.click("#draft-save");
await A.click("#audit-btn");
await A.waitForSelector("#results:not([hidden])", { timeout: 60000 });
await sleep(400);
check(!reqA.some((r) => r.url.startsWith(fake.base)), "guest with the flag on: no request to the auth service before the writer asks for a link");
check(!reqA.some((r) => r.url.includes("/api/account/") && !r.url.endsWith("/api/account/config")), "guest with the flag on: no account API call except the public config");
check(await A.evaluate(() => JSON.parse(localStorage.getItem("qqa-draft-v1") || "{}").text) === GUEST, "guest draft saved in localStorage as today");
check(await A.isVisible("#account-form") && !(await A.isVisible("#account-in")), "account section shows only the sign-in form");
check(await A.$$eval("#options .btn.primary", (b) => b.length) === 0, "no new primary action inside the options");

// ------------------------------------------------------------------------------------------------ 3. sign-in, explicit save
console.log("\n== sign-in (fake magic link) and explicit save");
const ARTICLE = "مقال للحساب. قال تعالى: إن مع العسر يسرا\nفقرة ثانية للاختبار.";
await A.fill("#article", ARTICLE);
const linkA = await requestLink(A, "writer-a@example.test");
const otp = (await fakeRequests()).find((r) => r.path === "/auth/v1/otp");
check(!!otp && otp.origin === base && otp.auth === "anon", "the link is requested from Supabase Auth directly, with the public anon key only");
const A2 = await followLink(ctxA, linkA);
check(!(await A2.evaluate(() => location.href)).includes("#") && !(await A2.evaluate(() => location.search)), "the landing tab cleared the tokens (fragment) and the nonce from the address bar");
await signedIn(A);
check(true, "the asking tab received the session from the landing tab (BroadcastChannel, memory to memory)");
check(await A.inputValue("#article") === ARTICLE, "signing in left the editor text untouched");
await sleep(500);
check(!reqA.some((r) => r.method !== "GET" && r.url.includes("/api/account/drafts")), "signing in uploaded nothing (no POST/PUT of a draft before «احفظ في حسابي»)");
check(await noTokensStored(A) && await noTokensStored(A2), "no token in localStorage, sessionStorage or cookies (both tabs)");
check(norm(await A.textContent("#account-who")).includes("writer-a@example.test"), "the signed-in line names the address");
await A.click("#account-save");
await A.waitForFunction(() => /حُفظت في حسابك/.test(document.getElementById("account-note").textContent));
const posted = reqA.filter((r) => r.method === "POST" && r.url.endsWith("/api/account/drafts"));
check(posted.length === 1 && /^Bearer eyJ/.test(posted[0].auth || ""), "«احفظ في حسابي» sent exactly one POST, with the bearer token, to this server");
check(!reqA.some((r) => r.url.startsWith(fake.base + "/rest/")), "the browser never calls PostgREST itself (only this server does)");
check(JSON.stringify(await listTitles(A)) === JSON.stringify(["مقال للحساب. قال تعالى: إن مع العسر يسرا"]), "the list shows the saved draft by its first line");
check(/حرفًا/.test(await A.textContent("#account-list .account-draft")), "the list row shows last saved and length");

// rename
await A.click("#account-list [data-act=rename]");
await A.fill("#account-list .account-rename input", "مقال الصبر");
await A.click("#account-list [data-act=rename-save]");
await A.waitForFunction(() => [...document.querySelectorAll("#account-list .account-draft-title")].some((n) => n.textContent === "مقال الصبر"));
check(true, "rename: the list shows the new title");
// a second draft, then delete it
const FIRST = "النص المحدّث للمسودة الأولى";
await A.fill("#article", FIRST);
await A.click("#account-save");   // «مسح» was not pressed: this updates the opened draft
await A.waitForFunction(() => /حُفظت في حسابك/.test(document.getElementById("account-note").textContent));
check((await listTitles(A)).length === 1, "saving again updates the opened draft instead of creating a second one");
await A.click("#clear-btn");
await A.fill("#article", "مسودة ثانية للحذف");
await A.click("#account-save");
await A.waitForFunction(() => document.querySelectorAll("#account-list .account-draft").length === 2);
check(true, "after «مسح», «احفظ في حسابي» creates a new draft (two in the list)");
await A.locator("#account-list .account-draft", { hasText: "مسودة ثانية للحذف" }).locator("[data-act=delete]").click();
await A.click("#account-list [data-act=delete-yes]");
await A.waitForFunction(() => document.querySelectorAll("#account-list .account-draft").length === 1);
check(await A.inputValue("#article") === "مسودة ثانية للحذف", "delete: the draft left the account; the editor text stayed");
// open (with the unsaved-text confirmation)
await A.locator("#account-list [data-act=open]").click();
check(await A.isVisible("#account-list [data-act=open-yes]"), "open over unsaved text asks first");
await A.click("#account-list [data-act=open-yes]");
await A.waitForFunction((t) => document.getElementById("article").value === t, FIRST);
check(true, "open: the editor holds the saved text of the chosen draft");
// export
const [dl] = await Promise.all([A.waitForEvent("download"), A.click("#account-export")]);
const exported = JSON.parse(fs.readFileSync(await dl.path(), "utf8"));
check(exported.drafts.length === 1 && exported.drafts[0].title === "مقال الصبر" && exported.drafts[0].body === FIRST && "preferences" in exported,
  `export: one JSON file with the draft and preferences (${dl.suggestedFilename()})`);

// preferences follow the account (the browser's own stay as they were)
const prefPut = A.waitForResponse((r) => r.url().endsWith("/api/account/preferences") && r.request().method() === "PUT");
await A.check("#opt-distinct");
check((await prefPut).status() === 200, "a suggestion option changed while signed in is saved to the account");
{
  const ctxP = await browser.newContext({ viewport: { width: 1366, height: 900 }, locale: "ar" });
  const P = await ctxP.newPage();
  await P.goto(base);
  await P.waitForSelector("#account", { state: "attached" });
  const before = await P.isChecked("#opt-distinct");
  const tabP = await followLink(ctxP, await requestLink(P, "writer-a@example.test"));
  await signedIn(P);
  await P.waitForFunction(() => document.getElementById("opt-distinct").checked === true);
  check(before === false, "another browser that signs in as the same writer gets the account's options (distinct on)");
  check(await P.evaluate(() => !/"distinct":true/.test(localStorage.getItem("qqa-suggest-v1") || "")), "the account's options are not written into this browser's own storage");
  await P.click("#account-signout");
  await P.waitForSelector("#account-form");
  check(await P.isChecked("#opt-distinct") === false, "sign out restores this browser's own options");
  await tabP.close(); await ctxP.close();
}

// ------------------------------------------------------------------------------------------------ 4. conflict with two pages
console.log("\n== two pages on one draft (409)");
await openOptions(A2);
await A2.evaluate(() => { const d = document.getElementById("options"); d.open = false; d.open = true; });
await A2.waitForSelector("#account-list [data-act=open]");
await A2.click("#account-list [data-act=open]");
await A2.waitForFunction((t) => document.getElementById("article").value === t, FIRST);
await A.fill("#article", "نسخة الصفحة الأولى");
await A.click("#account-save");
await A.waitForFunction(() => /حُفظت في حسابك/.test(document.getElementById("account-note").textContent));
await A2.fill("#article", "نسخة الصفحة الثانية");
await A2.click("#account-save");
await A2.waitForSelector("#account-conflict:not([hidden])");
check(await A2.inputValue("#article") === "نسخة الصفحة الثانية", "409: the second page's text stays in its editor");
check(await A2.$$eval("#account-conflict button", (b) => b.length) === 3, "409: a visible choice of three (keep mine / save as new / open the saved copy)");
check(await A2.evaluate(() => document.activeElement?.id) === "account-conflict-title", "409: focus moves to the explanation");
await axeAccount(A2, "1366 conflict choice");
await A2.click("#account-keep-mine");
await A2.waitForFunction(() => /حُفظت في حسابك/.test(document.getElementById("account-note").textContent));
check(await A2.isHidden("#account-conflict"), "keep mine: saved explicitly over the other copy, the choice closes");
await A.fill("#article", "تعديل متأخر في الأولى");
await A.click("#account-save");
await A.waitForSelector("#account-conflict:not([hidden])");
await A.click("#account-take-saved");
await A.waitForFunction(() => document.getElementById("article").value === "نسخة الصفحة الثانية");
check(true, "open the saved copy: the first page now holds the second page's saved text (the writer chose it)");

// ------------------------------------------------------------------------------------------------ 5. token expiry mid-edit
console.log("\n== token expiry mid-edit");
await F("/__fake/ttl", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ seconds: 3 }) });
const ctxC = await browser.newContext({ viewport: { width: 1366, height: 900 }, locale: "ar" });
const C = await ctxC.newPage();
await C.goto(base);
const linkC = await requestLink(C, "writer-c@example.test");
const C2 = await followLink(ctxC, linkC);
await signedIn(C);
const MID = "نص كتبه الكاتب أثناء الجلسة ولم يحفظه بعد.";
await C.fill("#article", MID);
await sleep(4200);
await C.click("#account-save");
await C.waitForFunction(() => /لم يُحفظ: سجّل الدخول من جديد/.test(document.getElementById("account-note").textContent));
check(await C.inputValue("#article") === MID, "expired token: the text stays in the editor");
check(norm(await note(C)).startsWith("لم يُحفظ: سجّل الدخول من جديد"), "expired token: the save fails visibly «لم يُحفظ: سجّل الدخول من جديد»");
check(await C.isVisible("#account-form"), "expired token: the sign-in form is offered again (no silent retry)");
await F("/__fake/ttl", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ seconds: 3600 }) });
const linkC2 = await requestLink(C, "writer-c@example.test");
const C3 = await followLink(ctxC, linkC2);
await signedIn(C);
await C.click("#account-save");
await C.waitForFunction(() => /حُفظت في حسابك/.test(document.getElementById("account-note").textContent));
check(await C.inputValue("#article") === MID && (await listTitles(C)).length === 1, "after signing in again from the same page, the same text is saved");
await C2.close(); await C3.close();

// ------------------------------------------------------------------------------------------------ 6. sign-out, deletion
console.log("\n== sign-out and account deletion");
await A.fill("#article", "تعديل لم يُحفظ قبل الخروج");
await A.click("#account-signout");
check(await A.isVisible("#account-signout-yes"), "sign out with unsaved changes to an account draft asks first");
await A.click("#account-signout-yes");
await A.waitForSelector("#account-form");
check(await A.inputValue("#article") === "" && await A.$$eval("#account-list li", (l) => l.length) === 0, "sign out: the account's draft left the editor and the list is gone");
check(await A.evaluate(() => !(sessionStorage.getItem("qqa-session-v3") || "").includes("نسخة")), "sign out: nothing of the account draft in sessionStorage");
check(await A.evaluate(() => JSON.parse(localStorage.getItem("qqa-draft-v1") || "{}").text) === GUEST, "sign out: the guest draft in localStorage is untouched (and was never uploaded)");
const logouts = (await F("/__fake/requests")).logouts;
check(logouts.some((l) => l.scope === "local"), "sign out also ended the provider session (POST /auth/v1/logout?scope=local)");
await C.click(".account-danger > summary");
await C.click("#account-delete");
await C.click("#account-delete-yes");
await C.waitForFunction(() => /حُذف من حسابك/.test(document.getElementById("account-note").textContent));
const st = await F("/__fake/state");
check(!("writer-c@example.test" in st.users) && st.deletion_log.length === 1 && /^[0-9a-f]{64}$/.test(st.deletion_log[0].user_hash),
  "account deletion: the fake has no user C, no rows for C, and one content-free deletion_log line");
check(/وحُذف حساب الدخول نفسه/.test(await note(C)), "deletion note says the sign-in account was deleted too (service-role key set on the server only)");
const browserSide = (await fakeRequests()).filter((r) => r.origin);
check(browserSide.every((r) => ["/auth/v1/otp", "/auth/v1/logout"].includes(r.path)), `the browser called the fake only for the link and sign-out (${browserSide.length} requests)`);
check((await fakeRequests()).filter((r) => r.auth === "service").every((r) => !r.origin), "the service-role key was only ever used by the server, never by a browser");
await ctxC.close();

// ------------------------------------------------------------------------------------------------ 7. axe + keyboard at three widths
for (const [label, vp, mobile] of [["1366", { width: 1366, height: 900 }, false], ["390", { width: 390, height: 844 }, true], ["320", { width: 320, height: 640 }, true]]) {
  console.log(`\n== ${label}px: axe and keyboard only`);
  const ctx = await browser.newContext({ viewport: vp, locale: "ar", isMobile: mobile, hasTouch: mobile });
  const page = await ctx.newPage();
  await page.goto(base);
  await page.waitForSelector("#account", { state: "attached" });
  await page.fill("#article", `مقال للوحة المفاتيح ${label}`);
  await openOptions(page);
  await axeAccount(page, `${label} signed out`);
  // keyboard only from here: Tab to the address field, type, Enter submits
  await page.focus("#options > summary");
  let found = false;
  for (let i = 0; i < 40 && !found; i++) { await page.keyboard.press("Tab"); found = await page.evaluate(() => document.activeElement?.id === "account-email"); }
  check(found, `${label}: Tab reaches the address field`);
  const email = `kb-${label}@example.test`;
  await page.keyboard.type(email);
  await page.keyboard.press("Enter");
  await page.waitForFunction(() => /أرسلنا رابط دخول/.test(document.getElementById("account-note").textContent));
  const tab = await followLink(ctx, await linkFor(email));
  await signedIn(page);
  await tab.close();
  await page.focus("#account-save");
  await page.keyboard.press("Enter");
  await page.waitForFunction(() => document.querySelectorAll("#account-list .account-draft").length === 1);
  let onRename = false;
  for (let i = 0; i < 12 && !onRename; i++) { await page.keyboard.press("Tab"); onRename = await page.evaluate(() => document.activeElement?.dataset.act === "rename"); }
  check(onRename, `${label}: Tab reaches «أعد التسمية» in the list`);
  await page.keyboard.press("Enter");
  check(await page.evaluate(() => document.activeElement?.matches(".account-rename input")), `${label}: the rename field takes focus`);
  await axeAccount(page, `${label} signed in, list with the rename form open`);
  await page.keyboard.press("ControlOrMeta+a");
  await page.keyboard.type("اسم بلوحة المفاتيح");
  await page.keyboard.press("Enter");
  await page.waitForFunction(() => document.querySelector("#account-list .account-draft-title")?.textContent === "اسم بلوحة المفاتيح");
  check(await page.evaluate(() => document.activeElement?.dataset.act === "rename"), `${label}: after renaming, focus returns to «أعد التسمية»`);
  await page.keyboard.press("Tab");
  check(await page.evaluate(() => document.activeElement?.dataset.act === "delete"), `${label}: Tab reaches «احذف»`);
  await page.keyboard.press("Enter");
  check(await page.evaluate(() => document.activeElement?.dataset.act === "delete-yes"), `${label}: the confirmation takes focus`);
  await page.keyboard.press("Enter");
  await page.waitForFunction(() => document.querySelectorAll("#account-list .account-draft").length === 0);
  check(await page.evaluate(() => document.activeElement?.id === "account-list-title"), `${label}: after deleting, focus goes to the list heading`);
  await axeAccount(page, `${label} signed in, empty list`);
  const over = await page.evaluate(() => document.documentElement.scrollWidth - innerWidth);
  check(over <= 0, `${label}: no horizontal overflow (${over}px)`);
  check(await noTokensStored(page), `${label}: no token in browser storage`);
  await page.focus("#account-signout");
  await page.keyboard.press("Enter");
  await page.waitForSelector("#account-form");
  check(await page.inputValue("#article") === `مقال للوحة المفاتيح ${label}`, `${label}: sign out without an account draft open leaves the guest text alone`);
  await ctx.close();
}

check(errors.length === 0, `no page errors (${errors.length})`);
await ctxA.close();
fake.stop();
finish(server, browser);
