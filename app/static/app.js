// Quran quotation auditor — frontend.
// All user-supplied and server-supplied text is inserted with textContent
// (never innerHTML), so article text cannot inject markup.
// Revision state (the editor's decisions) lives only in this browser tab
// (memory + sessionStorage); it is never sent to the server.
"use strict";

const $ = (id) => document.getElementById(id);
const R = window.Revision;
let MAX_CHARS = 6000;
let lastArticle = "";
let ART = [];            // the audited article as an array of code points (the server's offsets are code points)
let lastResult = null;
let decisions = {};      // changeId -> "approved" | "rejected"
let dismissed = {};      // findingId -> true: the writer said «ليس اقتباسًا» (reversible)
let reviewed = {};       // findingId -> true: the writer checked a review-only item by hand
let current = null;      // the finding shown in the decision panel
let auditedAt = null;
let demoText = null;     // the text of the demonstration article once it has been loaded in this tab
let isDemo = false;      // the audited article is the demonstration article (it holds two deliberate misquotations)
let lastAction = null;   // { text, undo } shown above the card: what the last click did, and how to take it back
let cardError = null;    // an error that belongs to the card (a verse check that failed), shown beside its buttons
let pendingSel = null;   // { start, end } the writer highlighted in the article view
let inputCollapsed = false;
const STORE_KEY = "qqa-session-v2";

function el(tag, attrs, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") node.className = v;
    else if (k === "text") node.textContent = v;
    else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
    else node.setAttribute(k, v === true ? "" : v);
  }
  for (const c of children.flat(Infinity)) {
    if (c === null || c === undefined || c === false) continue;
    node.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return node;
}

const toArabicDigits = (n) => String(n).replace(/\d/g, (d) => "٠١٢٣٤٥٦٧٨٩"[d]);
const fmtTime = (secs) => new Date(secs * 1000).toLocaleString("ar", { dateStyle: "medium", timeStyle: "short" });
const motion = () => (window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth");
const narrow = () => !!(window.matchMedia && matchMedia("(max-width: 900px)").matches);

// Latin runs, URLs and e-mail addresses inside Arabic text are isolated (<bdi dir="ltr">) so that the sentence punctuation
// around them keeps its place (W3C: "Inline markup and bidirectional text in HTML"). The characters themselves are unchanged.
const LTR_RUN = /(?:https?:\/\/|www\.)[^\s<>]+|[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}|[A-Za-z][A-Za-z0-9'’._:/\-]*(?: [A-Za-z0-9][A-Za-z0-9'’._:/\-]*)*/g;
function bidi(text) {
  const out = [];
  let last = 0;
  for (const m of String(text).matchAll(LTR_RUN)) {
    let run = m[0];
    run = run.replace(/[.,;:!?)\]»”'’]+$/, "");  // closing punctuation belongs to the Arabic sentence
    if (!run) continue;
    if (m.index > last) out.push(text.slice(last, m.index));
    out.push(el("bdi", { dir: "ltr", class: "ltr", text: run }));
    last = m.index + run.length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

const WORDING = {
  matched: { literal: "مطابق حرفيًا", diacritics: "مطابق بتجاهل التشكيل", normalized: "مطابق بعد توحيد الرسم", uthmani: "مطابق — رسم عثماني" },
  difference: { diacritics: "اختلاف في التشكيل", normalized: "اختلاف في رسم الحروف", uthmani: "اختلاف في التشكيل (رسم عثماني)", fuzzy: "اختلاف — أقرب موضع مقترح" },
};
// What a recognised Uthmani spelling was matched through (codes from app/uthmani.py).
const SCRIPT_FEATURE = {
  wasla: "ألف الوصل ٱ", small_marks: "علامات الضبط والوقف الصغيرة", dagger_alef: "الألف الخنجرية", waw_alef: "واو بدل الألف (ٱلصَّلَوٰة)",
  hamza_alef: "همزة قبل الألف (ءَامَنُوا)", hamza_seat: "كرسي الهمزة", madd_sign: "علامة المد (لَآ)", idgham_shadda: "شدّة الإدغام",
  small_letters: "حروف صغيرة", vocative: "يا النداء متصلة", lam: "لام واحدة بدل لامين", silent_alef: "ألف لا تُكتب إملائيًا",
  word_spelling: "رسم خاص بالكلمة", lexicon: "رسم خاص بالكلمة", tatweel: "تطويل",
};
const wordingLabel = (w) => (w.status === "uncertain" ? "غير محسوم" : (WORDING[w.status] || {})[w.level] || (w.status === "matched" ? "مطابق" : "اختلاف"));
const REF_LABEL = { matched: "مطابقة", missing: "غير مكتوبة", incorrect: "خاطئة", uncertain: "غير محسومة" };
const DETECTED = { marked: "معلَّم بأقواس أو علامات", phrase: "بحث آلي عن عبارة مطابقة للمصحف", manual: "حدّدته بنفسك" };
// The model only proposes places. "Only" is reserved for a finding that would be absent without it; when a marker or the
// phrase search found the span too, the model merely proposed the same one (it added nothing for this finding).
const AI_ROLE = { only: "اقترحه الذكاء الاصطناعي وحده (لم يجده البحث الآلي)", also: "اقترح الذكاء الاصطناعي المقطع نفسه أيضًا" };
const detectedLabel = (f, d) => (d === "ai" ? (AI_ROLE[f.detection?.ai_role] || "اقترح الذكاء الاصطناعي هذا المقطع") : (DETECTED[d] || d));
// "مقطعًا" after a number: the counted noun is plural for 3–10 («٣ مقاطع»), singular accusative from 11 («١١ مقطعًا»)
const maqatiAr = (n) => (n === 1 ? "مقطعًا واحدًا" : n === 2 ? "مقطعين" : `${toArabicDigits(n)} ${n <= 10 ? "مقاطع" : "مقطعًا"}`);
const aiShare = (ai) => (ai.added_only === undefined || !ai.proposed ? "" : ` ومن النتائج ${ai.added_only} لم يجدها غير النموذج، و${ai.also_found} اقترح فيها المقطع نفسه الذي وجدته وسيلة أخرى${ai.overlapped ? `، و${ai.overlapped} اقترح فيها مقطعًا مختلفًا يتداخل معها فبقي الحكم لما وجده البرنامج` : ""}.`);
// A model span that overlaps a finding the program made: shown beside it, never in its place.
const AI_RELATION = { wider: "أوسع منه", narrower: "أضيق منه", shifted: "يتداخل معه جزئيًا" };
function aiSpanNote(f) {
  const spans = f.detection?.ai_spans;
  if (!spans?.length) return null;
  return el("p", { class: "muted small" }, "اقترح الذكاء الاصطناعي مقطعًا مختلفًا يتداخل مع هذا الموضع (لم يغيّر هذا الحكم المبني على نص المصحف): ",
    ...spans.map((x) => el("span", {}, el("span", { class: "quran", text: x.quote }), ` (${AI_RELATION[x.relation] || "مختلف"}) `)));
}
const COVERAGE = { full: "آية كاملة", partial: "جزء من آية", "multi-partial": "أجزاء من آيات متتالية" };
const KIND = {
  wording: "تصحيح ألفاظ الاقتباس",
  diacritics: "تصحيح التشكيل",
  vocalize: "كتابة الاقتباس بالتشكيل الكامل",
  script: "كتابة الاقتباس بالرسم الإملائي لقرآنبيديا",
  reference: "تصحيح الإحالة",
  reference_add: "إضافة الإحالة بجوار الاقتباس",
};
const DECISION_TITLE = { wording: "هل تصحّح الكلمة؟", diacritics: "هل تصحّح التشكيل؟", reference: "هل تصحّح الإحالة؟" };

const setArticleText = (t) => { lastArticle = t; ART = Array.from(t); parasCache = null; };
const cpSlice = (a, b) => ART.slice(a, b).join("");
const findingById = (id) => (lastResult?.findings || []).find((f) => String(f.id) === String(id));
const allFindings = () => lastResult?.findings || [];
const activeFindings = () => allFindings().filter((f) => !dismissed[f.id]);
const requiredOf = (f) => (f.changes || []).filter((c) => !c.optional);
const allChanges = () => activeFindings().flatMap((f) => f.changes || []);

// ---------------------------------------------------------------- where in the article
let parasCache = null;
function paraStarts() {
  if (parasCache) return parasCache;
  const starts = [0];
  for (let i = 0; i < ART.length; i++) {
    if (ART[i] !== "\n") continue;
    let j = i + 1;
    while (j < ART.length && (ART[j] === " " || ART[j] === "\t")) j++;
    if (ART[j] === "\n") {
      while (j < ART.length && /\s/.test(ART[j])) j++;
      if (j < ART.length) starts.push(j);
      i = j - 1;
    }
  }
  return (parasCache = starts);
}
const paraNo = (pos) => paraStarts().filter((s) => s <= pos).length;  // 1-based
function paraBounds(pos) {
  const ps = paraStarts();
  const n = paraNo(pos);
  const start = ps[n - 1];
  let end = n < ps.length ? ps[n] : ART.length;
  while (end > start && /\s/.test(ART[end - 1])) end--;
  return [start, end];
}
// «الفقرة ٣ من ٨» in a long article, «السطر ٢» in a short one.
function whereText(f) {
  const total = paraStarts().length;
  return total > 1 ? `الفقرة ${toArabicDigits(paraNo(f.start))} من ${toArabicDigits(total)}` : `السطر ${toArabicDigits(f.line)}`;
}
const isSpace = (ch) => ch === undefined || /\s/.test(ch);
// The quoted words with a few words of the same paragraph on each side.
function contextParts(f, limit = 80) {
  const [ps, pe] = paraBounds(f.start);
  let b0 = Math.max(ps, f.start - limit);
  let before = cpSlice(b0, f.start);
  const cutB = b0 > ps;
  if (cutB && !isSpace(ART[b0 - 1])) before = before.replace(/^\S*\s?/, "");
  let a1 = Math.min(pe, f.end + limit);
  let after = cpSlice(f.end, a1);
  const cutA = a1 < pe;
  if (cutA && !isSpace(ART[a1])) after = after.replace(/\s?\S*$/, "");
  let quote = cpSlice(f.start, f.end);
  const q = Array.from(quote);
  if (q.length > 240) quote = q.slice(0, 120).join("") + " … " + q.slice(-80).join("");
  return { before, quote, after, cutB, cutA };
}
// «… قبل [الاقتباس] بعد …» with the quoted words marked.
function contextView(f, cls = "") {
  const c = contextParts(f);
  return el("p", { class: `ctx ${cls}`, dir: "rtl" },
    c.cutB ? "… " : null, bidi(c.before),
    el("mark", { class: "q-hit" }, bidi(c.quote)),
    bidi(c.after), c.cutA ? " …" : null);
}
const excerpt = (q) => { const w = q.trim().split(/\s+/); return w.length > 7 ? w.slice(0, 7).join(" ") + " …" : q; };

// ---------------------------------------------------------------- what the writer still has to do
// The first open question of a finding: which verse (an unmarked passage), where it begins and ends, a correction, a manual check.
function pendingKind(f) {
  if (dismissed[f.id]) return null;
  const det = f.detection || {};
  if (det.unconfirmed || f.needs_choice) return "verse";
  if (f.lead_in || f.continuation) return "bounds";
  if (requiredOf(f).some((c) => !decisions[c.id])) return "fix";
  if (f.needs_review && !requiredOf(f).length && !reviewed[f.id]) return "review";
  return null;
}
const pendingList = () => activeFindings().filter((f) => pendingKind(f));
const PENDING_TEXT = { verse: "يحتاج تأكيدك", bounds: "حدود الاقتباس غير محسومة", fix: "تصحيح مقترح بانتظار قرارك", review: "يحتاج مراجعتك" };
// [text, class] — one plain state per quotation, never a stack of badges.
function stateOf(f) {
  if (dismissed[f.id]) return ["استبعدتَه: ليس اقتباسًا", "off"];
  const p = pendingKind(f);
  if (p) return [PENDING_TEXT[p], "need"];
  const req = requiredOf(f);
  if (req.length) return req.some((c) => decisions[c.id] === "approved") ? ["اعتمدتَ التصحيح", "done"] : ["أبقيتَه كما كتبتَ", "done"];
  if (f.needs_review) return ["راجعتَه بنفسك", "done"];
  return ["مطابق للمصحف", "done"];
}
// «اقتباس واحد ينتظر قرارك»، «اقتباسان ينتظران قرارك»، «٣ اقتباسات تنتظر قرارك»، «١١ اقتباسًا ينتظر قرارك»
function pendingText(n) {
  if (n === 0) return "حسمتَ كل ما يحتاج قرارك";
  if (n === 1) return "اقتباس واحد ينتظر قرارك";
  if (n === 2) return "اقتباسان ينتظران قرارك";
  return n <= 10 ? `${toArabicDigits(n)} اقتباسات تنتظر قرارك` : `${toArabicDigits(n)} اقتباسًا ينتظر قرارك`;
}

// ---------------------------------------------------------------- session state
function saveSession() {
  try {
    sessionStorage.setItem(STORE_KEY, JSON.stringify({ article: lastArticle, result: lastResult, decisions, dismissed, reviewed, current, auditedAt, isDemo }));
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
      banner.className = "banner";
      banner.append(el("strong", { text: "الذكاء الاصطناعي مُعَدّ" }), " — ", el("bdi", { dir: "ltr", text: h.provider }), ". ");
      if (last.outcome === "ok") banner.append("آخر استدعاء له على هذا الخادم نجح. ");
      else if (last.outcome === "failed") banner.append(el("b", { text: "آخر استدعاء له على هذا الخادم فشل" }), last.cooldown_seconds > 0 ? ` ويُتخطّى مؤقتًا (${toArabicDigits(last.cooldown_seconds)} ث). ` : ". ");
      else banner.append("لم يُستدعَ بعدُ على هذا الخادم. ");
      banner.append("نتيجة كل تدقيق تبيّن هل استجاب النموذج فعلًا. دوره اقتراح مواضع الاقتباس فقط، ويُتحقق من كل مقترح بنص المقال ثم بنص المصحف.");
    } else {
      banner.className = "banner reduced";
      banner.append(el("strong", { text: "الذكاء الاصطناعي غير مفعّل (وضع مخفّض)." }), " تُفحص الاقتباسات المعلَّمة والعبارات التي تطابق المصحف دون علامات؛ وقد تفوت بعض الاقتباسات القصيرة، ويمكنك تحديدها بنفسك.");
    }
  } catch {
    banner.hidden = true;
  }
}

// ---------------------------------------------------------------- input
function updateCount() {
  const value = $("article").value;
  const n = value.length;
  const c = $("char-count");
  c.textContent = `${toArabicDigits(n)} / ${toArabicDigits(MAX_CHARS)} حرف`;
  c.classList.toggle("char-over", n > MAX_CHARS);
  const stale = !!lastResult && value.replace(/\r\n?/g, "\n") !== lastArticle;
  $("stale-note").hidden = !stale;
  // An empty page offers the demonstration as one visible action and keeps the empty box short.
  const empty = !value.trim();
  $("demo-hero").hidden = !empty;
  $("input-card").classList.toggle("is-empty", empty);
  $("audit-btn").disabled = empty || n > MAX_CHARS;
}

// After an audit the box gives way to one line: the article is shown once, in the review.
function setInputCollapsed(on) {
  inputCollapsed = on;
  $("input-body").hidden = on;
  $("input-summary").hidden = !on;
  $("input-card").classList.toggle("is-collapsed", on);
  if (on) $("summary-text").textContent = `المقال المُدقَّق: ${toArabicDigits(ART.length)} حرفًا، ${toArabicDigits(paraStarts().length)} ${paraStarts().length === 1 ? "فقرة" : paraStarts().length === 2 ? "فقرتان" : "فقرات"}.`;
}

const DEMO_NOTE = "هذا مقال تجريبي كُتب لهذا العرض؛ فيه خطآن مقصودان في الاقتباس (لفظ وإحالة)، وهما من صنع المثال وليسا نصًا قرآنيًا.";

async function loadSample(name, thenAudit) {
  if (!name) return false;
  try {
    const res = await fetch(`/static/samples/${encodeURIComponent(name)}.txt`);
    if (!res.ok) throw new Error();
    $("article").value = (await res.text()).trim();
    if (name === "sample-demo") demoText = $("article").value.replace(/\r\n?/g, "\n");
    updateCount();
    if (name === "sample-demo" && !thenAudit) setStatus(DEMO_NOTE + " اضغط «دقّق الاقتباسات».");
    return true;
  } catch {
    setStatus("تعذّر تحميل المثال.", true);
    return false;
  }
}

// One click: load the demonstration article and audit it.
async function runDemo() {
  const btn = $("demo-btn");
  btn.disabled = true;
  setStatus("جارٍ تحميل المقال التجريبي…", false, true);
  try {
    if (await loadSample("sample-demo", true)) await runAudit();
  } finally {
    btn.disabled = false;
  }
}

function setStatus(text, isError, busy, retry) {
  const s = $("status");
  s.replaceChildren();
  s.classList.toggle("error", !!isError);
  if (busy) s.append(el("span", { class: "spinner", "aria-hidden": "true" }));
  if (text) s.append(text);
  if (retry) s.append(" ", el("button", { type: "button", class: "btn small", onclick: retry, text: "أعد المحاولة" }));
}

async function runAudit() {
  const article = $("article").value.replace(/\r\n?/g, "\n");
  if (!article.trim()) { setStatus("ألصق نص المقال أولًا.", true); return; }
  if (article.length > MAX_CHARS) { setStatus(`النص أطول من الحد المسموح (${toArabicDigits(MAX_CHARS)} حرف).`, true); return; }
  const btn = $("audit-btn");
  btn.disabled = true;
  btn.textContent = "جارٍ التدقيق…";
  setStatus("جارٍ التدقيق ومقارنة الاقتباسات بنص المصحف…", false, true);
  // The free host sleeps when idle and needs up to a minute to wake: say so instead of leaving a spinner.
  const slow1 = setTimeout(() => setStatus("ما زال التدقيق جاريًا. الخادم المجاني يستيقظ بعد خمول وقد يستغرق نحو دقيقة؛ لا تغلق الصفحة، ومقالك محفوظ في المربع.", false, true), 7000);
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 100000);
  try {
    const res = await fetch("/api/audit", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ article }),
      signal: ctrl.signal,
    });
    let data;
    try { data = await res.json(); } catch { data = { error: "استجابة غير متوقعة من الخادم." }; }
    if (!res.ok) { setStatus(data.error || "تعذّر إكمال التدقيق.", true, false, res.status >= 500 || res.status === 429 ? runAudit : null); return; }
    setArticleText(article);
    lastResult = data;
    decisions = {}; dismissed = {}; reviewed = {};
    lastAction = null; cardError = null; pendingSel = null;
    auditedAt = Date.now() / 1000;
    isDemo = demoText !== null && article === demoText;
    current = (pendingList()[0] || activeFindings()[0] || {}).id ?? null;
    saveSession();
    render(true);
    loadHealth();  // refresh the banner with this call's real outcome
    setStatus("");
    announce(`اكتمل التدقيق. ${verdictText(data).headline}.`);
  } catch (e) {
    setStatus(e.name === "AbortError" ? "انتهت مهلة الطلب. مقالك ما زال في المربع." : "تعذّر الاتصال بالخادم. مقالك ما زال في المربع.", true, false, runAudit);
  } finally {
    clearTimeout(slow1);
    clearTimeout(timer);
    btn.textContent = "دقّق الاقتباسات";
    updateCount();
  }
}

function announce(text) { $("sr-live").textContent = ""; setTimeout(() => { $("sr-live").textContent = text; }, 30); }

// ---------------------------------------------------------------- render
// One quiet line about how this audit was made; the model, timing and source details sit behind it.
// A server notice that only reports what the model did (not something the editor must act on) belongs in the details.
const isModelNote = (n) => /الذكاء الاصطناعي|النموذج/.test(n.text) && (n.level === "info" || /تعذّر الاستخراج/.test(n.text));

function auditMeta(data) {
  const ai = data.ai || {};
  const details = (data.notices || []).filter((n) => isModelNote(n) && n.level === "info").map((n) => el("p", { text: n.text }));
  let line = null, tone = "plain";
  if (data.mode === "reduced") {
    tone = "limited";
    line = "دون ذكاء اصطناعي: قد تفوت عبارة قصيرة بلا علامات؛ حدّدها في المقال لتفحصها.";
  } else if (data.mode === "ai_failed") {
    tone = "limited";
    line = "تعذّر اقتراح الذكاء الاصطناعي هذه المرة. فُحص المقال بالعلامات وبالبحث في المصحف، وقد تفوت عبارة قصيرة بلا علامات؛ حدّدها في المقال لتفحصها.";
    if (ai.error) details.push(el("p", {}, "سبب التعذّر: ", el("bdi", { dir: "ltr", text: String(ai.error) })));
  } else if (data.mode === "ai" && ai.responded) {
    line = "اقترح نموذج ذكاء اصطناعي مواضع الاقتباس فقط، والحكم على كل اقتباس من نص قرآنبيديا وحده." + (ai.proposed ? "" : " ولم يقترح هذه المرة أي مقطع.");
    details.push(el("p", {}, "النموذج: ", el("bdi", { dir: "ltr", text: ai.model || data.provider_model || data.provider }),
      ` — استجاب في ${toArabicDigits(((ai.elapsed_ms || 0) / 1000).toFixed(1))} ث`,
      ai.proposed ? `؛ اقترح ${maqatiAr(ai.proposed)}، وُجد منها في المقال ${toArabicDigits(ai.located)}، واستُبعد ${toArabicDigits(ai.discarded)}.` : "؛ لم يقترح أي مقطع، فاعتمد الرصد على العلامات والبحث الآلي في المصحف.",
      toArabicDigits(aiShare(ai))));
  }
  if (data.source?.available && data.source.fetched_at) {
    details.push(el("p", {}, "نص المصحف من قرآنبيديا (مصحف حفص)، جُلب في ", el("b", { text: fmtTime(data.source.fetched_at) }), data.source.stale ? " — نسخة مخبأة لتعذّر التحديث." : "."));
  }
  if (!line && !details.length) return null;
  const box = el("div", { class: `audit-meta ${tone}` });
  if (tone === "limited") {
    // no model took part: that limits what the editor can rely on, so the one-line caveat stays in view
    box.append(el("p", { class: "am-line", text: line }));
    if (details.length) box.append(el("details", {}, el("summary", { text: "تفاصيل هذا التدقيق" }), ...details));
  } else {
    box.append(el("details", {}, el("summary", { text: "كيف جرى هذا التدقيق؟ (النموذج والمصدر)" }),
      line ? el("p", { class: "am-line", text: line }) : null, ...details));
  }
  return box;
}

function render(scroll) {
  $("results").hidden = false;
  $("legend").hidden = false;
  const data = lastResult;
  const notices = $("notices");
  notices.replaceChildren(...(data.notices || []).filter((n) => !isModelNote(n)).map((n) => el("div", { class: `notice ${n.level}`, text: n.text })));
  const meta = auditMeta(data);
  if (meta) notices.append(meta);
  setInputCollapsed(true);
  renderVerdict(data);
  renderArticle();
  renderPanel();
  renderFinal();
  renderDock();
  updateCount();
  if (scroll) goToFirstReview();
}

// «وجدنا ٤ اقتباسات؛ يحتاج اثنان إلى قرارك»: the counted noun and the verb agree with the number.
function verdictText(data) {
  const fs = data.findings || [];
  const total = fs.length, n = fs.filter((f) => f.needs_review).length;
  const found = total === 1 ? "وجدنا اقتباسًا واحدًا" : total === 2 ? "وجدنا اقتباسين" : `وجدنا ${toArabicDigits(total)} ${total <= 10 ? "اقتباسات" : "اقتباسًا"}`;
  if (!total) return { headline: "لم نجد اقتباسات قرآنية في النص", total, needing: 0 };
  let tail;
  if (n === 0) tail = total === 1 ? "ولا يحتاج إلى قرارك" : "ولا يحتاج أيٌّ منها إلى قرارك";
  else if (n === total) tail = total === 1 ? "ويحتاج إلى قرارك" : total === 2 ? "يحتاج كلاهما إلى قرارك" : "تحتاج كلها إلى قرارك";
  else tail = n === 1 ? "يحتاج واحد منها إلى قرارك" : n === 2 ? "يحتاج اثنان إلى قرارك" : `${n <= 10 ? "تحتاج" : "يحتاج"} ${toArabicDigits(n)} منها إلى قرارك`;
  return { headline: tail.startsWith("و") ? `${found} ${tail}` : `${found}؛ ${tail}`, total, needing: n };
}

function renderVerdict(data) {
  const v = verdictText(data);
  const box = $("verdict");
  box.className = `verdict ${v.needing ? "has-review" : "clear"}`;
  box.replaceChildren(...[
    el("h2", { id: "verdict-title", tabindex: "-1", text: v.headline }),
    el("p", { class: "verdict-sub", text: "الفحص يشمل الاقتباسات التي رُصدت فقط، وليس حكمًا على المقال كله." }),
    !v.total ? el("p", { class: "verdict-sub", text: "إن كان في مقالك آية لم نرصدها، حدّدها في المقال أدناه ثم اضغط «افحص المحدَّد»." }) : null,
    isDemo ? el("p", { class: "verdict-demo", text: DEMO_NOTE }) : null,
  ].filter(Boolean));
}

// The first quotation that needs the writer: the verdict and the decision stay on one screen.
async function goToFirstReview() {
  void document.body.offsetHeight;
  try { await document.fonts.ready; } catch { /* no font loading API: measure now */ }
  // wide screens: the verdict and the first decision share the screen; a phone: the decision itself comes first (the bar and the panel head repeat the count)
  (narrow() && !$("panel").hidden ? $("panel") : $("verdict")).scrollIntoView({ behavior: motion(), block: "start" });
  const card = $("current").firstElementChild;
  if (card) card.focus({ preventScroll: true });
  if (!narrow()) showInArticle();
}

// ---------------------------------------------------------------- article view (the writer's own text, with the quotations marked)
function textSpan(a, b) { return a < b ? el("span", { "data-o": a }, bidi(cpSlice(a, b))) : null; }

// The article view is a keyboard stop only where it scrolls inside its own column; on a phone it is part of the page.
function syncArticleFocusable() {
  const view = $("article-view");
  const scrolls = getComputedStyle(view).overflowY !== "visible" && view.scrollHeight > view.clientHeight + 4;
  if (scrolls) view.setAttribute("tabindex", "0"); else view.removeAttribute("tabindex");
}

function renderArticle() {
  const view = $("article-view");
  view.replaceChildren();
  let pos = 0;
  for (const f of [...activeFindings()].sort((a, b) => a.start - b.start)) {
    if (f.start < pos) continue;
    view.append(textSpan(pos, f.start));
    const [label, cls] = stateOf(f);
    view.append(el("mark", { class: `m ${cls} ${String(f.id) === String(current) ? "current" : ""}`, "data-id": f.id, role: "button", tabindex: "-1",
      "aria-label": `الاقتباس ${toArabicDigits(f.id)}: ${label}`, onclick: () => { if (!window.getSelection().toString()) goTo(f.id, { scroll: "panel" }); } },
      el("span", { "data-o": f.start }, bidi(cpSlice(f.start, f.end))), el("sup", { "aria-hidden": "true", text: toArabicDigits(f.id) })));
    pos = f.end;
  }
  view.append(textSpan(pos, ART.length));
  syncArticleFocusable();
}

function markCurrent() {
  document.querySelectorAll("#article-view mark.current").forEach((m) => m.classList.remove("current"));
  document.querySelector(`#article-view mark[data-id="${CSS.escape(String(current))}"]`)?.classList.add("current");
}
// Show the current quotation in the article column without moving the page when the card is what the writer is looking at.
function showInArticle() {
  const m = document.querySelector(`#article-view mark[data-id="${CSS.escape(String(current))}"]`);
  if (!m) return;
  const view = $("article-view");
  if (view.scrollHeight > view.clientHeight + 4 && getComputedStyle(view).overflowY !== "visible") {
    // wide screens: the article scrolls inside its own column, so the page (and the decision beside it) stays where it is
    view.scrollTo({ top: Math.max(0, m.offsetTop - view.clientHeight / 2 + m.offsetHeight / 2), behavior: motion() });
  } else if (narrow()) m.scrollIntoView({ behavior: motion(), block: "center" });
}

// Selecting words in the article view: a code-point range, snapped to whole words.
function offsetFromBoundary(node, off) {
  const view = $("article-view");
  if (!view.contains(node)) return null;
  if (node === view) {
    const kid = view.children[off];
    if (!kid) return ART.length;
    return Number((kid.matches("[data-o]") ? kid : kid.querySelector("[data-o]"))?.dataset.o ?? ART.length);
  }
  const base = node.nodeType === 1 ? node : node.parentElement;
  const holder = base.closest("[data-o]");
  if (holder) {
    const r = document.createRange();
    r.setStart(holder, 0);
    r.setEnd(node, off);
    return Number(holder.dataset.o) + Array.from(r.toString()).length;
  }
  const mark = base.closest("mark[data-id]");
  if (mark) { const f = findingById(mark.dataset.id); return f ? (node === mark && off === 0 ? f.start : f.end) : null; }
  return null;
}
function readSelection() {
  const sel = window.getSelection();
  if (!sel || sel.isCollapsed || !sel.rangeCount || !lastResult) return null;
  const r = sel.getRangeAt(0);
  let a = offsetFromBoundary(r.startContainer, r.startOffset), b = offsetFromBoundary(r.endContainer, r.endOffset);
  if (a === null || b === null) return null;
  if (a > b) [a, b] = [b, a];
  while (a < b && isSpace(ART[a])) a++;
  while (b > a && isSpace(ART[b - 1])) b--;
  return b > a ? { start: a, end: b } : null;
}
function updateSelectionBar() {
  const sel = readSelection();
  if (sel) pendingSel = sel;
  else if (document.activeElement?.id !== "phrase-btn") pendingSel = null;
  const bar = $("sel-bar");
  bar.hidden = !pendingSel;
  document.documentElement.classList.toggle("has-sel-bar", !!pendingSel);
  if (pendingSel) $("sel-text").textContent = `حدّدتَ: «${excerpt(cpSlice(pendingSel.start, pendingSel.end))}»`;
}

// ---------------------------------------------------------------- the decision panel
// Move to a finding: the card, the row and the mark follow it. `scroll`: "panel" (bring the card into view), "article" (show it in the text).
function goTo(id, { scroll = "panel", focus = true, keepError = false } = {}) {
  current = id;
  if (!keepError) cardError = null;
  saveSession();
  renderPanel();
  markCurrent();
  renderDock();
  const card = $("current").firstElementChild;
  if (!narrow()) showInArticle();
  if (scroll === "panel" && card) {
    const top = card.getBoundingClientRect().top;
    if (narrow() || top < 0 || top > innerHeight * 0.6) $("panel").scrollIntoView({ behavior: motion(), block: "start" });
  }
  if (focus && card) card.focus({ preventScroll: true });
  const f = findingById(id);
  if (f) announce(`الاقتباس ${toArabicDigits(f.id)} من ${toArabicDigits(allFindings().length)}: ${stateOf(f)[0]}`);
}

// The next quotation after `fromId` that still waits for the writer (wrapping round), in the order of the article.
function nextPending(fromId, dir = 1) {
  const fs = activeFindings();
  if (!fs.length) return null;
  const i = fs.findIndex((f) => String(f.id) === String(fromId));
  for (let k = 1; k <= fs.length; k++) {
    const f = fs[((i < 0 ? (dir > 0 ? -1 : 0) : i) + dir * k + fs.length * 2) % fs.length];
    if (pendingKind(f)) return f.id;
  }
  return null;
}

function undoNodes() {
  const out = [lastAction.text];
  if (lastAction.undo) out.push(" ", el("button", { type: "button", class: "link-btn", onclick: () => { const u = lastAction?.undo; lastAction = null; $("undo-line").hidden = true; u && u(); }, text: "تراجع" }));
  return out;
}
function notify(text, undo) {
  lastAction = { text, undo };
  const line = $("undo-line");
  line.replaceChildren(...undoNodes());
  line.hidden = false;
}

function afterDecision(f, text, undo) {
  saveSession();
  notify(text, undo);
  renderArticle();
  renderFinal();
  const nxt = pendingKind(f) ? null : nextPending(f.id);
  if (nxt !== null) goTo(nxt, { scroll: "panel" });
  else { renderAll(); if (!pendingList().length) $("current").firstElementChild?.focus({ preventScroll: true }); }
}

function renderAll() {
  renderArticle();
  renderPanel();
  renderFinal();
  renderDock();
}

function setDecision(id, value) {
  const f = activeFindings().find((x) => (x.changes || []).some((c) => c.id === id));
  const c = f.changes.find((x) => x.id === id);
  const before = decisions[id];
  if (decisions[id] === value) delete decisions[id];
  else decisions[id] = value;
  const undo = () => { if (before) decisions[id] = before; else delete decisions[id]; saveSession(); goTo(f.id, { scroll: "panel" }); };
  if (c.optional) { saveSession(); renderAll(); return; }
  const d = deltaParts(c);
  const msg = decisions[id] === "approved" ? `اعتمدتَ تغيير «${d.prefix}${d.before}» إلى «${d.prefix}${d.after}» (الاقتباس ${toArabicDigits(f.id)}).`
    : decisions[id] === "rejected" ? `أبقيتَ «${d.prefix}${d.before}» كما كتبتَه (الاقتباس ${toArabicDigits(f.id)}).`
    : `ألغيتَ قرارك في الاقتباس ${toArabicDigits(f.id)}.`;
  afterDecision(f, msg, undo);
}

function dismiss(f, on = true) {
  if (on) dismissed[f.id] = true; else delete dismissed[f.id];
  saveSession();
  renderArticle(); renderFinal(); renderDock();
  if (on) {
    notify(`استبعدتَ الاقتباس ${toArabicDigits(f.id)} («${excerpt(f.quote)}»): ليس اقتباسًا قرآنيًا.`, () => dismiss(f, false));
    const nxt = nextPending(f.id);
    if (nxt !== null && !activeFindings().some((g) => String(g.id) === String(current) && pendingKind(g))) { goTo(nxt, { scroll: "panel" }); return; }
    if (String(current) === String(f.id)) current = (activeFindings().find((g) => g.start > f.start) || activeFindings()[0] || {}).id ?? null;
    renderAll();
    $("panel-title").focus({ preventScroll: true });
  } else {
    current = f.id;
    notify(`أعدتَ الاقتباس ${toArabicDigits(f.id)} إلى المراجعة.`);
    renderAll();
    goTo(f.id, { scroll: "panel" });
  }
}

function markReviewed(f, on) {
  if (on) reviewed[f.id] = true; else delete reviewed[f.id];
  afterDecision(f, on ? `سجّلتَ أنك راجعتَ الاقتباس ${toArabicDigits(f.id)} بنفسك.` : `ألغيتَ تسجيل مراجعتك للاقتباس ${toArabicDigits(f.id)}.`, () => markReviewed(f, !on));
}

function renderPanel() {
  const fs = activeFindings();
  const hasAny = allFindings().length > 0;
  $("workbench").classList.toggle("no-panel", !hasAny);
  $("panel").hidden = !hasAny;
  if (!hasAny) return;
  const pend = pendingList();
  if (!fs.some((f) => String(f.id) === String(current))) current = (pend[0] || fs[0] || {}).id ?? null;
  const f = fs.find((x) => String(x.id) === String(current)) || null;
  const idx = f ? fs.indexOf(f) + 1 : 0;
  $("panel-title").textContent = f && pendingKind(f) ? "قرارك الآن" : pend.length ? "مراجعة اقتباس" : "اكتملت قراراتك";
  $("panel-progress").replaceChildren(el("b", { text: pendingText(pend.length) }), f ? ` · ${toArabicDigits(idx)} من ${toArabicDigits(fs.length)}` : "");
  $("panel-nav").hidden = pend.length < 2 && !(pend.length === 1 && f && !pendingKind(f));
  const undo = $("undo-line");
  undo.hidden = !lastAction;
  if (lastAction) undo.replaceChildren(...undoNodes());
  $("current").replaceChildren(f ? findingCard(f, idx, fs.length) : doneCard());
  renderQueue();
}

function doneCard() {
  return el("div", { class: "card done-card", tabindex: "-1" },
    el("p", { class: "q-title", text: "حسمتَ كل ما يحتاج قرارك" }),
    el("p", { text: "لم يبقَ اقتباس ينتظر قرارك. راجع المقال المعدّل قبل نسخه." }),
    el("button", { type: "button", class: "btn primary", onclick: goToFinal, text: "إلى المراجعة الأخيرة" }));
}

function goToFinal() {
  $("final").scrollIntoView({ behavior: motion(), block: "start" });
  $("final-title").focus({ preventScroll: true });
}

function renderQueue() {
  const fs = allFindings();
  const row = (f) => {
    const [label, cls] = stateOf(f);
    const isCur = String(f.id) === String(current);
    return el("li", {}, el("button", { type: "button", class: `row ${cls} ${isCur ? "current" : ""}`, id: `row-${f.id}`, "aria-current": isCur ? "true" : null,
      onclick: () => (dismissed[f.id] ? dismiss(f, false) : goTo(f.id, { scroll: "panel" })) },
      el("span", { class: "row-num", text: toArabicDigits(f.id) }),
      el("span", { class: "row-q", dir: "rtl" }, excerpt(f.quote)),
      el("span", { class: `state ${cls}`, text: dismissed[f.id] ? "استبعدتَه — اضغط للتراجع" : label })));
  };
  const group = (title, items, open, cls) => (items.length ? el("details", { class: `q-group ${cls}`, open: open ? "" : null },
    el("summary", {}, `${title} (${toArabicDigits(items.length)})`), el("ul", {}, items.map(row))) : null);
  const pend = fs.filter((f) => !dismissed[f.id] && pendingKind(f));
  const done = fs.filter((f) => !dismissed[f.id] && !pendingKind(f));
  const off = fs.filter((f) => dismissed[f.id]);
  $("queue").replaceChildren(...[
    group("تنتظر قرارك", pend, true, "need"),
    group("لا تحتاج قرارًا أو حسمتَها", done, pend.length === 0 || done.length <= 3, "done"),
    group("استبعدتَها: ليست اقتباسًا", off, true, "off"),
  ].filter(Boolean));
}

// ---------------------------------------------------------------- the card of one quotation
function sourceLink(f) {
  const seg = f.source?.segments?.[0];
  return seg ? el("a", { class: "src-link", href: seg.page_url, target: "_blank", rel: "noopener" }, "قرآنبيديا ↗", el("span", { class: "sr-only", text: ` — ${placeLabel(f.source)} (يفتح في نافذة جديدة)` })) : null;
}
const placeLabel = (src) => `سورة ${src.surah_name}، ${src.ayah_start === src.ayah_end ? "الآية " + toArabicDigits(src.ayah_start) : "الآيات " + toArabicDigits(src.ayah_start) + "–" + toArabicDigits(src.ayah_end)}`;

// «في المصحف: سورة الزمر، الآية ١٠ · إحالتك: الزمر: 10 (غير محسومة) · قرآنبيديا»: the place, what the writer wrote, the source
function whereInQuran(f, weak) {
  if (!f.source) return null;
  const r = f.reference;
  const refTxt = r.status === "missing" ? null : r.found ? `إحالتك: ${r.found.text} (${REF_LABEL[r.status]})` : `الإحالة ${REF_LABEL[r.status]}`;
  return el("p", { class: "where" },
    el("span", { class: "where-label", text: weak ? "قد تكون: " : "في المصحف: " }), el("b", { text: placeLabel(f.source) }), sourceLink(f),
    refTxt ? el("span", { class: `ref-note ${r.status}` }, refTxt) : null);
}

function findingCard(f, idx, total) {
  const [label, cls] = stateOf(f);
  const kind = pendingKind(f);
  const det = f.detection || {};
  const card = el("article", { class: `card finding ${cls}`, id: `finding-${f.id}`, tabindex: "-1", "aria-labelledby": `fh-${f.id}` },
    el("header", { class: "f-head" },
      el("h3", { id: `fh-${f.id}`, text: `الاقتباس ${toArabicDigits(f.id)}` }),
      el("span", { class: "f-where", text: whereText(f) }),
      el("span", { class: `state ${cls}`, text: label })),
    el("div", { class: "f-ctx" }, el("span", { class: "row-label", text: "في مقالك" }), contextView(f),
      el("button", { type: "button", class: "link-btn show-in-article", onclick: showInArticle, text: "اعرضه في المقال" })));
  if (cardError) card.append(el("p", { class: "card-error", role: "alert", text: cardError }));
  if (kind === "verse") card.append(verseBlock(f));
  else if (kind === "bounds") card.append(whereInQuran(f, false), boundsBlock(f), ...fixBlocks(f, true));
  else if (kind === "review") card.append(whereInQuran(f, false), reviewBlock(f));
  else {
    card.append(whereInQuran(f, false));
    const blocks = fixBlocks(f, false);
    if (blocks.length) card.append(...blocks);
    else card.append(el("p", { class: "okline" }, f.needs_review ? "راجعتَ هذا الموضع بنفسك." : `${wordingLabel(f.wording)}${f.wording.status === "matched" ? ": لا يحتاج إلى قرارك." : "."}`));
    if (f.needs_review && !requiredOf(f).length) card.append(el("div", { class: "actions-row" }, el("button", { type: "button", class: "btn", onclick: () => markReviewed(f, false), text: "ألغِ تسجيل المراجعة" })));
  }
  card.append(moreDetails(f));
  if (!kind) card.append(el("div", { class: "foot-row" }, nextButton(f)));
  return card;
}

function nextButton(f) {
  const nxt = nextPending(f.id);
  return nxt === null ? el("button", { type: "button", class: "btn primary", onclick: goToFinal, text: "إلى المراجعة الأخيرة" })
    : el("button", { type: "button", class: "btn primary", onclick: () => goTo(nxt, { scroll: "panel" }), text: `التالي: الاقتباس ${toArabicDigits(nxt)}` });
}

const notQuoteButton = (f) => el("button", { type: "button", class: "btn ghost not-quote", onclick: () => dismiss(f), text: "ليس اقتباسًا" });

// «الشرح: ٦ ← ٥» / «يجزى ← يوفى»: the one thing that differs, split so the old and the new value can be coloured.
const REF_SPLIT = /^(.*?:\s*)(.+)$/;
function deltaParts(c) {
  if (c.kind === "reference") {
    const a = REF_SPLIT.exec(c.original || ""), b = REF_SPLIT.exec(c.replacement || "");
    if (a && b && a[1] === b[1]) return { prefix: toArabicDigits(a[1]), before: toArabicDigits(a[2]), after: toArabicDigits(b[2]) };
    return { prefix: "", before: toArabicDigits(c.original || "—"), after: toArabicDigits((c.replacement || "").trim()) };
  }
  return { prefix: "", before: c.original || "—", after: (c.replacement || "").trim() };
}

// Required corrections, each with the exact change first and the two choices after it.
function fixBlocks(f, secondary) {
  return requiredOf(f).map((c) => decisionBlock(c, f, secondary));
}
function decisionBlock(c, f, secondary) {
  const d = deltaParts(c);
  const quoteLevel = c.kind !== "reference" && c.kind !== "reference_add";
  const short = Array.from(d.before + d.after + d.prefix).length <= 34;
  const [yes, no] = short ? [`غيّر إلى «${d.prefix}${d.after}»`, `أبقِ «${d.prefix}${d.before}»`] : ["اعتمد هذا التغيير", "أبقِ ما كتبتُه"];
  const warns = (f.review_reasons || []).filter((x) => x !== c.reason).slice(0, 2);
  const lead = c.kind === "reference" || !warns.length ? [c.reason] : warns;
  const side = (cap, cls, text) => el("div", { class: "d-side" }, el("span", { class: "d-cap", text: cap }),
    el("span", { class: cls }, d.prefix ? el("span", { class: "d-pre", text: d.prefix }) : null, text));
  const node = el("div", { class: `decide ${secondary ? "secondary" : ""}`, "data-change": c.id },
    el("p", { class: "q-title", text: DECISION_TITLE[c.kind] || KIND[c.kind] || c.kind }),
    el("div", { class: "delta", dir: "rtl" },
      side("في مقالك", "d-before", d.before),
      el("span", { class: "d-arrow", "aria-hidden": "true", text: "←" }),
      side("في المصحف", "d-after", d.after)),
    ...lead.filter(Boolean).map((x) => el("p", { class: "ch-lead", text: x })),
    c.kind === "diacritics" ? el("p", { class: "muted small", text: "تختلف طبعات المصاحف في بعض علامات الضبط (كشدّة الإدغام)؛ تأكد قبل الاعتماد." }) : null,
    el("div", { class: "actions-row" },
      el("button", { type: "button", class: "btn approve", "data-act": "approved", "aria-pressed": String(decisions[c.id] === "approved"), onclick: () => setDecision(c.id, "approved"), text: yes }),
      el("button", { type: "button", class: "btn reject", "data-act": "rejected", "aria-pressed": String(decisions[c.id] === "rejected"), onclick: () => setDecision(c.id, "rejected"), text: no })),
    quoteLevel && (c.quote_before || c.quote_after) ? el("details", { class: "ch-more" }, el("summary", { text: "الاقتباس كاملًا قبل التصحيح وبعده" }),
      el("div", { class: "ch-diff" },
        el("div", {}, el("span", { class: "row-label", text: "قبل" }), el("div", { class: "ch-before", dir: "rtl", text: c.quote_before })),
        el("div", {}, el("span", { class: "row-label", text: "بعد" }), el("div", { class: "ch-after quran", dir: "rtl", text: c.quote_after })))) : null);
  return node;
}

// ---- «هل قصدتَ هذه الآية؟»: an unmarked passage whose verse the writer has not confirmed
function verseBlock(f) {
  const cs = f.choices || [];
  const det = f.detection || {};
  const box = el("div", { class: "ask" });
  if (cs.length === 1) {
    box.append(el("p", { class: "q-title", text: "هل قصدتَ اقتباس هذه الآية؟" }), choiceView(cs[0], f, false),
      el("div", { class: "actions-row" },
        el("button", { type: "button", class: "btn approve", "data-act": "confirm-verse", onclick: () => requestPhrase(f.start, f.end, cs[0], f.id, "verse"), text: "نعم، هذه الآية" }),
        el("button", { type: "button", class: "btn", "data-act": "other-verse", "aria-expanded": "false", onclick: (e) => toggleVerseForm(e.currentTarget), text: "آية أخرى" }),
        notQuoteButton(f)));
  } else if (cs.length > 1) {
    box.append(el("p", { class: "q-title", text: "أي آية قصدتَ؟" }),
      el("p", { class: "muted small", text: "العبارة تتطابق مع أكثر من موضع، فلا نختار أحدها عنك." }),
      el("ul", { class: "choices" }, cs.map((ch) => el("li", {}, choiceView(ch, f, true)))),
      el("div", { class: "actions-row" },
        el("button", { type: "button", class: "btn", "data-act": "other-verse", "aria-expanded": "false", onclick: (e) => toggleVerseForm(e.currentTarget), text: "آية أخرى" }),
        notQuoteButton(f)));
  } else {
    box.append(el("p", { class: "q-title", text: "هل هذا اقتباس من آية؟" }),
      el("p", { text: "لم نجد لهذه العبارة موضعًا مطابقًا في المصحف. إن كنت قصدتَ آية فاختر موضعها لنقارن بها، وإلا فاستبعدها." }),
      el("div", { class: "actions-row" },
        el("button", { type: "button", class: "btn approve", "data-act": "other-verse", "aria-expanded": "false", onclick: (e) => toggleVerseForm(e.currentTarget), text: "اختر الآية" }),
        notQuoteButton(f)));
  }
  box.append(el("p", { class: "muted small ask-note", text: "لن يتغيّر شيء في مقالك قبل قرارك. بعد أن تؤكد الآية نعرض الفرق ونقترح التصحيح لتعتمده أو ترفضه." }));
  if (det.reasons?.length) box.append(el("p", { class: "muted small", text: det.reasons.join(" ") }));
  return box;
}

function choiceView(ch, f, withButton) {
  const words = ch.text.split(/\s+/);
  const text = words.length > 18 ? words.slice(0, 18).join(" ") + " …" : ch.text;
  return el("div", { class: "choice" },
    el("p", { class: "choice-place" }, el("b", { text: ch.label.includes(":") ? `سورة ${ch.label.split(":")[0]}، الآية ${toArabicDigits(ch.label.split(":")[1].trim())}` : ch.label }),
      f.source && ch.surah === f.source.surah && ch.ayah_start === f.source.ayah_start ? sourceLink(f) : null),
    el("p", { class: "quran", dir: "rtl", text }),
    withButton ? el("button", { type: "button", class: "btn approve", "data-act": "choose-verse", onclick: () => requestPhrase(f.start, f.end, ch, f.id, "verse"), text: "هذه الآية" }) : null);
}

// «آية أخرى»: sourced suggestions are not the only way; the writer can name the surah and ayah (the check then runs against it).
function toggleVerseForm(btn) {
  const host = btn.closest(".ask");
  const open = btn.getAttribute("aria-expanded") === "true";
  host.querySelector(".verse-form")?.remove();
  host.querySelectorAll('[data-act="other-verse"]').forEach((b) => b.setAttribute("aria-expanded", "false"));
  if (open) return;
  btn.setAttribute("aria-expanded", "true");
  const f = findingById(current);
  const sel = el("select", { id: "vf-surah", name: "surah" }, (window.SURAHS || []).map(([n, name]) => el("option", { value: n, text: `${toArabicDigits(n)}. ${name}` })));
  const a1 = el("input", { id: "vf-a1", type: "number", inputmode: "numeric", min: "1", value: "1", required: "" });
  const a2 = el("input", { id: "vf-a2", type: "number", inputmode: "numeric", min: "1", placeholder: "اختياري" });
  const limit = () => { const c = (window.SURAHS || [])[Number(sel.value) - 1]?.[2] || 286; a1.max = c; a2.max = c; };
  sel.addEventListener("change", limit); limit();
  const form = el("form", { class: "verse-form", novalidate: "", onsubmit: (e) => {
    e.preventDefault();
    const s = Number(sel.value), x = Number(a1.value), y = a2.value ? Number(a2.value) : x;
    const max = (window.SURAHS || [])[s - 1]?.[2] || 286;
    if (!(x >= 1 && x <= max && y >= x && y <= max)) { cardError = `رقم الآية خارج سورة ${(window.SURAHS || [])[s - 1]?.[1] || ""} (١–${toArabicDigits(max)}).`; goTo(f.id, { scroll: null, keepError: true }); return; }
    requestPhrase(f.start, f.end, { surah: s, ayah_start: x, ayah_end: y }, f.id, "verse");
  } },
    el("label", { for: "vf-surah", text: "السورة" }), sel,
    el("label", { for: "vf-a1", text: "من الآية" }), a1,
    el("label", { for: "vf-a2", text: "إلى الآية" }), a2,
    el("button", { type: "submit", class: "btn approve", text: "قارن بهذه الآية" }));
  btn.parentElement.after(form);
  form.scrollIntoView({ behavior: motion(), block: "nearest" });
  sel.focus({ preventScroll: true });
}

// ---- «أين ينتهي الاقتباس؟»: the words next to the span are what is uncertain; one click settles each
function tokensAround(f) {
  const [ps, pe] = paraBounds(f.start);
  const toks = [];
  let i = ps;
  while (i < pe) {
    while (i < pe && isSpace(ART[i])) i++;
    let j = i;
    while (j < pe && !isSpace(ART[j])) j++;
    if (j > i) toks.push({ start: i, end: j, text: cpSlice(i, j) });
    i = j;
  }
  return toks;
}
const hasLetters = (t) => /[؀-ۿ]/.test(t);
function neighbour(f, dir) {
  const toks = tokensAround(f);
  if (dir > 0) return toks.find((t) => t.start >= f.end && hasLetters(t.text)) || null;
  return [...toks].reverse().find((t) => t.end <= f.start && hasLetters(t.text)) || null;
}
const pinOf = (f) => (!f.detection?.unconfirmed && f.source ? { surah: f.source.surah, ayah_start: f.source.ayah_start, ayah_end: f.source.ayah_end } : null);

function boundsBlock(f) {
  const lead = f.lead_in, cont = f.continuation;
  const title = lead && cont ? "أين يبدأ الاقتباس وأين ينتهي؟" : lead ? "أين يبدأ الاقتباس؟" : "أين ينتهي الاقتباس؟";
  const box = el("div", { class: "ask bounds" }, el("p", { class: "q-title", text: title }),
    el("p", { text: "ما بين الحدّين مطابق للآية، لكننا لا نعرف هل الكلمة المجاورة من كلامك أم من الاقتباس." }));
  const side = (info, dir) => {
    const tok = neighbour(f, dir);
    const where = dir > 0 ? "بعد المقطع" : "قبل المقطع";
    const row = el("div", { class: "b-side" },
      el("p", {}, `${where} في مقالك: `, el("b", { class: "b-word", text: info.article }), `، وفي الآية: `, el("b", { class: "b-word quran", text: info.quran }), "."));
    if (tok) row.append(el("button", { type: "button", class: "btn", "data-act": dir > 0 ? "extend-end" : "extend-start",
      onclick: () => requestPhrase(dir > 0 ? f.start : tok.start, dir > 0 ? tok.end : f.end, pinOf(f), f.id, "bounds"), text: `«${info.article}» من الاقتباس` }));
    return row;
  };
  if (lead) box.append(side(lead, -1));
  if (cont) box.append(side(cont, 1));
  box.append(el("div", { class: "actions-row" },
    el("button", { type: "button", class: "btn approve", "data-act": "confirm-bounds", onclick: () => requestPhrase(f.start, f.end, pinOf(f), f.id, "bounds"), text: "نعم، هذا هو الاقتباس كاملًا" }),
    el("button", { type: "button", class: "btn", "data-act": "adjust-bounds", "aria-expanded": "false", onclick: (e) => toggleSpanEditor(e.currentTarget, f), text: "حدّد الكلمات بنفسك" }),
    f.detection?.kind === "marked" ? null : notQuoteButton(f)));
  return box;
}

// The word-level editor: tap a word outside the span to add it, the first or last word inside it to drop it.
function toggleSpanEditor(btn, f) {
  const host = btn.closest(".ask");
  const open = btn.getAttribute("aria-expanded") === "true";
  host.querySelector(".span-editor")?.remove();
  btn.setAttribute("aria-expanded", String(!open));
  if (open) return;
  const toks = tokensAround(f);
  let k0 = toks.findIndex((t) => t.end > f.start), k1 = toks.length - [...toks].reverse().findIndex((t) => t.start < f.end);
  if (k0 < 0) k0 = 0;
  const lo0 = Math.max(0, k0 - 6), hi0 = Math.min(toks.length, k1 + 6);
  const state = { a: k0, b: k1 };
  const words = el("div", { class: "span-words", dir: "rtl", role: "group", "aria-label": "كلمات الفقرة؛ المحدَّدة منها هي الاقتباس" });
  const go = el("button", { type: "button", class: "btn approve", "data-act": "check-span", text: "افحص هذا المقطع" });
  const draw = () => {
    words.replaceChildren(...toks.slice(lo0, hi0).map((t, i) => {
      const k = lo0 + i, inside = k >= state.a && k < state.b;
      return el("button", { type: "button", class: `w ${inside ? "in" : "out"}`, "aria-pressed": String(inside),
        onclick: () => {
          if (!inside) { if (k < state.a) state.a = k; else state.b = k + 1; }
          else if (state.b - state.a > 1) { if (k - state.a <= state.b - 1 - k) state.a = k + 1; else state.b = k; }
          draw(); words.querySelectorAll("button")[k - lo0]?.focus();
        }, text: t.text });
    }));
    go.disabled = state.b <= state.a;
  };
  go.addEventListener("click", () => { const s = toks[state.a].start, e = toks[state.b - 1].end; requestPhrase(s, e, pinOf(f), f.id, "bounds"); });
  draw();
  const ed = el("div", { class: "span-editor" },
    el("p", { class: "muted small", text: "اضغط كلمة خارج المقطع لإضافتها إليه، أو أول كلمة فيه أو آخرها لاستبعادها." }), words, go);
  btn.parentElement.after(ed);
  ed.scrollIntoView({ behavior: motion(), block: "nearest" });
}

// ---- review-only: the tool cannot decide and proposes nothing to change
function reviewBlock(f) {
  const w = f.wording;
  const box = el("div", { class: "ask review" }, el("p", { class: "q-title", text: "راجع هذا الموضع بنفسك" }));
  const reasons = (f.review_reasons || []).slice(0, 2);
  reasons.forEach((x) => box.append(el("p", { class: "ch-lead", text: x })));
  if (f.reference?.status === "incorrect" && f.reference.message) box.append(el("p", { class: "ch-lead", text: f.reference.message }));
  const nonEqual = (w.diff || []).filter((d) => d.op !== "equal");
  if (f.source && nonEqual.length) box.append(el("div", {}, el("div", { class: "row-label", text: "الفرق بالكلمات" }), diffView(w.diff),
    el("div", { class: "diff-legend", text: "الأحمر المشطوب: في مقالك لا في المصحف · الأخضر: في المصحف لا في مقالك" })));
  box.append(el("p", { class: "muted small", text: "لا نقترح تصحيحًا آليًا هنا. إن وجدتَ خطأً فصحّحه في نص مقالك ثم أعد التدقيق." }),
    el("div", { class: "actions-row" },
      el("button", { type: "button", class: "btn approve", "data-act": "reviewed", onclick: () => markReviewed(f, true), text: "راجعتُه بنفسي" }),
      notQuoteButton(f)));
  return box;
}

// ---- the long material, one click away: the full verse, the comparison, the technical notes
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
    el("b", { text: placeLabel(src) }), el("span", { class: "muted", text: COVERAGE[src.coverage] || "" }),
    ...src.segments.flatMap((seg) => [
      el("a", { href: seg.page_url, target: "_blank", rel: "noopener", text: `عرض ${toArabicDigits(src.surah)}:${toArabicDigits(seg.ayah)} في قرآنبيديا` }),
      el("a", { href: seg.api_url, target: "_blank", rel: "noopener", text: "سجل API" }),
    ]));
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

// The Uthmani convention a matched quotation was written in, with the words it was matched through.
function scriptNote(w) {
  const sc = w.script;
  if (!sc) return null;
  const box = el("div", { class: "script-note" },
    el("span", { class: "row-label", text: "رسم الاقتباس" }),
    el("p", {}, el("b", { text: sc.label }), " — ", (sc.features || []).map((x) => SCRIPT_FEATURE[x] || x).join("، ")));
  if (sc.words?.length) box.append(el("details", { class: "script-words" }, el("summary", { text: `الكلمات المطابَقة بعد توحيد الرسم (${toArabicDigits(sc.word_count || sc.words.length)})` }), pairsList(sc.words)));
  return box;
}

function referenceRow(r) {
  const box = el("div", { class: "status-box" }, el("div", { class: "row-label", text: "الإحالة" }), el("b", { text: `الإحالة ${REF_LABEL[r.status] || "—"}` }));
  if (r.found) box.append(el("p", {}, "المذكور: ", el("b", { text: r.found.text })));
  if (r.message) box.append(el("p", { text: r.message }));
  return box;
}

// Optional formatting of text that is already right (full vocalisation, Quranpedia's spelling, an added reference): neutral, never counted as a correction.
function changeCard(c) {
  const before = c.kind === "reference_add" ? "—" : c.quote_before || c.original || "—";
  const after = c.kind === "reference_add" ? c.replacement.trim() : c.quote_after || c.replacement;
  const d = decisions[c.id];
  const node = el("div", { class: `change optional ${d === "approved" ? "approved" : ""}`, "data-change": c.id },
    el("div", { class: "ch-head" }, el("b", { text: KIND[c.kind] || c.kind }),
      el("span", { class: "ch-state", text: d === "approved" ? "مطبَّق" : d === "rejected" ? "متجاهَل" : "لن يُطبَّق ما لم تختره" })),
    el("div", { class: "ch-diff" },
      el("div", {}, el("span", { class: "row-label", text: "كما كتبتَه" }), el("div", { class: "ch-before", dir: "rtl", text: before })),
      el("div", {}, el("span", { class: "row-label", text: "بعد التنسيق" }), el("div", { class: `ch-after ${c.kind !== "reference_add" ? "quran" : ""}`, dir: "rtl", text: after }))),
    el("p", { class: "ch-reason", text: c.reason }),
    el("div", { class: "actions-row" },
      el("button", { type: "button", class: "btn small approve", "data-act": "approved", "aria-pressed": String(d === "approved"), onclick: () => setDecision(c.id, "approved"), text: "تطبيق" }),
      el("button", { type: "button", class: "btn small reject", "data-act": "rejected", "aria-pressed": String(d === "rejected"), onclick: () => setDecision(c.id, "rejected"), text: "تجاهل" })));
  return node;
}

function moreDetails(f) {
  const w = f.wording, det = f.detection || {};
  const optional = (f.changes || []).filter((c) => c.optional);
  const body = el("div", { class: "f-detail" });
  if (f.source) {
    body.append(el("div", {}, el("div", { class: "row-label", text: w.level === "fuzzy" ? "أقرب موضع في المصحف (غير مؤكد)" : "النص في المصحف (حفص — قرآنبيديا)" }), sourceBox(f.source)));
  }
  const nonEqual = (w.diff || []).filter((d) => d.op !== "equal");
  const wBox = el("div", { class: "status-box" }, el("div", { class: "row-label", text: det.unconfirmed ? "مطابقة النص للمصحف (إن كان اقتباسًا)" : "الألفاظ" }), el("b", { text: wordingLabel(w) }));
  if (w.message) wBox.append(el("p", { text: w.message }));
  if (w.level === "fuzzy" && w.similarity != null) wBox.append(el("p", { class: "muted", text: `نسبة التشابه: ${toArabicDigits(Math.round(w.similarity * 100))}٪` }));
  if (w.level === "diacritics" && w.status === "matched") wBox.append(el("p", { class: "muted", text: "الحروف مطابقة؛ التشكيل ناقص أو غائب لكنه غير مخالف، فليس خطأً." }));
  if (w.level === "literal") wBox.append(el("p", { class: "muted", text: "مطابق حرفًا وتشكيلًا (بعد تجاهل علامات الوقف)." }));
  body.append(el("div", { class: "statuses" }, wBox, referenceRow(f.reference)));
  if (nonEqual.length) {
    body.append(el("div", {}, el("div", { class: "row-label", text: "الفرق بالكلمات" }), diffView(w.diff),
      el("div", { class: "diff-legend", text: "الأحمر المشطوب: في المقال لا في المصحف · الأخضر: في المصحف لا في المقال" })));
  }
  if (w.unresolved_words?.length) body.append(el("div", {}, el("div", { class: "row-label", text: "رسم لم تستطع الأداة مطابقته (المقال ← المصحف) — قد يكون صحيحًا" }), pairsList(w.unresolved_words)));
  if (w.diacritic_conflicts?.length) body.append(el("div", {}, el("div", { class: "row-label", text: "تشكيل مخالف (المقال ← المصحف)" }), pairsList(w.diacritic_conflicts)));
  const sig = (w.script_diffs || []).filter((d) => d.kind !== "benign" || w.status !== "matched");
  if (sig.length) body.append(el("div", {}, el("div", { class: "row-label", text: "فروق الرسم (المقال ← المصحف)" }), pairsList(sig)));
  const sn = scriptNote(w);
  if (sn) body.append(sn);
  if (f.review_reasons?.length && f.needs_review) body.append(el("div", {}, el("div", { class: "row-label", text: "سبب طلب المراجعة" }), el("ul", { class: "reasons" }, f.review_reasons.map((x) => el("li", { text: x })))));
  if (f.alternatives?.length) {
    body.append(el("div", {}, el("div", { class: "row-label", text: `مواضع أخرى محتملة (${toArabicDigits(f.alternatives.length)}${f.occurrences > f.alternatives.length ? " من " + toArabicDigits(f.occurrences) : ""})` }),
      el("ul", { class: "alts-list" }, f.alternatives.map((a) => el("li", {}, el("b", { text: a.label }), " — ", el("span", { class: "quran", text: a.source.matched_text }),
        a.similarity < 1 ? el("span", { class: "muted", text: ` (${toArabicDigits(Math.round(a.similarity * 100))}٪)` }) : null)))));
  }
  if (optional.length) {
    body.append(el("div", { class: "optional-box" }, el("div", { class: "row-label", text: `تنسيق اختياري — ليس تصحيحًا (${toArabicDigits(optional.length)})` }),
      el("p", { class: "muted small", text: "نصك صحيح هنا. هذه خيارات تنسيق لا تُطبَّق إلا إذا اخترتها." }), ...optional.map(changeCard)));
  }
  body.append(el("p", { class: "muted small" }, "طريقة الرصد: ", f.detected_by.map((d) => detectedLabel(f, d)).join("، "), ".",
    det.label ? ` (${det.label})` : ""));
  const aiNote = aiSpanNote(f);
  if (aiNote) body.append(aiNote);
  const actions = [];
  if (!pendingKind(f) && det.kind !== "manual") actions.push(notQuoteButton(f));
  if (actions.length) body.append(el("div", { class: "actions-row" }, ...actions));
  return el("details", { class: "f-all" }, el("summary", { text: "التفاصيل: الآية كاملة، المقارنة، روابط المصدر" }), body);
}

// ---------------------------------------------------------------- checking a span with the server
async function requestPhrase(start, end, choice, findingId, why) {
  if (!lastResult) return;
  const f = findingById(findingId);
  cardError = null;
  const card = $("current").firstElementChild;
  card?.querySelectorAll("button").forEach((b) => { b.disabled = true; });
  setStatus("جارٍ فحص المقطع ومقارنته بنص المصحف…", false, true);
  try {
    // the other findings' spans, so a reference that belongs to a neighbouring quotation is not taken by this span
    const others = (lastResult.findings || []).filter((g) => g.start >= end || g.end <= start).map((g) => [g.start, g.end]).slice(0, 200);
    const body = { article: lastArticle, start, end, finding_id: findingId, others };
    if (choice) Object.assign(body, { surah: choice.surah, ayah_start: choice.ayah_start, ayah_end: choice.ayah_end });
    const res = await fetch("/api/phrase", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    let data;
    try { data = await res.json(); } catch { data = { error: "استجابة غير متوقعة من الخادم." }; }
    if (!res.ok) { cardError = data.error || "تعذّر فحص المقطع."; setStatus(""); goTo(findingId, { scroll: null, focus: false, keepError: true }); return; }
    setStatus("");
    applyPhrase(data.finding, why, f);
  } catch {
    cardError = "تعذّر الاتصال بالخادم. لم يتغيّر شيء؛ حاول مرة أخرى.";
    setStatus("");
    goTo(findingId, { scroll: null, focus: false, keepError: true });
  }
}

function applyPhrase(nf, why, previous) {
  const overlapped = allFindings().filter((g) => g.start < nf.end && nf.start < g.end);
  const priorState = overlapped.map((g) => ({ f: g, d: dismissed[g.id], r: reviewed[g.id], ch: Object.fromEntries((g.changes || []).map((c) => [c.id, decisions[c.id]]).filter(([, v]) => v)) }));
  for (const old of overlapped) { for (const c of old.changes || []) delete decisions[c.id]; delete dismissed[old.id]; delete reviewed[old.id]; }
  lastResult.findings = [...allFindings().filter((g) => !overlapped.includes(g)), nf].sort((a, b) => a.start - b.start);
  lastResult.stats = computeStats(allFindings());
  current = nf.id;
  const undo = () => {
    lastResult.findings = [...allFindings().filter((g) => g.id !== nf.id || g.start !== nf.start), ...priorState.map((p) => p.f)].sort((a, b) => a.start - b.start);
    for (const p of priorState) { Object.assign(decisions, p.ch); if (p.d) dismissed[p.f.id] = true; if (p.r) reviewed[p.f.id] = true; }
    lastResult.stats = computeStats(allFindings());
    current = priorState[0]?.f.id ?? null;
    saveSession();
    renderAll();
    goTo(current, { scroll: "panel" });
  };
  const text = why === "verse" ? `ثبّتَّ الآية للاقتباس ${toArabicDigits(nf.id)}؛ راجع ما نقترحه عليها.` : why === "bounds" ? `ثبّتَّ حدود الاقتباس ${toArabicDigits(nf.id)}؛ راجع النتيجة.` : `فُحص المقطع المحدَّد (الاقتباس ${toArabicDigits(nf.id)}).`;
  notify(text, priorState.length ? undo : null);
  saveSession();
  renderAll();
  goTo(nf.id, { scroll: "panel" });
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
    proposed_changes: findings.reduce((a, f) => a + (f.changes || []).filter((c) => !c.optional).length, 0),
    optional_changes: findings.reduce((a, f) => a + (f.changes || []).filter((c) => c.optional).length, 0),
  };
}

async function checkSelection() {
  const sel = pendingSel;
  if (!sel || !lastResult) return;
  const hit = allFindings().filter((f) => f.start < sel.end && sel.start < f.end);
  const fixed = hit.find((f) => !["phrase", "manual"].includes(f.detection?.kind) && !f.detection?.unconfirmed);
  if (fixed) { setStatus(`هذا الموضع مشمول بالفعل بالاقتباس ${toArabicDigits(fixed.id)} (رُصد بالعلامات أو بالذكاء الاصطناعي).`, true); goTo(fixed.id, { scroll: "panel" }); return; }
  const id = hit.length ? hit[0].id : Math.max(0, ...allFindings().map((f) => f.id)) + 1;
  window.getSelection()?.removeAllRanges();
  pendingSel = null;
  updateSelectionBar();
  await requestPhrase(sel.start, sel.end, null, id, "manual");
}

// ---------------------------------------------------------------- the final check: what will be copied, what is still open
function approvedRows() {
  return activeFindings().flatMap((f) => (f.changes || []).filter((c) => decisions[c.id] === "approved").map((c) => ({ f, c })));
}
function unresolvedNow() { return R.unresolvedFindings(activeFindings(), decisions); }

function changeContext(f, c) {
  const [ps, pe] = paraBounds(c.start);
  const a0 = Math.max(ps, c.start - 50), a1 = Math.min(pe, c.end + 50);
  let pre = cpSlice(a0, c.start), post = cpSlice(c.end, a1);
  if (a0 > ps && !isSpace(ART[a0 - 1])) pre = pre.replace(/^\S*\s?/, "");
  if (a1 < pe && !isSpace(ART[a1])) post = post.replace(/\s?\S*$/, "");
  return el("p", { class: "ctx", dir: "rtl" }, a0 > ps ? "… " : null, bidi(pre),
    c.original ? el("del", {}, bidi(c.original)) : null, c.replacement ? el("ins", {}, bidi(c.replacement)) : null, bidi(post), a1 < pe ? " …" : null);
}

function renderFinal() {
  const fs = activeFindings();
  $("final").hidden = !allFindings().length;
  if (!allFindings().length) return;
  const changes = allChanges();
  const { text, refused } = R.applyApproved(lastArticle, changes, decisions);
  const rows = approvedRows();
  const pend = pendingList();
  const unresolved = unresolvedNow();
  const left = requiredOfAll().filter((c) => decisions[c.id] === "rejected").length;
  const off = allFindings().filter((f) => dismissed[f.id]).length;
  const sentence = [
    rows.length ? `سيُنسخ مقالك بعد ${toArabicDigits(rows.length)} ${rows.length === 1 ? "تغيير اعتمدتَه" : rows.length === 2 ? "تغييرين اعتمدتَهما" : rows.length <= 10 ? "تغييرات اعتمدتَها" : "تغييرًا اعتمدتَها"}` : "لم تعتمد أي تغيير؛ سيُنسخ مقالك كما كتبتَه",
    left ? `أبقيتَ ${toArabicDigits(left)} كما كتبتَ` : null,
    off ? `واستبعدتَ ${toArabicDigits(off)} ${off === 1 ? "مقطعًا ليس اقتباسًا" : "مقاطع ليست اقتباسات"}` : null,
  ].filter(Boolean).join("، ") + ".";
  $("final-summary").replaceChildren(el("p", { class: "final-sentence", text: sentence }));

  $("final-changes").replaceChildren(rows.length ? el("div", {}, el("h3", { text: "التغييرات التي ستظهر في النص" }),
    el("ul", { class: "change-list" }, rows.map(({ f, c }) => el("li", {}, el("div", { class: "cl-head" },
      el("b", { text: `الاقتباس ${toArabicDigits(f.id)} — ${whereText(f)}` }),
      el("button", { type: "button", class: "link-btn", onclick: () => goTo(f.id, { scroll: "panel" }), text: "افتحه" })), changeContext(f, c))))) : null);

  const open = [...new Map([...pend, ...unresolved].map((f) => [f.id, f])).values()].sort((a, b) => a.start - b.start);
  $("final-pending").replaceChildren(open.length ? el("div", { class: "open-box" },
    el("h3", { text: pend.length ? `${pendingText(pend.length)} — وسيبقى كما كتبتَه إن لم تقرّر` : "اقتباسات لم تحسمها الأداة" }),
    el("ul", { class: "open-list" }, open.map((f) => el("li", {}, el("span", { class: "row-num", text: toArabicDigits(f.id) }), el("span", { class: "row-q", dir: "rtl" }, excerpt(f.quote)),
      el("span", { class: `state ${pendingKind(f) ? "need" : "off"}`, text: pendingKind(f) ? PENDING_TEXT[pendingKind(f)] : reviewed[f.id] ? "راجعتَه بنفسك؛ لم تحسمه الأداة" : "لم تحسمه الأداة" }),
      el("button", { type: "button", class: "link-btn", onclick: () => goTo(f.id, { scroll: "panel" }), text: pendingKind(f) ? "قرّر" : "راجع" }))))) : null);

  const view = $("preview-view");
  view.replaceChildren();
  for (const s of R.previewSegments(lastArticle, changes, decisions, unresolvedSpans())) {
    if (s.type === "text") view.append(...bidi(s.text));
    else if (s.type === "del") view.append(el("del", { title: "قبل", text: s.text }));
    else if (s.type === "ins") view.append(el("ins", { title: "بعد (معتمد)", text: s.text }));
    else view.append(el("span", { class: "unresolved", title: "اقتباس لم يُحسم — يحتاج مراجعة بشرية" }, bidi(s.text)), el("sup", { class: "unres-mark", text: toArabicDigits(s.id) }));
  }
  $("revised-text").value = text;
  $("reply-text").value = R.replyDraft(fs, changes, decisions);
  updateReplyCount();
  $("copy-btn").classList.toggle("ready", !pend.length);
  $("copy-note").classList.toggle("copy-bad", $("copy-note").classList.contains("copy-bad"));
  if (refused.length) $("final-changes").append(el("p", { class: "notice error", text: `تعذّر تطبيق ${toArabicDigits(refused.length)} تغييرًا (تداخل أو إزاحة)؛ لن يظهر في النص المنسوخ.` }));
}
const requiredOfAll = () => activeFindings().flatMap(requiredOf);
function unresolvedSpans() { return unresolvedNow().map((f) => ({ start: f.start, end: f.end, id: f.id })); }

function updateReplyCount() {
  const n = Array.from($("reply-text").value).length;
  $("reply-count").textContent = `${toArabicDigits(n)} حرفًا`;
}

// ---------------------------------------------------------------- the bottom bar (narrow screens): where the review stands, and the next step
function renderDock() {
  const dock = $("review-dock");
  if (!lastResult || !allFindings().length) { dock.hidden = true; document.documentElement.style.setProperty("--dock-h", "0px"); return; }
  const pend = pendingList();
  dock.hidden = false;
  $("dock-text").textContent = pendingText(pend.length);
  const btn = $("dock-next");
  btn.textContent = pend.length ? "التالي" : "المراجعة الأخيرة";
  btn.setAttribute("aria-label", pend.length ? "انتقل إلى الاقتباس التالي الذي ينتظر قرارك" : "انتقل إلى المراجعة الأخيرة قبل النسخ");
  dock.classList.toggle("done", !pend.length);
  syncDockHeight();
}
// The bar must never hide the element that has keyboard focus (WCAG 2.2, 2.4.11 and failure F110): keep the space it takes as scroll padding.
function syncDockHeight() {
  const dock = $("review-dock");
  const h = dock.hidden || getComputedStyle(dock).display === "none" ? 0 : Math.ceil(dock.getBoundingClientRect().height);
  document.documentElement.style.setProperty("--dock-h", `${h}px`);
}

// ---------------------------------------------------------------- copy, tabs, print record
function copyFeedback(btn, note, text, ok) {
  const label = btn.dataset.label || btn.textContent;
  btn.dataset.label = label;
  btn.textContent = ok ? "✓ تم النسخ" : label;
  if (note) { note.textContent = text; note.classList.toggle("copy-bad", !ok); }
  clearTimeout(btn._copyTimer);
  btn._copyTimer = setTimeout(() => { btn.textContent = label; if (note) note.textContent = ""; }, ok ? 4000 : 8000);
}

async function copyRevised() {
  const text = $("revised-text").value;
  try {
    await navigator.clipboard.writeText(text);
    const pend = pendingList().length;
    const msg = `نُسخ المقال المعدّل${pend ? `، وبقي ${toArabicDigits(pend)} ${pend === 1 ? "اقتباس" : "اقتباسات"} لم تقرّر فيها كما كتبتَها` : ""}. الأداة فحصت الاقتباسات القرآنية التي رُصدت فقط؛ وما بقي غير محسوم يحتاج مراجعتك.`;
    copyFeedback($("copy-btn"), $("copy-note"), msg, true);
    announce(msg);
  } catch {
    $("final").querySelector("details.full-text").open = true;
    showTab("text"); $("revised-text").select();
    copyFeedback($("copy-btn"), $("copy-note"), "تعذّر النسخ التلقائي؛ النص المعدّل محدد الآن، انسخه يدويًا (Ctrl+C).", false);
  }
}

function showTab(which) {
  const preview = which === "preview";
  $("tab-preview").setAttribute("aria-selected", String(preview));
  $("tab-text").setAttribute("aria-selected", String(!preview));
  $("preview-view").hidden = !preview;
  $("revised-text").hidden = preview;
}

function aiRecordText(data) {
  const ai = data.ai || {};
  if (!ai.configured) return "لم يُستخدم الذكاء الاصطناعي (وضع مخفّض): فُحصت الاقتباسات المعلَّمة والعبارات المطابقة لنص المصحف دون علامات، وقد تفوت الاقتباسات القصيرة غير المعلَّمة.";
  if (ai.responded) return `نعم — استجاب النموذج ${ai.model} (${ai.provider}) في هذا التدقيق خلال ${((ai.elapsed_ms || 0) / 1000).toFixed(1)} ث؛ اقترح ${ai.proposed} مقطعًا، وُجد منها في المقال ${ai.located}، واستُبعد ${ai.discarded}.${aiShare(ai)} دوره اقتراح المواضع فقط.`;
  return `لا — كان ${ai.provider} مُعَدًّا لكنه لم يستجب في هذا التدقيق (${ai.error || ai.outcome})، فاستُخدم الوضع الاحتياطي الحتمي، وقد تفوت الاقتباسات القصيرة غير المعلَّمة.`;
}

function buildRecord() {
  const data = lastResult;
  const rec = $("print-record");
  const changes = allChanges();
  const approved = changes.filter((c) => decisions[c.id] === "approved");
  const rejected = changes.filter((c) => decisions[c.id] === "rejected");
  const pending = changes.filter((c) => !decisions[c.id]);
  const notApplied = changes.filter((c) => decisions[c.id] === "rejected" || (!decisions[c.id] && !c.optional));
  const optionalPending = changes.filter((c) => !decisions[c.id] && c.optional).length;
  const unresolved = unresolvedNow();
  const off = allFindings().filter((f) => dismissed[f.id]);
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
      kv("الأعداد", `اقتباسات مرصودة ${activeFindings().length} · تصحيحات معتمدة ${approved.length} · مرفوضة ${rejected.length} · بلا قرار ${pending.length} · غير محسومة ${unresolved.length} · مستبعدة (ليست اقتباسًا) ${off.length}`),
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
        el("td", { class: "url" }, el("bdi", { dir: "ltr", text: c.source_urls.join("\n") })))))) : el("p", { text: "لم يُعتمد أي تصحيح." }),
    el("h2", { text: "تصحيحات مقترحة رُفضت أو لم يُبتّ فيها" }),
    notApplied.length ? el("ul", {}, notApplied.map((c) =>
      el("li", {}, `#${c.finding_id} ${KIND[c.kind] || c.kind}: «${c.original || "(إضافة)"}» ← «${c.replacement.trim()}» — `, el("b", { text: decisions[c.id] === "rejected" ? "رُفض" : "بلا قرار" }), ` (${c.label})`))) : el("p", { text: "لا يوجد." }),
    optionalPending ? el("p", { class: "muted", text: `إضافةً إلى ${optionalPending} اقتراحًا اختياريًا للتنسيق (ضبط بالتشكيل أو إضافة إحالة) لم يُبتّ فيه؛ لا يدل على خطأ.` }) : null,
    el("h2", { text: "اقتباسات غير محسومة (تحتاج مراجعة بشرية)" }),
    unresolved.length ? el("ul", {}, unresolved.map((f) => el("li", {},
      `#${f.id} (السطر ${f.line}) «${f.quote}» — `,
      (f.review_reasons || []).join("؛ ") || (f.correction?.reason || "تصحيح مقترح لم يُعتمد"),
      f.source ? (f.wording.level === "fuzzy" ? ` — أقرب موضع مقترح (غير مؤكد): ${f.source.label}` : ` — الموضع في المصدر: ${f.source.label}`) : ""))) : el("p", { text: "لا يوجد في الاقتباسات المرصودة. (قد توجد اقتباسات لم تُرصد.)" }),
    off.length ? el("h2", { text: "مقاطع استبعدها المحرر (ليست اقتباسًا قرآنيًا)" }) : null,
    off.length ? el("ul", {}, off.map((f) => el("li", { text: `#${f.id} (السطر ${f.line}) «${f.quote}»` }))) : null,
    el("p", { class: "rec-foot", text: "أُعدّ بواسطة مدقق الاقتباسات القرآنية. نص المقال لا يُخزَّن على الخادم؛ هذا السجل مولَّد في المتصفح." }),
  );
}

function printRecord() {
  if (!lastResult) return;
  buildRecord();
  window.print();
}

// ---------------------------------------------------------------- init
function resetAll() {
  $("article").value = ""; lastResult = null; setArticleText(""); decisions = {}; dismissed = {}; reviewed = {}; current = null;
  isDemo = false; lastAction = null; cardError = null; pendingSel = null; clearSession();
  $("results").hidden = true; $("legend").hidden = true; setInputCollapsed(false); updateSelectionBar(); setStatus(""); updateCount(); renderDock();
}

document.addEventListener("DOMContentLoaded", () => {
  $("article").addEventListener("input", updateCount);
  $("audit-btn").addEventListener("click", runAudit);
  $("clear-btn").addEventListener("click", resetAll);
  $("edit-btn").addEventListener("click", () => { setInputCollapsed(false); $("article").focus(); });
  $("sample-select").addEventListener("change", (e) => loadSample(e.target.value));
  $("demo-btn").addEventListener("click", runDemo);
  $("dock-next").addEventListener("click", () => {
    const id = nextPending(current);
    if (id === null) goToFinal(); else goTo(id, { scroll: "panel" });
  });
  $("next-btn").addEventListener("click", () => { const id = nextPending(current); if (id !== null) goTo(id, { scroll: "panel" }); });
  $("prev-btn").addEventListener("click", () => { const id = nextPending(current, -1); if (id !== null) goTo(id, { scroll: "panel" }); });
  $("phrase-btn").addEventListener("mousedown", (e) => e.preventDefault());
  $("phrase-btn").addEventListener("click", checkSelection);
  document.addEventListener("selectionchange", updateSelectionBar);
  $("article").addEventListener("keydown", (e) => { if ((e.ctrlKey || e.metaKey) && e.key === "Enter") runAudit(); });
  $("copy-btn").addEventListener("click", copyRevised);
  $("reply-text").addEventListener("input", updateReplyCount);
  $("reply-copy").addEventListener("click", async () => {
    try { await navigator.clipboard.writeText($("reply-text").value); copyFeedback($("reply-copy"), null, "", true); announce("نُسخت المسودة. راجعها قبل نشرها بنفسك."); }
    catch { $("reply-text").select(); setStatus("تعذّر النسخ التلقائي؛ النص محدد، انسخه يدويًا.", true); }
  });
  $("print-btn").addEventListener("click", printRecord);
  $("reset-btn").addEventListener("click", () => {
    decisions = {}; dismissed = {}; reviewed = {}; lastAction = null; saveSession();
    renderAll();
    announce("أُلغيت كل قراراتك.");
  });
  $("tab-preview").addEventListener("click", () => showTab("preview"));
  $("tab-text").addEventListener("click", () => showTab("text"));
  window.addEventListener("beforeprint", () => { if (lastResult) buildRecord(); });
  window.addEventListener("resize", () => { syncDockHeight(); syncArticleFocusable(); });
  if (window.ResizeObserver) new ResizeObserver(syncDockHeight).observe($("review-dock"));

  const saved = loadSession();
  if (saved) {
    setArticleText(saved.article); lastResult = saved.result; decisions = saved.decisions || {}; dismissed = saved.dismissed || {}; reviewed = saved.reviewed || {};
    current = saved.current ?? null; auditedAt = saved.auditedAt || null; isDemo = !!saved.isDemo;
    $("article").value = lastArticle;
    render(false);
    setStatus("استُعيدت نتيجة التدقيق وقراراتك من هذه الجلسة.");
  }
  updateCount();
  loadHealth();
});
