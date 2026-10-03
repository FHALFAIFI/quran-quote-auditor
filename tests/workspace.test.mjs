// Tests for app/static/workspace.js: edits, stale findings, carried decisions (run: node --test tests/workspace.test.mjs).
import test from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "module";

const require = createRequire(import.meta.url);
const W = require("../app/static/workspace.js");
const R = require("../app/static/revision.js");

const cp = (s) => Array.from(s);
const at = (text, sub) => cp(text.slice(0, text.indexOf(sub))).length;
// A finding for `quote` inside `text`, with an optional correction «original ← replacement» inside it.
function finding(text, id, quote, fix) {
  const start = at(text, quote), end = start + cp(quote).length;
  const changes = [];
  if (fix) {
    const s = start + at(quote, fix[0]);
    changes.push({ id: `${id}-wording`, finding_id: id, kind: "wording", optional: false, start: s, end: s + cp(fix[0]).length, original: fix[0], replacement: fix[1] });
  }
  return W.withZone({ id, start, end, quote, changes, source: { surah: 2, ayah_start: 153, ayah_end: 153 }, reference: { status: "missing" }, detection: { kind: "marked" } }, text);
}

test("diffEdit finds the replaced region and reads nothing into an unchanged text", () => {
  assert.equal(W.diffEdit("abc", "abc"), null);
  assert.deepEqual(W.diffEdit("abcdef", "abXXdef"), { start: 2, oldEnd: 3, newEnd: 4 });
  assert.deepEqual(W.diffEdit("abc", "abXc"), { start: 2, oldEnd: 2, newEnd: 3 });
  assert.deepEqual(W.diffEdit("abXc", "abc"), { start: 2, oldEnd: 3, newEnd: 2 });
});

test("the caret decides which of two equal words was deleted", () => {
  const prev = "الصبر والصبر";
  const next = "الصبر ";            // the second word was deleted ...
  const e = W.diffEdit(prev, "والصبر", 0);   // ... or the first (caret at 0): the same text, two different edits
  assert.deepEqual(e, { start: 0, oldEnd: 6, newEnd: 0 });
  assert.deepEqual(W.diffEdit(prev, next, cp(next).length), { start: 6, oldEnd: 12, newEnd: 6 });
});

test("astral characters are counted as one", () => {
  assert.deepEqual(W.diffEdit("😀😀ab", "😀😀aXb"), { start: 3, oldEnd: 3, newEnd: 4 });
});

test("findings before an edit stay, findings after it move, and neither goes stale", () => {
  const text = "مقدمة قصيرة. قال تعالى: ﴿إن مع العسر يسرا﴾ [الشرح: 6] وبعدها كلام كثير هنا ﴿الحمد لله رب العالمين﴾.";
  const a = finding(text, 1, "إن مع العسر يسرا"), b = finding(text, 2, "الحمد لله رب العالمين");
  const edited = text.replace("مقدمة", "مقدمة طويلة جدا");
  const e = W.diffEdit(text, edited, at(edited, "مقدمة طويلة جدا") + cp("مقدمة طويلة جدا").length);
  const r = W.applyEdit([a, b], e, edited);
  assert.equal(r.touched.length, 0);
  assert.equal(r.findings.map((f) => cp(edited).slice(f.start, f.end).join("")).join("|"), "إن مع العسر يسرا|الحمد لله رب العالمين");
  // an edit after both leaves both where they were
  const edited2 = text + " ختام.";
  const r2 = W.applyEdit([a, b], W.diffEdit(text, edited2), edited2);
  assert.equal(r2.touched.length, 0);
  assert.deepEqual(r2.findings.map((f) => [f.start, f.end]), [[a.start, a.end], [b.start, b.end]]);
});

test("an edit inside the quotation, or in the next word, or adjacent to it, makes the finding stale and drops its corrections", () => {
  const text = "كتب الكاتب ﴿إن مع العسر يسرى﴾ ثم أكمل الكلام بعد ذلك بكلمات أخرى كثيرة.";
  const f = finding(text, 1, "إن مع العسر يسرى", ["يسرى", "يسرا"]);
  for (const [edited, caret, prevSel] of [
    [text.replace("العسر", "اليسر"), undefined, undefined],                                       // inside
    [text.replace("ثم أكمل", "ثم ثم أكمل"), at(text, "ثم أكمل") + cp("ثم ").length, [at(text, "ثم أكمل"), at(text, "ثم أكمل")]],  // the word after it
    [text.replace("كتب الكاتب", "كتب الأستاذ"), undefined, undefined],                           // the word before it
  ]) {
    const e = W.diffEdit(text, edited, caret, prevSel);
    const r = W.applyEdit([f], e, edited);
    assert.equal(r.findings.length, 1, edited);
    assert.equal(r.findings[0].stale, true, edited);
    assert.deepEqual(r.findings[0].changes, []);
  }
  // far away: not stale
  const far = text.replace("كثيرة", "قليلة");
  assert.equal(W.applyEdit([f], W.diffEdit(text, far), far).findings[0].stale, undefined);
});

test("typing at the very edge of the zone counts as touching it", () => {
  const text = "قال ﴿إن مع العسر يسرا﴾ وانتهى الأمر";
  const f = finding(text, 1, "إن مع العسر يسرا");
  const edited = text + "ا";   // appended to the last word of the zone? the zone ends at «وانتهى»: not touched
  assert.equal(W.applyEdit([f], W.diffEdit(text, edited), edited).findings[0].stale, undefined);
  const edited2 = text.replace("وانتهى", "وانتهىا");
  assert.equal(W.applyEdit([f], W.diffEdit(text, edited2), edited2).findings[0].stale, true);
});

test("deleting the whole quotation removes the finding", () => {
  const text = "قبل ﴿إن مع العسر يسرا﴾ بعد وبعد وبعد وبعد.";
  const f = finding(text, 1, "إن مع العسر يسرا");
  const edited = text.replace("إن مع العسر يسرا", "");
  const r = W.applyEdit([f], W.diffEdit(text, edited), edited);
  assert.equal(r.removed.length + r.findings.filter((x) => x.stale).length, 1);
});

test("an approved correction is applied to the edited text only where it still stands", () => {
  const text = "مقدمة. ﴿إن مع العسر يسرى﴾ وخاتمة طويلة هنا وهناك.";
  const f = finding(text, 1, "إن مع العسر يسرى", ["يسرى", "يسرا"]);
  const decisions = { "1-wording": "approved" };
  const edited = text.replace("مقدمة", "مقدمة جديدة أطول");
  const r = W.applyEdit([f], W.diffEdit(text, edited, at(edited, "مقدمة جديدة أطول") + cp("مقدمة جديدة أطول").length), edited);
  const out = R.applyApproved(edited, r.findings.flatMap((x) => x.changes), decisions);
  assert.equal(out.text, edited.replace("يسرى", "يسرا"));
  assert.equal(out.refused.length, 0);
  // the same approval is never applied to a different place by offsets alone
  const wrong = R.applyApproved("نص آخر تماما مختلف عن السابق كليا ولا يشبهه", f.changes, decisions);
  assert.equal(wrong.applied.length, 0);
});

test("carry: a decision survives a new audit only for an untouched finding with the same words, place and change", () => {
  const text = "أول ﴿إن مع العسر يسرى﴾ ثم قال في موضع آخر بعيد عنه بجمل كثيرة وكلمات متعددة ﴿الحمد لله رب العالمين﴾ وختم القول بما تيسر.";
  const f1 = finding(text, 1, "إن مع العسر يسرى", ["يسرى", "يسرا"]);
  const f2 = finding(text, 2, "الحمد لله رب العالمين");
  const prev = { findings: [f1, f2], decisions: { "1-wording": "approved" }, dismissed: { 2: true }, reviewed: {} };
  // the fresh audit returns the same two findings (numbered afresh by the server)
  const fresh = [finding(text, 1, "إن مع العسر يسرى", ["يسرى", "يسرا"]), finding(text, 2, "الحمد لله رب العالمين")];
  const out = W.carry(prev, fresh);
  assert.equal(out.decisions["1-wording"], "approved");
  assert.equal(out.dismissed[2], true);
  assert.equal(out.report.reset.length, 0);

  // the writer edited the first quotation: it is stale, so the new audit starts it undecided
  const edited = text.replace("يسرى", "يسرا");
  const r = W.applyEdit([f1, f2], W.diffEdit(text, edited), edited);
  const prev2 = { findings: r.findings, decisions: {}, dismissed: { 2: true }, reviewed: {} };
  const fresh2 = [finding(edited, 1, "إن مع العسر يسرا"), finding(edited, 2, "الحمد لله رب العالمين")];
  const out2 = W.carry(prev2, fresh2);
  assert.equal(out2.decisions["1-wording"], undefined);
  assert.equal(out2.dismissed[2], true);                 // untouched: the dismissal is kept

  // a different correction for the same span is a different decision
  const fresh3 = [finding(text, 1, "إن مع العسر يسرى", ["العسر", "اليسر"]), finding(text, 2, "الحمد لله رب العالمين")];
  const out3 = W.carry(prev, fresh3);
  assert.equal(out3.decisions["1-wording"], undefined);
  assert.equal(out3.report.reset.length >= 1, true);
});

test("carry renumbers findings in article order and keeps a manual finding the new audit did not make", () => {
  const text = "أ ﴿الحمد لله رب العالمين﴾ ب وبينهما كلام طويل كثير جدا ثم ج مع الصابرين أخيرا.";
  const manual = { ...finding(text, 7, "مع الصابرين"), detection: { kind: "manual" } };
  const prev = { findings: [manual], decisions: {}, dismissed: {}, reviewed: { 7: true } };
  const fresh = [finding(text, 1, "الحمد لله رب العالمين")];
  const out = W.carry(prev, fresh);
  assert.deepEqual(out.findings.map((f) => f.id), [1, 2]);
  assert.equal(out.findings[1].quote, "مع الصابرين");
  assert.equal(out.reviewed[2], true);
});

test("applyText replaces a code-point range", () => {
  assert.equal(W.applyText("😀 قال ﴿وما خلقت الجن والإنس إلا", 0, 0, "x"), "x😀 قال ﴿وما خلقت الجن والإنس إلا");
  assert.equal(W.applyText("abc", 1, 2, "XY"), "aXYc");
  assert.equal(W.cpToUnit("😀a", 1), 2);
  assert.equal(W.unitToCp("😀a", 2), 1);
});
