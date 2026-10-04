// Quran quotation auditor — frontend.
// All user-supplied and server-supplied text is inserted with textContent
// (never innerHTML), so article text cannot inject markup.
// The article is a plain textarea (native Arabic caret, selection and undo) with a highlight layer behind it. The writer keeps
// editing after an audit: every edit moves the findings (workspace.js) and marks the ones it touched as stale.
// Revision state (the editor's decisions) lives only in this browser tab (memory + sessionStorage), unless the writer
// explicitly saves a draft in this browser; it is never sent to the server.
"use strict";

const $ = (id) => document.getElementById(id);
const R = window.Revision;
const W = window.Workspace;
let MAX_CHARS = 20000;
let AI_MAX_CHARS = 6000;
let aiConfigured = null;  // null until /api/health answers; only used to describe what an audit will do, never to switch the model
let lastArticle = "";    // the CURRENT text of the editor (not the text of the last audit: see auditedText)
let auditedText = "";    // the text the last audit was made on
let baseText = "";       // the text as first audited: the writer's original
let invalidated = [];    // decisions that fell because the text changed: { quote, why }
let carryNote = null;    // what the last recheck kept and dropped
let lastSel = null;      // the selection (code points) just before the edit being processed, read in beforeinput
const DRAFT_KEY = "qqa-draft-v1";
let ART = [];            // the current article as an array of code points (the server's offsets are code points)
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
let pendingSel = null;   // { start, end } the writer highlighted in the editor
let recheckBusy = false;
let docGen = 0;          // bumped when the document is replaced (clear, sample, draft); an answer for an older one is dropped
const STORE_KEY = "qqa-session-v3";

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

// replaceChildren with the empty slots of a conditional («cond ? node : null») left out: replaceChildren(null) would print the word «null»
const fill = (node, ...kids) => node.replaceChildren(...kids.flat(Infinity).filter((k) => k !== null && k !== undefined && k !== false));

const toArabicDigits = (n) => String(n).replace(/\d/g, (d) => "٠١٢٣٤٥٦٧٨٩"[d]);
// a character count with the Arabic thousands separator: «٢٠٬٠٠٠» (the Arabic zero is a dot, so «٢٠٠٠٠» reads as «٢····»)
const arabicCount = (n) => toArabicDigits(String(n).replace(/\B(?=(\d{3})+(?!\d))/g, "٬"));
// a server notice in Arabic digits, numbers of four digits or more grouped («٦٬٠٠٠», not «٦٠٠٠»)
const noticeText = (t) => toArabicDigits(String(t).replace(/\d{4,}/g, (m) => arabicCount(Number(m))));
const fmtTime = (secs) => new Date(secs * 1000).toLocaleString("ar-u-nu-arab", { dateStyle: "medium", timeStyle: "short" });   // Arabic-Indic digits, as elsewhere on the page
const motion = () => (window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth");
// a short move may glide; a jump across a long article is instant (smooth scrolling over several screens takes seconds)
const motionFor = (distance) => (Math.abs(distance) > innerHeight * 1.5 ? "auto" : motion());
const scrollToNode = (node, block = "start") => node.scrollIntoView({ behavior: motionFor(node.getBoundingClientRect().top), block });
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
const DETECTED = { marked: "معلَّم بأقواس أو علامات", phrase: "بحث آلي عن عبارة مطابقة للمصحف", cue: "بحث في المصحف عمّا قدّمتَ له بعبارة تمهيد أو إحالة أو علامتي تنصيص", manual: "حدّدته بنفسك" };
// The model only proposes places. "Only" is reserved for a finding that would be absent without it; when a marker or the
// phrase search found the span too, the model merely proposed the same one (it added nothing for this finding).
const AI_ROLE = { only: "اقترحه الذكاء الاصطناعي وحده (لم يجده البحث الآلي)", also: "اقترح الذكاء الاصطناعي المقطع نفسه أيضًا" };
const detectedLabel = (f, d) => (d === "ai" ? (AI_ROLE[f.detection?.ai_role] || "اقترح الذكاء الاصطناعي هذا المقطع") : (DETECTED[d] || d));
// A counted noun in Arabic: one and two are said without a numeral («تغيير واحد», «تغييرين»), 3–10 take the plural («٣ تغييرات»),
// 11 and above the singular in the accusative («١١ تغييرًا»). Each form is the whole phrase, so what follows the noun agrees with it.
const countAr = (n, one, two, few, many) => (n === 1 ? one : n === 2 ? two : `${toArabicDigits(n)} ${n <= 10 ? few : many}`);
const maqatiAr = (n) => countAr(n, "مقطعًا واحدًا", "مقطعين", "مقاطع", "مقطعًا");
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
const lineOf = (pos) => { let n = 1; for (let i = 0; i < pos && i < ART.length; i++) if (ART[i] === "\n") n++; return n; };
// «الفقرة ٣ من ٨» in a long article, «السطر ٢» in a short one.
function whereText(f) {
  const total = paraStarts().length;
  return total > 1 ? `الفقرة ${toArabicDigits(paraNo(f.start))} من ${toArabicDigits(total)}` : `السطر ${toArabicDigits(lineOf(f.start))}`;
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
  if (f.stale) return "stale";
  if (dismissed[f.id]) return null;
  const det = f.detection || {};
  if (det.unconfirmed || f.needs_choice) return "verse";
  if (f.lead_in || f.continuation) return "bounds";
  if (requiredOf(f).some((c) => !decisions[c.id])) return "fix";
  if (f.needs_review && !requiredOf(f).length && !reviewed[f.id]) return "review";
  return null;
}
const pendingList = () => activeFindings().filter((f) => pendingKind(f));
// An exact match of a short or common phrase («في كل عام») that nothing marks as a quotation: the phrase search's own code «common», without
// a near-miss («approximate»). In the two labelled article sets about two in five of these were real quotations (4 Oct, docs/EVALUATION.md),
// so they stay listed, marked and reachable; they only wait behind the concrete decisions instead of leading the queue. No detection rule is changed.
const isWeak = (f) => { const c = f.detection?.codes || []; return !!f.detection?.unconfirmed && c.includes("common") && !c.includes("approximate"); };
const weakPending = (f) => pendingKind(f) === "verse" && isWeak(f);
const itemName = (f) => (weakPending(f) ? "العبارة" : "الاقتباس");   // «العبارة ٣» until the writer confirms it is a quotation
const mainPendingList = () => pendingList().filter((f) => !weakPending(f));
const weakPendingList = () => pendingList().filter(weakPending);
const orderedPending = () => [...mainPendingList(), ...weakPendingList()];
const PENDING_TEXT = { verse: "يحتاج تأكيدك", bounds: "حدود الاقتباس غير محسومة", fix: "تصحيح مقترح بانتظار قرارك", review: "يحتاج مراجعتك", stale: "عُدّل بعد التدقيق" };
// [text, class] — one plain state per quotation, never a stack of badges. The second class tells apart what the tool matched («exact»),
// a passage that may not be a quotation or may be another verse («possible»), what rests on the writer's own word («own»), and a correction
// the writer approved («approved»): it is applied to the copy, not to the text in the box, so it is not drawn as a match either.
function stateOf(f) {
  if (f.stale) return [PENDING_TEXT.stale, "stale"];
  if (dismissed[f.id]) return ["استبعدتَه: ليس اقتباسًا", "off"];
  const p = pendingKind(f);
  // a common phrase that only may be a quotation: an optional confirmation, drawn lighter than a decision (no ground, a grey dotted line)
  if (p === "verse" && isWeak(f)) return ["تأكيد اختياري", "need possible weak"];
  if (p) return [PENDING_TEXT[p], p === "verse" ? "need possible" : "need"];
  const req = requiredOf(f);
  if (req.length) return req.some((c) => decisions[c.id] === "approved") ? ["اعتمدتَ التصحيح", "done approved"] : ["أبقيتَه كما كتبتَ", "done own"];
  if (f.needs_review) return ["راجعتَه بنفسك", "done own"];
  return ["مطابق للمصحف", "done exact"];
}
// «اقتباس واحد ينتظر قرارك»، «اقتباسان ينتظران قرارك»، «٣ اقتباسات تنتظر قرارك»، «١١ اقتباسًا ينتظر قرارك»
function pendingText(n) {
  if (n === 0) return "حسمتَ كل ما يحتاج قرارك";
  if (n === 1) return "اقتباس واحد ينتظر قرارك";
  if (n === 2) return "اقتباسان ينتظران قرارك";
  return n <= 10 ? `${toArabicDigits(n)} اقتباسات تنتظر قرارك` : `${toArabicDigits(n)} اقتباسًا ينتظر قرارك`;
}

// «٣ عبارات للتأكيد»: phrases that may be quotations, said apart from the quotations that wait for a decision
const weakText = (n) => countAr(n, "عبارة واحدة للتأكيد", "عبارتان للتأكيد", "عبارات للتأكيد", "عبارة للتأكيد");
function openText() {
  const m = mainPendingList().length, w = weakPendingList().length;
  if (!m && w) return weakText(w);
  return pendingText(m) + (w ? `، و${weakText(w)}` : "");
}

// ---------------------------------------------------------------- session state
let sessionWarned = false;
function saveSession() {
  try {
    sessionStorage.setItem(STORE_KEY, JSON.stringify({ article: lastArticle, result: lastResult, decisions, dismissed, reviewed, current, auditedAt, isDemo,
      auditedText: auditedText === lastArticle ? null : auditedText, baseText: baseText === lastArticle ? null : baseText, invalidated }));
    sessionWarned = false;
  } catch {
    // storage unavailable or full (a long article with many findings): the state stays in memory only, and the writer is told once
    if (!sessionWarned && lastResult) { sessionWarned = true; setStatus("تعذّر حفظ نتيجة التدقيق في هذا المتصفح (المساحة ممتلئة أو التخزين معطّل)؛ تبقى القرارات ما دامت الصفحة مفتوحة، فلا تُعد تحميلها.", true); }
  }
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
    AI_MAX_CHARS = h.ai_max_chars || AI_MAX_CHARS;
    aiConfigured = !!h.ai_configured;
    if (h.accounts_enabled === true) loadAccounts();
    $("limit-note").textContent = arabicCount(MAX_CHARS);
    document.querySelectorAll(".ai-limit").forEach((n) => { n.textContent = arabicCount(AI_MAX_CHARS); });
    // what leaves the page at the next audit, said for this server (the page's default text names the configured case)
    if (!aiConfigured) $("send-note").textContent = "لا نموذج لغوي مهيّأ على هذا الخادم، فلا يُرسَل مقالك عند التدقيق إلى جهة خارجية، ولا يُحفظ على خادمنا؛";
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
      banner.append(`نتيجة كل تدقيق تبيّن هل استجاب النموذج فعلًا. دوره اقتراح مواضع الاقتباس فقط، ويُتحقق من كل مقترح بنص المقال ثم بنص المصحف، ولا يُستعمل في مقال أطول من ${arabicCount(AI_MAX_CHARS)} حرف. اقتراحات الآيات أثناء الكتابة لا يشارك فيها النموذج أبدًا.`);
    } else {
      banner.className = "banner reduced";
      banner.append(el("strong", { text: "الذكاء الاصطناعي غير مفعّل على هذا الخادم." }), " تُفحص الاقتباسات المعلَّمة والعبارات التي تطابق المصحف دون علامات؛ وقد تفوت بعض الاقتباسات القصيرة، ويمكنك تحديدها بنفسك. الكتابة والاقتراح والتدقيق تعمل كلها بدونه.");
    }
  } catch {
    banner.hidden = true;
  }
}

// ---------------------------------------------------------------- input
const editor = () => $("article");
const normalizeNl = (t) => t.replace(/\r\n?/g, "\n");
const cpCount = (t) => { let n = 0; for (const _ of t) n++; return n; };  // the server counts code points

const edited = () => !!lastResult && lastArticle !== auditedText;
const staleList = () => allFindings().filter((f) => f.stale);

function updateCount() {
  const value = editor().value;
  const n = cpCount(value);
  const c = $("char-count");
  c.textContent = `${arabicCount(n)} / ${arabicCount(MAX_CHARS)} حرف`;
  c.classList.toggle("char-over", n > MAX_CHARS);
  const stale = staleList().length;
  const note = $("stale-note");
  note.hidden = !edited();
  if (edited()) {
    note.textContent = stale
      ? `عدّلتَ المقال بعد آخر تدقيق: ${countAr(stale, "موضع واحد يحتاج", "موضعان يحتاجان", "مواضع تحتاج", "موضعًا يحتاج")} إلى إعادة التدقيق.`
      : "عدّلتَ المقال بعد آخر تدقيق. لم يمسّ تعديلك اقتباسًا مرصودًا، لكن لم يُفحص ما كتبتَه بعده.";
  }
  $("recheck-btn").hidden = !edited();
  // a calm word before the audit: an article over the model's limit is still audited in full, without the model
  const overAi = aiConfigured && n > AI_MAX_CHARS && n <= MAX_CHARS;
  $("ai-limit-note").hidden = !overAi;
  if (overAi) $("ai-limit-note").textContent = `أطول من ${arabicCount(AI_MAX_CHARS)} حرف: يُدقَّق كاملًا دون النموذج اللغوي`;
  // one filled button per state: «دقّق» before the first audit; after it the decision panel leads, and an edit fills «أعد التدقيق» beside its note
  $("audit-btn").classList.toggle("primary", !lastResult);
  // An empty page offers the demonstration as one visible action.
  const empty = !value.trim();
  $("demo-hero").hidden = !empty || !!lastResult;
  $("audit-btn").disabled = empty || n > MAX_CHARS || recheckBusy;
  $("recheck-btn").disabled = n > MAX_CHARS || recheckBusy;
  $("complete-btn").disabled = empty;
}

// The textarea grows with its text: the page scrolls, never the box, so the highlight layer behind it stays aligned.
function syncEditorHeight() {
  const ta = editor();
  ta.style.height = "auto";
  ta.style.height = `${ta.scrollHeight}px`;
  $("article-view").style.height = ta.style.height;
}

// A new document (a sample, a clear): the old audit does not describe this text.
function clearAudit() {
  docGen++;
  lastResult = null; decisions = {}; dismissed = {}; reviewed = {}; current = null; lastAction = null; cardError = null; pendingSel = null;
  auditedText = ""; baseText = ""; invalidated = []; carryNote = null; isDemo = false; auditedAt = null; finalInView = false;
  $("results").hidden = true; $("legend").hidden = true; $("panel").hidden = true; $("final").hidden = true;
  $("intro").classList.remove("audited");
  $("workbench").classList.add("no-panel");
  clearSession();
  updateSelectionBar();
  renderDock();
}

function setEditorText(text) {
  editor().value = text;
  clearAudit();
  setArticleText(normalizeNl(text));
  syncEditorHeight();
  renderBackdrop();
  updateCount();
}

const DEMO_NOTE = "مقال تجريبي كُتب لهذا العرض؛ الخطآن فيه مقصودان (لفظ وإحالة)، وليسا نصًا قرآنيًا.";

async function loadSample(name, thenAudit) {
  if (!name) return false;
  try {
    const res = await fetch(`/static/samples/${encodeURIComponent(name)}.txt`);
    if (!res.ok) throw new Error();
    setEditorText((await res.text()).trim());
    if (name === "sample-demo") demoText = lastArticle;
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

// ---- import a file: read in this browser by a worker (app/static/import.js), never uploaded. The text goes into the editor like a
// paste: it is never audited automatically and never corrected; a text already in the editor is replaced only if the writer says so.
const IMPORT_TIMEOUT_MS = 10000;
const IMPORT_MAX_BYTES = 5 * 1024 * 1024;
let importWorker = null;
let importBusy = false;
let importSeq = 0;
let importPending = null;   // { name, res }: an extracted text waiting for the writer's answer (replace the text in the editor, or not)
let importNotice = null;    // { gen, text }: the notice of the imported text, kept while that document is in the editor
// The status a document starts with: the import notice for an imported text (an older audit's late answer must not wipe it), else none.
const docNote = () => (importNotice && importNotice.gen === docGen ? importNotice.text : "");

function importWorkerReady() {
  if (!importWorker && window.Worker) {
    try { importWorker = new Worker("/static/import.js"); } catch { importWorker = null; }
  }
  return importWorker;
}

// The worker reads the file and answers once; if it takes longer than the limit it is stopped (and a new one is made next time).
function extractFile(file) {
  return new Promise((resolve) => {
    const w = importWorkerReady();
    if (!w) { resolve({ ok: false, message: "لا يستطيع هذا المتصفح قراءة الملف هنا؛ انسخ النص من الملف والصقه." }); return; }
    const id = ++importSeq;
    let timer = null;
    const done = (r) => { clearTimeout(timer); w.onmessage = null; w.onerror = null; resolve(r); };
    const stop = (message) => { w.terminate(); if (importWorker === w) importWorker = null; done({ ok: false, message }); };
    timer = setTimeout(() => stop(`استغرقت قراءة الملف أكثر من ${toArabicDigits(String(IMPORT_TIMEOUT_MS / 1000))} ثوانٍ فأُوقفت.`), IMPORT_TIMEOUT_MS);
    w.onmessage = (ev) => { if (ev.data && ev.data.id === id) done(ev.data); };
    w.onerror = (ev) => { ev.preventDefault(); stop("تعذّرت قراءة الملف."); };
    w.postMessage({ id, file, maxChars: MAX_CHARS });
  });
}

function importNote(text, isError, busy) {
  const n = $("import-note");
  n.replaceChildren();
  n.classList.toggle("error", !!isError);
  if (busy) n.append(el("span", { class: "spinner", "aria-hidden": "true" }));
  if (text) n.append(text);
  if (isError && text) n.scrollIntoView({ block: "nearest", behavior: motion() });
}

function openImport() {
  if (importBusy) return;
  importWorkerReady();     // the worker's script is fetched now, before a file is chosen: nothing is fetched while a file is read
  $("import-file").click();
}

async function onImportChosen(e) {
  const input = e.target;
  const file = input.files && input.files[0];
  if (!file || importBusy) { input.value = ""; return; }
  hideImportAsk(false);
  if (file.size > IMPORT_MAX_BYTES) { input.value = ""; importNote("حجم الملف أكبر من ٥ ميغابايت. لم يتغيّر شيء في المحرر.", true); return; }
  importBusy = true;
  $("import-btn").setAttribute("aria-busy", "true");
  importNote("جارٍ قراءة الملف في متصفحك…", false, true);
  let res;
  try { res = await extractFile(file); } finally { importBusy = false; input.value = ""; $("import-btn").removeAttribute("aria-busy"); }
  if (!res.ok) { importNote(`${res.message} لم يتغيّر شيء في المحرر.`, true); return; }
  importNote("");
  if (editor().value.trim()) askReplace(file.name, res);
  else applyImport(res);
}

function askReplace(name, res) {
  importPending = { name, res };
  $("import-ask-text").textContent = `في المحرر نص الآن${lastResult ? " ومعه نتيجة تدقيق وقراراتك" : ""}. أتستبدل به نص الملف «\u2068${name}\u2069» (${arabicCount(res.chars)} حرف)؟`;
  $("import-ask").hidden = false;
  $("import-ask-text").focus({ preventScroll: true });
  $("import-ask").scrollIntoView({ block: "nearest", behavior: motion() });
}

function hideImportAsk(focusButton) {
  importPending = null;
  $("import-ask").hidden = true;
  if (focusButton) $("import-btn").focus();
}

function applyImport(res) {
  window.QQASuggest?.hide();
  setEditorText(res.text);
  importNotice = { gen: docGen, text: res.notice };
  showDraftBanner();
  setStatus(res.notice);
  const ta = editor();
  ta.focus({ preventScroll: true });
  ta.setSelectionRange(0, 0);
  $("status").scrollIntoView({ block: "nearest", behavior: motion() });
}

function setStatus(text, isError, busy, retry) {
  const s = $("status");
  s.replaceChildren();
  s.classList.toggle("error", !!isError);
  if (busy) s.append(el("span", { class: "spinner", "aria-hidden": "true" }));
  if (text) s.append(text);
  if (retry) s.append(" ", el("button", { type: "button", class: "btn small", onclick: retry, text: "أعد المحاولة" }));
  // an error must be seen: the status sits beside the toolbar, which a long article may have scrolled away
  if (isError && text) s.scrollIntoView({ block: "nearest", behavior: motion() });
}

// ---- editing after an audit: every edit moves the findings, and the ones it touched are stale
function dropDecisionsOf(f, why) {
  let n = 0;
  for (const c of f.changes || []) if (decisions[c.id]) { delete decisions[c.id]; n++; }
  if (dismissed[f.id]) { delete dismissed[f.id]; n++; }
  if (reviewed[f.id]) { delete reviewed[f.id]; n++; }
  if (n) invalidated.push({ quote: f.quote, count: n, why });
}

function trackEdit(edit) {
  const moved = W.applyEdit(allFindings(), edit, lastArticle);
  for (const f of [...moved.touched, ...moved.removed]) dropDecisionsOf(f, "edited");
  lastResult.findings = moved.findings;
  lastResult.stats = computeStats(moved.findings);
  return moved.touched.length + moved.removed.length;
}

let derivedTimer = null;
// The final text, the bar and the saved session are derived from the editor; they are brought up to date shortly after typing stops,
// and at once before anything leaves the page (copy, print).
function flushDerived() {
  clearTimeout(derivedTimer);
  if (lastResult) { renderFinal(); renderDock(); }
  saveSession();
}
function refreshDerived() {
  clearTimeout(derivedTimer);
  derivedTimer = setTimeout(flushDerived, 250);
}

function onEditorInput() {
  const ta = editor();
  const value = normalizeNl(ta.value);
  if (value === lastArticle) return;
  const caret = W.unitToCp(ta.value, ta.selectionEnd);
  const edit = W.diffEdit(lastArticle, value, caret, lastSel);
  lastSel = null;
  const prevStale = staleList().length;
  setArticleText(value);
  let touched = 0;
  if (lastResult && edit) touched = trackEdit(edit);
  syncEditorHeight();
  renderBackdrop();
  updateCount();
  if (lastResult && (touched || staleList().length !== prevStale)) { renderVerdict(lastResult); renderPanel(); }
  refreshDerived();
  autosaveDraft();
}

// ---- the audit (first audit and every recheck)
async function runAudit() {
  const sent = normalizeNl(editor().value);
  if (!sent.trim()) { setStatus("ألصق نص المقال أولًا.", true); return; }
  if (cpCount(sent) > MAX_CHARS) { setStatus(`النص أطول من الحد المسموح (${arabicCount(MAX_CHARS)} حرف).`, true); return; }
  if (recheckBusy) return;
  const recheck = !!lastResult;
  const gen = docGen;
  recheckBusy = true;
  const btn = $("audit-btn");
  btn.textContent = "جارٍ التدقيق…";
  updateCount();
  setStatus(recheck ? "جارٍ إعادة التدقيق على نصّك الحالي…" : "جارٍ التدقيق ومقارنة الاقتباسات بنص المصحف…", false, true);
  // The free host sleeps when idle and needs up to a minute to wake: say so instead of leaving a spinner.
  // A long article also takes time on its own: about 16 s for 17,500 characters on the free host (measured), besides any waking up.
  const longText = cpCount(sent) > 8000;
  const slow1 = setTimeout(() => gen === docGen && setStatus(longText
    ? `المقال طويل (${arabicCount(cpCount(sent))} حرف)، فيستغرق تدقيقه على الخادم المجاني عشرات الثواني، وأكثر إن كان الخادم نائمًا. لا تغلق الصفحة، ومقالك محفوظ في المربع.`
    : "ما زال التدقيق جاريًا. الخادم المجاني يستيقظ بعد خمول وقد يستغرق نحو دقيقة؛ لا تغلق الصفحة، ومقالك محفوظ في المربع.", false, true), 7000);
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 100000);
  try {
    const res = await fetch("/api/audit", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ article: sent }),
      signal: ctrl.signal,
    });
    let data;
    try { data = await res.json(); } catch { data = { error: "استجابة غير متوقعة من الخادم." }; }
    if (gen !== docGen) { setStatus(docNote()); return; }   // «مسح», a sample or a restored draft replaced the document while this audit ran: its answer describes text that is gone
    if (!res.ok) { setStatus(data.error || "تعذّر إكمال التدقيق.", true, false, res.status >= 500 || res.status === 429 ? runAudit : null); return; }

    // The result describes `sent`. If the writer kept typing while the audit ran, move it through those edits first.
    data.findings = data.findings.map((f) => W.withZone(f, sent));
    const now = normalizeNl(editor().value);
    let movedMeanwhile = 0;
    if (now !== sent) {
      const moved = W.applyEdit(data.findings, W.diffEdit(sent, now), now);
      movedMeanwhile = moved.touched.length + moved.removed.length;
      data.findings = moved.findings;
    }
    if (now !== lastArticle) setArticleText(now);
    const anchor = findingById(current)?.start;
    if (recheck) {
      const out = W.carry({ findings: allFindings(), decisions, dismissed, reviewed }, data.findings);
      data.findings = out.findings;
      decisions = out.decisions; dismissed = out.dismissed; reviewed = out.reviewed;
      carryNote = out.report;
    } else {
      decisions = {}; dismissed = {}; reviewed = {}; invalidated = []; carryNote = null;
      baseText = sent;
      isDemo = demoText !== null && sent === demoText;
    }
    data.stats = computeStats(data.findings);
    lastResult = data;
    auditedText = sent;
    lastAction = null; cardError = null; pendingSel = null;
    auditedAt = Date.now() / 1000;
    const keep = anchor !== undefined ? allFindings().find((f) => f.start <= anchor && anchor <= f.end) : null;
    current = (keep || orderedPending()[0] || activeFindings()[0] || {}).id ?? null;
    saveSession();
    render(!recheck);
    loadHealth();  // refresh the banner with this call's real outcome
    setStatus("");
    if (recheck) {
      const lost = invalidated.reduce((a, x) => a + x.count, 0);
      const dropped = lost + carryNote.reset.length;
      const parts = [
        carryNote.carried ? `حُفظ ${toArabicDigits(carryNote.carried)} من قراراتك لاقتباسات لم يتغيّر نصها` : null,
        dropped ? `سقط ${toArabicDigits(dropped)} لأن النص تغيّر` : null,
        movedMeanwhile ? `عدّلتَ ${countAr(movedMeanwhile, "موضعًا واحدًا", "موضعين", "مواضع", "موضعًا")} أثناء التدقيق فأعد التدقيق مرة أخرى` : null,
      ].filter(Boolean);
      const msg = `أُعيد التدقيق على نصّك الحالي${parts.length ? ". " + parts.join("، ") : ""}.`;
      notify(msg, null);
      announce(msg);
      invalidated = [];
    } else {
      const v = verdictText(data);
      announce(`اكتمل التدقيق. ${v.headline}.${v.maybe ? " " + v.maybe : ""}`);
    }
  } catch (e) {
    setStatus(e.name === "AbortError" ? "انتهت مهلة الطلب. مقالك ما زال في المربع." : "تعذّر الاتصال بالخادم. مقالك ما زال في المربع.", true, false, runAudit);
  } finally {
    clearTimeout(slow1);
    clearTimeout(timer);
    recheckBusy = false;
    btn.textContent = lastResult ? "أعد التدقيق" : "دقّق الاقتباسات";
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
  // information that asks nothing of the writer (what the model did, short common phrases left unlisted) is one click away
  const details = (data.notices || []).filter((n) => n.level === "info" && !(ai.outcome === "skipped_length" && /أطول من \d+ حرف/.test(n.text))
      && !(ai.outcome === "skipped_cooldown" && /لم يُسأل الذكاء الاصطناعي/.test(n.text)))   // said by the line itself
    .map((n) => el("p", { text: noticeText(n.text) }));
  let line = null, tone = "plain";
  if (data.mode === "reduced" && ai.outcome === "skipped_length") {
    tone = "limited";
    line = `المقال أطول من ${arabicCount(AI_MAX_CHARS)} حرف، فلم يُسأل النموذج اللغوي. فُحص كله بالعلامات وبالبحث في المصحف، وقد تفوت عبارة قصيرة بلا علامات؛ حدّدها في المقال لتفحصها.`;
  } else if (ai.outcome === "skipped_cooldown") {
    // no request was made in this audit: an earlier call failed moments ago and the server is waiting before it asks again
    tone = "limited";
    line = "لم يُسأل النموذج اللغوي هذه المرة لأنه تعذّر قبل قليل. فُحص المقال بالعلامات وبالبحث في المصحف، وقد تفوت عبارة قصيرة بلا علامات؛ حدّدها في المقال لتفحصها.";
    if (ai.cooldown_seconds) details.push(el("p", { text: `يُسأل النموذج من جديد بعد نحو ${toArabicDigits(ai.cooldown_seconds)} ث؛ أعد التدقيق بعدها إن شئت.` }));
  } else if (data.mode === "reduced") {
    tone = "limited";
    line = "دون ذكاء اصطناعي: قد تفوت عبارة قصيرة بلا علامات؛ حدّدها في المقال لتفحصها.";
  } else if (data.mode === "ai_failed") {
    tone = "limited";
    line = "تعذّر اقتراح الذكاء الاصطناعي هذه المرة. فُحص المقال بالعلامات وبالبحث في المصحف، وقد تفوت عبارة قصيرة بلا علامات؛ حدّدها في المقال لتفحصها، أو أعد التدقيق لاحقًا.";
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
  $("intro").classList.add("audited");   // the introduction shrinks to its title once there is work to review
  $("legend").hidden = false;
  const data = lastResult;
  const notices = $("notices");
  notices.replaceChildren(...(data.notices || []).filter((n) => n.level !== "info" && !isModelNote(n)).map((n) => el("div", { class: `notice ${n.level}`, text: noticeText(n.text) })));
  const meta = auditMeta(data);
  if (meta) notices.append(meta);
  renderVerdict(data);
  renderBackdrop();
  renderPanel();
  renderFinal();
  renderDock();
  syncEditorHeight();
  updateCount();
  if (scroll) goToFirstReview();
  updateFinalInView();   // the layout changed without a scroll: the bar must not keep the old answer
}

// «وجدنا ٤ اقتباسات؛ يحتاج اثنان إلى قرارك»: the counted noun and the verb agree with the number.
function verdictText(data) {
  const all = (data.findings || []).filter((f) => !dismissed[f.id]);
  // a phrase that may be a quotation (an exact but common phrase, unconfirmed) is said apart, never counted as a quotation found
  const maybe = all.filter((f) => !f.stale && weakPending(f)).length;
  const fs = all.filter((f) => f.stale || !weakPending(f));
  const total = fs.length, n = fs.filter((f) => f.needs_review || f.stale).length;
  const found = total === 1 ? "وجدنا اقتباسًا واحدًا" : total === 2 ? "وجدنا اقتباسين" : `وجدنا ${toArabicDigits(total)} ${total <= 10 ? "اقتباسات" : "اقتباسًا"}`;
  const also = maybe ? countAr(maybe, "وعبارة واحدة تشبه آية ولم نتأكد أنها اقتباس؛ تأكيدها اختياري.", "وعبارتان تشبهان آيتين ولم نتأكد أنهما اقتباسان؛ تأكيدهما اختياري.",
    "عبارات تشبه آيات ولم نتأكد أنها اقتباسات؛ تأكيدها اختياري.", "عبارة تشبه آيات ولم نتأكد أنها اقتباسات؛ تأكيدها اختياري.") : null;
  const maybeLine = also && maybe > 2 ? `و${also}` : also;
  if (!total && maybe) return { headline: "لم نجد اقتباسًا مؤكدًا في النص", total, needing: 0, maybe: maybeLine.replace(/^و/, "") };
  if (!total) return { headline: "لم نجد اقتباسات قرآنية في النص", total, needing: 0 };
  let tail;
  if (n === 0) tail = total === 1 ? "ولا يحتاج إلى قرارك" : "ولا يحتاج أيٌّ منها إلى قرارك";
  else if (n === total) tail = total === 1 ? "ويحتاج إلى قرارك" : total === 2 ? "يحتاج كلاهما إلى قرارك" : "تحتاج كلها إلى قرارك";
  else tail = n === 1 ? "يحتاج واحد منها إلى قرارك" : n === 2 ? "يحتاج اثنان إلى قرارك" : `${n <= 10 ? "تحتاج" : "يحتاج"} ${toArabicDigits(n)} منها إلى قرارك`;
  return { headline: tail.startsWith("و") ? `${found} ${tail}` : `${found}؛ ${tail}`, total, needing: n, maybe: maybeLine };
}

function renderVerdict(data) {
  const v = verdictText(data);
  const box = $("verdict");
  box.className = `verdict ${v.needing || v.maybe ? "has-review" : "clear"}`;
  box.replaceChildren(...[
    el("h2", { id: "verdict-title", tabindex: "-1", text: v.headline }),
    v.maybe ? el("p", { class: "verdict-maybe", text: v.maybe }) : null,
    el("p", { class: "verdict-sub", text: "فحص للاقتباسات المرصودة، وليس حكمًا على المقال كله." + (edited() ? " النص تغيّر بعد هذا التدقيق." : "") }),
    !v.total && !v.maybe ? el("p", { class: "verdict-sub", text: "إن كان في مقالك آية لم نرصدها، حدّدها في المقال ثم اضغط «افحص المحدَّد»." }) : null,
    isDemo ? el("p", { class: "verdict-demo", text: DEMO_NOTE }) : null,
  ].filter(Boolean));
}

// The first quotation that needs the writer: the verdict and the decision stay on one screen.
async function goToFirstReview() {
  void document.body.offsetHeight;
  try { await document.fonts.ready; } catch { /* no font loading API: measure now */ }
  syncEditorHeight();
  // wide screens: the verdict, the article and the first decision share the screen; a phone: the decision itself comes first.
  // In a long article the first open quotation may be far below the verdict: then the text scrolls to it, and the card (sticky) stays beside it.
  const m = narrow() ? null : document.querySelector(`#article-view mark[data-id="${CSS.escape(String(current))}"]`);
  const below = m && m.getBoundingClientRect().bottom - $("results").getBoundingClientRect().top > innerHeight - 40;
  if (below) { const top = Math.max(0, scrollY + m.getBoundingClientRect().top - innerHeight * 0.3); window.scrollTo({ top, behavior: motionFor(top - scrollY) }); }
  else scrollToNode(narrow() && !$("panel").hidden ? $("panel") : $("results"));
  const card = $("current").firstElementChild;
  if (card) card.focus({ preventScroll: true });
}

// ---------------------------------------------------------------- the editor: the writer's own text, with the quotations marked behind it
// A highlight layer sits exactly behind the textarea (same font, padding and wrapping, transparent text), so the writer edits a plain
// textarea with its native Arabic caret, selection and undo, and sees the marks without any contenteditable machinery.
// An approved correction is not written into the box (the box keeps the writer's own text, which undo, edit tracking and the recheck rely on).
// It is drawn the way a proofreader marks a page: the writer's words that change are struck through (red, as «قبل» elsewhere), and the
// source's text stands small above where the change starts; the copied text carries the change. The labels lie in their own layer under the
// textarea, so the writer's text is always drawn over them, and each is kept inside the box (cut with «…» only if wider than the box).
function fixLabel(c) {
  const d = deltaParts(c);
  return `${c.start === c.end ? "+ " : ""}${d.prefix}${d.after}`;   // a word to add is drawn at its place, marked «+»
}
// the same order as revision.js's plan(), so that of two overlapping changes the box draws the one the copy applies
const approvedFixes = () => approvedRows().map(({ c }) => c).filter((c) => !c.optional).sort((a, b) => a.start - b.start || a.end - b.end);
// The writer's words in [c.start, c.end) that the change replaces: those not kept in a longest common run of words with the replacement
// («ولا تكن في ضيق مما يكيدون» → «ولا تك في ضيق مما يمكرون» strikes «تكن» and «يكيدون», not the words that stay). All of it if none differs.
function changedWords(c) {
  const toks = [];
  for (let i = c.start; i < c.end;) {
    while (i < c.end && isSpace(ART[i])) i++;
    const s = i;
    while (i < c.end && !isSpace(ART[i])) i++;
    if (i > s) toks.push({ s, e: i, w: cpSlice(s, i), kept: false });
  }
  const rep = toArabicDigits(c.replacement || "").trim().split(/\s+/).filter(Boolean);
  const n = toks.length, m = rep.length;
  const L = Array.from({ length: n + 1 }, () => new Array(m + 1).fill(0));
  for (let i = n - 1; i >= 0; i--) for (let j = m - 1; j >= 0; j--) L[i][j] = toArabicDigits(toks[i].w) === rep[j] ? L[i + 1][j + 1] + 1 : Math.max(L[i + 1][j], L[i][j + 1]);
  for (let i = 0, j = 0; i < n && j < m;) {
    if (toArabicDigits(toks[i].w) === rep[j]) { toks[i].kept = true; i++; j++; } else if (L[i + 1][j] >= L[i][j + 1]) i++; else j++;
  }
  const out = toks.filter((t) => !t.kept);
  if (!out.length && m > toks.length) return [];   // only words added: nothing of the writer's goes, nothing is struck
  return out.length ? out : toks;
}
function fixSpan(c) {
  if (c.start === c.end) return el("span", { class: "fix add" });   // an insertion adds no character
  const kids = [];
  let p = c.start;
  for (const t of changedWords(c)) {
    if (t.s > p) kids.push(cpSlice(p, t.s));
    kids.push(el("span", { class: "fix-del" }, cpSlice(t.s, t.e)));
    p = t.e;
  }
  if (p < c.end) kids.push(cpSlice(p, c.end));
  return el("span", { class: "fix" }, kids);
}
// [a, b) of the article as text, with each approved correction that lies wholly inside it wrapped in a .fix span
function withFixes(a, b, fixes) {
  const out = [];
  let p = a;
  for (const c of fixes) {
    if (c.start < p || c.end > b || (c.start === c.end && c.start === b && b < ART.length)) continue;   // an insertion at a boundary belongs to the segment that starts there
    if (c.start > p) out.push(cpSlice(p, c.start));
    const span = fixSpan(c);
    span.dataset.to = fixLabel(c);
    out.push(span);
    p = c.end;
  }
  if (p < b) out.push(cpSlice(p, b));
  return out;
}
function renderBackdrop() {
  const view = $("article-view");
  const fixes = lastResult ? approvedFixes() : [];
  // a drawn correction needs room above its line: the lines open up while one is drawn, and close again when none is (textarea and layer alike)
  if ($("editor").classList.contains("has-fixes") !== fixes.length > 0) { $("editor").classList.toggle("has-fixes", fixes.length > 0); syncEditorHeight(); }
  if (!lastResult) { view.replaceChildren(); return; }
  const kids = [];
  let pos = 0;
  for (const f of [...activeFindings()].sort((a, b) => a.start - b.start)) {
    if (f.start < pos || f.end > ART.length) continue;
    if (f.start > pos) kids.push(...withFixes(pos, f.start, fixes));
    const [, cls] = stateOf(f);
    kids.push(el("mark", { class: `m ${cls} ${String(f.id) === String(current) ? "current" : ""}`, "data-id": f.id }, withFixes(f.start, f.end, fixes)));
    pos = f.end;
  }
  kids.push(...withFixes(pos, ART.length, fixes), "​");
  view.replaceChildren(...kids.map((k) => (typeof k === "string" ? document.createTextNode(k) : k)));
  placeFixLabels();
}
// Each label above the start of its change (the right end of its first line, Arabic running right to left), moved sideways if it would
// cross the box's edge. Its bottom overlaps the top of the line's own type area slightly: the line height leaves the rest of its room.
function placeFixLabels() {
  const view = $("article-view");
  view.querySelector(".fix-layer")?.remove();
  const spans = [...view.querySelectorAll(".fix")];
  if (!spans.length) return;
  const layer = el("div", { class: "fix-layer" });
  const vr = view.getBoundingClientRect();
  const cs = getComputedStyle(view);
  const minX = parseFloat(cs.paddingLeft) / 2, maxX = vr.width - parseFloat(cs.paddingRight) / 2;
  const em = parseFloat(cs.fontSize);
  // reads first (one layout), then writes
  const items = spans.map((s) => { const r = s.getClientRects()[0] || s.getBoundingClientRect(); return { r, label: el("span", { class: "fix-to", text: s.dataset.to }) }; });
  for (const it of items) { it.label.style.maxWidth = `${Math.floor(maxX - minX)}px`; layer.append(it.label); }
  view.append(layer);
  for (const it of items) { it.w = it.label.offsetWidth; it.h = it.label.offsetHeight; }
  // in reading order on each line (right to left): each label starts at its change, inside the box, left of the label before it on that line
  items.sort((a, b) => a.r.top - b.r.top || b.r.right - a.r.right);
  let lineTop = null, floor = maxX;
  for (const it of items) {
    if (lineTop === null || Math.abs(it.r.top - lineTop) > 2) { lineTop = it.r.top; floor = maxX; }
    let right = Math.min(floor, it.r.right - vr.left);
    let w = it.w;
    if (right - w < minX) { if (right - minX >= w || floor === maxX) right = Math.min(floor, minX + w); w = Math.min(w, right - minX); }
    it.left = right - w; it.width = w; floor = it.left - 4;
  }
  for (const it of items) {
    if (it.width < it.w) { it.label.style.maxWidth = `${Math.max(24, Math.floor(it.width))}px`; it.label.classList.add("cut"); }
    it.label.style.left = `${Math.round(it.left)}px`;
    it.label.style.top = `${Math.round(it.r.top - vr.top - it.h + em * 0.22)}px`;
  }
  for (const it of items) if (it.label.scrollWidth > it.label.clientWidth + 1) it.label.classList.add("cut");
}

function markCurrent() {
  document.querySelectorAll("#article-view mark.current").forEach((m) => m.classList.remove("current"));
  document.querySelector(`#article-view mark[data-id="${CSS.escape(String(current))}"]`)?.classList.add("current");
}

// Bring the current quotation into view in the text (and flash it). With `caret`, put the caret at its start so the writer can edit it.
function showInArticle({ caret = false } = {}) {
  const m = document.querySelector(`#article-view mark[data-id="${CSS.escape(String(current))}"]`);
  const f = findingById(current);
  if (!m || !f) return;
  const r = m.getBoundingClientRect();
  const dockH = parseInt(getComputedStyle(document.documentElement).getPropertyValue("--dock-h")) || 0;
  if (r.top < 90 || r.bottom > innerHeight - dockH - 90) { const top = Math.max(0, scrollY + r.top - innerHeight * 0.3); window.scrollTo({ top, behavior: motionFor(top - scrollY) }); }
  m.classList.remove("pulse");
  void m.offsetWidth;
  m.classList.add("pulse");
  if (caret) {
    const ta = editor();
    const u = W.cpToUnit(ta.value, f.start);
    ta.focus({ preventScroll: true });
    ta.setSelectionRange(u, u);
  }
}

// The selection in the editor: a code-point range, trimmed to its words.
function readSelection() {
  const ta = editor();
  if (ta.selectionStart === ta.selectionEnd) return null;
  let a = W.unitToCp(ta.value, ta.selectionStart), b = W.unitToCp(ta.value, ta.selectionEnd);
  while (a < b && isSpace(ART[a])) a++;
  while (b > a && isSpace(ART[b - 1])) b--;
  return b > a ? { start: a, end: b } : null;
}
function updateSelectionBar() {
  const sel = document.activeElement === editor() || document.activeElement?.closest?.("#sel-bar") ? readSelection() : null;
  if (sel) pendingSel = sel;
  else if (!document.activeElement?.closest?.("#sel-bar")) pendingSel = null;
  const bar = $("sel-bar");
  bar.hidden = !pendingSel;
  $("phrase-btn").hidden = !lastResult;
  document.documentElement.classList.toggle("has-sel-bar", !!pendingSel);
  if (pendingSel) $("sel-text").textContent = `حدّدتَ: «${excerpt(cpSlice(pendingSel.start, pendingSel.end))}»`;
}

// Which quotation is the caret in? Moving the caret into a highlight opens its card beside the text, without moving the writer's focus.
let caretId = null;
function caretFinding() {
  const ta = editor();
  if (!lastResult || ta.selectionStart !== ta.selectionEnd) return null;
  const pos = W.unitToCp(ta.value, ta.selectionStart);
  return activeFindings().find((f) => pos >= f.start && pos < f.end) || null;
}
let lastCaretSig = "";
function onCaretMoved() {
  const ta = editor();
  if (document.activeElement !== ta) return;
  const sig = `${ta.selectionStart}-${ta.selectionEnd}-${lastArticle.length}`;
  if (sig === lastCaretSig) return;
  lastCaretSig = sig;
  updateSelectionBar();
  const f = caretFinding();
  const id = f ? f.id : null;
  if (id !== caretId) {
    caretId = id; renderDock();
    const fx = f ? requiredOf(f).filter((c) => decisions[c.id] === "approved").map((c) => `«${fixLabel(c)}»`) : [];
    if (f) announce(`داخل ${itemName(f)} ${toArabicDigits(f.id)} من ${toArabicDigits(allFindings().length)}: ${stateOf(f)[0]}${fx.length ? `؛ يُكتب ${fx.join(" و")} في النسخة التي تنسخها، ونصّك هنا كما كتبتَه` : ""}. القرار في اللوحة المجاورة.`);   // the marks are drawn behind the text and are not read by a screen reader
  }
  if (f && String(f.id) !== String(current)) goTo(f.id, { scroll: null, focus: false, quiet: true });
}


// ---------------------------------------------------------------- the decision panel
// Move to a finding: the card, the row and the mark follow it. `scroll`: "panel" (bring the card into view), "article" (show it in the text).
function goTo(id, { scroll = "panel", focus = true, keepError = false, quiet = false } = {}) {
  current = id;
  if (!keepError) cardError = null;
  saveSession();
  renderPanel();
  markCurrent();
  renderDock();
  const card = $("current").firstElementChild;
  if (!quiet && scroll === "panel") {
    if (!narrow()) showInArticle();
    if (card) {
      const top = card.getBoundingClientRect().top;
      if (narrow() || top < 0 || top > innerHeight * 0.6) scrollToNode($("panel"));
    }
  }
  if (focus && card) card.focus({ preventScroll: true });
  const f = findingById(id);
  if (f && !quiet) announce(`${itemName(f)} ${toArabicDigits(f.id)} من ${toArabicDigits(allFindings().length)}: ${stateOf(f)[0]}`);
}

// The next quotation after `fromId` that still waits for the writer (wrapping round), in the order of the article: the concrete decisions
// first, and the phrases that may be quotations («عبارات للتأكيد») once none of those is left.
function nextPending(fromId, dir = 1) {
  const fs = activeFindings();
  if (!fs.length) return null;
  const want = mainPendingList().length ? (f) => pendingKind(f) && !weakPending(f) : (f) => pendingKind(f);
  const i = fs.findIndex((f) => String(f.id) === String(fromId));
  for (let k = 1; k <= fs.length; k++) {
    const f = fs[((i < 0 ? (dir > 0 ? -1 : 0) : i) + dir * k + fs.length * 2) % fs.length];
    if (want(f)) return f.id;
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
  renderBackdrop();
  renderFinal();
  const nxt = pendingKind(f) ? null : nextPending(f.id);
  if (nxt !== null) goTo(nxt, { scroll: "panel" });
  else { renderAll(); if (!pendingList().length) $("current").firstElementChild?.focus({ preventScroll: true }); }
}

function renderAll() {
  if (lastResult) renderVerdict(lastResult);   // the headline counts the phrases to confirm, which a decision can settle
  renderBackdrop();
  renderPanel();
  renderFinal();
  renderDock();
  updateFinalInView();
}

function setDecision(id, value) {
  const f = activeFindings().find((x) => (x.changes || []).some((c) => c.id === id));
  const c = f.changes.find((x) => x.id === id);
  const before = decisions[id];
  if (decisions[id] === value) delete decisions[id];
  else decisions[id] = value;
  // the text, the marks and the final review follow the decision back (goTo alone redraws only the panel)
  const undo = () => { if (before) decisions[id] = before; else delete decisions[id]; saveSession(); renderAll(); goTo(f.id, { scroll: "panel" }); };
  if (c.optional) { saveSession(); renderAll(); return; }
  const d = deltaParts(c);
  const msg = decisions[id] === "approved" ? `اعتمدتَ «${d.prefix}${d.after}» مكان «${d.prefix}${d.before}» (الاقتباس ${toArabicDigits(f.id)}) في النسخة التي تنسخها؛ نصّك في المربع لم يُمحَ.`
    : decisions[id] === "rejected" ? `أبقيتَ «${d.prefix}${d.before}» كما كتبتَه (الاقتباس ${toArabicDigits(f.id)}).`
    : `ألغيتَ قرارك في الاقتباس ${toArabicDigits(f.id)}.`;
  afterDecision(f, msg, undo);
}

// «تراجع عنه» in the final review: the approval goes, the writer stays where they are (the next item of the list, or its heading)
function undoApproval(f, c) {
  const d = deltaParts(c);
  const idx = [...document.querySelectorAll('#final-changes [data-act="undo-approval"]')].findIndex((b) => b.dataset.change === c.id);
  delete decisions[c.id];
  saveSession();
  renderAll();
  // an addition (nothing written there) is not copied as anything: it is simply not added. The undo line is a live region: it is read once.
  notify(c.start === c.end || !c.original ? `تراجعتَ عن إضافة «${d.prefix}${d.after}» (الاقتباس ${toArabicDigits(f.id)})؛ لن تُضاف إلى النسخة المنسوخة.`
    : `تراجعتَ عن اعتماد «${d.prefix}${d.after}» (الاقتباس ${toArabicDigits(f.id)})؛ سيُنسخ «${d.prefix}${d.before}» كما كتبتَه.`, () => { decisions[c.id] = "approved"; saveSession(); renderAll(); });
  const left = [...document.querySelectorAll('#final-changes [data-act="undo-approval"]')];
  const next = left[Math.min(Math.max(idx, 0), left.length - 1)];
  if (next) { next.focus({ preventScroll: true }); next.scrollIntoView({ block: "nearest" }); } else $("final-title").focus({ preventScroll: true });
}

function dismiss(f, on = true) {
  if (on) dismissed[f.id] = true; else delete dismissed[f.id];
  saveSession();
  renderVerdict(lastResult); renderBackdrop(); renderFinal(); renderDock();   // the headline counts what is dismissed
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
  const hasAny = allFindings().length > 0 && !!lastResult;
  $("workbench").classList.toggle("no-panel", !hasAny);
  $("panel").hidden = !hasAny;
  if (!hasAny) return;
  const pend = pendingList();
  if (!fs.some((f) => String(f.id) === String(current))) current = (pend[0] || fs[0] || {}).id ?? null;
  const f = fs.find((x) => String(x.id) === String(current)) || null;
  const idx = f ? fs.indexOf(f) + 1 : 0;
  $("panel-title").textContent = f && pendingKind(f) ? "قرارك الآن" : pend.length ? "مراجعة اقتباس" : "اكتملت قراراتك";
  $("panel-progress").replaceChildren(el("b", { text: openText() }), f ? ` — ${toArabicDigits(idx)} من ${toArabicDigits(fs.length)}` : "");   // not «·»: beside an Arabic digit it reads as a zero («· ٣» looks like «٣٠»)
  const nx = nextPending(current);
  $("panel-nav").hidden = nx === null || String(nx) === String(current);   // shown only when it leads to another quotation
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
  scrollToNode($("final"));
  $("final-title").focus({ preventScroll: true });
}

let maybeOpen = null;   // the writer's own choice for the optional group, once they open or close it
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
  const group = (title, items, open, cls) => (items.length ? el("details", { class: `q-group ${cls}`, open: open ? "" : null, ontoggle: cls === "maybe" ? (e) => { if (e.isTrusted) maybeOpen = e.currentTarget.open; } : null },
    el("summary", {}, `${title} (${toArabicDigits(items.length)})`), el("ul", {}, items.map(row))) : null);
  const stale = fs.filter((f) => f.stale);
  const pend = fs.filter((f) => !f.stale && !dismissed[f.id] && pendingKind(f) && !weakPending(f));
  const maybe = fs.filter((f) => !f.stale && !dismissed[f.id] && weakPending(f));
  const done = fs.filter((f) => !f.stale && !dismissed[f.id] && !pendingKind(f));
  const off = fs.filter((f) => dismissed[f.id]);
  $("queue").replaceChildren(...[
    group("عُدّلت بعد التدقيق", stale, true, "stale"),
    group("تنتظر قرارك", pend, true, "need"),
    // closed while decisions wait (they are not one of them), unless it holds the open card or the writer opened it
    group("عبارات للتأكيد (اختياري): قد تكون اقتباسات", maybe, maybeOpen ?? (pend.length === 0 || maybe.some((f) => String(f.id) === String(current))), "maybe"),
    group("تمت مراجعتها", done, pend.length === 0 || done.length <= 3, "done"),
    group("استبعدتَها", off, true, "off"),
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
      el("h3", { id: `fh-${f.id}`, text: `${itemName(f)} ${toArabicDigits(f.id)}` }),   // a phrase not yet confirmed is not called a quotation
      el("span", { class: "f-where", text: whereText(f) }),
      el("span", { class: `state ${cls}`, text: label })),
    el("div", { class: "f-ctx" }, el("span", { class: "row-label", text: "في مقالك" }), contextView(f),
      el("button", { type: "button", class: "link-btn show-in-article", onclick: () => showInArticle({ caret: true }), text: "اذهب إليه في المقال لتحرّره" })));
  if (cardError) card.append(el("p", { class: "card-error", role: "alert", text: cardError }));
  if (kind === "stale") { card.append(staleBlock(f)); return card; }
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

// A quotation the writer edited after the audit: the old verdict and the old decisions no longer describe this text.
function staleBlock(f) {
  return el("div", { class: "ask stale-block" },
    el("p", { class: "q-title", text: "عدّلتَ هذا الموضع بعد التدقيق" }),
    el("p", { text: "سقط قرارك السابق فيه ونتيجة الفحص القديمة، لأننا لا نربط قرارًا قديمًا بنص تغيّر. أعد التدقيق ليُفحص النص كما هو الآن." }),
    el("div", { class: "actions-row" },
      el("button", { type: "button", class: "btn approve", "data-act": "recheck", onclick: runAudit, text: "أعد التدقيق الآن" }),
      el("button", { type: "button", class: "btn", "data-act": "forget-stale", onclick: () => forgetStale(f), text: "تجاهل هذا الموضع" })),
    el("p", { class: "muted small", text: "«تجاهل» يزيل العلامة فقط من القائمة؛ لا يغيّر نصك." }));
}
function forgetStale(f) {
  lastResult.findings = allFindings().filter((g) => g !== f);
  lastResult.stats = computeStats(lastResult.findings);
  if (String(current) === String(f.id)) current = (orderedPending()[0] || activeFindings()[0] || {}).id ?? null;
  saveSession();
  renderVerdict(lastResult); renderAll(); updateCount();
  notify(`أزلتَ علامة الموضع «${excerpt(f.quote)}» من القائمة.`, null);
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
  const firstFix = !decisions[c.id] && !approvedFixes().length;
  const [yes, no] = short ? [`غيّر إلى «${d.prefix}${d.after}»`, `أبقِ «${d.prefix}${d.before}»`] : ["اعتمد هذا التغيير", "أبقِ ما كتبتُه"];
  // One concise warning stays beside the decision. The complete list remains
  // in the expanded evidence section below the card.
  const warns = (f.review_reasons || []).filter((x) => x !== c.reason).slice(0, 1);
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
      el("button", { type: "button", class: "btn approve", "data-act": "approved", "aria-pressed": String(decisions[c.id] === "approved"), "aria-describedby": firstFix ? `fx-${c.id}` : null, onclick: () => setDecision(c.id, "approved"), text: yes }),
      el("button", { type: "button", class: "btn reject", "data-act": "rejected", "aria-pressed": String(decisions[c.id] === "rejected"), onclick: () => setDecision(c.id, "rejected"), text: no })),
    // until the writer has approved one correction, say where it goes: the box keeps their text
    firstFix ? el("p", { class: "fix-note", id: `fx-${c.id}` }, "عند الاعتماد يبقى نصّك في المربع ويظهر ", el("b", { text: `«${d.prefix}${d.after}»` }), " فوقه، ويُكتب مكانه في النسخة التي تنسخها.") : null,
    // once approved: which text is the writer's, which is copied, and how to take it back
    decisions[c.id] === "approved" ? el("p", { class: "fix-note" }, "اعتمدتَه: يُكتب ", el("b", { text: `«${d.prefix}${d.after}»` }),
      c.start === c.end ? " في النسخة المنسوخة، ونصّك في المربع كما هو." : " في النسخة المنسوخة، ونصّك في المربع باقٍ تحته مشطوبًا.", " للتراجع اضغط زر الاعتماد أعلاه مرة أخرى.") : null,
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
  if (isWeak(f)) box.append(el("p", { class: "weak-note", text: "عبارة شائعة توافق لفظ آية، وقد تكون كلامًا عاديًا. أكّدها إن قصدتَ الآية؛ وإن تركتها نُسخت كما كتبتَها." }));
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
  // Where the writer is now. If they open another quotation while the request runs,
  // the answer updates its own finding but does not pull them away from that card.
  const startedOn = String(current);
  const gen = docGen, sentText = lastArticle;
  cardError = null;
  const card = $("current").firstElementChild;
  // disabling the focused button would drop keyboard focus to the page: it waits on the card itself until the answer comes
  const hadFocus = !!card && card.contains(document.activeElement);
  if (hadFocus) card.focus({ preventScroll: true });
  card?.setAttribute("aria-busy", "true");
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
    if (gen !== docGen || !lastResult) { setStatus(docNote()); return; }   // the writer cleared or replaced the document meanwhile
    if (lastArticle !== sentText) {
      // the offsets in the answer are for the text that was sent; the text has been edited since, so the answer is not applied
      setStatus("تغيّر النص أثناء الفحص فلم يُطبَّق الجواب. أعد الفحص على النص الحالي.", true);
      renderPanel();
      if (hadFocus) $("current").firstElementChild?.focus({ preventScroll: true });
      return;
    }
    if (!res.ok) {
      const message = data.error || "تعذّر فحص المقطع.";
      setStatus("");
      if (String(current) === startedOn) { cardError = message; goTo(findingId, { scroll: null, focus: hadFocus, keepError: true }); }
      else setStatus(`تعذّر فحص الاقتباس ${toArabicDigits(findingId)}: ${message}`, true);
      return;
    }
    setStatus("");
    // The writer may have opened another quotation while this network request
    // was running. Update the result without pulling them back to the old card.
    applyPhrase(data.finding, why, f, String(current) === startedOn ? null : current);
  } catch {
    setStatus("");
    if (gen !== docGen || !lastResult) return;
    const message = "تعذّر الاتصال بالخادم. لم يتغيّر شيء؛ حاول مرة أخرى.";
    if (String(current) === startedOn) { cardError = message; goTo(findingId, { scroll: null, focus: hadFocus, keepError: true }); }
    else setStatus(`تعذّر فحص الاقتباس ${toArabicDigits(findingId)}: ${message}`, true);
  }
}

function applyPhrase(nf, why, previous, preserveId = null) {
  nf = W.withZone(nf, lastArticle);
  const overlapped = allFindings().filter((g) => g.start < nf.end && nf.start < g.end);
  const priorState = overlapped.map((g) => ({ f: g, d: dismissed[g.id], r: reviewed[g.id], ch: Object.fromEntries((g.changes || []).map((c) => [c.id, decisions[c.id]]).filter(([, v]) => v)) }));
  for (const old of overlapped) { for (const c of old.changes || []) delete decisions[c.id]; delete dismissed[old.id]; delete reviewed[old.id]; }
  lastResult.findings = [...allFindings().filter((g) => !overlapped.includes(g)), nf].sort((a, b) => a.start - b.start);
  lastResult.stats = computeStats(allFindings());
  const keepViewing = preserveId && allFindings().some((g) => String(g.id) === String(preserveId)) ? preserveId : null;
  current = keepViewing ?? nf.id;
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
  goTo(current, { scroll: keepViewing ? null : "panel" });
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
  pendingSel = null;
  const ta = editor();
  const u = W.cpToUnit(ta.value, sel.end);
  ta.setSelectionRange(u, u);
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
    rows.length ? `سيُنسخ مقالك بعد ${countAr(rows.length, "تغيير واحد اعتمدتَه", "تغييرين اعتمدتَهما", "تغييرات اعتمدتَها", "تغييرًا اعتمدتَها")}` : "لم تعتمد أي تغيير؛ سيُنسخ مقالك كما كتبتَه",
    left ? `وأبقيتَ ${countAr(left, "موضعًا واحدًا كما كتبتَه", "موضعين كما كتبتَهما", "مواضع كما كتبتَها", "موضعًا كما كتبتَها")}` : null,
    off ? `واستبعدتَ ${countAr(off, "مقطعًا واحدًا ليس اقتباسًا", "مقطعين ليسا اقتباسين", "مقاطع ليست اقتباسات", "مقطعًا ليست اقتباسات")}` : null,
  ].filter(Boolean).join("، ") + ".";
  const staleN = staleList().length;
  $("final-summary").replaceChildren(...[
    el("p", { class: "final-sentence", text: sentence }),
    edited() ? el("p", { class: "final-sentence final-stale", text: `عدّلتَ المقال بعد آخر تدقيق، والنص أدناه هو نصّك الحالي.${staleN ? ` ${countAr(staleN, "موضع مرصود واحد مسّه تعديلك وسقط قراره", "موضعان مرصودان مسّهما تعديلك وسقط قراراهما", "مواضع مرصودة مسّها تعديلك وسقطت قراراتها", "موضعًا مرصودًا مسّها تعديلك وسقطت قراراتها")}.` : ""} ما كتبتَه بعد التدقيق لم يُفحص؛ اضغط «أعد التدقيق» قبل النسخ إن أردت فحصه.` }) : null,
  ].filter(Boolean));

  fill($("final-changes"), rows.length ? el("div", {}, el("h3", { text: "التغييرات التي ستظهر في النص" }),
    el("ul", { class: "change-list" }, rows.map(({ f, c }) => el("li", {}, el("div", { class: "cl-head" },
      el("b", { text: `الاقتباس ${toArabicDigits(f.id)} — ${whereText(f)}` }),
      el("span", { class: "cl-acts" },
        el("button", { type: "button", class: "link-btn", onclick: () => goTo(f.id, { scroll: "panel" }), text: "افتحه" }),
        el("button", { type: "button", class: "link-btn", "data-act": "undo-approval", "data-change": c.id, "aria-label": `تراجع عن اعتماد «${deltaParts(c).prefix}${deltaParts(c).after}» في الاقتباس ${toArabicDigits(f.id)}`, onclick: () => undoApproval(f, c), text: "تراجع عنه" }))), changeContext(f, c))))) : null);

  const open = [...new Map([...pend, ...unresolved].map((f) => [f.id, f])).values()].sort((a, b) => a.start - b.start);
  fill($("final-pending"), open.length ? el("div", { class: "open-box" },
    el("h3", { text: pend.length ? `${openText()} — وسيبقى كما كتبتَه إن لم تقرّر` : "اقتباسات لم تحسمها الأداة" }),
    el("ul", { class: "open-list" }, open.map((f) => el("li", {}, el("span", { class: "row-num", text: toArabicDigits(f.id) }), el("span", { class: "row-q", dir: "rtl" }, excerpt(f.quote)),
      el("span", { class: `state ${pendingKind(f) ? "need" : "off"}`, text: pendingKind(f) ? PENDING_TEXT[pendingKind(f)] : reviewed[f.id] ? "راجعتَه بنفسك؛ لم تحسمه الأداة" : "لم تحسمه الأداة" }),
      el("button", { type: "button", class: "link-btn", onclick: () => goTo(f.id, { scroll: "panel" }), text: pendingKind(f) ? "قرّر" : "راجع" }))))) : null);

  const view = $("preview-view");
  view.replaceChildren();
  for (const s of R.previewSegments(lastArticle, changes, decisions, unresolvedSpans())) {
    if (s.type === "text") view.append(...bidi(s.text));
    else if (s.type === "del") view.append(el("del", { title: "قبل", text: s.text }));
    else if (s.type === "ins") view.append(el("ins", { title: "بعد (معتمد)", text: s.text }));
    else view.append(el("span", { class: "unresolved", title: weakPending(findingById(s.id) || {}) ? "عبارة تشبه آية لم تؤكّدها — لم يتغيّر فيها شيء" : "اقتباس لم يُحسم — يحتاج مراجعة بشرية" }, bidi(s.text)), el("sup", { class: "unres-mark", text: toArabicDigits(s.id) }));
  }
  $("revised-text").value = text;
  $("reply-text").value = R.replyDraft(fs, changes, decisions);
  updateReplyCount();
  $("copy-btn").classList.toggle("ready", !mainPendingList().length);
  $("copy-note").classList.toggle("copy-bad", $("copy-note").classList.contains("copy-bad"));
  if (refused.length) $("final-changes").append(el("p", { class: "notice error", text: `تعذّر تطبيق ${countAr(refused.length, "تغيير واحد", "تغييرين", "تغييرات", "تغييرًا")} (تداخل أو إزاحة)؛ يبقى النص المنسوخ في ذلك كما كتبتَه.` }));
}
const requiredOfAll = () => activeFindings().flatMap(requiredOf);
function unresolvedSpans() { return unresolvedNow().map((f) => ({ start: f.start, end: f.end, id: f.id })); }

function updateReplyCount() {
  const n = Array.from($("reply-text").value).length;
  $("reply-count").textContent = `${toArabicDigits(n)} حرفًا`;
}

// ---------------------------------------------------------------- the bottom bar (narrow screens): where the review stands, and the next step
// Is the writer reading the final review? Entered when its top passes 60% of the screen, left only when it is clearly away (75%, or
// scrolled past), so the bar does not flicker at the edge.
let finalInView = false;
function updateFinalInView() {
  const f = $("final");
  let v = false;
  if (!f.hidden && lastResult) {
    const r = f.getBoundingClientRect();
    v = finalInView ? r.top < innerHeight * 0.75 && r.bottom > 40 : r.top < innerHeight * 0.6 && r.bottom > 120;
  }
  if (v !== finalInView) { finalInView = v; renderDock(); }
}
let finalViewFrame = 0;
const onScrollForDock = () => { if (!finalViewFrame) finalViewFrame = requestAnimationFrame(() => { finalViewFrame = 0; updateFinalInView(); }); };

function hideDock(dock) {
  // the bar must not take keyboard focus with it: focus goes to the heading of the review the writer is reading
  if (dock.contains(document.activeElement)) $("final-title").focus({ preventScroll: true });
  dock.hidden = true;
  document.documentElement.style.setProperty("--dock-h", "0px");
}

function renderDock() {
  const dock = $("review-dock");
  if (!lastResult || !allFindings().length) { hideDock(dock); return; }
  const pend = pendingList();
  // nothing waits and the final review is on screen: the bar would only offer the place the writer already is, over its buttons
  if (!pend.length && finalInView) { hideDock(dock); return; }
  const here = caretId !== null ? findingById(caretId) : null;
  dock.hidden = false;
  // when the caret is inside a highlighted quotation the bar names it and offers to open its decision
  $("dock-text").textContent = here ? `${itemName(here)} ${toArabicDigits(here.id)}: ${stateOf(here)[0]}` : openText();
  $("dock-open").hidden = !here;
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
  flushDerived();
  const text = $("revised-text").value;
  try {
    await navigator.clipboard.writeText(text);
    const pend = mainPendingList().length, weak = weakPendingList().length;
    const msg = `نُسخ المقال المعدّل${pend ? `، وبقي ${countAr(pend, "اقتباس واحد لم تقرّر فيه فنُسخ كما كتبتَه", "اقتباسان لم تقرّر فيهما فنُسخا كما كتبتَهما", "اقتباسات لم تقرّر فيها فنُسخت كما كتبتَها", "اقتباسًا لم تقرّر فيها فنُسخت كما كتبتَها")}` : ""}${weak ? `، و${countAr(weak, "عبارة واحدة للتأكيد نُسخت كما كتبتَها", "عبارتان للتأكيد نُسختا كما كتبتَهما", "عبارات للتأكيد نُسخت كما كتبتَها", "عبارة للتأكيد نُسخت كما كتبتَها")}` : ""}. الأداة فحصت الاقتباسات القرآنية التي رُصدت فقط${pend || unresolvedNow().some((f) => !weakPending(f)) ? "؛ وما بقي غير محسوم يحتاج مراجعتك" : ""}.`;
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
  if (ai.outcome === "skipped_length") return `لم يُستدعَ النموذج لأن المقال أطول من ${arabicCount(AI_MAX_CHARS)} حرف؛ فُحص كامل المقال بالعلامات والبحث في المصحف، وقد تفوت الاقتباسات القصيرة غير المعلَّمة.`;
  if (ai.outcome === "skipped_cooldown") return `لا — لم يُسأل ${ai.provider} في هذا التدقيق لأن استدعاءً سابقًا له تعذّر قبل قليل، فاستُخدم الوضع الاحتياطي الحتمي، وقد تفوت الاقتباسات القصيرة غير المعلَّمة.`;
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
  const unresolved = unresolvedNow().filter((f) => !weakPending(f));
  const maybe = weakPendingList();
  const off = allFindings().filter((f) => dismissed[f.id]);
  const kv = (k, v) => el("tr", {}, el("th", { text: k }), el("td", {}, v));

  fill(rec, 
    el("h1", { text: "سجل مراجعة الاقتباسات" }),
    el("p", { class: "rec-disclaimer" },
      el("b", { text: "أداة مساعدة تحريرية، وليست شهادة بصحة النص الديني أو سلامته. " }),
      "يقتصر الفحص على الاقتباسات القرآنية التي رُصدت وإحالاتها، بمقارنتها بنص مصحف حفص من قرآنبيديا. لا يشهد هذا السجل بأن المقال كله متحقق منه أو جاهز للنشر، ولا يغني عن مراجعة المختص."),
    el("table", { class: "rec-meta" },
      kv("وقت التدقيق", auditedAt ? fmtTime(auditedAt) : "—"),
      kv("وقت إعداد السجل", fmtTime(Date.now() / 1000)),
      kv("حالة النص", edited()
        ? `عُدّل المقال بعد آخر تدقيق${staleList().length ? `؛ ${staleList().length} موضعًا من الاقتباسات المرصودة مسّه التعديل وسقطت قراراتها، ولم يُفحص ما كُتب بعد التدقيق` : "؛ لم يمسّ التعديل اقتباسًا مرصودًا، لكن لم يُفحص ما كُتب بعد التدقيق"}.`
        : "النص كما دُقِّق (لم يُعدَّل بعد آخر تدقيق)."),
      kv("طول المقال", `${arabicCount(cpCount(lastArticle))} حرفًا الآن؛ وكان ${arabicCount(cpCount(baseText || lastArticle))} حرفًا عند أول تدقيق.`),
      kv("مصدر النص القرآني", `${data.source.name} — ${data.source.url}`),
      kv("وقت جلب المصدر", data.source.fetched_at ? fmtTime(data.source.fetched_at) + (data.source.stale ? " (نسخة مخبأة)" : "") : "المصدر غير متاح — لم يُحكم على أي اقتباس"),
      kv("هل عمل الاستخراج بالذكاء الاصطناعي؟", aiRecordText(data)),
      kv("الأعداد", `اقتباسات مرصودة ${activeFindings().filter((f) => !weakPending(f)).length} · عبارات تشبه آيات لم يؤكّدها المحرر ${weakPendingList().length} · تصحيحات معتمدة ${approved.length} · مرفوضة ${rejected.length} · بلا قرار ${pending.length} · غير محسومة ${unresolved.length} · مستبعدة (ليست اقتباسًا) ${off.length}`),
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
      `#${f.id} (السطر ${lineOf(f.start)}) «${f.quote}» — `,
      (f.review_reasons || []).join("؛ ") || (f.correction?.reason || "تصحيح مقترح لم يُعتمد"),
      f.source ? (f.wording.level === "fuzzy" ? ` — أقرب موضع مقترح (غير مؤكد): ${f.source.label}` : ` — الموضع في المصدر: ${f.source.label}`) : ""))) : el("p", { text: "لا يوجد في الاقتباسات المرصودة. (قد توجد اقتباسات لم تُرصد.)" }),
    maybe.length ? el("h2", { text: "عبارات تشبه آيات لم يؤكّدها المحرر (لم يتغيّر فيها شيء)" }) : null,
    maybe.length ? el("ul", {}, maybe.map((f) => el("li", { text: `#${f.id} (السطر ${lineOf(f.start)}) «${f.quote}» — ${(f.choices || []).map((c) => c.label).join("، ") || "—"}` }))) : null,
    off.length ? el("h2", { text: "مقاطع استبعدها المحرر (ليست اقتباسًا قرآنيًا)" }) : null,
    off.length ? el("ul", {}, off.map((f) => el("li", { text: `#${f.id} (السطر ${lineOf(f.start)}) «${f.quote}»` }))) : null,
    el("p", { class: "rec-foot", text: "أُعدّ بواسطة مدقق الاقتباسات القرآنية. نص المقال لا يُخزَّن على الخادم؛ هذا السجل مولَّد في المتصفح." }),
  );
}

function printRecord() {
  if (!lastResult) return;
  flushDerived();
  buildRecord();
  window.print();
}

// ---------------------------------------------------------------- local draft (only when the writer chooses it)
const draftNote = (t) => { $("draft-note").textContent = t; };
function readDraft() {
  try { const d = JSON.parse(localStorage.getItem(DRAFT_KEY) || "null"); return d && typeof d.text === "string" ? d : null; } catch { return null; }
}
function writeDraft(auto) {
  try {
    localStorage.setItem(DRAFT_KEY, JSON.stringify({ v: 1, savedAt: Date.now(), text: lastArticle, auto: !!auto }));
    draftAuto = !!auto;
    draftNote(`حُفظت المسودة (${arabicCount(cpCount(lastArticle))} حرفًا) في هذا المتصفح فقط. القرارات والنتائج لا تُحفظ؛ تحتاج بعد الاستعادة إلى إعادة التدقيق.`);
    $("draft-auto-row").hidden = false;
    return true;
  } catch {
    draftNote("تعذّر الحفظ: التخزين في هذا المتصفح غير متاح (قد تكون نافذة خاصة).");
    return false;
  }
}
let autosaveTimer = null;
let draftAuto = false;   // mirrors the saved draft's "auto" flag, so typing does not parse localStorage
function autosaveDraft() {
  if (!draftAuto) return;
  clearTimeout(autosaveTimer);
  autosaveTimer = setTimeout(() => writeDraft(true), 800);
}
function deleteDraft() {
  try { localStorage.removeItem(DRAFT_KEY); } catch { /* ignore */ }
  draftAuto = false;
  $("draft-auto-row").hidden = true;
  $("draft-banner").hidden = true;
  draftNote("حُذفت المسودة المحفوظة من هذا المتصفح.");
}
function download(name, mime, body) {
  const url = URL.createObjectURL(new Blob([body], { type: `${mime};charset=utf-8` }));
  const a = el("a", { href: url, download: name });
  document.body.append(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
const stamp = () => new Date().toISOString().slice(0, 10);
function decisionsRecord() {
  const rows = activeFindings().map((f) => ({
    id: f.id, quote: f.quote, place: f.source ? f.source.label : null, stale: !!f.stale, dismissed: !!dismissed[f.id], reviewed: !!reviewed[f.id],
    changes: (f.changes || []).map((c) => ({ kind: c.kind, optional: c.optional, original: c.original, replacement: c.replacement, decision: decisions[c.id] || null })),
  }));
  return {
    exported_at: new Date().toISOString(), note: "تصدير من مدقق الاقتباسات القرآنية؛ النص والقرارات من متصفحك فقط.",
    audited_at: auditedAt ? new Date(auditedAt * 1000).toISOString() : null, edited_since_audit: edited(),
    original_text: baseText || null, text: lastArticle, revised_text: lastResult ? R.applyApproved(lastArticle, allChanges(), decisions).text : null, findings: rows,
  };
}
function exportDecisions() {
  download(`quran-quote-draft-${stamp()}.json`, "application/json", JSON.stringify(decisionsRecord(), null, 2));
}

// Optional accounts (roadmap Stage 2): only when the server says ACCOUNTS_ENABLED is on does the page load a separate
// script for it. With the flag off nothing below runs: no account script, no control, no request to an auth service.
function loadAccounts() {
  if (window.QQAHost) return;
  window.QQAHost = {
    text: () => lastArticle,
    record: decisionsRecord,
    auditedText: () => (lastResult ? auditedText : null),
    open: (text) => { window.QQASuggest?.hide(); setEditorText(text); },
    clear: resetAll,
    download,
  };
  const s = document.createElement("script");
  s.src = "/static/account.js";
  document.head.append(s);
}

function showDraftBanner() {
  const d = readDraft();
  const box = $("draft-banner");
  if (!d || editor().value.trim()) { box.hidden = true; return; }
  box.hidden = false;
  box.replaceChildren(el("span", {}, `توجد مسودة محفوظة في هذا المتصفح (${arabicCount(cpCount(d.text))} حرفًا، ${fmtTime(d.savedAt / 1000)}). `),
    el("button", { type: "button", class: "btn small", onclick: () => { setEditorText(d.text); box.hidden = true; editor().focus(); setStatus("استُعيدت المسودة. أعد التدقيق لتظهر الاقتباسات."); }, text: "استعدها" }), " ",
    el("button", { type: "button", class: "btn small ghost", onclick: deleteDraft, text: "احذفها" }));
}

// ---------------------------------------------------------------- init
function resetAll() {
  hideImportAsk(false);
  setEditorText("");
  setStatus("");
  window.QQASuggest?.hide();
  editor().focus();
}

document.addEventListener("DOMContentLoaded", () => {
  const ta = editor();
  ta.addEventListener("beforeinput", () => { lastSel = [W.unitToCp(ta.value, ta.selectionStart), W.unitToCp(ta.value, ta.selectionEnd)]; });
  ta.addEventListener("input", onEditorInput);
  ta.addEventListener("keydown", (e) => { if ((e.ctrlKey || e.metaKey) && e.key === "Enter") runAudit(); });
  for (const ev of ["keyup", "mouseup", "touchend", "click", "focus", "select"]) ta.addEventListener(ev, onCaretMoved);
  document.addEventListener("selectionchange", onCaretMoved);
  ta.addEventListener("blur", () => { setTimeout(() => { updateSelectionBar(); }, 0); });
  $("audit-btn").addEventListener("click", runAudit);
  $("recheck-btn").addEventListener("click", runAudit);
  $("clear-btn").addEventListener("click", resetAll);
  $("sample-select").addEventListener("change", (e) => { loadSample(e.target.value); e.target.value = ""; });
  $("demo-btn").addEventListener("click", runDemo);
  $("import-btn").addEventListener("click", openImport);
  $("import-file").addEventListener("change", onImportChosen);
  $("import-replace").addEventListener("click", () => { const p = importPending; hideImportAsk(false); if (p) applyImport(p.res); });
  $("import-cancel").addEventListener("click", () => { hideImportAsk(true); importNote("لم يُستورد الملف، ولم يتغيّر شيء في المحرر."); });
  $("import-ask").addEventListener("keydown", (e) => { if (e.key === "Escape") { e.preventDefault(); $("import-cancel").click(); } });
  $("dock-next").addEventListener("click", () => {
    const id = nextPending(current);
    if (id === null) goToFinal(); else goTo(id, { scroll: "panel" });
  });
  $("dock-open").addEventListener("click", () => {
    scrollToNode($("panel"));
    $("current").firstElementChild?.focus({ preventScroll: true });
  });
  $("next-btn").addEventListener("click", () => { const id = nextPending(current); if (id !== null) goTo(id, { scroll: "panel" }); });
  $("prev-btn").addEventListener("click", () => { const id = nextPending(current, -1); if (id !== null) goTo(id, { scroll: "panel" }); });
  $("phrase-btn").addEventListener("mousedown", (e) => e.preventDefault());
  $("phrase-btn").addEventListener("click", checkSelection);
  $("sel-complete").addEventListener("mousedown", (e) => e.preventDefault());
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
  $("draft-save").addEventListener("click", () => writeDraft(false));
  $("draft-delete").addEventListener("click", deleteDraft);
  $("draft-export").addEventListener("click", () => download(`quran-quote-article-${stamp()}.txt`, "text/plain", lastArticle));
  $("draft-export-json").addEventListener("click", exportDecisions);
  $("draft-auto").addEventListener("change", (e) => { if (e.target.checked) writeDraft(true); else { const d = readDraft(); if (d) writeDraft(false); } });
  window.addEventListener("beforeprint", () => { if (lastResult) { flushDerived(); buildRecord(); } });
  window.addEventListener("resize", () => { syncDockHeight(); syncEditorHeight(); placeFixLabels(); updateFinalInView(); });
  window.addEventListener("scroll", onScrollForDock, { passive: true });
  if (window.ResizeObserver) new ResizeObserver(syncDockHeight).observe($("review-dock"));
  // the editor can change width without a window resize (the review panel opens beside it): the drawn corrections follow their words
  let editorW = 0;
  if (window.ResizeObserver) new ResizeObserver(([e]) => { const w = Math.round(e.contentRect.width); if (w !== editorW) { editorW = w; syncEditorHeight(); placeFixLabels(); } }).observe($("editor"));
  document.fonts?.ready.then(() => { syncEditorHeight(); placeFixLabels(); });

  const saved = loadSession();
  if (saved) {
    ta.value = saved.article;
    setArticleText(saved.article); lastResult = saved.result; decisions = saved.decisions || {}; dismissed = saved.dismissed || {}; reviewed = saved.reviewed || {};
    current = saved.current ?? null; auditedAt = saved.auditedAt || null; isDemo = !!saved.isDemo;
    auditedText = saved.auditedText ?? saved.article; baseText = saved.baseText ?? saved.article; invalidated = saved.invalidated || [];
    render(false);
    setStatus("استُعيدت نتيجة التدقيق وقراراتك من هذه الجلسة.");
  } else {
    setArticleText(normalizeNl(ta.value));
    showDraftBanner();
  }
  const d0 = readDraft();
  draftAuto = !!(d0 && d0.auto);
  $("draft-auto-row").hidden = !d0;
  $("draft-auto").checked = !!(d0 && d0.auto);
  syncEditorHeight();
  updateCount();
  loadHealth();
});
