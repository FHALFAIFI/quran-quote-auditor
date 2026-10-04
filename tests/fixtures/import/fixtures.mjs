// Import fixtures, built in code (no binary file of unknown origin is committed): a tiny ZIP writer, a minimal DOCX builder and the
// list of cases with the text each must give, code point for code point, or the refusal it must give.
// Used by tests/import.test.mjs (Node) and scripts/ui_import_e2e.mjs (the same bytes through the page's real file input).
// `node tests/fixtures/import/fixtures.mjs <dir>` writes every fixture to <dir>, to try them by hand.
import zlib from "zlib";
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const enc = new TextEncoder();
const bytes = (x) => (typeof x === "string" ? enc.encode(x) : x);
const cat = (parts) => { const n = parts.reduce((s, p) => s + p.length, 0); const o = new Uint8Array(n); let i = 0; for (const p of parts) { o.set(p, i); i += p.length; } return o; };
const le = (n, size) => { const b = new Uint8Array(size); for (let i = 0; i < size; i++) b[i] = (n >>> (8 * i)) & 0xff; return b; };

// entries: [{ name, data, method = 8, flags = 0, usize (declared, to make a lying header), csize }]
export function zip(entries) {
  const locals = [], centrals = [];
  let offset = 0;
  for (const e of entries) {
    const raw = bytes(e.data);
    const method = e.method ?? 8;
    const comp = e.compressed ?? (method === 8 ? new Uint8Array(zlib.deflateRawSync(raw)) : raw);
    const name = enc.encode(e.name);
    const crc = e.crc ?? zlib.crc32(raw);
    const usize = e.usize ?? raw.length, csize = comp.length, flags = e.flags ?? 0;
    const head = [le(20, 2), le(flags, 2), le(method, 2), le(0, 2), le(0x21, 2), le(crc, 4), le(csize, 4), le(usize, 4), le(name.length, 2), le(0, 2)];
    const local = cat([le(0x04034b50, 4), ...head, name, comp]);
    centrals.push(cat([le(0x02014b50, 4), le(20, 2), ...head, le(0, 2), le(0, 2), le(0, 2), le(0, 4), le(offset, 4), name]));
    locals.push(local);
    offset += local.length;
  }
  const cd = cat(centrals);
  const end = cat([le(0x06054b50, 4), le(0, 2), le(0, 2), le(entries.length, 2), le(entries.length, 2), le(cd.length, 4), le(offset, 4), le(0, 2)]);
  return cat([...locals, cd, end]);
}

const W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main";
const NS = `xmlns:w="${W}" xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006" xmlns:wps="http://schemas.microsoft.com/office/word/2010/wordprocessingShape" xmlns:v="urn:schemas-microsoft-com:vml" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" mc:Ignorable="wps"`;
const CT = (extra = "") => `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>${extra}</Types>`;
const RELS = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>`;
export const docXml = (body) => `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<w:document ${NS}><w:body>${body}<w:sectPr><w:pgSz w:w="11906" w:h="16838"/></w:sectPr></w:body></w:document>`;
const P = (inner, ppr = "") => `<w:p><w:pPr><w:bidi/>${ppr}</w:pPr>${inner}</w:p>`;
const R = (t, rpr = "<w:rtl/>") => `<w:r><w:rPr>${rpr}</w:rPr><w:t xml:space="preserve">${t}</w:t></w:r>`;

export function docx(body, { footnotes, endnotes, contentTypes, extra = [], rawDocument } = {}) {
  const entries = [
    { name: "[Content_Types].xml", data: contentTypes ?? CT() },
    { name: "_rels/.rels", data: RELS },
    { name: "word/document.xml", data: rawDocument ?? docXml(body) },
  ];
  if (footnotes) entries.push({ name: "word/footnotes.xml", data: footnotes });
  if (endnotes) entries.push({ name: "word/endnotes.xml", data: endnotes });
  return zip([...entries, ...extra]);
}

const notesXml = (kind, notes) => `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:${kind}s ${NS}>`
  + `<w:${kind} w:type="separator" w:id="-1"><w:p><w:r><w:separator/></w:r></w:p></w:${kind}>`
  + `<w:${kind} w:type="continuationSeparator" w:id="0"><w:p><w:r><w:continuationSeparator/></w:r></w:p></w:${kind}>`
  + notes.map(([id, t]) => `<w:${kind} w:id="${id}">${P(`<w:r><w:rPr><w:rStyle w:val="FootnoteReference"/></w:rPr><w:${kind}Ref/></w:r>${R(" " + t)}`)}</w:${kind}>`).join("")
  + `</w:${kind}s>`;

// ---- the texts -------------------------------------------------------------------------------------------------------------------
const VERSE = "﴿وَاسْتَعِينُوا بِالصَّبْرِ وَالصَّلَاةِ﴾";
const ARTICLE = `قال تعالى: ${VERSE} [البقرة: 45]\nوقال الشاعر: «الصبــر مفتاح الفرج»، والتطويل هنا مقصود.\n\nفقرة ثالثة فيها ${"‏"}علامة اتجاه وتنوين: صبرًا جميلًا.`;

const W1256 = new Uint8Array([0xc7, 0xe1, 0xd5, 0xc8, 0xd1, 0x20, 0xe3, 0xdd, 0xca, 0xc7, 0xcd, 0x20, 0xc7, 0xe1, 0xdd, 0xd1, 0xcc]);   // «الصبر مفتاح الفرج» in Windows-1256
const PNG = new Uint8Array([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 0, 0, 0, 13, 0x49, 0x48, 0x44, 0x52, 0, 0, 0, 1, 0, 0, 0, 1, 8, 6, 0, 0, 0, 0x1f, 0x15, 0xc4, 0x89]);
const utf16le = (s) => { const o = [0xff, 0xfe]; for (let i = 0; i < s.length; i++) { const c = s.charCodeAt(i); o.push(c & 0xff, c >> 8); } return new Uint8Array(o); };
function cfb(withEncryption) {
  const b = new Uint8Array(4096);
  b.set([0xd0, 0xcf, 0x11, 0xe0, 0xa1, 0xb1, 0x1a, 0xe1]);
  const names = withEncryption ? ["EncryptionInfo", "EncryptedPackage"] : ["WordDocument", "1Table"];
  let at = 1024;
  for (const n of names) { b.set(utf16le(n).subarray(2), at); at += 128; }
  return b;
}
const long = (n) => { const unit = "الصبر مفتاح "; let s = ""; while (Array.from(s).length < n) s += unit; return Array.from(s).slice(0, n - 1).join("") + "."; };

// A document that uses what Word writes: runs split inside a word, a tab, a line break, tab stops (not text), a table, a hyperlink,
// a field (its code is not text, its result is), a text box written twice (mc:Choice and mc:Fallback: read once), a symbol.
const DOCX_QURAN_BODY = [
  P(`${R("قال تعالى: ")}${R("﴿وَاسْتَعِينُوا بِال", "<w:rtl/><w:b/>")}${R("صَّبْرِ وَالصَّلَاةِ﴾")}${R(" [البقرة: 45]")}`, `<w:tabs><w:tab w:val="right" w:pos="9000"/></w:tabs>`),
  P(`${R("قبل الجدولة")}<w:r><w:tab/></w:r>${R("بعدها")}<w:r><w:br/></w:r>${R("سطر بعد فاصل")}`),
  `<w:tbl><w:tblPr><w:bidiVisual/></w:tblPr><w:tblGrid><w:gridCol w:w="4000"/></w:tblGrid><w:tr><w:tc><w:tcPr><w:tcW w:w="4000"/></w:tcPr>${P(R("خلية: «الصبر»"))}</w:tc></w:tr></w:tbl>`,
  P(`<w:hyperlink r:id="rId9">${R("رابط لا يُفتح")}</w:hyperlink>${R(" ")}<w:r><w:fldChar w:fldCharType="begin"/></w:r><w:r><w:instrText xml:space="preserve"> PAGE </w:instrText></w:r><w:r><w:fldChar w:fldCharType="separate"/></w:r>${R("٣")}<w:r><w:fldChar w:fldCharType="end"/></w:r>`),
  P(`${R("نص")}<w:r><mc:AlternateContent><mc:Choice Requires="wps"><w:drawing><wps:txbx><w:txbxContent>${P(R("مربع نص"))}</w:txbxContent></wps:txbx></w:drawing></mc:Choice><mc:Fallback><w:pict><v:textbox><w:txbxContent>${P(R("مربع نص"))}</w:txbxContent></v:textbox></w:pict></mc:Fallback></mc:AlternateContent></w:r>${R(" بعده")}<w:r><w:sym w:font="Wingdings" w:char="F04A"/></w:r>`),
  P(R("&lt;علامات&gt; &amp; &#1589;&#x0628;ر")),
].join("");
const DOCX_QURAN_TEXT = `قال تعالى: ${VERSE} [البقرة: 45]\nقبل الجدولة بعدها\nسطر بعد فاصل\nخلية: «الصبر»\nرابط لا يُفتح ٣\nنص\nمربع نص\n بعده\n<علامات> & صبر`;

const DOCX_TRACKED_BODY = [
  P(`${R("قال تعالى: ﴿")}<w:del w:id="1" w:author="A" w:date="2026-10-04T00:00:00Z"><w:r><w:delText>واصبروا</w:delText></w:r></w:del><w:ins w:id="2" w:author="A" w:date="2026-10-04T00:00:00Z">${R("وَاسْتَعِينُوا")}</w:ins>${R(" بِالصَّبْرِ﴾")}`),
  // a paragraph whose mark was deleted runs on into the next one
  P(R("سطر أول "), `<w:rPr><w:del w:id="3" w:author="A" w:date="2026-10-04T00:00:00Z"/></w:rPr>`),
  P(R("يكمله سطر ثانٍ")),
  P(`<w:moveFrom w:id="4" w:author="A" w:date="2026-10-04T00:00:00Z">${R("نُقل من هنا")}</w:moveFrom>${R("ثابت")}<w:moveTo w:id="5" w:author="A" w:date="2026-10-04T00:00:00Z">${R(" نُقل إلى هنا")}</w:moveTo>`),
  // an older paragraph format kept by Word (w:pPrChange holds its own w:pPr): not text
  P(R("فقرة غيّر شكلها"), `<w:pPrChange w:id="6" w:author="A" w:date="2026-10-04T00:00:00Z"><w:pPr><w:jc w:val="center"/></w:pPr></w:pPrChange>`),
].join("");
const DOCX_TRACKED_TEXT = "قال تعالى: ﴿وَاسْتَعِينُوا بِالصَّبْرِ﴾\nسطر أول يكمله سطر ثانٍ\nثابت نُقل إلى هنا\nفقرة غيّر شكلها";

const fnRef = (id) => `<w:r><w:rPr><w:rStyle w:val="FootnoteReference"/></w:rPr><w:footnoteReference w:id="${id}"/></w:r>`;
const DOCX_FOOTNOTES_BODY = [
  P(`${R("الصبر")}${fnRef(2)}${R(" وهو خلق عظيم، قال تعالى: ﴿إِنَّ اللَّهَ مَعَ الصَّابِرِينَ﴾")}${fnRef(1)}`),
  P(`${R("والشكر")}<w:r><w:endnoteReference w:id="1"/></w:r>${R(" قرين الصبر.")}`),
  P(`<w:del w:id="9" w:author="A" w:date="2026-10-04T00:00:00Z">${fnRef(3)}</w:del>${R("آخر")}`),
].join("");
const FOOTNOTES = notesXml("footnote", [["1", "سورة البقرة: 153."], ["2", "الصبر لغةً: الحبس."], ["3", "حاشية حُذفت إحالتها."]]);
const ENDNOTES = notesXml("endnote", [["1", "تعليق ختامي."]]);
const DOCX_FOOTNOTES_TEXT = "الصبر وهو خلق عظيم، قال تعالى: ﴿إِنَّ اللَّهَ مَعَ الصَّابِرِينَ﴾\nوالشكر قرين الصبر.\nآخر\n\n__________\n(1) الصبر لغةً: الحبس.\n(2) سورة البقرة: 153.\n(3) تعليق ختامي.";

// Self-closing elements inside skipped ones (Word's run properties, the VML shape type of a text box's fallback copy): each must count
// as one opened and one closed element, or the skipped text leaks back (found by an independent review of this code, 4 Oct).
const TRK = 'w:author="A" w:date="2026-10-04T00:00:00Z"';
const DOCX_SELFCLOSING_BODY = [
  P(`${R("قبل")}<w:r><mc:AlternateContent><mc:Choice Requires="wps"><w:drawing><wps:txbx><w:txbxContent>${P(R("صندوق"))}</w:txbxContent></wps:txbx></w:drawing></mc:Choice><mc:Fallback><w:pict><v:shapetype id="t202" coordsize="21600,21600"><v:stroke joinstyle="miter"/><v:path gradientshapeok="t"/></v:shapetype><v:shape type="#t202"><v:textbox><w:txbxContent>${P(R("صندوق"))}</w:txbxContent></v:textbox></v:shape></w:pict></mc:Fallback></mc:AlternateContent></w:r>${R("بعد")}`),
  P(`<w:moveFrom w:id="1" ${TRK}><w:r><w:rPr><w:rFonts w:cs="Arial"/><w:sz w:val="28"/><w:rtl/></w:rPr><w:t>منقول</w:t></w:r></w:moveFrom>${R("باق")}`),
  P(`${R("أ")}<w:del w:id="2" ${TRK}><w:r><w:rPr><w:b/><w:i/></w:rPr><w:tab/><w:br/></w:r></w:del>${R("ب")}`),
  P(`${R("حاشية")}<w:del w:id="3" ${TRK}><w:r><w:rPr><w:rStyle w:val="FootnoteReference"/><w:rtl/></w:rPr><w:footnoteReference w:id="1"/></w:r></w:del>${fnRef(2)}`),
  P(R("سطر "), `<w:rPr><w:moveFrom w:id="4" ${TRK}/></w:rPr>`),
  P(R("يتبعه")),
  `<w:p><w:pPr/>${R("فقرة بخصائص فارغة")}</w:p>`,
].join("");
const SELFCLOSING_NOTES = notesXml("footnote", [["1", "حاشية محذوفة"], ["2", "حاشية باقية"]]);
const DOCX_SELFCLOSING_TEXT = "قبل\nصندوق\nبعد\nباق\nأب\nحاشية\nسطر يتبعه\nفقرة بخصائص فارغة\n\n__________\n(1) حاشية باقية";

// Presentation forms (as some converters store them): replaced by letters; ﴿ ﴾ and the word ligature ﷺ kept as written.
const PRES = "ﻗﺎﻝ ﺗﻌﺎﻟﻰ: ﴿ﺇﻥ ﺍﻟﻠﻪ ﻣﻊ ﺍﻟﺼﺎﺑﺮﻳﻦ﴾ ﻻ ﷺ";
const PRES_TEXT = "قال تعالى: ﴿إن الله مع الصابرين﴾ لا ﷺ";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const office = (name) => new Uint8Array(fs.readFileSync(path.join(HERE, "office", name)));

let bombCache = null;
const bomb = () => (bombCache ??= new Uint8Array(zlib.deflateRawSync(Buffer.alloc(50 * 1024 * 1024), { level: 9 })));
const bombCrc = () => zlib.crc32(Buffer.alloc(50 * 1024 * 1024));

// Every case: name (the file name given to the page), make() → bytes, and either text (exact) or code (the refusal).
// notes: the counts the result must report (only the listed keys are checked).
export const FIXTURES = [
  { id: "txt-arabic", name: "مقال.txt", make: () => bytes(ARTICLE), text: ARTICLE, notes: { presentation: 0, bom: 0, crlf: 0 } },
  { id: "txt-bom-crlf", name: "bom-crlf.txt", make: () => bytes("﻿" + ARTICLE.replace(/\n/g, "\r\n") + "\r\n"), text: ARTICLE, notes: { bom: 1, crlf: 4 } },
  { id: "txt-controls", name: "controls.txt", make: () => bytes("الصبر\u0007 مفتاح\u001B الفرج\u0085"), text: "الصبر مفتاح الفرج", notes: { controls: 3 } },
  { id: "txt-utf16", name: "utf16.txt", make: () => utf16le(ARTICLE), text: ARTICLE },
  { id: "txt-presentation", name: "presentation.txt", make: () => bytes(PRES), text: PRES_TEXT, notes: { presentation: 25 } },
  { id: "txt-1256", name: "windows-1256.txt", make: () => W1256, code: "not_utf8" },
  { id: "txt-nul", name: "nul.txt", make: () => bytes("الصبر\u0000مفتاح"), code: "binary" },
  { id: "png-renamed", name: "صورة.txt", make: () => PNG, code: "image" },
  { id: "gzip-renamed", name: "data.txt", make: () => new Uint8Array(zlib.gzipSync(Buffer.from("x".repeat(64)))), code: "binary" },
  { id: "zip-renamed", name: "archive.txt", make: () => zip([{ name: "notes.txt", data: "نص" }]), code: "zip_not_docx" },
  { id: "pdf", name: "article.pdf", make: () => bytes("%PDF-1.7\n%âãÏÓ\n1 0 obj\n<<>>\nendobj\n"), code: "pdf" },
  { id: "txt-20000", name: "20000.txt", make: () => bytes(long(20000)), text: long(20000) },
  { id: "txt-20001", name: "20001.txt", make: () => bytes(long(20001)), code: "too_long" },
  { id: "txt-empty", name: "empty.txt", make: () => new Uint8Array(0), code: "empty" },
  { id: "txt-blank", name: "blank.txt", make: () => bytes(" \r\n\t\r\n"), code: "no_text" },
  { id: "docx-quran", name: "مقال.docx", make: () => docx(DOCX_QURAN_BODY), text: DOCX_QURAN_TEXT, notes: { tracked: false, notes: 0 } },
  { id: "docx-tracked", name: "tracked.docx", make: () => docx(DOCX_TRACKED_BODY), text: DOCX_TRACKED_TEXT, notes: { tracked: true } },
  { id: "docx-footnotes", name: "footnotes.docx", make: () => docx(DOCX_FOOTNOTES_BODY, { footnotes: FOOTNOTES, endnotes: ENDNOTES }), text: DOCX_FOOTNOTES_TEXT, notes: { notes: 3, tracked: true } },
  { id: "docx-selfclosing", name: "selfclosing.docx", make: () => docx(DOCX_SELFCLOSING_BODY, { footnotes: SELFCLOSING_NOTES }), text: DOCX_SELFCLOSING_TEXT, notes: { tracked: true, notes: 1 } },
  { id: "docx-presentation", name: "presentation.docx", make: () => docx(P(R(PRES))), text: PRES_TEXT, notes: { presentation: 25 } },
  { id: "docx-stored", name: "stored.docx", make: () => zip([{ name: "[Content_Types].xml", data: CT(), method: 0 }, { name: "word/document.xml", data: docXml(P(R("محفوظ دون ضغط"))), method: 0 }]), text: "محفوظ دون ضغط" },
  { id: "docx-corrupt", name: "corrupt.docx", make: () => cat([new Uint8Array([0x50, 0x4b, 0x03, 0x04]), bytes("ليس ملفًّا مضغوطًا".repeat(20))]), code: "corrupt" },
  { id: "docx-truncated", name: "truncated.docx", make: () => { const d = docx(DOCX_QURAN_BODY); return d.subarray(0, Math.floor(d.length / 2)); }, code: "corrupt" },
  { id: "docx-bad-crc", name: "bad-crc.docx", make: () => zip([{ name: "word/document.xml", data: docXml(P(R("نص"))), crc: 12345 }]), code: "corrupt" },
  { id: "docx-doctype", name: "doctype.docx", make: () => docx("", { rawDocument: `<?xml version="1.0"?><!DOCTYPE w:document [<!ENTITY a "aaaaaaaaaa"><!ENTITY b "&a;&a;&a;&a;&a;&a;&a;&a;&a;&a;">]><w:document ${NS}><w:body>${P(R("&b;"))}</w:body></w:document>` }), code: "corrupt" },
  { id: "zip-no-document", name: "no-document.docx", make: () => zip([{ name: "[Content_Types].xml", data: CT() }, { name: "word/styles.xml", data: "<w:styles/>" }]), code: "zip_not_docx" },
  { id: "docx-encrypted-entry", name: "encrypted-entry.docx", make: () => zip([{ name: "[Content_Types].xml", data: CT() }, { name: "word/document.xml", data: docXml(P(R("سر"))), flags: 1 }]), code: "encrypted" },
  { id: "ole-encrypted", name: "protected.docx", make: () => cfb(true), code: "encrypted" },
  { id: "ole-doc", name: "old.doc", make: () => cfb(false), code: "doc_old" },
  { id: "docm", name: "macros.docx", make: () => docx(P(R("نص")), { extra: [{ name: "word/vbaProject.bin", data: new Uint8Array([1, 2, 3]) }] }), code: "macro" },
  { id: "docm-type", name: "macros2.docx", make: () => docx(P(R("نص")), { contentTypes: CT().replace("document.main+xml", "document.macroEnabled.main+xml").replace("wordprocessingml.document.macro", "ms-word.document.macro") }), code: "macro" },
  { id: "zip-bomb", name: "bomb.docx", make: () => zip([{ name: "[Content_Types].xml", data: CT() }, { name: "word/document.xml", data: new Uint8Array(0), compressed: bomb(), usize: 50 * 1024 * 1024, crc: bombCrc() }]), code: "unzipped_too_big" },
  { id: "zip-bomb-lying", name: "bomb-lying.docx", make: () => zip([{ name: "[Content_Types].xml", data: CT() }, { name: "word/document.xml", data: new Uint8Array(0), compressed: bomb(), usize: 900 * 1024, crc: 0 }]), code: "corrupt" },
  // made by real word processors from our own text (see office/make.sh): LibreOffice and macOS textutil
  { id: "lo-docx", name: "lo-article.docx", make: () => office("lo-article.docx"), notes: { tracked: true, notes: 1 },
    text: "قال تعالى: ﴿وَاسْتَعِينُوا بِالصَّبْرِ وَالصَّلَاةِ﴾ [البقرة: 45]\nالصبر مفتاح الفرج، والتطويل: الصبــــر.\n«سطر بعد فاصل»\n\nفقرة بعد سطر فارغ.\n\n__________\n(1) الصبر لغةً: الحبس." },
  { id: "textutil-docx", name: "textutil-article.docx", make: () => office("textutil-article.docx"),
    text: "قال تعالى: ﴿إِنَّ اللَّهَ مَعَ الصَّابِرِينَ﴾ [البقرة: 153]\n«الصبر» مفتاح الفرج." },
];

// `node fixtures.mjs <dir>`: write every fixture to a folder
if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const dir = process.argv[2];
  if (!dir) { console.error("usage: node tests/fixtures/import/fixtures.mjs <dir>"); process.exit(2); }
  fs.mkdirSync(dir, { recursive: true });
  for (const f of FIXTURES) fs.writeFileSync(path.join(dir, `${f.id}-${f.name}`), f.make());
  console.log(`${FIXTURES.length} fixtures written to ${dir}`);
}
