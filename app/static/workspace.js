// Edit tracking for the writing workspace: pure functions, no DOM.
// The article stays editable after an audit. Every edit is described as one replaced region (code points, like the server's
// offsets), and each finding is moved through it, or marked stale if the edit touched the quotation, its reference or the
// words next to it. A decision is carried to a new audit only for a finding whose span, words and place are unchanged.
// Used by app.js in the browser and by tests/workspace.test.mjs under Node.
"use strict";

(function (root) {
  const cps = (s) => (typeof s === "string" ? Array.from(s) : s);
  const isLetter = (ch) => ch !== undefined && /[\p{L}\p{M}\p{N}]/u.test(ch);
  const GAP_LIMIT = 12;  // how many characters of spaces / punctuation are looked through to reach the neighbouring word

  // ---- the edit between two texts -------------------------------------------------------------------------------
  // `caret` (code points, after the edit) and `prevSel` ([start, end] before it, read in `beforeinput`) say where the writer was
  // working, so that typing a word next to an equal word is not read as typing it on the other side.
  function diffEdit(prev, next, caret, prevSel) {
    const a = cps(prev), b = cps(next);
    if (a.length === b.length && a.every((ch, i) => ch === b[i])) return null;
    const same = (x, i, y, j, n) => { for (let k = 0; k < n; k++) if (x[i + k] !== y[j + k]) return false; return true; };
    if (prevSel && Number.isInteger(caret)) {
      const [s, e] = prevSel;
      if (s >= 0 && s <= e && e <= a.length && caret >= s && caret <= b.length && same(a, 0, b, 0, s) && a.length - e === b.length - caret && same(a, e, b, caret, a.length - e)) {
        return { start: s, oldEnd: e, newEnd: caret };
      }
    }
    if (Number.isInteger(caret) && caret >= 0 && caret <= b.length) {
      const tail = b.length - caret;           // the text after the caret is unchanged by a typed / pasted / deleted run
      const oldEnd = a.length - tail;
      if (oldEnd >= 0 && same(a, oldEnd, b, caret, tail)) {
        let s = 0;
        const n = Math.min(oldEnd, caret);
        while (s < n && a[s] === b[s]) s++;
        return { start: s, oldEnd, newEnd: caret };
      }
    }
    let s = 0;
    const n = Math.min(a.length, b.length);
    while (s < n && a[s] === b[s]) s++;
    let ea = a.length, eb = b.length;
    while (ea > s && eb > s && a[ea - 1] === b[eb - 1]) { ea--; eb--; }
    return { start: s, oldEnd: ea, newEnd: eb };
  }

  // A point moves through an edit: before it stays, after it shifts, inside the replaced region it goes to the nearer edge.
  function mapPoint(p, e, side) {
    if (p <= e.start) return p;
    if (p >= e.oldEnd) return p + (e.newEnd - e.oldEnd);
    return side === "end" ? e.newEnd : e.start;
  }

  // ---- zones: what an edit must not touch if a decision is to survive ---------------------------------------------
  // What the verdict was read from: the sentence before the quotation (the server looks for a lead-in such as «قال تعالى» up to 80
  // characters before it: audit.py reads 80, phrases.quran_cue 70), the quotation, its closing mark, the next word when nothing but
  // spaces / commas separates them (the end rule reads it), its reference and every change. Text beyond a full stop or a line break
  // does not enter the verdict.
  const LEAD_WINDOW = 80;
  const CLOSERS = "﴾»\"”)}]";
  function zoneOf(text, start, end, extra) {
    const t = cps(text);
    let i = start;
    const floor = Math.max(0, start - LEAD_WINDOW);
    while (i > floor && t[i - 1] !== "\n" && !".!؟?".includes(t[i - 1])) i--;
    let j = end, closed = 0;
    while (j < t.length && closed < 2 && CLOSERS.includes(t[j])) { j++; closed++; }
    let k = j, gap = 0;
    while (k < t.length && gap < GAP_LIMIT && (t[k] === " " || t[k] === "\t" || t[k] === "\u00a0" || t[k] === "،" || t[k] === "," || t[k] === "؛")) { k++; gap++; }
    let ze = j;
    if (k < t.length && isLetter(t[k])) { while (k < t.length && isLetter(t[k])) k++; ze = k; }
    let zs = Math.min(i, start), zEnd = Math.max(ze, end);
    for (const [a, b] of extra || []) { zs = Math.min(zs, a); zEnd = Math.max(zEnd, b); }
    return [zs, zEnd];
  }

  function extraRanges(f) {
    const out = (f.changes || []).map((c) => [c.start, c.end]);
    const r = f.reference && f.reference.found;
    if (r && Number.isInteger(r.start) && Number.isInteger(r.end)) out.push([r.start, r.end]);
    return out;
  }

  function withZone(f, text) {
    return { ...f, zone: zoneOf(text, f.start, f.end, extraRanges(f)) };
  }

  const shiftRef = (r, d) => (r && r.found && Number.isInteger(r.found.start) ? { ...r, found: { ...r.found, start: r.found.start + d, end: r.found.end + d } } : r);
  function shifted(f, d) {
    if (!d) return f;
    return {
      ...f, start: f.start + d, end: f.end + d, zone: f.zone ? [f.zone[0] + d, f.zone[1] + d] : f.zone,
      reference: shiftRef(f.reference, d),
      changes: (f.changes || []).map((c) => ({ ...c, start: c.start + d, end: c.end + d })),
    };
  }

  // Move findings through one edit. `text` is the text AFTER the edit.
  // returns { findings, touched: [finding as it was before the edit], removed: [finding as it was] }
  function applyEdit(findings, edit, text) {
    const delta = edit.newEnd - edit.oldEnd;
    const out = [], touched = [], removed = [];
    const t = cps(text);
    for (const f of findings) {
      const [zs, ze] = f.zone || [f.start, f.end];
      if (ze < edit.start) { out.push(f); continue; }                // wholly before the edit
      if (zs > edit.oldEnd) { out.push(shifted(f, delta)); continue; } // wholly after it
      // the edit overlaps or touches the zone: the result no longer describes this text
      const s = mapPoint(f.start, edit, "start"), e = mapPoint(f.end, edit, "end");
      if (e <= s) { removed.push(f); continue; }
      touched.push(f);
      const nf = {
        ...f, start: s, end: e, quote: t.slice(s, e).join(""), stale: true, staleSince: f.staleSince || Date.now(),
        changes: [], needs_review: true,
        review_reasons: ["عُدِّل النص في هذا الموضع أو بجواره بعد التدقيق؛ أعد التدقيق ليُفحص كما هو الآن."],
      };
      nf.zone = zoneOf(text, s, e, []);
      out.push(nf);
    }
    return { findings: out, touched, removed };
  }

  // ---- carrying decisions to a new audit ------------------------------------------------------------------------------
  const placeKey = (f) => (f.source ? `${f.source.surah}:${f.source.ayah_start}-${f.source.ayah_end}` : "-");
  const changeKey = (c) => [c.kind, c.start, c.end, c.original, c.replacement].join("|");
  const sameFinding = (o, n) => o.start === n.start && o.end === n.end && o.quote === n.quote && placeKey(o) === placeKey(n);
  const hasDecision = (f, st) => !!(st.dismissed[f.id] || st.reviewed[f.id] || (f.changes || []).some((c) => st.decisions[c.id]));

  // prev = { findings, decisions, dismissed, reviewed }: the writer's state, findings already moved through every edit.
  // fresh = the findings of a new audit of the current text.
  // A decision survives only if the new finding has the same span, the same words and the same place as a finding that no edit
  // touched, and (for a correction) the very same change. A finding the writer confirmed by hand is kept as it was.
  function carry(prev, fresh) {
    const valid = prev.findings.filter((f) => !f.stale);
    const manual = valid.filter((f) => f.detection && f.detection.kind === "manual");
    const kept = fresh.filter((n) => !manual.some((m) => m.start < n.end && n.start < m.end));
    const merged = [...kept, ...manual].sort((a, b) => a.start - b.start || a.end - b.end);
    const decisions = {}, dismissed = {}, reviewed = {};
    const report = { carried: 0, reset: [] };
    const used = new Set();
    // renumber: ids are sequential in article order
    const finalList = merged.map((n, i) => {
      const id = i + 1;
      const o = manual.includes(n) ? n : valid.find((p) => !used.has(p) && sameFinding(p, n));
      if (o) used.add(o);
      const changes = (n.changes || []).map((c) => ({ ...c, id: `${id}-${String(c.id).split("-").slice(1).join("-")}`, finding_id: id }));
      if (o) {
        if (prev.dismissed[o.id]) dismissed[id] = true;
        if (prev.reviewed[o.id]) reviewed[id] = true;
        (o.changes || []).forEach((oc) => {
          const dec = prev.decisions[oc.id];
          if (!dec) return;
          const nc = changes.find((c) => changeKey(c) === changeKey(oc));
          if (nc) { decisions[nc.id] = dec; report.carried++; } else report.reset.push({ quote: o.quote, why: "changed" });
        });
        if (prev.dismissed[o.id] || prev.reviewed[o.id]) report.carried++;
      }
      return { ...n, id, changes };
    });
    // decided findings that have no counterpart any more
    for (const p of prev.findings) {
      if (used.has(p) || !hasDecision(p, prev)) continue;
      report.reset.push({ quote: p.quote, why: p.stale ? "edited" : "gone" });
    }
    return { findings: finalList, decisions, dismissed, reviewed, report };
  }

  // The editor's own words for what an accepted suggestion does, applied to a string (code points): used for the draft and by tests.
  // `replaceStart/End` are code-point offsets into `text`.
  function applyText(text, replaceStart, replaceEnd, insert) {
    const t = cps(text);
    return t.slice(0, replaceStart).join("") + insert + t.slice(replaceEnd).join("");
  }

  const cpToUnit = (s, cp) => Array.from(s).slice(0, cp).join("").length;
  const unitToCp = (s, unit) => Array.from(s.slice(0, unit)).length;

  const api = { cps, diffEdit, mapPoint, zoneOf, withZone, applyEdit, carry, applyText, cpToUnit, unitToCp, changeKey, placeKey };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.Workspace = api;
})(typeof window !== "undefined" ? window : globalThis);
