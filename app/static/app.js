// Quran quotation auditor — frontend.
// All user-supplied and server-supplied text is inserted with textContent
// (never innerHTML), so article text cannot inject markup.
// Revision state (the editor's approve/reject decisions) lives only in this
// browser tab (memory + sessionStorage); it is never sent to the server.
"use strict";

const $ = (id) => document.getElementById(id);
const R = window.Revision;
let MAX_CHARS = 6000;
let lastArticle = "";
let lastResult = null;
let decisions = {};  // changeId -> "approved" | "rejected"
let auditedAt = null;
const STORE_KEY = "qqa-session-v1";

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
const fmtTime = (secs) => new Date(secs * 1000).toLocaleString("ar", { dateStyle: "medium", timeStyle: "short" });

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
const DETECTED = { marked: "معلَّم بأقواس أو علامات", ai: "استخراج بالذكاء الاصطناعي", phrase: "بحث آلي عن عبارة مطابقة للمصحف", manual: "حدّدته بنفسك" };
const TIER_CLASS = { candidate: "cand", possible: "maybe", manual: "manual" };
const COVERAGE = { full: "آية كاملة", partial: "جزء من آية", "multi-partial": "أجزاء من آيات متتالية" };
const KIND = {
  wording: "تصحيح ألفاظ الاقتباس",
  diacritics: "تصحيح التشكيل",
  vocalize: "ضبط كامل بتشكيل المصحف (اختياري)",
  reference: "تصحيح الإحالة",
  reference_add: "إضافة إحالة (اختياري)",
};

function chip(label, cls) { return el("span", { class: `chip ${cls}`, text: label }); }

function allChanges() { return (lastResult?.findings || []).flatMap((f) => f.changes || []); }

// ---------------------------------------------------------------- session state
function saveSession() {
  try {
    sessionStorage.setItem(STORE_KEY, JSON.stringify({ article: lastArticle, result: lastResult, decisions, auditedAt }));
  } catch { /* storage unavailable: state stays in memory only */ }
}
function loadSession() {
  try {
    const s = JSON.parse(sessionStorage.getItem(STORE_KEY) || "null");
    if (s && s.result && typeof s.article === "string") return s;
  } catch { /* ignore */ }
  return null;
}
function clearSession() { try { sessionStorage.removeItem(STORE_KEY); } catch { /* ignore */ } }

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
      banner.append(el("strong", { text: "الاستخراج بالذكاء الاصطناعي مُعَدّ" }), " — ", el("bdi", { dir: "ltr", text: h.provider }), ". ");
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
        "تُفحص الاقتباسات المعلَّمة صراحةً (﴿ ﴾ أو { } أو علامات تنصيص مع «قال تعالى» أو إحالة)، ويُبحث في بقية النص عن عبارات (3 كلمات فأكثر) تطابق المصحف دون علامات؛ ",
        "وما كان شائعًا أو تقريبيًا يُعرض بعبارة «قد يكون اقتباسًا قرآنيًا — يحتاج مراجعة». قد تفوت بعض الاقتباسات القصيرة، ويمكنك تحديدها بنفسك.");
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
  const stale = lastResult && $("article").value.replace(/\r\n?/g, "\n") !== lastArticle;
  $("stale-note").hidden = !stale;
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
    decisions = {};
    auditedAt = Date.now() / 1000;
    saveSession();
    render(data, true);
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
function aiNotice(data) {
  const ai = data.ai || {};
  if (data.mode === "reduced") {
    return el("div", { class: "notice warning", text: "نُفِّذ هذا التدقيق في الوضع المخفّض دون ذكاء اصطناعي؛ قد تفوت الاقتباسات القصيرة غير المعلَّمة." });
  }
  if (data.mode === "ai" && ai.responded) {
    return el("div", { class: "notice info" }, "استجاب نموذج الذكاء الاصطناعي ", el("bdi", { dir: "ltr", text: ai.model || data.provider_model || data.provider }),
      ` في هذا التدقيق (${toArabicDigits(((ai.elapsed_ms || 0) / 1000).toFixed(1))} ث): اقترح ${toArabicDigits(ai.proposed)} مقطعًا، وُجد منها في المقال ${toArabicDigits(ai.located)}، واستُبعد ${toArabicDigits(ai.discarded)}. `,
      "ثم حُكم على كل اقتباس بمقارنته بنص المصحف فقط.");
  }
  return null;
}

function render(data, scroll) {
  $("results").hidden = false;
  const notices = $("notices");
  notices.replaceChildren(...(data.notices || []).map((n) => el("div", { class: `notice ${n.level}`, text: n.text })));
  const an = aiNotice(data);
  if (an) notices.append(an);
  if (data.source?.available && data.source.fetched_at) {
    notices.append(el("div", { class: "notice info" }, "نص المصحف من قرآنبيديا، جُلب في ", el("b", { text: fmtTime(data.source.fetched_at) }),
      data.source.stale ? " (نسخة مخبأة لتعذّر التحديث)" : ""));
  }
  renderSummary(data);
  renderArticle(data.findings);
  renderFindings();
  renderEditor();
  updateCount();
  if (scroll) $("results").scrollIntoView({ behavior: "smooth", block: "start" });
}

function renderSummary(data) {
  const s = data.stats;
  const tile = (n, l, cls) => el("div", { class: `tile ${cls || ""}` }, el("div", { class: "n", text: toArabicDigits(n) }), el("div", { class: "l", text: l }));
  $("summary").replaceChildren(
    tile(s.total, "اقتباسات مرصودة", "accent"),
    tile(s.matched, "ألفاظ مطابقة"),
    tile(s.possible || 0, "عبارات «قد تكون اقتباسًا»"),
    tile(s.difference, "اختلافات في الألفاظ"),
    tile(s.uncertain, "غير محسومة"),
    tile(s.ref_incorrect, "إحالات خاطئة"),
    tile(s.ref_missing, "بلا إحالة"),
    tile(s.needs_review, "تحتاج مراجعة بشرية", "review"),
    tile(allChanges().filter((c) => !c.optional).length, "تصحيحات مقترحة من المصدر", "fix"),
  );
}

function renderArticle(findings) {
  const view = $("article-view");
  view.replaceChildren();
  let pos = 0;
  for (const f of [...findings].sort((a, b) => a.start - b.start)) {
    if (f.start < pos) continue;
    view.append(R.slice(lastArticle, pos, f.start));
    const mark = el("mark", { class: `s-${f.detection?.unconfirmed ? "possible" : f.wording.status}`, "data-id": f.id, title: `اقتباس ${f.id}`, tabindex: "0",
      onclick: () => focusFinding(f.id), onkeydown: (e) => { if (e.key === "Enter") focusFinding(f.id); } },
      R.slice(lastArticle, f.start, f.end), el("sup", { text: toArabicDigits(f.id) }));
    view.append(mark);
    pos = f.end;
  }
  view.append(R.slice(lastArticle, pos));
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
  const items = (lastResult?.findings || []).filter((f) => !onlyReview || f.needs_review || (f.changes || []).some((c) => !c.optional));
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

function setDecision(id, value) {
  if (decisions[id] === value) delete decisions[id];
  else decisions[id] = value;
  saveSession();
  document.querySelectorAll(`[data-change="${CSS.escape(id)}"]`).forEach(updateChangeNode);
  renderEditor();
}

function updateChangeNode(node) {
  const id = node.getAttribute("data-change");
  const d = decisions[id];
  node.classList.toggle("approved", d === "approved");
  node.classList.toggle("rejected", d === "rejected");
  const state = node.querySelector(".ch-state");
  if (state) state.textContent = d === "approved" ? "معتمد" : d === "rejected" ? "مرفوض" : "بانتظار قرارك";
  node.querySelectorAll("button[data-act]").forEach((b) => b.setAttribute("aria-pressed", String(d === b.getAttribute("data-act"))));
}

function changeCard(c) {
  const quoteLevel = c.kind !== "reference" && c.kind !== "reference_add";
  const before = quoteLevel ? c.quote_before : c.original || "—";
  const after = quoteLevel ? c.quote_after : (c.original ? c.replacement : c.replacement.trim());
  const node = el("div", { class: `change ${c.optional ? "optional" : ""}`, "data-change": c.id },
    el("div", { class: "ch-head" },
      el("b", { text: KIND[c.kind] || c.kind }),
      el("span", { class: "ch-state", text: "بانتظار قرارك" })),
    el("div", { class: "ch-diff" },
      el("div", {}, el("span", { class: "row-label", text: "قبل" }), el("div", { class: "ch-before", dir: "rtl", text: before })),
      el("div", {}, el("span", { class: "row-label", text: "بعد" }), el("div", { class: `ch-after ${quoteLevel ? "quran" : ""}`, dir: "rtl", text: after }))),
    el("p", { class: "ch-reason", text: c.reason }),
    c.kind === "diacritics" ? el("p", { class: "muted small", text: "تنبيه: تختلف طبعات المصاحف في بعض علامات الضبط (كشدّة الإدغام)؛ تأكد قبل الاعتماد." }) : null,
    el("div", { class: "ch-src" }, "المصدر: ", el("b", { text: c.label }), " — ",
      ...c.source_urls.map((u, i) => el("a", { href: u, target: "_blank", rel: "noopener", text: i ? ` (${toArabicDigits(i + 1)})` : "قرآنبيديا" }))),
    el("div", { class: "ch-actions" },
      el("button", { type: "button", class: "btn small approve", "data-act": "approved", "aria-pressed": "false", onclick: () => setDecision(c.id, "approved") }, "اعتماد"),
      el("button", { type: "button", class: "btn small reject", "data-act": "rejected", "aria-pressed": "false", onclick: () => setDecision(c.id, "rejected") }, "رفض")),
  );
  updateChangeNode(node);
  return node;
}

function renderFinding(f) {
  const w = f.wording, r = f.reference;
  const det = f.detection || {};
  const weak = !!det.unconfirmed;  // found only as a possible quotation: the match to the text is shown, but not as a verdict
  let [wl, wc] = wordingChip(w);
  if (weak) { wl = "إن كان اقتباسًا: " + wl; wc = "muted-chip"; }
  const [rl, rc] = REF[r.status] || ["—", "muted-chip"];
  const tierChip = det.label ? chip(det.label, TIER_CLASS[det.tier] || "src") : null;
  const head = el("div", { class: "f-head" },
    el("span", { class: "f-num", text: toArabicDigits(f.id) }),
    el("span", { class: "f-loc", text: `السطر ${toArabicDigits(f.line)}، الحرف ${toArabicDigits(f.column)}` }),
    tierChip, chip(wl, wc), chip(rl, rc),
    f.needs_review && !weak ? chip("يحتاج مراجعة", "review") : null,
  );

  const body = el("div", { class: "f-body" });
  body.append(el("div", {}, el("div", { class: "row-label", text: "النص في المقال" }), el("div", { class: "quote-text", dir: "rtl", text: f.quote })));

  if (f.source) {
    body.append(el("div", {},
      el("div", { class: "row-label", text: w.level === "fuzzy" ? "أقرب موضع مقترح في المصحف (غير مؤكد)" : "النص في المصحف (حفص — قرآنبيديا)" }),
      sourceBox(f.source)));
  }

  if (det.reasons?.length && det.kind === "phrase") {
    body.append(el("div", { class: `detect-note ${det.tier}` }, el("b", { text: det.label + ": " }), det.reasons.join(" ")));
  }

  const wBox = el("div", { class: "status-box" }, el("div", { class: "row-label", text: weak ? "مطابقة النص للمصحف (إن كان اقتباسًا)" : "الألفاظ" }), chip(wl, wc));
  if (w.message) wBox.append(el("p", { text: w.message }));
  if (w.level === "fuzzy" && w.similarity != null) wBox.append(el("p", { class: "muted", text: `نسبة التشابه: ${toArabicDigits(Math.round(w.similarity * 100))}٪` }));
  if (w.level === "diacritics" && w.status === "matched") wBox.append(el("p", { class: "muted", text: "الحروف مطابقة؛ التشكيل في المقال ناقص أو غائب لكنه غير مخالف، فليس خطأً." }));
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

  // proposed corrections (source-backed only)
  const changes = f.changes || [];
  if (changes.length) {
    body.append(el("div", { class: "changes" }, el("div", { class: "row-label", text: "تصحيحات مقترحة من نص المصحف — لا يُغيَّر شيء إلا بعد اعتمادك" }), ...changes.map(changeCard)));
  }
  if (f.continuation) {
    body.append(el("p", { class: "muted small continuation" }, "بعد هذا المقطع في المصحف: ", el("b", { class: "quran", text: f.continuation.quran }),
      "، وبعده في المقال: ", el("b", { text: f.continuation.article }),
      ". لا تستطيع الأداة معرفة أين ينتهي الاقتباس عندك؛ إن كانت هذه الكلمة منه فراجعها."));
  }
  const confirm = choicesBox(f);
  if (confirm) body.append(confirm);
  if (f.correction?.status === "unconfirmed") {
    body.append(el("div", { class: "no-fix" }, el("b", { text: "لا تصحيحات مقترحة بعد. " }), f.correction.reason));
  } else if (f.correction?.status === "review_only" && f.needs_review) {
    body.append(el("div", { class: "no-fix" }, el("b", { text: "لا يُقترح تصحيح تلقائي. " }), f.correction.reason || "الموضع المقصود غير محسوم."));
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

  return el("li", { id: `finding-${f.id}`, class: `finding ${f.needs_review ? "review" : ""} ${weak ? "weak" : ""}` }, head, body);
}

// ---------------------------------------------------------------- confirming a possible quotation / choosing a verse / manual selection
function choicesBox(f) {
  const choices = f.choices || [];
  const det = f.detection || {};
  if (!choices.length || !(det.unconfirmed || f.needs_choice || (!f.source && ["manual", "phrase"].includes(det.kind)))) return null;
  const single = choices.length === 1;
  const box = el("div", { class: "confirm-box" },
    el("div", { class: "row-label", text: single ? "هل هذا اقتباس قرآني؟" : "اختر الموضع المقصود من المصحف" }),
    el("p", { class: "muted small", text: det.unconfirmed
      ? "لا تُقترح تصحيحات قبل أن تؤكد أن المقطع اقتباس قرآني وتحدد موضعه. اختيارك لا يغيّر المقال؛ يُنشئ اقتراحات تعتمدها أو ترفضها واحدًا واحدًا."
      : "العبارة تتطابق مع أكثر من موضع، فلا يُختار أحدها تلقائيًا." }));
  for (const ch of choices) {
    box.append(el("div", { class: "choice" },
      el("b", { text: ch.label }), " — ", el("span", { class: "quran", dir: "rtl", text: ch.text }),
      el("button", { type: "button", class: "btn small", onclick: () => requestPhrase(f.start, f.end, ch, f.id) },
        single ? "أؤكد أنه اقتباس قرآني في هذا الموضع" : "هذا هو الموضع")));
  }
  return box;
}

function computeStats(findings) {
  const weak = (f) => !!f.detection?.unconfirmed;
  const n = (fn) => findings.filter(fn).length;
  return {
    total: findings.length,
    matched: n((f) => f.wording.status === "matched" && !weak(f)),
    difference: n((f) => f.wording.status === "difference"),
    uncertain: n((f) => f.wording.status === "uncertain"),
    needs_review: n((f) => f.needs_review),
    possible: n(weak),
    candidates: n((f) => f.detection?.tier === "candidate"),
    ref_matched: n((f) => f.reference.status === "matched"),
    ref_missing: n((f) => f.reference.status === "missing"),
    ref_incorrect: n((f) => f.reference.status === "incorrect"),
    ref_uncertain: n((f) => f.reference.status === "uncertain"),
    proposed_changes: findings.reduce((a, f) => a + (f.changes || []).length, 0),
  };
}

// Offsets from the server are Unicode code points; a textarea reports UTF-16 units.
function selectedSpan() {
  const ta = $("article");
  const a = ta.selectionStart, b = ta.selectionEnd;
  if (a === b) return null;
  const text = ta.value.replace(/\r\n?/g, "\n");
  return { start: Array.from(text.slice(0, a)).length, end: Array.from(text.slice(0, b)).length };
}

function updateSelectionButton() {
  const btn = $("phrase-btn");
  const stale = !lastResult || $("article").value.replace(/\r\n?/g, "\n") !== lastArticle;
  btn.disabled = !selectedSpan() || stale;
  btn.title = !lastResult ? "دقّق المقال أولًا ثم حدّد المقطع" : stale ? "تغيّر النص بعد آخر تدقيق؛ أعد التدقيق أولًا" : "";
}

async function checkSelection() {
  const sel = selectedSpan();
  if (!sel || !lastResult) return;
  const hit = (lastResult.findings || []).filter((f) => f.start < sel.end && sel.start < f.end);
  const fixed = hit.find((f) => !["phrase", "manual"].includes(f.detection?.kind));
  if (fixed) { setStatus(`هذا الموضع مشمول بالفعل بالنتيجة رقم ${toArabicDigits(fixed.id)} (رُصد بالعلامات أو بالذكاء الاصطناعي).`, true); focusFinding(fixed.id); return; }
  const id = hit.length ? hit[0].id : Math.max(0, ...(lastResult.findings || []).map((f) => f.id)) + 1;
  await requestPhrase(sel.start, sel.end, null, id);
}

async function requestPhrase(start, end, choice, findingId) {
  if (!lastResult) return;
  setStatus("جارٍ فحص المقطع ومقارنته بنص المصحف…", false, true);
  try {
    const body = { article: lastArticle, start, end, finding_id: findingId };
    if (choice) Object.assign(body, { surah: choice.surah, ayah_start: choice.ayah_start, ayah_end: choice.ayah_end });
    const res = await fetch("/api/phrase", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    let data;
    try { data = await res.json(); } catch { data = { error: "استجابة غير متوقعة من الخادم." }; }
    if (!res.ok) { setStatus(data.error || "تعذّر فحص المقطع.", true); return; }
    applyPhrase(data.finding);
    setStatus(choice ? "حُدِّد الموضع وحُدِّثت الاقتراحات؛ راجعها قبل الاعتماد." : "فُحص المقطع المحدَّد؛ راجع النتيجة.");
  } catch {
    setStatus("تعذّر الاتصال بالخادم.", true);
  }
}

function applyPhrase(nf) {
  const overlapped = (lastResult.findings || []).filter((g) => g.start < nf.end && nf.start < g.end);
  for (const old of overlapped) for (const c of old.changes || []) delete decisions[c.id];
  lastResult.findings = [...lastResult.findings.filter((g) => !overlapped.includes(g)), nf].sort((a, b) => a.start - b.start);
  lastResult.stats = computeStats(lastResult.findings);
  saveSession();
  render(lastResult, false);
  focusFinding(nf.id);
}

// ---------------------------------------------------------------- editor: before/after + copy
function unresolvedSpans() {
  return R.unresolvedFindings(lastResult?.findings || [], decisions).map((f) => ({ start: f.start, end: f.end, id: f.id }));
}

function renderEditor() {
  if (!lastResult) return;
  const changes = allChanges();
  const nApproved = changes.filter((c) => decisions[c.id] === "approved").length;
  const nRejected = changes.filter((c) => decisions[c.id] === "rejected").length;
  const nPending = changes.length - nApproved - nRejected;
  const unresolved = R.unresolvedFindings(lastResult.findings, decisions);
  const { text, refused } = R.applyApproved(lastArticle, changes, decisions);

  $("editor-progress").replaceChildren(
    el("span", { class: "pill ok", text: `معتمد ${toArabicDigits(nApproved)}` }),
    el("span", { class: "pill bad", text: `مرفوض ${toArabicDigits(nRejected)}` }),
    el("span", { class: "pill", text: `بانتظار قرارك ${toArabicDigits(nPending)}` }),
    el("span", { class: "pill warn", text: `اقتباسات غير محسومة ${toArabicDigits(unresolved.length)}` }),
  );
  if (refused.length) {
    $("editor-progress").append(el("span", { class: "pill bad", text: `تعذّر تطبيق ${toArabicDigits(refused.length)} (تداخل أو إزاحة)` }));
  }

  const view = $("preview-view");
  view.replaceChildren();
  for (const s of R.previewSegments(lastArticle, changes, decisions, unresolvedSpans())) {
    if (s.type === "text") view.append(s.text);
    else if (s.type === "del") view.append(el("del", { title: "قبل", text: s.text }));
    else if (s.type === "ins") view.append(el("ins", { title: "بعد (معتمد)", text: s.text }));
    else view.append(el("span", { class: "unresolved", title: "اقتباس غير محسوم — يحتاج مراجعة بشرية", text: s.text }), el("sup", { class: "unres-mark", text: "⚠" + toArabicDigits(s.id) }));
  }
  $("revised-text").value = text;
  $("reply-text").value = R.replyDraft(lastResult.findings, changes, decisions);
  updateReplyCount();
}

function updateReplyCount() {
  const n = Array.from($("reply-text").value).length;
  $("reply-count").textContent = `${toArabicDigits(n)} حرفًا`;
}

async function copyRevised() {
  const text = $("revised-text").value;
  try {
    await navigator.clipboard.writeText(text);
    setStatus("نُسخ المقال المعدّل. تذكير: الأداة فحصت الاقتباسات القرآنية فقط، والحالات غير المحسومة تحتاج مراجعة.");
  } catch {
    $("revised-text").select();
    setStatus("تعذّر النسخ التلقائي؛ النص محدد الآن، انسخه يدويًا (Ctrl+C).", true);
  }
}

function showTab(which) {
  const preview = which === "preview";
  $("tab-preview").setAttribute("aria-selected", String(preview));
  $("tab-text").setAttribute("aria-selected", String(!preview));
  $("preview-view").hidden = !preview;
  $("revised-text").hidden = preview;
}

// ---------------------------------------------------------------- print record
function aiRecordText(data) {
  const ai = data.ai || {};
  if (!ai.configured) return "لم يُستخدم الذكاء الاصطناعي (وضع مخفّض): فُحصت الاقتباسات المعلَّمة والعبارات المطابقة لنص المصحف دون علامات، وقد تفوت الاقتباسات القصيرة غير المعلَّمة.";
  if (ai.responded) return `نعم — استجاب النموذج ${ai.model} (${ai.provider}) في هذا التدقيق خلال ${((ai.elapsed_ms || 0) / 1000).toFixed(1)} ث؛ اقترح ${ai.proposed} مقطعًا، وُجد منها في المقال ${ai.located}، واستُبعد ${ai.discarded}. دوره اقتراح المواضع فقط.`;
  return `لا — كان ${ai.provider} مُعَدًّا لكنه لم يستجب في هذا التدقيق (${ai.error || ai.outcome})، فاستُخدم الوضع الاحتياطي الحتمي، وقد تفوت الاقتباسات القصيرة غير المعلَّمة.`;
}

function buildRecord() {
  const data = lastResult;
  const rec = $("print-record");
  const changes = allChanges();
  const byFinding = Object.fromEntries(data.findings.map((f) => [f.id, f]));
  const approved = changes.filter((c) => decisions[c.id] === "approved");
  const rejected = changes.filter((c) => decisions[c.id] === "rejected");
  const pending = changes.filter((c) => !decisions[c.id]);
  const notApplied = changes.filter((c) => decisions[c.id] === "rejected" || (!decisions[c.id] && !c.optional));
  const optionalPending = changes.filter((c) => !decisions[c.id] && c.optional).length;
  const unresolved = R.unresolvedFindings(data.findings, decisions);
  const kv = (k, v) => el("tr", {}, el("th", { text: k }), el("td", {}, v));

  rec.replaceChildren(
    el("h1", { text: "سجل مراجعة الاقتباسات" }),
    el("p", { class: "rec-disclaimer" },
      el("b", { text: "أداة مساعدة تحريرية، وليست شهادة بصحة النص الديني أو سلامته. " }),
      "يقتصر الفحص على الاقتباسات القرآنية التي رُصدت وإحالاتها، بمقارنتها بنص مصحف حفص من قرآنبيديا. لا يشهد هذا السجل بأن المقال كله متحقق منه أو جاهز للنشر، ولا يغني عن مراجعة المختص."),
    el("table", { class: "rec-meta" },
      kv("وقت التدقيق", auditedAt ? fmtTime(auditedAt) : "—"),
      kv("وقت إعداد السجل", fmtTime(Date.now() / 1000)),
      kv("مصدر النص القرآني", `${data.source.name} — ${data.source.url}`),
      kv("وقت جلب المصدر", data.source.fetched_at ? fmtTime(data.source.fetched_at) + (data.source.stale ? " (نسخة مخبأة)" : "") : "المصدر غير متاح — لم يُحكم على أي اقتباس"),
      kv("هل عمل الاستخراج بالذكاء الاصطناعي؟", aiRecordText(data)),
      kv("الأعداد", `اقتباسات مرصودة ${data.stats.total} · تصحيحات معتمدة ${approved.length} · مرفوضة ${rejected.length} · بلا قرار ${pending.length} · غير محسومة ${unresolved.length}`),
    ),
    el("h2", { text: "التصحيحات المعتمدة" }),
    approved.length ? el("table", { class: "rec-table" },
      el("thead", {}, el("tr", {}, ...["#", "النوع", "النص الأصلي", "البديل المعتمد", "السبب", "السورة/الآية", "رابط المصدر"].map((h) => el("th", { text: h })))),
      el("tbody", {}, approved.map((c) => el("tr", {},
        el("td", { text: String(c.finding_id) }),
        el("td", { text: KIND[c.kind] || c.kind }),
        el("td", { class: "q", text: c.original || "(إضافة)" }),
        el("td", { class: "q", text: c.replacement.trim() }),
        el("td", { text: c.reason }),
        el("td", { text: c.label }),
        el("td", { class: "url", text: c.source_urls.join("\n") }))))) : el("p", { text: "لم يُعتمد أي تصحيح." }),
    el("h2", { text: "تصحيحات مقترحة رُفضت أو لم يُبتّ فيها" }),
    notApplied.length ? el("ul", {}, notApplied.map((c) =>
      el("li", {}, `#${c.finding_id} ${KIND[c.kind] || c.kind}: «${c.original || "(إضافة)"}» ← «${c.replacement.trim()}» — `, el("b", { text: decisions[c.id] === "rejected" ? "رُفض" : "بلا قرار" }), ` (${c.label})`))) : el("p", { text: "لا يوجد." }),
    optionalPending ? el("p", { class: "muted", text: `إضافةً إلى ${optionalPending} اقتراحًا اختياريًا للتنسيق (ضبط بالتشكيل أو إضافة إحالة) لم يُبتّ فيه؛ لا يدل على خطأ.` }) : null,
    el("h2", { text: "اقتباسات غير محسومة (تحتاج مراجعة بشرية)" }),
    unresolved.length ? el("ul", {}, unresolved.map((f) => el("li", {},
      `#${f.id} (السطر ${f.line}) «${f.quote}» — `,
      (f.review_reasons || []).join("؛ ") || (f.correction?.reason || "تصحيح مقترح لم يُعتمد"),
      f.source ? (f.wording.level === "fuzzy" ? ` — أقرب موضع مقترح (غير مؤكد): ${f.source.label}` : ` — الموضع في المصدر: ${f.source.label}`) : ""))) : el("p", { text: "لا يوجد في الاقتباسات المرصودة. (قد توجد اقتباسات لم تُرصد.)" }),
    el("p", { class: "rec-foot", text: "أُعدّ بواسطة مدقق الاقتباسات القرآنية. نص المقال لا يُخزَّن على الخادم؛ هذا السجل مولَّد في المتصفح." }),
  );
}

function printRecord() {
  if (!lastResult) return;
  buildRecord();
  window.print();
}

// ---------------------------------------------------------------- init
document.addEventListener("DOMContentLoaded", () => {
  $("article").addEventListener("input", updateCount);
  $("audit-btn").addEventListener("click", runAudit);
  $("clear-btn").addEventListener("click", () => {
    $("article").value = ""; lastResult = null; lastArticle = ""; decisions = {}; clearSession();
    updateCount(); $("results").hidden = true; setStatus("");
  });
  $("sample-select").addEventListener("change", (e) => loadSample(e.target.value));
  $("only-review").addEventListener("change", renderFindings);
  $("phrase-btn").addEventListener("click", checkSelection);
  for (const ev of ["select", "keyup", "mouseup", "input", "focus"]) $("article").addEventListener(ev, updateSelectionButton);
  $("article").addEventListener("keydown", (e) => { if ((e.ctrlKey || e.metaKey) && e.key === "Enter") runAudit(); });
  $("copy-btn").addEventListener("click", copyRevised);
  $("reply-text").addEventListener("input", updateReplyCount);
  $("reply-copy").addEventListener("click", async () => {
    try { await navigator.clipboard.writeText($("reply-text").value); setStatus("نُسخت المسودة. راجعها قبل نشرها بنفسك."); }
    catch { $("reply-text").select(); setStatus("تعذّر النسخ التلقائي؛ النص محدد، انسخه يدويًا.", true); }
  });
  $("print-btn").addEventListener("click", printRecord);
  $("reset-btn").addEventListener("click", () => {
    decisions = {}; saveSession();
    document.querySelectorAll("[data-change]").forEach(updateChangeNode);
    renderEditor();
  });
  $("tab-preview").addEventListener("click", () => showTab("preview"));
  $("tab-text").addEventListener("click", () => showTab("text"));
  window.addEventListener("beforeprint", () => { if (lastResult) buildRecord(); });

  const saved = loadSession();
  if (saved) {
    lastArticle = saved.article; lastResult = saved.result; decisions = saved.decisions || {}; auditedAt = saved.auditedAt || null;
    $("article").value = lastArticle;
    render(lastResult, false);
    setStatus("استُعيدت نتيجة التدقيق وقراراتك من هذه الجلسة.");
  }
  updateCount();
  updateSelectionButton();
  loadHealth();
});
