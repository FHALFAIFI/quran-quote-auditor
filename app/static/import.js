// Reading an article from a file, in the browser: plain text (.txt) and Word (.docx). No library, no network.
// The file is never sent anywhere: the page runs this file as a Web Worker (it stops it after a time limit), and tests/import.test.mjs
// loads it under Node. It returns the text as written, or a refusal with its reason. It never corrects a word, and never compares a
// word with the Quran: the only changes are the ones listed in `clean` (byte-order mark, line ends, invisible control characters,
// Arabic presentation forms), and each one is counted so that the page can say what was done.
"use strict";

(function (root) {
  const MB = 1024 * 1024;
  const LIMITS = {
    maxFileBytes: 5 * MB,      // the file itself
    maxUnzipped: 20 * MB,      // a DOCX: every part, as declared, and every part we inflate (zip-bomb guard)
    maxRatio: 200,             // a DOCX part larger than 1 MB that claims to be more than 200 times its compressed size is refused
    maxEntries: 5000,
    maxChars: 20000,           // the article limit; the page passes the server's own value
  };

  const AR_DIGITS = "٠١٢٣٤٥٦٧٨٩";
  const arNum = (n) => String(n).replace(/\B(?=(\d{3})+(?!\d))/g, "٬").replace(/\d/g, (d) => AR_DIGITS[d]);

  const MESSAGES = {
    empty: () => "الملف فارغ.",
    no_text: () => "لم نجد في الملف نصًّا يُقرأ.",
    file_too_big: () => `حجم الملف أكبر من ${arNum(LIMITS.maxFileBytes / MB)} ميغابايت.`,
    too_long: (d) => `في الملف ${arNum(d.chars)} حرف، وحدّ المقال ${arNum(d.max)} حرف. لم يُدرَج شيء؛ قسّم الملف وأعد المحاولة.`,
    not_utf8: () => "ترميز الملف ليس UTF-8 (قد يكون Windows-1256). احفظه من محرر النصوص بترميز UTF-8 ثم أعد المحاولة.",
    binary: () => "هذا ليس ملفًّا نصيًّا: فيه بيانات ثنائية وإن كان اسمه ينتهي بـ ‎.txt.",
    image: (d) => `هذا الملف صورة (${d.kind}) لا نصّ مكتوب فيها. قراءة الصور (OCR) غير مدعومة.`,
    pdf: () => "ملفات PDF غير مدعومة بعد. افتح الملف وانسخ نصّه والصقه هنا.",
    rtf: () => "ملفات RTF غير مدعومة. احفظ الملف بصيغة ‎.docx أو ‎.txt ثم أعد المحاولة.",
    doc_old: () => "هذا ملف Word قديم (‎.doc). احفظه بصيغة ‎.docx ثم أعد المحاولة.",
    encrypted: () => "الملف محمي بكلمة مرور. أزل الحماية في Word ثم أعد المحاولة.",
    zip_not_docx: () => "ملف مضغوط ليس مستند Word (لا يحوي word/document.xml).",
    macro: () => "لا يُقبل مستند Word فيه وحدات ماكرو (‎.docm). احفظه بصيغة ‎.docx ثم أعد المحاولة.",
    unzipped_too_big: () => `محتوى المستند بعد فكّ ضغطه أكبر من ${arNum(LIMITS.maxUnzipped / MB)} ميغابايت، فلم يُقرأ حمايةً لمتصفحك.`,
    corrupt: () => "الملف تالف أو لا يمكن قراءته.",
    unsupported: () => "نوع الملف غير مدعوم. المقبول: ملف نص (‎.txt) أو مستند Word (‎.docx).",
  };

  class ImportError extends Error {
    constructor(code, detail) { super(code); this.code = code; this.detail = detail || {}; }
  }
  const refuse = (code, detail) => { throw new ImportError(code, detail); };

  const startsWith = (b, sig, at = 0) => b.length >= at + sig.length && sig.every((x, i) => b[at + i] === x);

  // ---- what the file is, from its first bytes (never from its name or the browser's type) -------------------------------------
  function sniff(b) {
    if (b.length === 0) return "empty";
    if (startsWith(b, [0x50, 0x4b, 0x03, 0x04]) || startsWith(b, [0x50, 0x4b, 0x05, 0x06])) return "zip";
    if (startsWith(b, [0xd0, 0xcf, 0x11, 0xe0, 0xa1, 0xb1, 0x1a, 0xe1])) return "cfb";
    if (startsWith(b, [0x25, 0x50, 0x44, 0x46, 0x2d])) return "pdf";                     // %PDF-
    if (startsWith(b, [0x7b, 0x5c, 0x72, 0x74, 0x66])) return "rtf";                     // {\rtf
    if (startsWith(b, [0x89, 0x50, 0x4e, 0x47])) return "png";
    if (startsWith(b, [0xff, 0xd8, 0xff])) return "jpeg";
    if (startsWith(b, [0x47, 0x49, 0x46, 0x38])) return "gif";
    if (startsWith(b, [0x52, 0x49, 0x46, 0x46]) && startsWith(b, [0x57, 0x45, 0x42, 0x50], 8)) return "webp";
    if (startsWith(b, [0xef, 0xbb, 0xbf])) return "utf8-bom";
    if (startsWith(b, [0xff, 0xfe])) return "utf16le";
    if (startsWith(b, [0xfe, 0xff])) return "utf16be";
    return "text";
  }

  // ---- the only changes made to the text, each counted ----------------------------------------------------------------------------
  // Presentation forms (U+FB50–FDFF, U+FE70–FEFF) are glyph shapes some programs store instead of letters (ﻻ for لا, ﺍ for ا).
  // A form is replaced by its compatibility letters when they are Arabic letters or marks only. Kept as written: the ornate parentheses
  // ﴾ ﴿ (U+FD3E, U+FD3F), the word ligatures U+FDF0–FDFF (ﷲ ﷺ ﷻ ﷽ …) and anything whose mapping is not Arabic letters.
  const isPresentation = (c) => (c >= 0xfb50 && c <= 0xfdff) || (c >= 0xfe70 && c <= 0xfefe);
  const keepAsWritten = (c) => c === 0xfd3e || c === 0xfd3f || (c >= 0xfdf0 && c <= 0xfdff);
  function baseLetters(ch) {
    const c = ch.codePointAt(0);
    if (!isPresentation(c) || keepAsWritten(c)) return null;
    const m = ch.normalize("NFKC").replace(/ /g, "");
    if (!m || m === ch) return null;
    for (const x of m) { const k = x.codePointAt(0); if (k < 0x0600 || k > 0x06ff) return null; }
    return m;
  }

  function clean(raw) {
    const notes = { bom: 0, crlf: 0, controls: 0, presentation: 0 };
    let t = raw;
    t = t.replace(/﻿/g, () => { notes.bom++; return ""; });                 // byte-order mark (and the obsolete zero-width no-break space)
    t = t.replace(/\r\n?/g, () => { notes.crlf++; return "\n"; });
    // invisible control characters (C0 except tab and line feed, DEL, C1); tabs and line ends are kept
    t = t.replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F-\u009F]/g, () => { notes.controls++; return ""; });
    t = t.replace(/[ﭐ-﷿ﹰ-﻾]/g, (ch) => { const m = baseLetters(ch); if (m === null) return ch; notes.presentation++; return m; });
    // blank lines before the first line and white space after the last are dropped; nothing inside the text is touched
    t = t.replace(/^(?:[ \t]*\n)+/, "").trimEnd();
    return { text: t, notes };
  }

  // ---- TXT ------------------------------------------------------------------------------------------------------------------------
  function decodeText(b, kind) {
    try {
      if (kind === "utf16le" || kind === "utf16be") return new TextDecoder(kind === "utf16le" ? "utf-16le" : "utf-16be", { fatal: true }).decode(b.subarray(2));
      if (b.includes(0)) refuse("binary");
      // ignoreBOM: the mark is kept here and removed (and counted) by clean()
      return new TextDecoder("utf-8", { fatal: true, ignoreBOM: true }).decode(b);
    } catch (e) {
      if (e instanceof ImportError) throw e;
      if (kind !== "text" && kind !== "utf8-bom") refuse("corrupt");
      // not UTF-8: a text in another encoding (Windows-1256 …) has few control bytes; a binary file (gzip, an executable …) has many
      let ctl = 0;
      for (let i = 0; i < b.length; i++) { const x = b[i]; if ((x < 0x20 && x !== 9 && x !== 10 && x !== 13) || x === 0x7f) ctl++; }
      refuse(ctl > b.length / 100 ? "binary" : "not_utf8");
    }
    return "";
  }

  function fromText(b, kind) {
    const raw = decodeText(b, kind);
    if (raw.includes("\u0000")) refuse("binary");
    // a renamed binary that happens to be valid UTF-8: many control characters
    const ctl = (raw.match(/[\u0001-\u0008\u000E-\u001F]/g) || []).length;
    if (ctl > 8 && ctl > raw.length / 100) refuse("binary");
    return { kind: "txt", raw, info: {} };
  }

  // ---- ZIP (a DOCX is one) ---------------------------------------------------------------------------------------------------------
  const u16 = (b, o) => b[o] | (b[o + 1] << 8);
  const u32 = (b, o) => (b[o] | (b[o + 1] << 8) | (b[o + 2] << 16) | (b[o + 3] << 24)) >>> 0;
  const latin1 = (b) => { let s = ""; for (let i = 0; i < b.length; i++) s += String.fromCharCode(b[i]); return s; };

  let CRC_TABLE = null;
  function crc32(b) {
    if (!CRC_TABLE) {
      CRC_TABLE = new Uint32Array(256);
      for (let n = 0; n < 256; n++) { let c = n; for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1; CRC_TABLE[n] = c >>> 0; }
    }
    let c = 0xffffffff;
    for (let i = 0; i < b.length; i++) c = CRC_TABLE[(c ^ b[i]) & 0xff] ^ (c >>> 8);
    return (c ^ 0xffffffff) >>> 0;
  }

  // The central directory: names, sizes, flags. Every declared size is checked before anything is inflated.
  function readZip(b) {
    let eocd = -1;
    for (let i = b.length - 22; i >= Math.max(0, b.length - 22 - 65535); i--) {
      if (b[i] === 0x50 && b[i + 1] === 0x4b && b[i + 2] === 0x05 && b[i + 3] === 0x06) { eocd = i; break; }
    }
    if (eocd < 0) refuse("corrupt");
    const count = u16(b, eocd + 10), cdSize = u32(b, eocd + 12), cdOff = u32(b, eocd + 16);
    if (count === 0xffff || cdSize === 0xffffffff || cdOff === 0xffffffff) refuse("corrupt");     // ZIP64: not written for documents this size
    if (count > LIMITS.maxEntries || cdOff + cdSize > eocd) refuse("corrupt");
    const entries = new Map();
    let p = cdOff, declared = 0;
    for (let n = 0; n < count; n++) {
      if (p + 46 > b.length || u32(b, p) !== 0x02014b50) refuse("corrupt");
      const flags = u16(b, p + 8), method = u16(b, p + 10), crc = u32(b, p + 16);
      const csize = u32(b, p + 20), usize = u32(b, p + 24);
      const nl = u16(b, p + 28), xl = u16(b, p + 30), cl = u16(b, p + 32), local = u32(b, p + 42);
      if (p + 46 + nl > b.length) refuse("corrupt");
      const name = latin1(b.subarray(p + 46, p + 46 + nl));
      if (flags & 1) refuse("encrypted");
      declared += usize;
      if (declared > LIMITS.maxUnzipped) refuse("unzipped_too_big");
      if (usize > MB && usize > csize * LIMITS.maxRatio) refuse("unzipped_too_big");
      entries.set(name, { name, flags, method, crc, csize, usize, local });
      p += 46 + nl + xl + cl;
    }
    return entries;
  }

  // Inflate one part, streaming, and stop as soon as it gives more than it declared (a bomb that lies about its size), or more than
  // the budget left. The compressed data is fed in small pieces, so one piece can never expand to more than about 2 MB at once.
  async function inflate(b, e, budget) {
    const h = e.local;
    if (h + 30 > b.length || u32(b, h) !== 0x04034b50) refuse("corrupt");
    const start = h + 30 + u16(b, h + 26) + u16(b, h + 28);
    if (start + e.csize > b.length) refuse("corrupt");
    const data = b.subarray(start, start + e.csize);
    const cap = Math.min(e.usize, budget.left);
    let out;
    if (e.method === 0) {
      if (e.csize !== e.usize) refuse("corrupt");
      if (e.usize > budget.left) refuse("unzipped_too_big");
      out = data;
    } else if (e.method === 8) {
      out = await inflateRaw(data, cap, e.usize > budget.left);
    } else refuse("corrupt");
    if (out.length !== e.usize || crc32(out) !== e.crc) refuse("corrupt");
    budget.left -= out.length;
    return out;
  }

  async function inflateRaw(data, cap, overBudget) {
    if (typeof DecompressionStream === "undefined") refuse("unsupported");
    const ds = new DecompressionStream("deflate-raw");
    const writer = ds.writable.getWriter(), reader = ds.readable.getReader();
    const PIECE = 2048;
    let stopped = false;
    const feeding = (async () => {
      try {
        for (let o = 0; o < data.length && !stopped; o += PIECE) await writer.write(data.subarray(o, o + PIECE));
        if (!stopped) await writer.close();
      } catch { /* the reader reports the error */ }
    })();
    const chunks = [];
    let total = 0, failure = null;
    try {
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        total += value.length;
        if (total > cap) { failure = overBudget ? "unzipped_too_big" : "corrupt"; break; }
        chunks.push(value);
      }
    } catch { failure = "corrupt"; }
    if (failure) {
      stopped = true;
      chunks.length = 0;
      reader.cancel().catch(() => {});
      writer.abort().catch(() => {});
      refuse(failure);
    }
    await feeding;
    const out = new Uint8Array(total);
    let o = 0;
    for (const c of chunks) { out.set(c, o); o += c.length; }
    return out;
  }

  function decodeXml(bytes) {
    try {
      if (startsWith(bytes, [0xff, 0xfe])) return new TextDecoder("utf-16le", { fatal: true }).decode(bytes.subarray(2));
      if (startsWith(bytes, [0xfe, 0xff])) return new TextDecoder("utf-16be", { fatal: true }).decode(bytes.subarray(2));
      return new TextDecoder("utf-8", { fatal: true }).decode(bytes);
    } catch { return refuse("corrupt"); }
  }

  // ---- a small XML reader (DOMParser does not exist in a worker) ------------------------------------------------------------------
  // Elements and text only. A DOCTYPE is refused (no entity is ever expanded beyond the five XML ones and character references).
  const ENT = { lt: "<", gt: ">", amp: "&", quot: "\"", apos: "'" };
  function decodeEntities(s) {
    if (s.indexOf("&") < 0) return s;
    return s.replace(/&(#x[0-9a-fA-F]+|#[0-9]+|[a-zA-Z]+);?/g, (m, e) => {
      if (m[m.length - 1] !== ";") refuse("corrupt");
      if (e[0] === "#") {
        const n = e[1] === "x" || e[1] === "X" ? parseInt(e.slice(2), 16) : parseInt(e.slice(1), 10);
        if (!(n >= 0 && n <= 0x10ffff) || (n >= 0xd800 && n <= 0xdfff)) refuse("corrupt");
        return String.fromCodePoint(n);
      }
      if (!(e in ENT)) refuse("corrupt");
      return ENT[e];
    });
  }
  const TAG = /<([A-Za-z_][\w.\-]*(?::[A-Za-z_][\w.\-]*)?)((?:\s+[A-Za-z_][\w.\-:]*\s*=\s*(?:"[^"]*"|'[^']*'))*)\s*(\/?)>/y;
  const CLOSE = /<\/([A-Za-z_][\w.\-]*(?::[A-Za-z_][\w.\-]*)?)\s*>/y;
  function attrsOf(s) {
    const a = {};
    if (!s) return a;
    for (const m of s.matchAll(/([A-Za-z_][\w.\-:]*)\s*=\s*(?:"([^"]*)"|'([^']*)')/g)) a[m[1]] = decodeEntities(m[2] ?? m[3]);
    return a;
  }
  // calls on.open(name, attrs, empty), on.close(name), on.text(text)
  function scanXml(xml, on) {
    let i = 0;
    const n = xml.length;
    let depth = 0;
    while (i < n) {
      const lt = xml.indexOf("<", i);
      if (lt < 0) { if (xml.slice(i).trim()) refuse("corrupt"); break; }
      if (lt > i && depth > 0) on.text(decodeEntities(xml.slice(i, lt)));
      if (xml.startsWith("<!--", lt)) { const e = xml.indexOf("-->", lt + 4); if (e < 0) refuse("corrupt"); i = e + 3; continue; }
      if (xml.startsWith("<?", lt)) { const e = xml.indexOf("?>", lt + 2); if (e < 0) refuse("corrupt"); i = e + 2; continue; }
      if (xml.startsWith("<![CDATA[", lt)) { const e = xml.indexOf("]]>", lt + 9); if (e < 0) refuse("corrupt"); if (depth > 0) on.text(xml.slice(lt + 9, e)); i = e + 3; continue; }
      if (xml.startsWith("<!", lt)) refuse("corrupt");                                              // DOCTYPE and declarations
      if (xml[lt + 1] === "/") {
        CLOSE.lastIndex = lt;
        const m = CLOSE.exec(xml);
        if (!m) refuse("corrupt");
        on.close(m[1]); depth--; i = CLOSE.lastIndex;
        if (depth < 0) refuse("corrupt");
        continue;
      }
      TAG.lastIndex = lt;
      const m = TAG.exec(xml);
      if (!m) refuse("corrupt");
      const empty = m[3] === "/";
      on.open(m[1], m[2], empty);
      if (empty) on.close(m[1]); else depth++;
      i = TAG.lastIndex;
    }
    if (depth !== 0) refuse("corrupt");
  }

  const W_NS = ["http://schemas.openxmlformats.org/wordprocessingml/2006/main", "http://purl.oclc.org/ooxml/wordprocessingml/main"];
  const MC_NS = "http://schemas.openxmlformats.org/markup-compatibility/2006";

  // ---- WordprocessingML to text: the document as it reads with every tracked change accepted ----------------------------------
  // Paragraph → line; w:br, w:cr → line break; w:tab → space; w:del and w:moveFrom (deleted / moved-away text) are left out and
  // w:ins, w:moveTo kept; field codes, mc:Fallback copies, properties and symbols are skipped; footnote and endnote marks are removed
  // from the text (their notes are listed at the end, see docxText). Text boxes are read where they are anchored.
  function wordText(xml, collectNotes) {
    let w = null, mc = null;                 // the prefixes bound to the WordprocessingML and markup-compatibility namespaces
    let skip = 0;                            // depth inside a skipped element
    let inText = false, inPPr = 0, markDeleted = false;   // inPPr: depth inside w:pPr (a w:pPrChange holds an older w:pPr)
    let out = [];
    const st = { tracked: false, refs: [], notes: new Map() };
    let note = null;                         // collecting a footnote / endnote: { id, kind, parts }
    const sink = () => (note ? note.parts : out);
    const wAttr = (a, k) => a[w ? `${w}:${k}` : k];
    const split = (name) => { const k = name.indexOf(":"); return k < 0 ? ["", name] : [name.slice(0, k), name.slice(k + 1)]; };
    const SKIP_W = new Set(["del", "moveFrom", "instrText", "delInstrText", "delText", "rPr", "sectPr", "sym", "footnotePr", "endnotePr", "tblPr", "trPr", "tcPr", "tblGrid"]);
    scanXml(xml, {
      open(name, attrStr, empty) {
        if (w === null) {                                                      // the root element declares the namespaces
          const a = attrsOf(attrStr);
          w = mc = undefined;
          for (const [k, v] of Object.entries(a)) {
            if (k !== "xmlns" && !k.startsWith("xmlns:")) continue;
            const prefix = k === "xmlns" ? "" : k.slice(6);
            if (W_NS.includes(v)) w = prefix;
            if (v === MC_NS) mc = prefix;
          }
          if (w === undefined) refuse("corrupt");
        }
        const [p, local] = split(name);
        // every element opened is closed by one call of close() (scanXml calls it for a self-closing one too), so each counts one level
        if (skip) { skip++; return; }
        if (p === mc && mc !== undefined && local === "Fallback") { skip = 1; return; }
        if (p !== w) return;
        if (inPPr) {
          if (local === "pPr") inPPr++;
          // a deleted paragraph mark: the paragraph runs on into the next one once the change is accepted
          if (local === "del" || local === "moveFrom") { markDeleted = true; st.tracked = true; }
          if (local === "ins" || local === "moveTo") st.tracked = true;
          return;
        }
        if (SKIP_W.has(local)) {
          if (local === "del" || local === "moveFrom") st.tracked = true;
          skip = 1;
          return;
        }
        switch (local) {
          case "pPr": inPPr = 1; break;
          case "ins": case "moveTo": st.tracked = true; break;
          case "t": if (!empty) inText = true; break;
          case "txbxContent": { const k = sink(); if (k.length && !k[k.length - 1].endsWith("\n")) k.push("\n"); break; }   // a text box is a block of its own
          case "tab": case "ptab": sink().push(" "); break;
          case "br": case "cr": sink().push("\n"); break;
          case "noBreakHyphen": sink().push("-"); break;
          case "footnoteReference": case "endnoteReference": {
            const a = attrsOf(attrStr);
            st.refs.push({ kind: local === "footnoteReference" ? "footnote" : "endnote", id: wAttr(a, "id") });
            break;
          }
          case "footnote": case "endnote": {
            if (!collectNotes) break;
            const a = attrsOf(attrStr);
            const type = wAttr(a, "type");
            if (type && type !== "normal") { skip = 1; break; }    // separators and continuation notices
            note = { kind: local, id: wAttr(a, "id"), parts: [] };
            break;
          }
          default: break;
        }
      },
      close(name) {
        if (skip) { skip--; return; }
        const [p, local] = split(name);
        if (p !== w) return;
        if (local === "pPr" && inPPr) { inPPr--; return; }
        if (inPPr) return;
        if (local === "t") inText = false;
        else if (local === "p") { if (!markDeleted) sink().push("\n"); markDeleted = false; }
        else if ((local === "footnote" || local === "endnote") && note) {
          st.notes.set(`${note.kind}:${note.id}`, note.parts.join("").trimEnd());
          note = null;
        }
      },
      text(s) { if (inText && !skip) sink().push(s); },
    });
    return { text: out.join(""), ...st };
  }

  // Notes: the footnotes, then the endnotes, in the order the text refers to them, each on its own line as "(n) text", after a separator
  // line at the end of the article. A note whose reference was deleted (tracked) is not listed, as in the accepted document.
  const NOTE_RULE = "__________";
  function withNotes(body, refs, notes) {
    const lines = [];
    const seen = new Set();
    for (const kind of ["footnote", "endnote"]) {
      for (const r of refs) {
        const key = `${r.kind}:${r.id}`;
        if (r.kind !== kind || seen.has(key) || !notes.has(key)) continue;
        seen.add(key);
        const t = notes.get(key).trimStart();
        if (t) lines.push(`(${lines.length + 1}) ${t}`);
      }
    }
    return { text: lines.length ? `${body.trimEnd()}\n\n${NOTE_RULE}\n${lines.join("\n")}` : body, count: lines.length };
  }

  async function fromDocx(b, name) {
    if (/\.docm$/i.test(name || "")) refuse("macro");
    const entries = readZip(b);
    const doc = entries.get("word/document.xml");
    if (!doc) refuse("zip_not_docx");
    if (entries.has("word/vbaProject.bin")) refuse("macro");
    const budget = { left: LIMITS.maxUnzipped };
    const ct = entries.get("[Content_Types].xml");
    if (ct && /macroEnabled/i.test(decodeXml(await inflate(b, ct, budget)))) refuse("macro");
    const body = wordText(decodeXml(await inflate(b, doc, budget)), false);
    const notes = new Map();
    for (const part of ["word/footnotes.xml", "word/endnotes.xml"]) {
      const e = entries.get(part);
      if (!e) continue;
      const r = wordText(decodeXml(await inflate(b, e, budget)), true);
      for (const [k, v] of r.notes) notes.set(k, v);
      if (r.tracked) body.tracked = true;
    }
    const joined = withNotes(body.text, body.refs, notes);
    return { kind: "docx", raw: joined.text, info: { tracked: body.tracked, notes: joined.count } };
  }

  // A Compound File (the Office 97 format): an encrypted DOCX is stored in one, as is an old .doc.
  function utf16Bytes(s) { const a = []; for (const ch of s) { const c = ch.charCodeAt(0); a.push(c & 0xff, c >> 8); } return a; }
  const ENC_NAME = utf16Bytes("EncryptedPackage");
  function hasBytes(b, sig) {
    outer: for (let i = 0; i + sig.length <= b.length; i++) {
      if (b[i] !== sig[0]) continue;
      for (let k = 1; k < sig.length; k++) if (b[i + k] !== sig[k]) continue outer;
      return true;
    }
    return false;
  }

  // ---- the whole path: bytes → text or a refusal -------------------------------------------------------------------------------
  // returns { ok: true, kind, text, chars, notes: { bom, crlf, controls, presentation, tracked, notes } }
  //      or { ok: false, code, message }
  async function extract(input, name, opts = {}) {
    const maxChars = opts.maxChars || LIMITS.maxChars;
    try {
      const b = input instanceof Uint8Array ? input : new Uint8Array(input);
      if (b.length > LIMITS.maxFileBytes) refuse("file_too_big");
      const kind = sniff(b);
      let got;
      switch (kind) {
        case "empty": refuse("empty"); break;
        case "zip": got = await fromDocx(b, name); break;
        case "cfb": refuse(hasBytes(b, ENC_NAME) ? "encrypted" : "doc_old"); break;
        case "pdf": refuse("pdf"); break;
        case "rtf": refuse("rtf"); break;
        case "png": case "jpeg": case "gif": case "webp": refuse("image", { kind: kind.toUpperCase() }); break;
        default: got = fromText(b, kind);
      }
      const c = clean(got.raw);
      if (!c.text.trim()) refuse("no_text");
      const chars = Array.from(c.text).length;
      if (chars > maxChars) refuse("too_long", { chars, max: maxChars });
      return { ok: true, kind: got.kind, text: c.text, chars, notes: { ...c.notes, tracked: !!got.info.tracked, notes: got.info.notes || 0 } };
    } catch (e) {
      const code = e instanceof ImportError ? e.code : "corrupt";
      const detail = e instanceof ImportError ? e.detail : {};
      return { ok: false, code, message: MESSAGES[code](detail) };
    }
  }

  // What the page says once the text is in the editor: one line, and everything that was changed.
  function noticeText(r, fileName) {
    // the name is isolated (U+2068 … U+2069) so that a Latin name such as «article.docx» keeps its order inside the Arabic sentence
    const parts = [`استُخرج النص من الملف «\u2068${fileName}\u2069»؛ راجعه قبل التدقيق.`];
    const n = r.notes || {};
    if (n.presentation) parts.push(`حُوِّل ${arNum(n.presentation)} من أشكال الحروف العربية المعروضة (مثل ﻻ) إلى حروفها الأساسية.`);
    if (n.tracked) parts.push("في الملف تعديلات متعقَّبة: أُخذ النص كما يُقرأ بعد قبولها.");
    if (n.notes) parts.push(`أُلحقت الحواشي (${arNum(n.notes)}) في آخر النص بعد خط فاصل، وحُذفت علامات الإحالة إليها من المتن.`);
    if (n.controls) parts.push(`حُذف ${arNum(n.controls)} من محارف التحكم غير المرئية.`);
    return parts.join(" ");
  }

  const api = { LIMITS, MESSAGES, NOTE_RULE, extract, clean, sniff, noticeText, arNum, crc32 };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.Importer = api;

  // As a Web Worker: one file in, one answer out. The page stops the worker if it takes longer than its time limit.
  if (typeof WorkerGlobalScope !== "undefined" && root instanceof WorkerGlobalScope) {
    root.onmessage = async (ev) => {
      const { id, file, maxChars } = ev.data || {};
      let res;
      try {
        if (!file || file.size > LIMITS.maxFileBytes) res = { ok: false, code: "file_too_big", message: MESSAGES.file_too_big() };
        else res = await extract(new Uint8Array(await file.arrayBuffer()), file.name, { maxChars });
      } catch {
        res = { ok: false, code: "corrupt", message: MESSAGES.corrupt() };
      }
      if (res.ok) res.notice = noticeText(res, file.name);
      root.postMessage({ id, ...res });
    };
  }
})(typeof self !== "undefined" ? self : globalThis);
