// Shared by the browser checks (scripts/ui_*.mjs): Playwright loading, arguments, an AI-off server of their own, PASS/FAIL printing.
//   npm i playwright            # in any scratch directory; not a project dependency
//   NODE_PATH=<scratch>/node_modules node scripts/ui_journey_e2e.mjs [--server URL] [--shots DIR] [--python PATH]
import { createRequire } from "module";
import { spawn } from "child_process";
import net from "net";
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const require = createRequire(import.meta.url);
const playwrightChromium = require("playwright").chromium;
// CI uses Playwright's browser; a local browser can be supplied where that download is unavailable (for example, Edge on Windows).
export const chromium = {
  launch: (options = {}) => playwrightChromium.launch(process.env.PLAYWRIGHT_CHROME_PATH ? { ...options, executablePath: process.env.PLAYWRIGHT_CHROME_PATH } : options),
};
export const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
export const argv = process.argv.slice(2);
export const opt = (name) => { const i = argv.indexOf(name); return i >= 0 ? argv[i + 1] : null; };
export const shots = opt("--shots");
export const python = opt("--python") || process.env.PYTHON || (fs.existsSync(path.join(root, ".venv/bin/python")) ? path.join(root, ".venv/bin/python") : "python3");
if (shots) fs.mkdirSync(shots, { recursive: true });

export let failures = 0;
export const check = (cond, msg) => { console.log(`${cond ? "PASS" : "FAIL"}  ${msg}`); if (!cond) failures++; };
export const norm = (t) => (t || "").replace(/\s+/g, " ").trim();
export const readSample = (name) => fs.readFileSync(path.join(root, "app/static/samples", `${name}.txt`), "utf8").trim().replace(/\r\n?/g, "\n");
export const VIEWPORTS = [["desktop", { width: 1366, height: 900 }, false], ["phone", { width: 390, height: 844 }, true], ["narrow", { width: 320, height: 640 }, true]];

// A server of our own with AI switched off in its environment: no Groq call is possible, and nothing can turn one on.
export async function startIsolatedServer() {
  const port = await new Promise((res, rej) => { const s = net.createServer(); s.listen(0, "127.0.0.1", () => { const p = s.address().port; s.close(() => res(p)); }); s.on("error", rej); });
  const env = { ...process.env, AI_PROVIDER: "none", RATE_LIMIT_PER_MINUTE: "1000" };
  for (const k of Object.keys(env)) if (/^(GROQ|GEMINI|GOOGLE)_|API_KEY/i.test(k)) delete env[k];
  const child = spawn(python, ["-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", String(port)], { cwd: root, env, stdio: ["ignore", "pipe", "pipe"] });
  let log = "";
  child.stdout.on("data", (d) => (log += d)); child.stderr.on("data", (d) => (log += d));
  const base = `http://127.0.0.1:${port}`;
  for (let i = 0; i < 150; i++) {
    if (child.exitCode !== null) throw new Error(`test server exited early:\n${log.slice(-1500)}`);
    try { if ((await fetch(base + "/api/health")).ok) return { base, stop: () => child.kill() }; } catch { /* not up yet */ }
    await new Promise((r) => setTimeout(r, 300));
  }
  child.kill();
  throw new Error(`test server did not start:\n${log.slice(-1500)}`);
}

// The server to test: --server URL (must have AI off: checked, not assumed) or a fresh isolated one.
export async function testServer() {
  const serverArg = opt("--server");
  const server = serverArg ? { base: serverArg.replace(/\/$/, ""), stop: () => {} } : await startIsolatedServer();
  const h = await (await fetch(server.base + "/api/health")).json();
  if (h.ai_configured) { console.log("refusing to run: this server has AI configured (a Groq call would be made)"); server.stop(); process.exit(3); }
  console.log(`INFO  server ${server.base} mode=${h.mode}`);
  return { ...server, health: h };
}

// Every page these checks open is watched for Content-Security-Policy violations (the securitypolicyviolation event, reported as a console
// error) and for any request to a host other than the app's own origin (fonts are self-hosted: a visit must contact nobody else).
// Both are pushed to the page's error list and counted; finish() fails the suite if either count is not 0.
export const watched = { csp: [], thirdParty: [] };
export async function watchPage(ctx, page, base, errors) {
  const origin = new URL(base).origin;
  await ctx.addInitScript(() => {
    document.addEventListener("securitypolicyviolation", (e) => console.error(`CSP violation: ${e.violatedDirective} blocked ${e.blockedURI || "(inline)"} at ${e.sourceFile || ""}:${e.lineNumber || ""}`));
  });
  page.on("console", (m) => { if (m.type() === "error" && /^CSP violation:/.test(m.text())) watched.csp.push(m.text()); });
  page.on("request", (r) => {
    const u = r.url();
    if (/^https?:/.test(u) && new URL(u).origin !== origin) { watched.thirdParty.push(u); errors?.push(`third-party request: ${u}`); }
  });
}

// A page with error collection, the clipboard allowed and a screenshot helper.
export async function openPage(browser, base, vp, mobile, tag) {
  const ctx = await browser.newContext({ viewport: vp, locale: "ar", isMobile: mobile, hasTouch: mobile });
  await ctx.grantPermissions(["clipboard-read", "clipboard-write"], { origin: base });
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  await watchPage(ctx, page, base, errors);
  const shot = async (n, full = false) => { if (shots) await page.screenshot({ path: path.join(shots, `${tag}-${n}.png`), fullPage: full }); };
  const inView = (sel, frac = 1) => page.evaluate(([s, f]) => { const r = document.querySelector(s)?.getBoundingClientRect(); return !!r && r.top >= 0 && r.bottom <= innerHeight * f + 1 && r.width > 0; }, [sel, frac]);
  const overflowX = () => page.evaluate(() => document.documentElement.scrollWidth - innerWidth);
  // Paste an article and audit it; resolves when the first card is shown.
  const audit = async (text) => {
    await page.fill("#article", text);
    await page.click("#audit-btn");
    await page.waitForSelector("#panel:not([hidden]) #current article", { timeout: 60000 });
    await page.waitForTimeout(900);
  };
  return { ctx, page, errors, shot, inView, overflowX, audit };
}
// Open a quotation from the list (its group may be folded).
export const openRow = async (page, id) => {
  await page.evaluate((i) => { const d = document.getElementById(`row-${i}`)?.closest("details"); if (d) d.open = true; }, id);
  await page.locator(`#row-${id}`).click();
  await page.waitForSelector(`#finding-${id}`);
};
export const finish = (server, browser) => {
  check(watched.csp.length === 0, `no Content-Security-Policy violation on any page of this run (${watched.csp.length}) ${watched.csp.slice(0, 3).join(" | ")}`);
  check(watched.thirdParty.length === 0, `no request to another host on any page of this run (${watched.thirdParty.length}) ${watched.thirdParty.slice(0, 3).join(" | ")}`);
  browser?.close(); server?.stop(); console.log(failures ? `\nfailures: ${failures}` : "\nall checks passed"); process.exit(failures ? 1 : 0); };
