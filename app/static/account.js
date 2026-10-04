// Optional accounts and private cloud drafts (roadmap Stage 2).
//
// Loaded ONLY when /api/health says "accounts_enabled": true (app.js → loadAccounts). A guest page never loads this file.
//
// - Sign-in: an email magic link, requested from Supabase Auth's REST endpoint directly (no SDK). The link comes back to this
//   site with the tokens in the URL fragment; the fragment is cleared from the address bar at once.
// - The access token is kept IN MEMORY ONLY (a variable in this closure): never localStorage, sessionStorage or a cookie.
//   The refresh token in the fragment is discarded. Reloading the page therefore means signing in again (the trade-off is
//   documented in docs/PRODUCTION_ROADMAP.md, "Stage 2 status").
// - The link usually opens in a new tab. That tab hands the session to the tab that asked for the link (and only to it: a
//   random nonce travels in the link) over a BroadcastChannel — memory to memory, nothing stored.
// - Nothing is uploaded by signing in. «احفظ في حسابي» is the only action that sends the article to the account.
// - Drafts are read and written through this server's /api/account/*, which verifies the token itself.
// All text is inserted with textContent.
"use strict";

(() => {
  const H = window.QQAHost;
  const $ = (id) => document.getElementById(id);
  if (!H || $("account")) return;

  const SAVE_FAILED_AUTH = "لم يُحفظ: سجّل الدخول من جديد. نصّك باقٍ في المحرر.";
  const toAr = (n) => String(n).replace(/\d/g, (d) => "٠١٢٣٤٥٦٧٨٩"[d]);
  const arCount = (n) => toAr(Number(n).toLocaleString("en-US")).replace(/,/g, "٬");
  const cp = (t) => { let n = 0; for (const _ of t || "") n++; return n; };
  const when = (iso) => { try { return new Date(iso).toLocaleString("ar", { dateStyle: "medium", timeStyle: "short" }); } catch { return ""; } };

  function el(tag, attrs, ...children) {
    const node = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v === undefined || v === null || v === false) continue;
      if (k === "text") node.textContent = v;
      else if (k === "class") node.className = v;
      else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
      else node.setAttribute(k, v === true ? "" : v);
    }
    for (const c of children.flat()) if (c !== null && c !== undefined && c !== false) node.append(c);
    return node;
  }

  // ---------------------------------------------------------------- state (memory only)
  let cfg = null;          // { supabase_url, anon_key, max_drafts, max_chars } from /api/account/config
  let session = null;      // { token, expiresAt, email }
  let drafts = [];         // metadata of the account's drafts (no bodies)
  let opened = null;       // { id, version, title, savedText }: the account draft the editor holds
  let conflict = null;     // the 409 answer while the writer chooses
  let localPrefs = null;   // the browser's own suggestion options, restored on sign-out
  let waitingNonce = null; // this tab asked for a magic link
  const channel = "BroadcastChannel" in window ? new BroadcastChannel("qqa-account-v1") : null;

  // ---------------------------------------------------------------- UI
  const css = el("link", { rel: "stylesheet", href: "/static/account.css" });
  document.head.append(css);

  const note = el("p", { id: "account-note", class: "small account-note", role: "status", "aria-live": "polite" });
  const setNote = (text, isError) => { note.textContent = text || ""; note.classList.toggle("is-error", !!isError); };

  const email = el("input", { id: "account-email", type: "email", autocomplete: "email", required: true, dir: "ltr", inputmode: "email" });
  const sendBtn = el("button", { type: "submit", class: "btn small", text: "أرسل رابط الدخول" });
  const outBox = el("div", { id: "account-out", class: "account-out" },
    el("p", { class: "small muted", text: "الكتابة والتدقيق لا تحتاجان حسابًا. إن أردت أن تحفظ مسوداتك في حساب خاص بك، اطلب رابط دخول إلى بريدك. الدخول لا يرفع شيئًا من مقالك؛ لا يُحفظ في الحساب إلا ما تختار حفظه." }),
    el("form", { id: "account-form", class: "account-form", novalidate: true, onsubmit: (e) => { e.preventDefault(); requestLink(); } },
      el("label", { for: "account-email", text: "بريدك الإلكتروني" }), email, sendBtn));

  const who = el("p", { id: "account-who", class: "small" });
  const saveBtn = el("button", { id: "account-save", type: "button", class: "btn small", text: "احفظ في حسابي", onclick: () => save() });
  const exportBtn = el("button", { id: "account-export", type: "button", class: "btn small", text: "نزّل كل مسوداتي (JSON)", onclick: exportAll });
  const outBtn = el("button", { id: "account-signout", type: "button", class: "btn small ghost", text: "اخرج من الحساب", onclick: () => signOut() });
  const openedLine = el("p", { id: "account-opened", class: "small muted", hidden: true });
  const conflictBox = el("div", { id: "account-conflict", class: "account-conflict", role: "group", "aria-labelledby": "account-conflict-title", hidden: true });
  const signoutConfirm = el("div", { id: "account-signout-confirm", class: "account-confirm", hidden: true });
  const listTitle = el("h4", { id: "account-list-title", class: "account-list-title", tabindex: "-1", text: "مسوداتك في الحساب" });
  const list = el("ul", { id: "account-list", class: "account-list", "aria-labelledby": "account-list-title" });
  const empty = el("p", { id: "account-empty", class: "small muted", text: "لا مسودات في حسابك بعد.", hidden: true });
  const delConfirm = el("div", { class: "account-confirm", hidden: true },
    el("p", { class: "small", text: "سيُحذف حسابك وكل مسوداته وتفضيلاته نهائيًا. النسخ الاحتياطية لدى مزوّد الخدمة تنتهي بانتهاء مدة احتفاظه بها. لا يمكن التراجع." }),
    el("div", { class: "actions-row" },
      el("button", { id: "account-delete-yes", type: "button", class: "btn small danger", text: "نعم، احذف حسابي نهائيًا", onclick: deleteAccount }),
      el("button", { type: "button", class: "btn small ghost", text: "إلغاء", onclick: () => { delConfirm.hidden = true; delBtn.focus(); } })));
  const delBtn = el("button", { id: "account-delete", type: "button", class: "btn small ghost", text: "احذف حسابي…", onclick: () => { delConfirm.hidden = false; $("account-delete-yes").focus(); } });
  const inBox = el("div", { id: "account-in", class: "account-in", hidden: true },
    who,
    el("div", { class: "actions-row" }, saveBtn, exportBtn, outBtn),
    signoutConfirm, openedLine, conflictBox, listTitle, empty, list,
    el("details", { class: "account-danger" }, el("summary", { text: "حذف الحساب" }), delBtn, delConfirm));

  const section = el("section", { id: "account", class: "account", "aria-labelledby": "account-title" },
    el("h3", { id: "account-title", class: "account-title", text: "حسابك (اختياري)" }), outBox, inBox, note);
  const body = document.querySelector("#options .options-body");
  if (!body) return;
  body.insertBefore(section, $("mode-banner"));

  // ---------------------------------------------------------------- server calls
  async function api(method, path, data) {
    if (!session) return { status: 401, data: { error: SAVE_FAILED_AUTH } };
    let res;
    try {
      res = await fetch(`/api/account${path}`, {
        method, cache: "no-store", credentials: "omit",
        headers: { Authorization: `Bearer ${session.token}`, ...(data ? { "Content-Type": "application/json" } : {}) },
        body: data ? JSON.stringify(data) : undefined,
      });
    } catch {
      return { status: 0, data: { error: "تعذّر الاتصال بالخادم؛ لم يُحفظ شيء. نصّك باقٍ في المحرر." } };
    }
    let out = null;
    try { out = res.status === 204 ? null : await res.json(); } catch { /* empty */ }
    return { status: res.status, data: out || {} };
  }

  async function supabase(path, init) {
    return fetch(`${cfg.supabase_url}/auth/v1${path}`, { ...init, credentials: "omit", cache: "no-store", headers: { apikey: cfg.anon_key, ...(init.headers || {}) } });
  }

  // A refused token (expired, revoked, account deleted): back to signed-out, the editor untouched.
  function expired(message) {
    session = null; drafts = []; conflict = null;
    restorePrefs();
    render();
    setNote(message || SAVE_FAILED_AUTH, true);
  }

  // ---------------------------------------------------------------- sign-in
  function randomNonce() {
    const a = new Uint8Array(16);
    crypto.getRandomValues(a);
    return Array.from(a, (b) => b.toString(16).padStart(2, "0")).join("");
  }

  async function requestLink() {
    const address = email.value.trim();
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(address)) { setNote("اكتب بريدًا إلكترونيًا صحيحًا.", true); email.focus(); return; }
    if (!cfg) { setNote("تعذّر تحميل إعداد الحساب من الخادم.", true); return; }
    waitingNonce = randomNonce();
    const back = `${location.origin}/?acct=${waitingNonce}`;
    sendBtn.disabled = true;
    try {
      const res = await supabase(`/otp?redirect_to=${encodeURIComponent(back)}`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email: address, create_user: true }),
      });
      if (!res.ok) throw new Error(String(res.status));
      setNote("أرسلنا رابط دخول إلى بريدك. افتحه في هذا المتصفح، وتبقى هذه الصفحة ونصّك كما هما؛ تدخل هنا حين يُفتح الرابط.");
    } catch {
      waitingNonce = null;
      setNote("تعذّر إرسال رابط الدخول الآن. أعد المحاولة بعد قليل.", true);
    } finally {
      sendBtn.disabled = false;
    }
  }

  function claimsOf(token) {
    try {
      const b = token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
      const bin = atob(b + "=".repeat((4 - (b.length % 4)) % 4));
      return JSON.parse(new TextDecoder().decode(Uint8Array.from(bin, (ch) => ch.charCodeAt(0))));
    } catch { return {}; }
  }

  function startSession(token, expiresAt) {
    const c = claimsOf(token);   // display only (the email); the server verifies the token on every call
    session = { token, expiresAt, email: typeof c.email === "string" ? c.email : "" };
    waitingNonce = null;
    onSignedIn();
  }

  // The magic link brought us here: read the fragment once and clear it (and the nonce) from the address bar.
  function readReturn() {
    const hash = location.hash.startsWith("#") ? location.hash.slice(1) : "";
    if (!hash || !/(^|&)(access_token|error)=/.test(hash)) return null;
    const f = new URLSearchParams(hash);
    const nonce = new URLSearchParams(location.search).get("acct");
    history.replaceState(null, "", location.pathname);
    if (f.get("error") || !f.get("access_token")) return { error: true };
    const expiresAt = Number(f.get("expires_at")) ? Number(f.get("expires_at")) * 1000 : Date.now() + (Number(f.get("expires_in")) || 3600) * 1000;
    return { token: f.get("access_token"), expiresAt, nonce };   // the refresh_token is deliberately not read
  }

  channel?.addEventListener("message", (e) => {
    const m = e.data || {};
    if (m.type === "session" && waitingNonce && m.nonce === waitingNonce && typeof m.token === "string") {
      startSession(m.token, m.expiresAt);
      setNote("دخلتَ إلى حسابك من الرابط. لم يُرفع شيء من مقالك؛ اضغط «احفظ في حسابي» متى أردت.");
    }
  });

  // ---------------------------------------------------------------- preferences (the two suggestion options)
  const optS = $("opt-suggest"), optD = $("opt-distinct");
  function applyPrefs(p) {
    const s = window.QQASuggest?.prefs;
    if (!p || !s) return;
    if (!localPrefs) localPrefs = { auto: s.auto, distinct: s.distinct };
    s.auto = !!p.suggest_on; s.distinct = !!p.distinct_on;
    if (optS) optS.checked = s.auto;
    if (optD) optD.checked = s.distinct;
  }
  function restorePrefs() {
    const s = window.QQASuggest?.prefs;
    if (!localPrefs || !s) return;
    s.auto = localPrefs.auto; s.distinct = localPrefs.distinct;
    if (optS) optS.checked = s.auto;
    if (optD) optD.checked = s.distinct;
    localPrefs = null;
  }
  async function pushPrefs() {
    if (!session) return;
    const r = await api("PUT", "/preferences", { suggest_on: !!optS?.checked, distinct_on: !!optD?.checked });
    if (r.status === 401) expired("لم تُحفظ الخيارات في حسابك: سجّل الدخول من جديد.");
  }
  optS?.addEventListener("change", pushPrefs);
  optD?.addEventListener("change", pushPrefs);

  // ---------------------------------------------------------------- signed in
  async function onSignedIn() {
    render();
    const [p, l] = await Promise.all([api("GET", "/preferences"), api("GET", "/drafts")]);
    if (p.status === 401 || l.status === 401) { expired("لم يُقبل الدخول؛ اطلب رابطًا جديدًا."); return; }
    if (p.status === 200 && p.data.preferences) applyPrefs(p.data.preferences);
    if (l.status === 200) { drafts = l.data.drafts || []; renderList(); }
  }

  async function refreshList() {
    const l = await api("GET", "/drafts");
    if (l.status === 401) { expired(); return; }
    if (l.status === 200) { drafts = l.data.drafts || []; renderList(); }
  }

  const titleFrom = (text) => {
    const line = (text.split("\n").find((x) => x.trim()) || "مسودة").trim();
    const chars = [...line];
    return chars.length > 60 ? chars.slice(0, 60).join("") + "…" : line;
  };

  function record() {
    const r = H.record();
    delete r.text; delete r.revised_text;   // the body is stored once, as the draft's text
    return r;
  }

  async function save(mode) {
    const text = H.text();
    if (!text.trim()) { setNote("المحرر فارغ؛ لا شيء يُحفظ.", true); return; }
    if (cfg && cp(text) > cfg.max_chars) { setNote(`المقال أطول من ${arCount(cfg.max_chars)} حرف، فلم يُحفظ في حسابك. نصّك باقٍ في المحرر.`, true); return; }
    saveBtn.disabled = true;
    const payload = { body: text, decisions: record(), audited_text: H.auditedText() };
    let r;
    if (opened && mode !== "new") {
      const version = mode === "overwrite" && conflict ? conflict.saved.version : opened.version;
      r = await api("PUT", `/drafts/${opened.id}`, { ...payload, version });
    } else {
      r = await api("POST", "/drafts", { ...payload, title: titleFrom(text) });
    }
    saveBtn.disabled = false;
    if (r.status === 401) { expired(SAVE_FAILED_AUTH); return; }
    if (r.status === 409) { showConflict(r.data); return; }
    if (r.status === 404 && opened) { opened = null; renderOpened(); setNote("لم تُجد هذه المسودة في حسابك (ربما حُذفت). اضغط «احفظ في حسابي» لحفظها مسودة جديدة. نصّك باقٍ في المحرر.", true); return; }
    if (r.status !== 200 && r.status !== 201) { setNote(r.data.error ? `لم يُحفظ: ${r.data.error}` : "لم يُحفظ. نصّك باقٍ في المحرر.", true); return; }
    hideConflict();
    opened = { id: r.data.id, version: r.data.version, title: r.data.title, savedText: text };
    renderOpened();
    setNote(`حُفظت في حسابك: «${r.data.title}» (${arCount(r.data.length)} حرفًا)، ${when(r.data.updated_at)}.`);
    refreshList();
  }

  function showConflict(data) {
    conflict = data;
    const saved = data.saved || {};
    conflictBox.replaceChildren(
      el("p", { id: "account-conflict-title", class: "small", tabindex: "-1" },
        el("strong", { text: "لم يُحفظ: " }),
        `حُفظت هذه المسودة من مكان آخر (تبويب أو جهاز آخر) بعد أن فتحتَها هنا — آخر حفظ ${when(saved.updated_at)}، ${arCount(saved.length || 0)} حرفًا. نسختك في المحرر ${arCount(cp(H.text()))} حرفًا. لم يُكتب شيء فوق الأخرى؛ أيّهما تبقى؟`),
      el("div", { class: "actions-row" },
        el("button", { id: "account-keep-mine", type: "button", class: "btn small", text: "احفظ نسختي فوق المحفوظة", onclick: () => save("overwrite") }),
        el("button", { id: "account-save-new", type: "button", class: "btn small", text: "احفظ نسختي مسودة جديدة", onclick: () => save("new") }),
        el("button", { id: "account-take-saved", type: "button", class: "btn small ghost", text: "افتح النسخة المحفوظة بدل نسختي", onclick: () => openDraft(saved.id || opened?.id, true) })));
    conflictBox.hidden = false;
    $("account-conflict-title").focus();
  }
  function hideConflict() { conflict = null; conflictBox.hidden = true; conflictBox.replaceChildren(); }

  async function openDraft(id, force) {
    const dirty = H.text().trim() && (!opened || H.text() !== opened.savedText);
    if (dirty && !force) return "confirm";
    const r = await api("GET", `/drafts/${id}`);
    if (r.status === 401) { expired(); return; }
    if (r.status !== 200) { setNote("تعذّر فتح المسودة.", true); refreshList(); return; }
    hideConflict();
    H.open(r.data.body);
    opened = { id: r.data.id, version: r.data.version, title: r.data.title, savedText: r.data.body };
    renderOpened();
    setNote(`فُتحت «${r.data.title}» من حسابك. أعد التدقيق لتظهر الاقتباسات؛ قراراتك السابقة محفوظة في سجلّها ولا تُطبَّق على النص من تلقاء نفسها.`);
    document.getElementById("article")?.focus();
  }

  async function rename(d, title) {
    const t = title.trim();
    if (!t) { setNote("اكتب اسمًا للمسودة.", true); return false; }
    const r = await api("PUT", `/drafts/${d.id}`, { version: d.version, title: t });
    if (r.status === 401) { expired(); return false; }
    if (r.status === 409) { setNote("تغيّرت هذه المسودة من مكان آخر؛ حُدّثت القائمة، فأعد التسمية.", true); await refreshList(); return false; }
    if (r.status !== 200) { setNote(r.data.error || "تعذّرت إعادة التسمية.", true); return false; }
    if (opened && opened.id === d.id) { opened.version = r.data.version; opened.title = r.data.title; renderOpened(); }
    setNote(`أصبح اسم المسودة «${r.data.title}».`);
    await refreshList();
    return true;
  }

  async function remove(d) {
    const r = await api("DELETE", `/drafts/${d.id}`);
    if (r.status === 401) { expired(); return; }
    if (r.status !== 204 && r.status !== 404) { setNote(r.data.error || "تعذّر الحذف.", true); return; }
    if (opened && opened.id === d.id) { opened = null; renderOpened(); }
    setNote(`حُذفت «${d.title}» من حسابك. ما في المحرر باقٍ كما هو.`);
    await refreshList();
    listTitle.focus();
  }

  async function exportAll() {
    const r = await api("GET", "/export");
    if (r.status === 401) { expired(); return; }
    if (r.status !== 200) { setNote("تعذّر التنزيل.", true); return; }
    H.download(`quran-quote-account-${new Date().toISOString().slice(0, 10)}.json`, "application/json", JSON.stringify(r.data, null, 2));
    setNote(`نُزّلت ${arCount((r.data.drafts || []).length)} مسودة مع تفضيلاتك في ملف JSON على جهازك.`);
  }

  // Sign out: the account's drafts leave the page (and the editor, if it holds one of them); a guest draft saved in this
  // browser (localStorage) is left alone and not uploaded.
  async function signOut(confirmed) {
    if (!session) return;
    const unsaved = opened && H.text() !== opened.savedText;
    if (unsaved && !confirmed) {
      signoutConfirm.replaceChildren(
        el("p", { class: "small", text: "في المحرر تعديلات لم تُحفظ في حسابك، وستُمسح من هذه الصفحة عند الخروج." }),
        el("div", { class: "actions-row" },
          el("button", { id: "account-signout-yes", type: "button", class: "btn small", text: "اخرج وامسح النص", onclick: () => signOut(true) }),
          el("button", { type: "button", class: "btn small ghost", text: "إلغاء", onclick: () => { signoutConfirm.hidden = true; outBtn.focus(); } })));
      signoutConfirm.hidden = false;
      $("account-signout-yes").focus();
      return;
    }
    const token = session.token;
    api("POST", "/signout").catch(() => {});
    supabase("/logout?scope=local", { method: "POST", headers: { Authorization: `Bearer ${token}` } }).catch(() => {});
    endSession();
    setNote("خرجتَ من حسابك، ومُسحت مسوداته من هذه الصفحة. المسودة المحفوظة في هذا المتصفح، إن وُجدت، باقية كما هي.");
    email.focus();
  }

  function endSession() {
    session = null; drafts = []; hideConflict(); signoutConfirm.hidden = true;
    if (opened) { opened = null; H.clear(); }
    restorePrefs();
    render();
  }

  async function deleteAccount() {
    const r = await api("DELETE", "");
    if (r.status === 401) { expired(); return; }
    if (r.status !== 200) { setNote(r.data.error || "تعذّر حذف الحساب.", true); return; }
    const token = session.token;
    supabase("/logout?scope=global", { method: "POST", headers: { Authorization: `Bearer ${token}` } }).catch(() => {});
    endSession();
    setNote(`حُذف من حسابك ${arCount(r.data.deleted_drafts)} مسودة مع تفضيلاتك.` +
      (r.data.auth_user_deleted ? " وحُذف حساب الدخول نفسه." : " حساب الدخول (البريد) لم يُحذف بعد لأن الخادم لم يُعدّ لذلك؛ راسل مشغّل الموقع لحذفه."));
    email.focus();
  }

  // ---------------------------------------------------------------- render
  function renderOpened() {
    openedLine.hidden = !opened;
    if (opened) openedLine.textContent = `المسودة المفتوحة من حسابك: «${opened.title}». «احفظ في حسابي» يحدّثها.`;
  }

  function renderList() {
    list.replaceChildren();
    empty.hidden = drafts.length > 0;
    for (const d of drafts) {
      const name = el("bdi", { class: "account-draft-title", text: d.title || "بلا عنوان" });
      const meta = el("span", { class: "small muted", text: `آخر حفظ ${when(d.updated_at)} · ${arCount(d.length || 0)} حرفًا` });
      const actions = el("div", { class: "account-row-actions" });
      const li = el("li", { class: "account-draft", "data-id": d.id }, el("div", { class: "account-draft-head" }, name, meta), actions);
      const plain = () => {
        actions.replaceChildren(
          el("button", { type: "button", class: "btn small", "data-act": "open", text: "افتح", "aria-label": `افتح ${d.title}`, onclick: async () => {
            if ((await openDraft(d.id)) === "confirm") confirmOpen();
          } }),
          el("button", { type: "button", class: "btn small ghost", "data-act": "rename", text: "أعد التسمية", "aria-label": `أعد تسمية ${d.title}`, onclick: renameForm }),
          el("button", { type: "button", class: "btn small ghost", "data-act": "delete", text: "احذف", "aria-label": `احذف ${d.title}`, onclick: confirmDelete }));
      };
      const confirmOpen = () => {
        actions.replaceChildren(
          el("span", { class: "small", text: "في المحرر نص لم يُحفظ في حسابك وسيحلّ محلّه نص هذه المسودة." }),
          el("button", { type: "button", class: "btn small", "data-act": "open-yes", text: "افتحها على أي حال", onclick: () => openDraft(d.id, true) }),
          el("button", { type: "button", class: "btn small ghost", text: "إلغاء", onclick: () => { plain(); actions.querySelector("[data-act=open]").focus(); } }));
        actions.querySelector("[data-act=open-yes]").focus();
      };
      const renameForm = () => {
        const id = `rename-${d.id}`;
        const input = el("input", { id, type: "text", value: d.title || "", maxlength: "200" });
        actions.replaceChildren(el("form", { class: "account-rename", onsubmit: async (e) => { e.preventDefault(); if (await rename(d, input.value)) list.querySelector(`[data-id="${d.id}"] [data-act=rename]`)?.focus(); } },
          el("label", { for: id, class: "sr-only", text: "الاسم الجديد للمسودة" }), input,
          el("button", { type: "submit", class: "btn small", "data-act": "rename-save", text: "احفظ الاسم" }),
          el("button", { type: "button", class: "btn small ghost", text: "إلغاء", onclick: () => { plain(); actions.querySelector("[data-act=rename]").focus(); } })));
        input.focus(); input.select();
      };
      const confirmDelete = () => {
        actions.replaceChildren(
          el("span", { class: "small", text: "تُحذف من حسابك نهائيًا." }),
          el("button", { type: "button", class: "btn small danger", "data-act": "delete-yes", text: "احذفها نهائيًا", onclick: () => remove(d) }),
          el("button", { type: "button", class: "btn small ghost", text: "إلغاء", onclick: () => { plain(); actions.querySelector("[data-act=delete]").focus(); } }));
        actions.querySelector("[data-act=delete-yes]").focus();
      };
      plain();
      list.append(li);
    }
  }

  function render() {
    const inside = !!session;
    outBox.hidden = inside;
    inBox.hidden = !inside;
    if (inside) {
      who.replaceChildren("داخل حسابك: ", el("bdi", { dir: "ltr", text: session.email || "—" }),
        ". الجلسة في هذه الصفحة وحدها: إعادة تحميلها تعني الدخول من جديد.");
      renderList();
    } else {
      list.replaceChildren();
    }
    renderOpened();
  }

  // A new document in the editor (clear, a sample, the demo) is no longer the opened account draft.
  for (const id of ["clear-btn", "demo-btn"]) $(id)?.addEventListener("click", () => { opened = null; hideConflict(); renderOpened(); });
  $("sample-select")?.addEventListener("change", () => { opened = null; hideConflict(); renderOpened(); });

  // Another tab may have saved meanwhile: the list is read again when the options open or this tab comes back into view.
  $("options")?.addEventListener("toggle", (e) => { if (e.target.open && session) refreshList(); });
  document.addEventListener("visibilitychange", () => { if (document.visibilityState === "visible" && session) refreshList(); });

  // ---------------------------------------------------------------- start
  (async () => {
    const back = readReturn();
    try {
      const res = await fetch("/api/account/config", { cache: "no-store" });
      if (res.ok) cfg = await res.json();
    } catch { /* stays null: the form says so when used */ }
    render();
    if (back && back.error) { setNote("لم يُقبل رابط الدخول (ربما انتهت صلاحيته أو استُعمل). اطلب رابطًا جديدًا.", true); return; }
    if (back && back.token) {
      if (channel && back.nonce) channel.postMessage({ type: "session", nonce: back.nonce, token: back.token, expiresAt: back.expiresAt });
      startSession(back.token, back.expiresAt);
      setNote("دخلتَ إلى حسابك. لم يُرفع شيء من مقالك؛ اضغط «احفظ في حسابي» متى أردت. إن طلبتَ الرابط من صفحة أخرى مفتوحة فقد دخلتَ فيها أيضًا.");
      const opts = $("options"); if (opts) opts.open = true;
    }
  })();
})();
