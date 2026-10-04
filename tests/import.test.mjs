// Tests for app/static/import.js: reading .txt and .docx in the browser (run: node --test tests/import.test.mjs).
// Every fixture is built in code by tests/fixtures/import/fixtures.mjs; the same bytes go through the page in scripts/ui_import_e2e.mjs.
import test from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "module";
import { FIXTURES, docx, docXml, zip } from "./fixtures/import/fixtures.mjs";

const require = createRequire(import.meta.url);
const I = require("../app/static/import.js");

const cps = (s) => Array.from(s).map((c) => c.codePointAt(0).toString(16));
function sameText(got, want, label) {
  // code point for code point; on a difference, show where
  if (got === want) return;
  const a = Array.from(got), b = Array.from(want);
  let i = 0;
  while (i < a.length && a[i] === b[i]) i++;
  assert.fail(`${label}: differs at code point ${i}: got ${JSON.stringify(a.slice(i, i + 12).join(""))} [${cps(a.slice(i, i + 4).join(""))}] want ${JSON.stringify(b.slice(i, i + 12).join(""))} [${cps(b.slice(i, i + 4).join(""))}]`);
}

for (const f of FIXTURES) {
  test(`fixture ${f.id} (${f.name}) → ${f.code ? `refused: ${f.code}` : "text"}`, async () => {
    const t0 = Date.now();
    const r = await I.extract(f.make(), f.name, { maxChars: 20000 });
    const ms = Date.now() - t0;
    if (f.code) {
      assert.equal(r.ok, false, `expected a refusal, got text: ${r.text && r.text.slice(0, 60)}`);
      assert.equal(r.code, f.code, r.message);
      assert.ok(typeof r.message === "string" && /[؀-ۿ]/.test(r.message), "an Arabic reason is given");
      assert.equal(r.text, undefined, "a refusal carries no text");
    } else {
      assert.equal(r.ok, true, `refused: ${r.code} ${r.message}`);
      sameText(r.text, f.text, f.id);
      assert.equal(r.chars, Array.from(f.text).length);
      for (const [k, v] of Object.entries(f.notes || {})) assert.equal(r.notes[k], v, `notes.${k}`);
    }
    assert.ok(ms < 10000, `within the 10 s limit (${ms} ms)`);
  });
}

test("a zip bomb (50 MB of zeros, ~50 KB compressed) is refused quickly without inflating it", async () => {
  for (const id of ["zip-bomb", "zip-bomb-lying"]) {
    const f = FIXTURES.find((x) => x.id === id);
    const bytes = f.make();
    assert.ok(bytes.length < 200 * 1024, `the bomb is small on disk (${bytes.length} bytes)`);
    global.gc?.();
    const before = process.memoryUsage();
    const t0 = Date.now();
    const r = await I.extract(bytes, f.name);
    const ms = Date.now() - t0;
    const after = process.memoryUsage();
    assert.equal(r.ok, false);
    assert.equal(r.code, f.code);
    assert.ok(ms < 3000, `${id}: refused in ${ms} ms`);
    // the lying bomb is inflated only up to the size it declared (900 KB) before it is stopped: far from 50 MB
    const grew = (after.arrayBuffers - before.arrayBuffers) / 1024 / 1024;
    assert.ok(grew < 20, `${id}: array buffers grew by ${grew.toFixed(1)} MB`);
  }
});

test("Quran text is never corrected or normalised: a misquotation stays as written", async () => {
  // «واستعينوا بالصبر والصلوة» (a wrong spelling) and a verse without diacritics: imported exactly
  const s = "قال تعالى: ﴿واستعينوا بالصبر والصلوة﴾ وقال: ﴿إن الله مع الصبرين﴾";
  const r = await I.extract(new TextEncoder().encode(s), "a.txt");
  assert.equal(r.text, s);
  const d = await I.extract(docx(`<w:p><w:r><w:t>${s}</w:t></w:r></w:p>`), "a.docx");
  assert.equal(d.text, s);
});

test("diacritics, tatweel, ﴿﴾, «», bidi marks, ZWNJ and the word ligatures are kept as written", () => {
  const s = "ﷲ ﷺ ﷻ ﷽ ﴿بِسْمِ اللَّهِ﴾ «الصبــــر» ‏‌نص‎";
  const c = I.clean(s);
  assert.equal(c.text, s);
  assert.equal(c.notes.presentation, 0);
});

test("presentation forms: letters and lam-alef become base letters; isolated marks lose the space NFKC adds", () => {
  assert.equal(I.clean("ﻻ ﻷ ﻵ ﻹ").text, "لا لأ لآ لإ");
  assert.equal(I.clean("ﺍﻟﺼﺒﺮ").text, "الصبر");
  assert.equal(I.clean("ﻙﹰ").text, "كً");        // FE70 FATHATAN ISOLATED → U+064B, not " ً"
  assert.equal(I.clean("ﭖ ﮒ").text, "پ گ");       // Persian letters: base letters too
  assert.equal(I.clean("﴾﴿").notes.presentation, 0);
});

test("line ends and the byte-order mark; leading blank lines and trailing space dropped, nothing inside touched", () => {
  const c = I.clean("﻿\r\n\r\n  سطر\r\rسطر ثالث  \t\n\n");
  assert.equal(c.text, "  سطر\n\nسطر ثالث");
  assert.equal(c.notes.bom, 1);
  assert.equal(c.notes.crlf, 4);
});

test("the size limit is the one the page passes (the server's)", async () => {
  const r = await I.extract(new TextEncoder().encode("أبجد هوز"), "a.txt", { maxChars: 5 });
  assert.equal(r.ok, false);
  assert.equal(r.code, "too_long");
  assert.match(r.message, /٨/);
  assert.match(r.message, /٥/);
});

test("a file larger than 5 MB is refused before it is read", async () => {
  const r = await I.extract(new Uint8Array(5 * 1024 * 1024 + 1).fill(0x41), "big.txt");
  assert.equal(r.code, "file_too_big");
});

test("a part that declares a ratio above 200:1 over 1 MB is refused before inflating", async () => {
  const bytes = zip([{ name: "word/document.xml", data: docXml("<w:p><w:r><w:t>x</w:t></w:r></w:p>") }]);
  // rewrite the declared size in the central directory to 2 MB (compressed size stays tiny)
  const cd = bytes.findLastIndex((_, i) => bytes[i] === 0x50 && bytes[i + 1] === 0x4b && bytes[i + 2] === 0x01 && bytes[i + 3] === 0x02);
  new DataView(bytes.buffer).setUint32(cd + 24, 2 * 1024 * 1024, true);
  const r = await I.extract(bytes, "ratio.docx");
  assert.equal(r.code, "unzipped_too_big");
});

test("the notice says what was done", async () => {
  const f = FIXTURES.find((x) => x.id === "docx-footnotes");
  const r = await I.extract(f.make(), f.name);
  const n = I.noticeText(r, f.name);
  assert.ok(n.startsWith("استُخرج النص من الملف «\u2068footnotes.docx\u2069»؛ راجعه قبل التدقيق."), n);
  assert.match(n, /تعديلات متعقَّبة/);
  assert.match(n, /الحواشي \(٣\)/);
  const p = await I.extract(new TextEncoder().encode("ﻻ"), "p.txt");
  assert.match(I.noticeText(p, "p.txt"), /حُوِّل ١ من أشكال الحروف/);
  const plain = await I.extract(new TextEncoder().encode("نص"), "n.txt");
  assert.equal(I.noticeText(plain, "n.txt"), "استُخرج النص من الملف «\u2068n.txt\u2069»؛ راجعه قبل التدقيق.");
});

test("no footnote number is left in the body text", async () => {
  const f = FIXTURES.find((x) => x.id === "docx-footnotes");
  const r = await I.extract(f.make(), f.name);
  const body = r.text.split(I.NOTE_RULE)[0];
  assert.doesNotMatch(body, /[0-9٠-٩]/);
});

test("a long run of spaces inside the text is read in linear time (no quadratic trim)", async () => {
  const t0 = Date.now();
  const r = await I.extract(new TextEncoder().encode("أ" + " ".repeat(400000) + "ب"), "spaces.txt", { maxChars: 500000 });
  assert.equal(r.ok, true);
  assert.ok(Date.now() - t0 < 2000, `${Date.now() - t0} ms`);
});
