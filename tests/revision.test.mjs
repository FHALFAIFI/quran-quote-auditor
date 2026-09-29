// Tests for app/static/revision.js (run: node --test tests/revision.test.mjs).
import test from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "module";

const require = createRequire(import.meta.url);
const R = require("../app/static/revision.js");

const ch = (id, start, end, original, replacement, extra = {}) => ({ id, start, end, original, replacement, optional: false, ...extra });

test("nothing changes without approval", () => {
  const a = "قال: {فإن مع العسر يسرا} [الشرح: 6]\nانتهى.";
  const s = Array.from(a.slice(0, a.indexOf("الشرح"))).length;
  const c = ch("1-reference", s, s + 8, "الشرح: 6", "الشرح: 5");
  assert.equal(Array.from(a).slice(s, s + 8).join(""), "الشرح: 6");
  assert.equal(R.applyApproved(a, [c], {}).text, a);
  assert.equal(R.applyApproved(a, [c], { "1-reference": "rejected" }).text, a);
  assert.equal(R.applyApproved(a, [c], { "1-reference": "approved" }).text, a.replace("الشرح: 6", "الشرح: 5"));
});

test("code-point offsets survive emoji (astral characters)", () => {
  const a = "😀😀 {إن مع العسر يسرا} [الشرح: 5] 👍";
  const cps = Array.from(a);
  const start = cps.join("").indexOf("الشرح") >= 0 ? Array.from(a.slice(0, a.indexOf("الشرح"))).length : -1;
  const c = ch("x", start, start + 8, "الشرح: 5", "الشرح: 6");
  const out = R.applyApproved(a, [c], { x: "approved" });
  assert.equal(out.refused.length, 0);
  assert.equal(out.text, "😀😀 {إن مع العسر يسرا} [الشرح: 6] 👍");
});

test("stale offsets are refused, not applied", () => {
  const a = "نص مختلف تمامًا";
  const out = R.applyApproved(a, [ch("x", 0, 2, "الشرح", "Z")], { x: "approved" });
  assert.equal(out.text, a);
  assert.equal(out.refused[0].why, "offset");
});

test("overlapping approved changes: the later one is refused", () => {
  const a = "abcdefghij";
  const c1 = ch("a", 2, 6, "cdef", "XX");
  const c2 = ch("b", 4, 8, "efgh", "YY");
  const out = R.applyApproved(a, [c1, c2], { a: "approved", b: "approved" });
  assert.equal(out.text, "abXXghij");
  assert.equal(out.refused.length, 1);
});

test("two insertions at the same point are not both applied", () => {
  const a = "abc";
  const out = R.applyApproved(a, [ch("a", 1, 1, "", "X"), ch("b", 1, 1, "", "Y")], { a: "approved", b: "approved" });
  assert.equal(out.text, "aXbc");
});

test("repeated identical text: only the targeted occurrence changes", () => {
  const a = "{فإن مع العسر يسرا} [الشرح: 6] و{فإن مع العسر يسرا} [الشرح: 6]";
  const second = Array.from(a.slice(0, a.lastIndexOf("الشرح"))).length;
  const out = R.applyApproved(a, [ch("x", second, second + 8, "الشرح: 6", "الشرح: 5")], { x: "approved" });
  assert.equal(out.text, "{فإن مع العسر يسرا} [الشرح: 6] و{فإن مع العسر يسرا} [الشرح: 5]");
});

test("everything outside approved spans is byte-identical (line breaks, punctuation, markup)", () => {
  const a = "سطر أول!\r\n\t<b>عنوان</b>\n\nقال: {ان مع العسر يسرا} [الشرح: 6]؛ «نص عادي»...\n";
  const s = Array.from(a.slice(0, a.indexOf("الشرح"))).length;
  const out = R.applyApproved(a, [ch("x", s, s + 8, "الشرح: 6", "الشرح: 6-7")], { x: "approved" });
  const [pre, post] = a.split("الشرح: 6");
  assert.equal(out.text, pre + "الشرح: 6-7" + post);
});

test("preview segments mark deletions, insertions and unresolved spans", () => {
  const a = "أ {إن الله مع الصابرون} ب [الشرح: 6] ج";
  const q0 = Array.from(a.slice(0, a.indexOf("إن"))).length;
  const r0 = Array.from(a.slice(0, a.indexOf("الشرح"))).length;
  const segs = R.previewSegments(a, [ch("r", r0, r0 + 8, "الشرح: 6", "الشرح: 5")], { r: "approved" }, [{ start: q0, end: q0 + 18, id: 2 }]);
  const types = segs.map((s) => s.type);
  assert.deepEqual(types, ["text", "unresolved", "text", "del", "ins", "text"]);
  assert.equal(segs.map((s) => (s.type === "del" ? "" : s.text)).join(""), R.applyApproved(a, [ch("r", r0, r0 + 8, "الشرح: 6", "الشرح: 5")], { r: "approved" }).text);
});

test("unresolved findings: needs review until every non-optional fix is approved", () => {
  const findings = [
    { id: 1, needs_review: false, changes: [ch("1-v", 0, 1, "a", "b", { optional: true })] },
    { id: 2, needs_review: true, changes: [] },
    { id: 3, needs_review: true, changes: [ch("3-r", 5, 6, "x", "y")] },
  ];
  assert.deepEqual(R.unresolvedFindings(findings, {}).map((f) => f.id), [2, 3]);
  assert.deepEqual(R.unresolvedFindings(findings, { "3-r": "approved" }).map((f) => f.id), [2]);
  assert.deepEqual(R.unresolvedFindings(findings, { "3-r": "rejected" }).map((f) => f.id), [2, 3]);
});
