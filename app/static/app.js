// Quran quotation auditor — frontend.
// All user-supplied and server-supplied text is inserted with textContent
// (never innerHTML), so article text cannot inject markup.
"use strict";

const $ = (id) => document.getElementById(id);
let MAX_CHARS = 6000;
let lastArticle = "";
let lastResult = null;

function el(tag, attrs, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") node.className = v;
    else if (k === "text") node.textContent = v;
    else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
    else node.setAttribute(k, v);
  }
  for (const c of children.flat()) {
    if (c === null || c === undefined || c === false) continue;
    node.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return node;
}

const toArabicDigits = (n) => String(n).replace(/\d/g, (d) => "٠١٢٣٤٥٦٧٨٩"[d]);

const WORDING = {
  matched: { literal: ["مطابق حرفيًا", "ok"], diacritics: ["مطابق بتجاهل التشكيل", "ok"], normalized: ["مطابق بعد توحيد الرسم", "ok"] },
  difference: { diacritics: ["اختلاف في التشكيل", "diff"], normalized: ["اختلاف في رسم الحروف", "diff"], fuzzy: ["اختلاف — أقرب موضع مقترح", "diff"] },
};
function wordingChip(w) {
  if (w.status === "uncertain") return ["غير محسوم", "warn"];
  const byLevel = WORDING[w.status] || {};
  return byLevel[w.level] || (w.status === "matched" ? ["مطابق", "ok"] : ["اختلاف", "diff"]);
}
const REF = {
  matched: ["إحالة مطابقة", "ok"],
  missing: ["بلا إحالة", "muted-chip"],
  incorrect: ["إحالة خاطئة", "bad"],
  uncertain: ["إحالة غير محسومة", "warn"],
};
const DETECTED = { marked: "معلَّم بأقواس أو علامات", ai: "استخراج بالذكاء الاصطناعي", scan: "مطابقة آلية مع نص المصحف" };
const COVERAGE = { full: "آية كاملة", partial: "جزء من آية", "multi-partial": "أجزاء من آيات متتالية" };

function chip(label, cls) { return el("span", { class: `chip ${cls}`, text: label }); }

// ---------------------------------------------------------------- health
async function loadHealth() {
  const banner = $("mode-banner");
  try {
    const res = await fetch("/api/health");
    const h = await res.json();
    MAX_CHARS = h.max_chars || MAX_CHARS;
    updateCount();
    banner.hidden = false;
    banner.replaceChildren();
    if (h.mode === "ai") {
      // "Configured" is not "working": state what is known about the last real call.
      const last = h.ai_last_call || {};
      banner.className = "banner ai";
      banner.append(el("strong", { text: "الاستخراج بالذكاء الاصطناعي مُعَدّ " }), `(${h.provider}). `);
      if (last.outcome === "ok") {
        banner.append("آخر استدعاء له على هذا الخادم نجح. ");
      } else if (last.outcome === "failed") {
        banner.append(el("b", { text: "آخر استدعاء له على هذا الخادم فشل" }),
          last.cooldown_seconds > 0 ? ` ويُتخطّى مؤقتًا (${toArabicDigits(last.cooldown_seconds)} ث). ` : ". ");
      } else {
        banner.append("لم يُستدعَ بعدُ على هذا الخادم. ");
      }
      banner.append("نتيجة كل تدقيق تبيّن هل استجاب النموذج فعلًا أو استُخدم الوضع الاحتياطي. ",
        "دوره اقتراح مواضع الاقتباس فقط، ويُتحقق من كل مقترح بمقارنته بنص المقال ثم بنص المصحف من قرآنبيديا.");
    } else {
      banner.className = "banner reduced";
      banner.append(el("strong", { text: "وضع مخفّض — الذكاء الاصطناعي غير مفعّل. " }),
        "تُفحص فقط الاقتباسات المعلَّمة صراحةً (﴿ ﴾ أو { } أو علامات تنصيص مع «قال تعالى» أو إحالة)، إضافةً إلى المقاطع المطابقة حرفيًا لنص المصحف (5 كلمات فأكثر). قد تفوت الاقتباسات غير المعلَّمة المنقولة بخطأ.");
    }
  } catch {
    banner.hidden = true;
  }
}

// ---------------------------------------------------------------- input
function updateCount() {
  const n = $("article").value.length;
  const c = $("char-count");
  c.textContent = `${toArabicDigits(n)} / ${toArabicDigits(MAX_CHARS)} حرف`;
  c.classList.toggle("char-over", n > MAX_CHARS);
}

async function loadSample(name) {
  if (!name) return;
  try {
    const res = await fetch(`/static/samples/${encodeURIComponent(name)}.txt`);
    if (!res.ok) throw new Error();
    $("article").value = (await res.text()).trim();
    updateCount();
  } catch {
    setStatus("تعذّر تحميل المثال.", true);
  }
}

function setStatus(text, isError, busy) {
  const s = $("status");
  s.replaceChildren();
  s.classList.toggle("error", !!isError);
  if (busy) s.append(el("span", { class: "spinner", "aria-hidden": "true" }));
  if (text) s.append(text);
}

async function runAudit() {
  const article = $("article").value.replace(/\r\n?/g, "\n");
  if (!article.trim()) { setStatus("الرجاء لصق نص المقال أولًا.", true); return; }
  if (article.length > MAX_CHARS) { setStatus(`النص أطول من الحد المسموح (${toArabicDigits(MAX_CHARS)} حرف).`, true); return; }
  const btn = $("audit-btn");
  btn.disabled = true;
  setStatus("جارٍ التدقيق ومقارنة الاقتباسات بنص المصحف…", false, true);
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 60000);
  try {
    const res = await fetch("/api/audit", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ article }),
      signal: ctrl.signal,
    });
    let data;
    try { data = await res.json(); } catch { data = { error: "استجابة غير متوقعة من الخادم." }; }
    if (!res.ok) { setStatus(data.error || "تعذّر إكمال التدقيق.", true); return; }
    lastArticle = article;
    lastResult = data;
    render(data);
    loadHealth();  // refresh the banner with this call's real outcome
    setStatus(`اكتمل التدقيق في ${toArabicDigits((data.elapsed_ms / 1000).toFixed(1))} ث.`);
  } catch (e) {
    setStatus(e.name === "AbortError" ? "انتهت مهلة الطلب؛ حاول مرة أخرى." : "تعذّر الاتصال بالخادم.", true);
  } finally {
    clearTimeout(timer);
    btn.disabled = false;
  }
}

// ---------------------------------------------------------------- render
function render(data) {
  $("results").hidden = false;
  const notices = $("notices");
  notices.replaceChildren(...(data.notices || []).map((n) => el("div", { class: `notice ${n.level}`, text: n.text })));
  if (data.mode === "reduced") {
    notices.append(el("div", { class: "notice warning", text: "نُفِّذ هذا التدقيق في الوضع المخفّض دون ذكاء اصطناعي." }));
  } else if (data.mode === "ai") {
    notices.append(el("div", { class: "notice info", text: `استجاب نموذج الذكاء الاصطناعي (${data.provider_model || data.provider}) في هذا التدقيق، وتحقق الخادم من كل مقترح منه.` }));
  }
  if (data.source?.available && data.source.fetched_at) {
    const when = new Date(data.source.fetched_at * 1000).toLocaleString("ar", { dateStyle: "medium", timeStyle: "short" });
    notices.append(el("div", { class: "notice info" }, "نص المصحف من قرآنبيديا، جُلب في ", el("b", { text: when }),
      data.source.stale ? " (نسخة مخبأة لتعذّر التحديث)" : ""));
  }
  renderSummary(data);
  renderArticle(data.findings);
  renderFindings();
  $("results").scrollIntoView({ behavior: "smooth", block: "start" });
}

function renderSummary(data) {
  const s = data.stats;
  const tile = (n, l, cls) => el("div", { class: `tile ${cls || ""}` }, el("div", { class: "n", text: toArabicDigits(n) }), el("div", { class: "l", text: l }));
  $("summary").replaceChildren(
    tile(s.total, "اقتباسات مرصودة", "accent"),
    tile(s.matched, "ألفاظ مطابقة"),
    tile(s.difference, "اختلافات في الألفاظ"),
    tile(s.uncertain, "غير محسومة"),
    tile(s.ref_incorrect, "إحالات خاطئة"),
    tile(s.ref_missing, "بلا إحالة"),
    tile(s.needs_review, "تحتاج مراجعة بشرية", "review"),
  );
}

function renderArticle(findings) {
  const view = $("article-view");
  view.replaceChildren();
  let pos = 0;
  for (const f of [...findings].sort((a, b) => a.start - b.start)) {
    if (f.start < pos) continue;
    view.append(lastArticle.slice(pos, f.start));
    const mark = el("mark", { class: `s-${f.wording.status}`, "data-id": f.id, title: `اقتباس ${f.id}`, tabindex: "0",
      onclick: () => focusFinding(f.id), onkeydown: (e) => { if (e.key === "Enter") focusFinding(f.id); } },
      lastArticle.slice(f.start, f.end), el("sup", { text: toArabicDigits(f.id) }));
    view.append(mark);
    pos = f.end;
  }
  view.append(lastArticle.slice(pos));
}

function focusFinding(id) {
  document.querySelectorAll(".finding.active, mark.active").forEach((n) => n.classList.remove("active"));
  const card = document.getElementById(`finding-${id}`);
  const mark = document.querySelector(`mark[data-id="${id}"]`);
  if (mark) mark.classList.add("active");
  if (card) { card.classList.add("active"); card.scrollIntoView({ behavior: "smooth", block: "center" }); }
}

function renderFindings() {
  const list = $("findings");
  const onlyReview = $("only-review").checked;
  const items = (lastResult?.findings || []).filter((f) => !onlyReview || f.needs_review);
  if (!items.length) {
    list.replaceChildren(el("li", { class: "empty", text: onlyReview ? "لا توجد حالات تحتاج مراجعة." : "لم تُرصد اقتباسات قرآنية في النص." }));
    return;
  }
  list.replaceChildren(...items.map(renderFinding));
}

function sourceBox(src) {
  const box = el("div", { class: "source-box" });
  const text = el("div", { class: "quran", dir: "rtl" });
  src.segments.forEach((seg, i) => {
    if (i) text.append(" ");
    seg.words.forEach((w, wi) => {
      if (wi) text.append(" ");
      text.append(el("span", { class: wi >= seg.from && wi < seg.to ? "w-hit" : "w-dim", text: w }));
    });
    text.append(" ", el("span", { class: "ayah-no", text: `﴿${toArabicDigits(seg.ayah)}﴾` }));
  });
  const meta = el("div", { class: "source-meta" },
    el("b", { text: `سورة ${src.surah_name} — ${src.ayah_start === src.ayah_end ? "الآية " + toArabicDigits(src.ayah_start) : "الآيات " + toArabicDigits(src.ayah_start) + "–" + toArabicDigits(src.ayah_end)}` }),
    el("span", { class: "muted", text: COVERAGE[src.coverage] || "" }),
    ...src.segments.flatMap((seg) => [
      el("a", { href: seg.page_url, target: "_blank", rel: "noopener", text: `عرض ${toArabicDigits(src.surah)}:${toArabicDigits(seg.ayah)} في قرآنبيديا` }),
      el("a", { href: seg.api_url, target: "_blank", rel: "noopener", text: "سجل API" }),
    ]),
  );
  box.append(text, meta);
  return box;
}

function diffView(ops) {
  const wrap = el("div", { class: "diff" });
  for (const d of ops) {
    if (d.op === "equal") wrap.append(el("span", { class: "eq", text: d.quote }));
    else if (d.op === "extra") wrap.append(el("span", { class: "extra", title: "زائد في المقال", text: d.quote }));
    else if (d.op === "missing") wrap.append(el("span", { class: "missing", title: "ناقص من المقال", text: "+ " + d.source }));
    else wrap.append(el("span", { class: "rep" }, el("span", { class: "extra", title: "في المقال", text: d.quote }), el("span", { class: "missing", title: "في المصحف", text: d.source })));
  }
  return wrap;
}

function pairsList(pairs) {
  return el("ul", { class: "pairs" }, pairs.map((p) => el("li", {}, el("span", { text: p.quote }), " ← ", el("b", { text: p.source }))));
}

function renderFinding(f) {
  const w = f.wording, r = f.reference;
  const [wl, wc] = wordingChip(w);
  const [rl, rc] = REF[r.status] || ["—", "muted-chip"];
  const head = el("div", { class: "f-head" },
    el("span", { class: "f-num", text: toArabicDigits(f.id) }),
    el("span", { class: "f-loc", text: `السطر ${toArabicDigits(f.line)}، الحرف ${toArabicDigits(f.column)}` }),
    chip(wl, wc), chip(rl, rc),
    f.needs_review ? chip("يحتاج مراجعة", "review") : null,
  );

  const body = el("div", { class: "f-body" });
  body.append(el("div", {}, el("div", { class: "row-label", text: "النص في المقال" }), el("div", { class: "quote-text", dir: "rtl", text: f.quote })));

  if (f.source) {
    body.append(el("div", {},
      el("div", { class: "row-label", text: w.level === "fuzzy" ? "أقرب موضع مقترح في المصحف (غير مؤكد)" : "النص في المصحف (حفص — قرآنبيديا)" }),
      sourceBox(f.source)));
  }

  // wording details
  const wBox = el("div", { class: "status-box" }, el("div", { class: "row-label", text: "الألفاظ" }), chip(wl, wc));
  if (w.message) wBox.append(el("p", { text: w.message }));
  if (w.level === "fuzzy" && w.similarity != null) wBox.append(el("p", { class: "muted", text: `نسبة التشابه: ${toArabicDigits(Math.round(w.similarity * 100))}٪` }));
  if (w.level === "diacritics" && w.status === "matched") wBox.append(el("p", { class: "muted", text: "الحروف مطابقة؛ التشكيل في المقال ناقص أو غائب لكنه غير مخالف." }));
  if (w.level === "literal") wBox.append(el("p", { class: "muted", text: "مطابق حرفًا وتشكيلًا (بعد تجاهل علامات الوقف)." }));

  const rBox = el("div", { class: "status-box" }, el("div", { class: "row-label", text: "الإحالة" }), chip(rl, rc));
  if (r.found) rBox.append(el("p", {}, "المذكور: ", el("b", { text: r.found.text })));
  if (r.message) rBox.append(el("p", { text: r.message }));
  body.append(el("div", { class: "statuses" }, wBox, rBox));

  const nonEqual = (w.diff || []).filter((d) => d.op !== "equal");
  if (nonEqual.length) {
    body.append(el("div", {}, el("div", { class: "row-label", text: "الفرق بالكلمات" }), diffView(w.diff),
      el("div", { class: "diff-legend", text: "المشطوب الأحمر: في المقال وليس في المصحف · الأخضر: في المصحف وليس في المقال" })));
  }
  if (w.diacritic_conflicts?.length) body.append(el("div", {}, el("div", { class: "row-label", text: "تشكيل مخالف (المقال ← المصحف)" }), pairsList(w.diacritic_conflicts)));
  if (w.script_diffs?.length) body.append(el("div", {}, el("div", { class: "row-label", text: "فروق الرسم (المقال ← المصحف)" }), pairsList(w.script_diffs)));

  if (f.review_reasons?.length && f.needs_review) {
    body.append(el("div", {}, el("div", { class: "row-label", text: "سبب طلب المراجعة" }), el("ul", { class: "reasons" }, f.review_reasons.map((x) => el("li", { text: x })))));
  }
  if (f.alternatives?.length) {
    body.append(el("details", { class: "alts" },
      el("summary", { text: `مواضع أخرى محتملة (${toArabicDigits(f.alternatives.length)}${f.occurrences > f.alternatives.length ? " من " + toArabicDigits(f.occurrences) : ""})` }),
      el("ul", {}, f.alternatives.map((a) => el("li", {},
        el("b", { text: a.label }), " — ",
        el("span", { class: "quran", text: a.source.matched_text }),
        a.similarity < 1 ? el("span", { class: "muted", text: ` (${toArabicDigits(Math.round(a.similarity * 100))}٪)` }) : null)))));
  }
  body.append(el("div", { class: "source-meta muted" }, "طريقة الرصد: ", ...f.detected_by.map((d) => chip(DETECTED[d] || d, "src"))));

  return el("li", { id: `finding-${f.id}`, class: `finding ${f.needs_review ? "review" : ""}` }, head, body);
}

// ---------------------------------------------------------------- init
document.addEventListener("DOMContentLoaded", () => {
  $("article").addEventListener("input", updateCount);
  $("audit-btn").addEventListener("click", runAudit);
  $("clear-btn").addEventListener("click", () => { $("article").value = ""; updateCount(); $("results").hidden = true; setStatus(""); });
  $("sample-select").addEventListener("change", (e) => loadSample(e.target.value));
  $("only-review").addEventListener("change", renderFindings);
  $("article").addEventListener("keydown", (e) => { if ((e.ctrlKey || e.metaKey) && e.key === "Enter") runAudit(); });
  updateCount();
  loadHealth();
});
