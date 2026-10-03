// Verse suggestions while writing. The words and the references come from the server's lookup in the Quranpedia text
// (/api/suggest); nothing is generated here and no language model takes part. A suggestion is only ever inserted by an explicit
// act: Tab, a click, or a tap. Typing on, moving the caret, Escape or a newer search dismisses it.
// All server text is inserted with textContent. The script touches the editor only through the textarea element.
"use strict";

(function () {
  const $ = (id) => document.getElementById(id);
  const W = window.Workspace;
  const PREF_KEY = "qqa-suggest-v1";
  const DEBOUNCE_MS = 220;
  const BEFORE_CHARS = 700;
  const AFTER_CHARS = 100;

  let ta, box, live;
  let prefs = { auto: true, distinct: false };
  let seq = 0, timer = null, abort = null;
  let state = null;           // { choices, selected, base, before, caret, explicit }
  let dismissedKey = null;    // `${caret}|${tail of before}` of a suggestion the writer dismissed
  let composing = false;
  let busy = false;

  const toAr = (n) => String(n).replace(/\d/g, (d) => "٠١٢٣٤٥٦٧٨٩"[d]);
  const MARKS = /[ً-ٰٟۖ-ۭـ​-‏]/g;
  const CUE = /(?:تعالى|سبحانه|قال الله|يقول الله|قوله|في القرآن|القرآن الكريم|الآية|آية|يقول ربنا|قال ربنا|في كتابه)/;

  function loadPrefs() {
    try { prefs = { ...prefs, ...JSON.parse(localStorage.getItem(PREF_KEY) || "{}") }; } catch { /* storage unavailable: defaults */ }
  }
  function savePrefs() {
    try { localStorage.setItem(PREF_KEY, JSON.stringify(prefs)); } catch { /* ignore */ }
  }

  // ---- when to ask the server (the same gate as the server's, so that ordinary prose is not sent) -----------------
  function openQuote(text) {
    const pairs = [["﴿", "﴾"], ["«", "»"], ["“", "”"], ["{", "}"]];
    for (const [o, c] of pairs) if (text.lastIndexOf(o) > text.lastIndexOf(c)) return true;
    return (text.match(/"/g) || []).length % 2 === 1;
  }
  function worthAsking(before) {
    const tail = before.slice(-300);
    if (openQuote(tail)) return true;
    const sentence = tail.slice(Math.max(tail.lastIndexOf("."), tail.lastIndexOf("؟"), tail.lastIndexOf("\n")) + 1, tail.length);
    if (CUE.test(sentence.replace(MARKS, ""))) return true;
    return prefs.distinct && sentence.trim().split(/\s+/).length >= 4;
  }

  // ---- the request ----------------------------------------------------------------------------------------------
  function context() {
    const value = ta.value;
    const caret = ta.selectionEnd;
    let from = Math.max(0, caret - BEFORE_CHARS);
    if (from > 0 && /[\uDC00-\uDFFF]/.test(value[from])) from++;   // do not start inside a surrogate pair
    return { value, caret, from, before: value.slice(from, caret), after: value.slice(caret, caret + AFTER_CHARS) };
  }

  async function ask(explicit) {
    if (composing) return;
    if (!explicit && ta.selectionStart !== ta.selectionEnd) return hide();
    const ctx = context();
    if (!explicit && (!prefs.auto && !prefs.distinct)) return hide();
    if (!explicit && !worthAsking(ctx.before)) return hide();
    if (!explicit && dismissedKey === `${ctx.caret}|${ctx.before.slice(-60)}`) return;
    const mySeq = ++seq;
    if (abort) abort.abort();
    abort = new AbortController();
    busy = true;
    if (explicit) showMessage("جارٍ البحث في نص المصحف…");
    try {
      const res = await fetch("/api/suggest", {
        method: "POST", headers: { "Content-Type": "application/json" }, signal: abort.signal,
        body: JSON.stringify({ before: ctx.before, after: ctx.after, explicit, distinct: prefs.distinct, request_id: mySeq }),
      });
      if (!res.ok) { if (explicit) showMessage(res.status === 429 ? "طلبات كثيرة؛ انتظر لحظات ثم أعد المحاولة." : "تعذّر الاتصال باقتراحات المصحف الآن."); return; }
      const data = await res.json();
      // A newer search, a keystroke, a caret move or another selection since the request left: the answer is for text that is gone.
      if (data.request_id !== seq || mySeq !== seq) return;
      const now = context();
      if (now.value.slice(ctx.from, ctx.caret) !== ctx.before || now.caret !== ctx.caret || ta.selectionStart !== ta.selectionEnd && !explicit) return;
      if (data.status === "suggest" && data.choices.length) show({ ...data, base: ctx.from, before: ctx.before, caret: ctx.caret, explicit });
      else if (explicit) showMessage(hintText(data));
      else hide();
    } catch (e) {
      if (e.name !== "AbortError" && explicit) showMessage("تعذّر الاتصال باقتراحات المصحف الآن.");
    } finally {
      if (mySeq === seq) busy = false;
    }
  }

  function schedule() {
    clearTimeout(timer);
    if (abort) abort.abort();
    seq++;                                         // an answer to an earlier text can no longer be shown
    timer = setTimeout(() => ask(false), DEBOUNCE_MS);
  }

  const HINTS = {
    too_short: "اكتب كلمتين على الأقل من أول الآية، ثم اضغط «أكمل من المصحف».",
    ambiguous: "هذه الكلمات تتطابق مع مواضع كثيرة في المصحف؛ أضف كلمة أو كلمتين لنحدّد الآية.",
    too_common: "هذه الكلمات شائعة في المصحف ولا تحدّد آية؛ أضف كلمة أو كلمتين.",
    no_match: "لا نجد في المصحف آية تبدأ بهذه الكلمات، أو أن الآية مكتملة عندك.",
    complete: "الآية مكتملة عندك؛ لا شيء يُضاف.",
    non_quran_cue: "سبقت هذه الكلمات إشارة إلى حديث أو دعاء، فلا نقترح عليها آية. اكتب «قال تعالى» أو افتح ﴿ إن كانت آية.",
    formula: "هذه عبارة شائعة الاستعمال؛ اكتب «قال تعالى» قبلها إن قصدتَ آية.",
    already_present: "الكلمة التالية موجودة عندك بالفعل.",
    inside_word: "المؤشر داخل كلمة؛ انقله إلى نهاية الكلمات التي كتبتَها.",
    source_unavailable: "تعذّر الوصول إلى قرآنبيديا الآن؛ لا نقترح آيات دون نصها.",
  };
  const hintText = (d) => HINTS[d.reason] || "لا نجد اقتراحًا لهذه الكلمات.";

  // ---- the box ---------------------------------------------------------------------------------------------------
  function announce(text) {
    if (!live) return;
    live.textContent = "";
    setTimeout(() => { live.textContent = text; }, 30);
  }

  function hide() {
    state = null;
    if (box) { box.hidden = true; box.replaceChildren(); box.classList.remove("is-message"); }
  }

  function dismiss() {
    if (!state) return hide();
    dismissedKey = `${state.caret}|${state.before.slice(-60)}`;
    hide();
    announce("تجاهلتَ الاقتراح.");
  }

  function showMessage(text) {
    state = null;
    box.classList.add("is-message");
    box.hidden = false;
    box.replaceChildren(el("p", { class: "sg-msg", text }), el("button", { type: "button", class: "btn small ghost sg-close", text: "إغلاق", onclick: hide }));
    place(ta.selectionEnd);
    announce(text);
  }

  function el(tag, attrs, ...kids) {
    const n = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v === null || v === undefined || v === false) continue;
      if (k === "class") n.className = v;
      else if (k === "text") n.textContent = v;
      else if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
      else n.setAttribute(k, v === true ? "" : v);
    }
    for (const c of kids.flat()) if (c !== null && c !== undefined && c !== false) n.append(c instanceof Node ? c : document.createTextNode(String(c)));
    return n;
  }

  const KIND_TEXT = {
    continue: "تكملة من المصحف", complete_word: "إتمام الكلمة", replace: "تصحيح محتمل", insert: "كلمة ناقصة محتملة",
  };

  function choiceLine(c) {
    if (c.kind === "replace") return [el("span", { class: "sg-old", text: c.from_text }), el("span", { class: "sg-arrow", "aria-hidden": "true", text: " ← " }), el("span", { class: "sg-new quran", text: c.to_text })];
    if (c.kind === "insert") return [el("span", { class: "sg-cap", text: "أضف " }), el("span", { class: "sg-new quran", text: c.to_text })];
    return [el("span", { class: "sg-new quran", text: c.to_text })];
  }

  function verseLine(c) {
    const v = c.verse;
    const line = el("p", { class: "sg-verse quran", dir: "rtl" });
    v.words.forEach((w, i) => {
      if (i) line.append(" ");
      const cls = i >= v.added[0] && i < v.added[1] ? "w-add" : i >= v.typed[0] && i < v.typed[1] ? "w-typed" : "w-dim";
      line.append(el("span", { class: cls, text: w }));
    });
    return line;
  }

  function show(s) {
    const ambiguous = s.ambiguous;
    state = { ...s, selected: ambiguous ? -1 : 0 };
    box.classList.remove("is-message");
    box.hidden = false;
    place(s.caret);
    render();
    const c0 = s.choices[0];
    announce(ambiguous
      ? `اقتراحات من المصحف: ${toAr(s.choices.length)} مواضع محتملة. استخدم السهمين للاختيار ثم Tab للإدراج، أو Esc للتجاهل.`
      : `اقتراح من المصحف: ${c0.kind === "replace" ? c0.from_text + " ← " : ""}${c0.to_text}، ${c0.label.replace(/\d+/g, toAr)}. اضغط Tab للإدراج أو Esc للتجاهل.`);
  }

  function render() {
    const s = state;
    if (!s) return;
    const certainties = new Set(s.choices.map((c) => c.certainty));
    const head = el("div", { class: "sg-head" },
      el("p", { class: "sg-title" },
        el("strong", { text: s.ambiguous ? "أكثر من آية تبدأ هكذا — اختر" : KIND_TEXT[s.choices[0].kind] }),
        certainties.has("probable") ? el("span", { class: "sg-tag probable", text: "احتمال، لا يُطبَّق إلا بموافقتك" }) : el("span", { class: "sg-tag exact", text: "من نص قرآنبيديا" })),
      el("button", { type: "button", class: "btn small ghost sg-close", tabindex: "-1", onclick: dismiss, "aria-label": "تجاهل الاقتباس المقترح", title: "Esc" }, "تجاهل", el("kbd", { class: "kbd", text: "Esc" })));
    const list = el("ul", { class: "sg-list" });
    s.choices.forEach((c, i) => {
      const sel = i === s.selected;
      const open = sel || s.choices.length === 1;
      const item = el("li", { id: `sg-${i}`, "aria-current": sel ? "true" : null, class: `sg-item ${open ? "sel" : ""} ${c.kind}` },
        el("div", { class: "sg-main" },
          el("span", { class: "sg-text" }, choiceLine(c)),
          el("span", { class: "sg-ref", text: c.label.replace(/\d+/g, toAr) })),
        open ? verseLine(c) : null,
        el("div", { class: "sg-actions" },
          open ? el("button", { type: "button", class: "btn small primary sg-accept", tabindex: "-1", onclick: () => accept(i, false), "aria-label": `${c.kind === "replace" ? "صحّح" : "أدرج"}: ${c.to_text} — ${c.label}` },
            c.kind === "replace" ? "صحّح" : "أدرج", el("kbd", { class: "kbd", text: "Tab" })) : null,
          open && c.extend_text ? el("button", { type: "button", class: "btn small sg-extend", tabindex: "-1", onclick: () => accept(i, true), "aria-label": `أدرج إلى نهاية الآية (${toAr(c.remaining_words)} كلمات أخرى)`, text: `إلى نهاية الآية (+${toAr(c.remaining_words)})` }) : null,
          !open ? el("button", { type: "button", class: "btn small", tabindex: "-1", onclick: () => { state.selected = i; render(); }, text: "اعرض الآية" }) : null));
      list.append(item);
    });
    const hint = s.selected < 0 ? el("p", { class: "sg-keys small muted", text: "↓ لاختيار آية، ثم Tab للإدراج" }) : s.choices.length > 1 ? el("p", { class: "sg-keys small muted", text: "↑↓ للتنقّل بين الآيات" }) : null;
    box.replaceChildren(...[head, list, hint].filter(Boolean));
    fit();
  }

  // ---- inserting ---------------------------------------------------------------------------------------------------
  function accept(i, extend) {
    const s = state;
    if (!s) return;
    const c = s.choices[i];
    const startUnit = s.base + W.cpToUnit(s.before, c.replace_start);
    const endUnit = s.base + W.cpToUnit(s.before, c.replace_end);
    // The text must still be exactly what the suggestion was made for.
    if (ta.value.slice(s.base, s.base + s.before.length) !== s.before || ta.value.slice(startUnit, endUnit) !== c.from_text) { hide(); return; }
    const insert = c.insert_text + (extend && c.extend_text ? c.extend_text : "");
    hide();
    ta.focus({ preventScroll: true });
    ta.setSelectionRange(startUnit, endUnit);
    // execCommand keeps the browser's own undo history (Ctrl+Z takes the insertion back); setRangeText is the fallback.
    let ok = false;
    try { ok = document.execCommand("insertText", false, insert); } catch { ok = false; }
    if (!ok || ta.value.slice(startUnit, startUnit + insert.length) !== insert) {
      ta.setRangeText(insert, startUnit, endUnit, "end");
      ta.dispatchEvent(new Event("input", { bubbles: true }));
    }
    const msg = c.kind === "replace" ? `صُحّحت «${c.from_text}» إلى «${c.to_text}» (${c.label.replace(/\d+/g, toAr)}).`
      : `أُدرجت من المصحف: «${c.to_text}» (${c.label.replace(/\d+/g, toAr)}).`;
    announce(msg + " Ctrl+Z يتراجع عنه.");
    document.dispatchEvent(new CustomEvent("qqa:suggestion-accepted", { detail: { kind: c.kind, label: c.label, text: insert } }));
  }

  // ---- where to draw the box -----------------------------------------------------------------------------------
  let mirror = null;
  function caretPoint(caretUnit) {
    if (!mirror) { mirror = el("div", { class: "caret-mirror ed-text", "aria-hidden": "true" }); $("editor").append(mirror); }
    mirror.style.width = ta.clientWidth + "px";
    mirror.textContent = ta.value.slice(0, caretUnit);
    const probe = el("span", { text: "​" });
    mirror.append(probe);
    const p = { x: probe.offsetLeft, y: probe.offsetTop, h: probe.offsetHeight || parseFloat(getComputedStyle(ta).lineHeight) || 30 };
    mirror.textContent = "";
    return p;
  }
  // Under the line the caret is on, its right edge near the caret (Arabic runs right to left), on every screen width: the writer's
  // eyes are already there. When the room below is short (a phone's keyboard) it goes above the line, else the page scrolls to show it.
  let anchor = null;
  function place(caretUnit) {
    const wrapW = $("editor").clientWidth;
    const w = Math.min(wrapW - 16, 430);
    anchor = caretPoint(caretUnit);
    box.style.width = w + "px";
    box.style.left = Math.max(8, Math.min(wrapW - w - 8, anchor.x + 24 - w)) + "px";
    box.style.top = anchor.y + anchor.h + 6 + "px";
  }
  function fit() {
    if (!anchor || box.hidden) return;
    const vv = window.visualViewport;
    const limit = (vv ? vv.offsetTop + vv.height : innerHeight) - 8;
    const top = (vv ? vv.offsetTop : 0) + 8;
    const r = box.getBoundingClientRect();
    if (r.bottom <= limit) return;
    const edTop = $("editor").getBoundingClientRect().top;
    const aboveTop = edTop + anchor.y - 6 - r.height;
    if (aboveTop >= top) { box.style.top = anchor.y - 6 - r.height + "px"; return; }
    window.scrollBy({ top: r.bottom - limit, behavior: "instant" });
  }

  // ---- events ----------------------------------------------------------------------------------------------------
  function onKeydown(e) {
    if (e.altKey && !e.ctrlKey && !e.metaKey && (e.key === "q" || e.key === "Q" || e.code === "KeyQ")) { e.preventDefault(); ask(true); return; }
    if (!state || composing) return;
    if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); dismiss(); return; }
    if (e.key === "Tab" && !e.shiftKey && !e.altKey && !e.ctrlKey && !e.metaKey && state.selected >= 0) { e.preventDefault(); accept(state.selected, false); return; }
    if ((e.key === "ArrowDown" || e.key === "ArrowUp") && state.choices.length > 1 && !e.shiftKey && !e.altKey && !e.ctrlKey && !e.metaKey) {
      e.preventDefault();
      const n = state.choices.length;
      state.selected = e.key === "ArrowDown" ? (state.selected + 1 + n) % n : (state.selected - 1 + n * 2) % n;
      render();
    }
  }

  function onSelection() {
    // The caret moved away from the place the suggestion was made for: it no longer applies.
    if (state && (document.activeElement !== ta || ta.selectionEnd !== state.caret || (!state.explicit && ta.selectionStart !== ta.selectionEnd))) hide();
  }

  function init() {
    ta = $("article"); box = $("suggest"); live = $("sr-live");
    if (!ta || !box) return;
    loadPrefs();
    const optSuggest = $("opt-suggest"), optDistinct = $("opt-distinct");
    if (optSuggest) { optSuggest.checked = prefs.auto; optSuggest.addEventListener("change", () => { prefs.auto = optSuggest.checked; savePrefs(); if (!prefs.auto) hide(); }); }
    if (optDistinct) { optDistinct.checked = prefs.distinct; optDistinct.addEventListener("change", () => { prefs.distinct = optDistinct.checked; savePrefs(); }); }
    ta.addEventListener("input", () => { hide(); dismissedKey = null; schedule(); });
    ta.addEventListener("keydown", onKeydown);
    ta.addEventListener("compositionstart", () => { composing = true; hide(); });
    ta.addEventListener("compositionend", () => { composing = false; schedule(); });
    ta.addEventListener("blur", () => { setTimeout(() => { if (!box.contains(document.activeElement)) hide(); }, 120); });
    document.addEventListener("selectionchange", onSelection);
    // Buttons in the box must not take the caret (or close the phone's keyboard) away from the text.
    box.addEventListener("mousedown", (e) => e.preventDefault());
    box.addEventListener("pointerdown", (e) => { if (e.pointerType !== "mouse") e.preventDefault(); });
    $("complete-btn")?.addEventListener("click", () => { ta.focus({ preventScroll: true }); ask(true); });
    $("sel-complete")?.addEventListener("click", () => { ta.focus({ preventScroll: true }); ask(true); });
    window.addEventListener("resize", () => { if (state) { place(state.caret); fit(); } });
  }

  window.QQASuggest = { hide, ask, get open() { return !!state; }, get prefs() { return prefs; } };
  document.addEventListener("DOMContentLoaded", init);
})();
