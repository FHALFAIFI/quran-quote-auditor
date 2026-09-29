// Revision engine: applies ONLY the changes the editor approved.
// Pure functions, no DOM. Offsets from the server are Unicode code points
// (Python str indices), so all slicing here works on code-point arrays; that
// keeps offsets right even when the article contains emoji or other
// characters outside the Basic Multilingual Plane.
// Used by app.js in the browser and by tests/revision.test.mjs under Node.
"use strict";

(function (root) {
  const cps = (s) => Array.from(s);

  // decisions: { [changeId]: "approved" | "rejected" | undefined (pending) }
  function approvedChanges(changes, decisions) {
    return changes.filter((c) => decisions[c.id] === "approved");
  }

  // Validate a set of changes against the article: each original must still be
  // at its offsets, and no two approved changes may overlap. Returns the
  // changes that can be applied (sorted by start) and the ones refused.
  function plan(article, changes) {
    const chars = cps(article);
    const ok = [], refused = [];
    const sorted = [...changes].sort((a, b) => a.start - b.start || a.end - b.end);
    let lastEnd = -1, lastInsertAt = -1;
    for (const c of sorted) {
      const valid = Number.isInteger(c.start) && Number.isInteger(c.end) && c.start >= 0 && c.end >= c.start && c.end <= chars.length;
      if (!valid || chars.slice(c.start, c.end).join("") !== c.original) { refused.push({ change: c, why: "offset" }); continue; }
      const overlaps = c.start < lastEnd || (c.start === c.end && c.start === lastInsertAt);
      if (overlaps) { refused.push({ change: c, why: "overlap" }); continue; }
      ok.push(c);
      lastEnd = Math.max(lastEnd, c.end);
      if (c.start === c.end) lastInsertAt = c.start;
    }
    return { ok, refused };
  }

  // The revised article: every character outside approved changes is kept exactly.
  function applyApproved(article, changes, decisions) {
    const { ok, refused } = plan(article, approvedChanges(changes, decisions));
    const chars = cps(article);
    const out = [];
    let pos = 0;
    for (const c of ok) {
      out.push(chars.slice(pos, c.start).join(""), c.replacement);
      pos = c.end;
    }
    out.push(chars.slice(pos).join(""));
    return { text: out.join(""), applied: ok, refused };
  }

  // Segments for a before/after preview.
  // type: "text" | "del" | "ins" | "unresolved" (an unchanged quotation still needing review)
  function previewSegments(article, changes, decisions, unresolvedSpans) {
    const { ok } = plan(article, approvedChanges(changes, decisions));
    const chars = cps(article);
    const events = [];
    for (const c of ok) events.push({ start: c.start, end: c.end, change: c });
    for (const u of unresolvedSpans || []) {
      if (!ok.some((c) => c.start < u.end && u.start < c.end)) events.push({ start: u.start, end: u.end, unresolved: u });
    }
    events.sort((a, b) => a.start - b.start || a.end - b.end);
    const segs = [];
    let pos = 0;
    for (const e of events) {
      if (e.start < pos) continue;
      if (e.start > pos) segs.push({ type: "text", text: chars.slice(pos, e.start).join("") });
      if (e.change) {
        if (e.change.original) segs.push({ type: "del", text: e.change.original, id: e.change.id });
        if (e.change.replacement) segs.push({ type: "ins", text: e.change.replacement, id: e.change.id });
      } else {
        segs.push({ type: "unresolved", text: chars.slice(e.start, e.end).join(""), id: e.unresolved.id });
      }
      pos = e.end;
    }
    if (pos < chars.length) segs.push({ type: "text", text: chars.slice(pos).join("") });
    return segs;
  }

  function slice(article, start, end) {
    return cps(article).slice(start, end).join("");
  }

  // Findings that still need a human after the editor's decisions:
  // needs review and no approved non-optional change resolves it.
  function unresolvedFindings(findings, decisions) {
    return findings.filter((f) => {
      const fixes = (f.changes || []).filter((c) => !c.optional);
      const pendingFix = fixes.some((c) => decisions[c.id] !== "approved");
      if (fixes.length) return pendingFix;
      return f.needs_review;
    });
  }

  const api = { approvedChanges, plan, applyApproved, previewSegments, slice, unresolvedFindings };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.Revision = api;
})(typeof window !== "undefined" ? window : globalThis);
