# First-time Arabic writer pilot (kit)

**Status (4 Oct 2026, challenge period): Not tested with users. No participant has been recruited or contacted.**
This file is a kit for the owner to run a study later. Nothing in it has happened, and nothing in it may be sent
without the owner's authorisation.

This kit is the study that the "Interface sign-off" gate in [PRODUCTION_ROADMAP.md](PRODUCTION_ROADMAP.md) (Stage 4)
asks for: at least five Arabic writers, not the author, on their own articles, with tasks, times and failures recorded.
It replaces the synthetic-article plan in [UX_REVIEW_PLAN.md](UX_REVIEW_PLAN.md) for that gate and keeps its questions
about the interface states. The recording sheet is [WRITER_PILOT_SHEET.csv](WRITER_PILOT_SHEET.csv); the issue
template is [`.github/ISSUE_TEMPLATE/pilot_observation.md`](../.github/ISSUE_TEMPLATE/pilot_observation.md).

Participant-facing text is in Arabic; instructions to the moderator are in English. Placeholders the owner must fill
are written `[OWNER: …]`. No name, contact, date or reward is invented here.

---

## 1. Purpose and the rule about what counts

**Purpose.** Find out where a writer who has never seen the tool gets stuck, misunderstands a state, or is misled,
while doing the real job on their own text: writing, inserting a verse, checking quotations, deciding, and copying the
result.

**What is tested**

- whether a first-time writer can complete the seven tasks in §4 without help;
- whether they read the states correctly: a matched quotation, a «possible» phrase, an unsettled boundary, an approved
  correction, a quotation kept as written;
- whether they understand what the language model does and does not do, and what happens to their text.

**What is not tested**

- detection accuracy, recall or correction accuracy (five people find usability problems; they do not give accuracy
  rates; see §7);
- time saved against manual checking (no comparison condition is run);
- the language model's benefit (not measured; on the live service it may or may not answer during a session);
- accessibility with assistive technology (a separate gate);
- satisfaction or "would you recommend" scores (not collected).

**Only real participants count.** A result comes only from a session with a real person who meets §2 and who gave
consent under §3. The following are **not results** and must never be reported as pilot findings:

- walkthroughs or "simulated users" produced by an assistant (Claude or any other model);
- browser automation (Playwright or similar), axe runs, screenshots;
- invented, composite or paraphrased participants;
- the author, or anyone who helped build or review the interface, as a participant.

Those activities may find bugs, and their findings go to `docs/TEST_LOG.md` under their own names, never into this
study's counts.

---

## 2. Participants and recruitment

**Who.** Five people who write or edit Arabic articles or posts that quote the Quran (columnists, content editors,
proofreaders, social-media editors), who have not used this interface and did not take part in building it. Not the
author.

**Material.** Each participant brings one or two of **their own published articles**, or articles they hold the rights
to use, that contain Quran quotations; ideally one of up to 6,000 characters and one longer (6,001–20,000), since the
app treats them differently (§3). **An unpublished draft is used only with the participant's explicit agreement**,
after the data-handling script has been read, because the text leaves their device when audited.

**Backup material** (only when a participant's own article cannot exercise a task; recorded as such in the sheet): the
built-in demonstration article («جرّب المقال التجريبي», it contains one wrong word and one wrong reference) for task 5,
and the sample «مثال: مقال بلا أقواس» for task 4. Results on backup material are reported separately.

**Before recruiting, the owner decides** (and writes the decision in the session log):

1. which service the sessions use: the live service (the model is configured: audits of articles up to 6,000
   characters are sent to Groq automatically), or an instance with no model. The consent text in §3 is written for the
   live service; for an instance with no model, use the alternative sentence given there;
2. who moderates and who takes notes (ideally two people, neither the participant's manager);
3. whether any reward is offered (none is promised in the text below);
4. who holds the notes, for how long, and the contact for withdrawal.

### Recruitment message (Arabic)

> **لا تُرسل قبل موافقة المالك** — not to be sent without the owner's authorisation.

```text
السلام عليكم ورحمة الله وبركاته،

أعمل على أداة عربية تجريبية تساعد الكتّاب والمحررين على مراجعة الآيات المقتبسة في مقالاتهم؛ إذ تقارن ألفاظ الآية وإحالتها (اسم السورة ورقم الآية) بنص مصحف حفص في موقع «قرآنبيديا»، وتقترح التصحيح، ولا تغيّر حرفًا في المقال إلا بموافقة الكاتب.

وأبحث عن خمسة كتّاب أو محررين يكتبون بالعربية ولم يستخدموا الأداة من قبل، للمشاركة في جلسة تجربة واحدة مدتها نحو ساعة [OWNER: حضوريًا / عن بُعد، والموعد المقترح].

ستعمل في الجلسة على مقال من مقالاتك المنشورة، أو مقال تملك حق استخدامه، يتضمن آيات قرآنية. ولا نستخدم مسودة غير منشورة إلا إذا وافقتَ على ذلك صراحةً بعد أن نوضح لك أين يُرسَل نصها.

الغرض من الجلسة اختبار الأداة لا اختبارك: نريد أن نعرف أين تتعثر الواجهة وما الذي يُفهم منها على غير وجهه. ونسجّل ملاحظات مكتوبة عن إنجاز المهام ومدتها ومواضع الالتباس، ولا نحتفظ بنص مقالك ولا نسجّل الشاشة إلا بإذن منك.

المشاركة تطوعية [OWNER: تُذكر المكافأة هنا إن قُررت، وإلا يُحذف هذا القوس]، ويحق لك الانسحاب في أي وقت دون إبداء سبب.

إن رغبت في المشاركة أو أردت مزيدًا من التفاصيل، يسعدني تواصلك عبر [OWNER: وسيلة التواصل].

مع خالص الشكر والتقدير،
[OWNER: الاسم]
```

---

## 3. Consent and data handling (read aloud or shown before anything else)

**Moderator.** On the day of each session, open `/privacy` on the service being used and check that the paragraph
«أين يذهب نص مقالك» below still matches it. It was matched on 4 Oct 2026 against `app/static/privacy.html` («راجعنا
هذه الصفحة على الشيفرة في ٤ أكتوبر ٢٠٢٦»). If the page has changed, update this script before the session, not during it.

### Script (Arabic)

```text
شكرًا لحضورك. قبل أن نبدأ، أقرأ عليك ما سنفعله في هذه الجلسة وما يحدث للبيانات، ثم أسألك عن موافقتك.

الغرض
نختبر أداة لمراجعة الآيات المقتبسة في المقالات العربية. الذي يخضع للاختبار هو الأداة لا أنت؛ فإن تعثرتَ في شيء، فذلك يعني أن الواجهة تحتاج إلى تحسين. ولن أشرح لك الأداة أثناء المهام، لأننا نريد أن نرى ما يحدث حين يستخدمها شخص لأول مرة.

ما نسجّله
- هل أنجزتَ كل مهمة: أنجزتَها، أو أنجزتَها بمساعدة، أو لم تُنجزها.
- الوقت الذي استغرقته كل مهمة.
- المواضع التي توقفتَ عندها أو التبس عليك فيها شيء، بوصف مختصر لما ظهر على الشاشة.
- أعدادًا فقط: كم آية لم تلتقطها الأداة، وكم عبارة عرضتها الأداة على أنها «محتملة» وليست اقتباسًا، وكم تصحيحًا مقترحًا كان خاطئًا.
- إجابتك عن سؤالين في آخر الجلسة، وبيانات عامة: دورك المهني ونوع الجهاز والمتصفح.
وتُحفظ الملاحظات برمز مثل (م١) لا باسمك.

ما لا نسجّله
- لا نحتفظ بنص مقالك ولا بمقاطع منه في الملاحظات، إلا إذا وافقتَ على ذلك صراحةً أدناه.
- لا نسجّل الشاشة ولا الصوت ولا الصورة، إلا إذا وافقتَ على ذلك صراحةً أدناه.
- لا نسجّل اسمك مقرونًا بالنتائج.

أين يذهب نص مقالك
- حين تضغط «دقّق الاقتباسات» أو «أعد التدقيق» أو «افحص المحدَّد» يُرسَل نص المقال كاملًا إلى خادم الأداة (المستضاف على منصة Render)، ويُعالَج في ذاكرة الخادم أثناء الطلب فقط، ولا يُكتب في ملف أو قاعدة بيانات ولا في سجل التطبيق.
- وفي «دقّق الاقتباسات» و«أعد التدقيق» (لا في «افحص المحدَّد»)، إذا كان المقال لا يتجاوز ٦٬٠٠٠ حرف، يُرسَل نصه كاملًا أيضًا، تلقائيًا، إلى شركة Groq، وهي مزوّد النموذج اللغوي، لاقتراح مواضع الاقتباس. ولا يمكن تعطيل ذلك في تدقيق بعينه. وتقول Groq في صفحة بياناتها إنها لا تحتفظ بطلبات الاستدلال افتراضيًا، وإنها قد تحتفظ ببيانات مؤقتًا لأغراض الموثوقية ومراقبة إساءة الاستخدام (حتى ٣٠ يومًا) ما لم يُفعَّل خيار «عدم الاحتفاظ». ولا نملك التحكم في ذلك، ولا نعرف إعداد حساب الخدمة لديها.
- أما المقال الذي يزيد على ٦٬٠٠٠ حرف فلا يُرسَل إلى Groq، ويُدقَّق بالعلامات والبحث في نص المصحف فقط.
- وفي اقتراح الآية أثناء الكتابة لا يُرسَل إلى خادم الأداة إلا الكلمات القريبة من المؤشر (حتى ٧٠٠ حرف قبله و١٠٠ حرف بعده)، ولا يُستعمل في ذلك نموذج لغوي. ولا يُرسَل شيء أثناء الكتابة العادية إلا بعد عبارة مثل «قال تعالى» أو داخل علامات الاقتباس، أو حين تطلب ذلك بنفسك.
- يبقى مقالك وقراراتك في تبويب المتصفح الحالي حتى تغلقه أو تضغط «مسح»، ولا يُحفظ في المتصفح بعد ذلك إلا إذا اخترتَ حفظ المسودة. وسنمسح ذلك كله في نهاية الجلسة.
- لا تُنشئ الأداة حسابات ولا تستعمل ملفات تعريف الارتباط. ويطلب تحميل الصفحة الخطوط من خوادم جوجل، فيصلها عنوان جهازك ومعلومات المتصفح، لا نص المقال. وللمستضيف Render سجلاته الخاصة خارج تحكمنا.
- إن لم يكن مسموحًا لك بإرسال مقال ما إلى خدمة خارجية، فلا نستخدمه في الجلسة.

حقك في الانسحاب
يمكنك أن توقف الجلسة في أي لحظة، أو أن تتخطى أي مهمة أو سؤال، دون إبداء سبب. ويمكنك بعد الجلسة أن تطلب حذف ملاحظاتك بمراسلة [OWNER: وسيلة التواصل] قبل [OWNER: تاريخ إعداد التقرير]؛ وبعد ذلك التاريخ لا تبقى في التقرير إلا أعداد مجمّعة لا تدل عليك.

من يحتفظ بالملاحظات ومدة الحفظ
يحتفظ بالملاحظات [OWNER: الاسم أو الجهة]، ولا يطّلع عليها إلا [OWNER: من يطّلع عليها]، وتُحذف الملاحظات التفصيلية بعد [OWNER: مدة الحفظ]، ويبقى التقرير المجمّع وحده.

هل لديك سؤال قبل أن نبدأ؟
```

**Alternative paragraph** if the sessions use an instance with no model configured (replace the second and third
bullets of «أين يذهب نص مقالك»; check that the page itself says «لا نموذج لغوي مهيّأ على هذا الخادم»):

```text
- الخادم المستخدم في هذه الجلسة ليس مهيّأً بنموذج لغوي، فلا يُرسَل مقالك عند التدقيق إلى أي جهة خارجية.
```

### Consent record (one per participant; the moderator ticks what the participant says)

```text
رمز المشارك: (م_)        التاريخ: [__/__/____]        الخدمة المستخدمة: [الحية / دون نموذج]

[ ] أوافق على المشاركة في الجلسة وعلى تسجيل الملاحظات المكتوبة الموضحة أعلاه.
[ ] أوافق على استخدام مسودة غير منشورة في الجلسة، وقد فهمتُ أين يُرسَل نصها.      (اختياري)
[ ] أوافق على الاحتفاظ بمقاطع قصيرة من نص مقالي في الملاحظات.                    (اختياري)
[ ] أوافق على تسجيل الشاشة دون صوت ولا صورة.                                       (اختياري)
[ ] أوافق على اقتباس عبارات قلتُها في التقرير دون ذكر اسمي.                          (اختياري)

طريقة الموافقة: [توقيع / موافقة شفهية سجّلها المشرف]
```

---

## 4. Session script (about 60 minutes)

### Before each session (moderator checklist)

- Note the build: open `/api/health` and copy the `build` commit into the sheet. All five sessions should use the same
  build; if it changes between sessions, say so in the report.
- Use a fresh browser profile or a private window (no saved draft, no earlier decisions). Record device, browser and
  screen width.
- Have the participant's article ready on their own device or clipboard. Read the published article beforehand and
  count its Quran quotations (keep the count only), so missed quotations can be counted in task 3.
- Have the backup material in mind (§2), the timer, the sheet and the consent record. No screen recording unless ticked.
- On Render Free the first request after idle can take about a minute: open the page yourself a few minutes before the
  session so the participant's first wait is not a cold start, and note if it was.

### Help protocol and neutral prompts

Do not explain the interface during a task. If the participant asks a question, reflect it back. Give help only when
the participant is stuck for about **3 minutes** or asks the same question twice; the first help is the smallest
possible hint, and the task is then recorded as «done with help».

Neutral prompts (use these; avoid leading ones):

| Use | Avoid |
|---|---|
| «ماذا تتوقع أن يحدث الآن؟» | «اضغط على الزر الأخضر» |
| «حدّثني بما تفكر فيه.» | «هل كان ذلك سهلًا؟» |
| «ما الذي تراه في هذا الجزء من الشاشة؟» | «هذا يعني أن الآية صحيحة، أليس كذلك؟» |
| «كيف تعرف أنك انتهيت من هذه المهمة؟» | «لاحظ هذه الرسالة» |
| «لو كنتَ وحدك الآن، ماذا كنتَ ستفعل؟» | «لا تقلق، الكل يخطئ هنا» |
| «ماذا يعني لك هذا الوصف؟» | تسمية الزر أو الحالة قبل أن يذكرها المشارك |

### Opening (Arabic, read aloud)

```text
سأعطيك سبع مهام قصيرة، أقرأ كل واحدة منها عليك وأتركها مكتوبة أمامك. حاول إنجازها كما لو كنتَ تعمل وحدك، وفكّر بصوت مسموع إن استطعت. لا توجد إجابة خاطئة؛ وإن قررتَ أن تتوقف عن مهمة، فقل ذلك وننتقل إلى التي تليها.
```

Warm-up (no notes beyond role): «كيف تتحقق اليوم من الآيات في مقالاتك قبل النشر؟»

### Tasks

Read each task card aloud and leave it in view. The cards describe the goal, not the controls.

#### Task 1 — Start an article

Card: «ابدأ مقالك في هذه الأداة: الصق مقالك [الأقصر] أو اكتب بدايته.»

- **Success:** the article text is in the writing box («مقالك») and the participant knows it is there to be edited.
- **Observe:** where they look first; whether they notice the note under the box about where the text is sent and the
  link to the privacy page; whether the explanatory line or «جرّب المقال التجريبي» distracts them; the character counter.

#### Task 2 — Insert a verse suggestion

Card: «أضف إلى مقالك آيةً تعرف أولها، ولا تنسخها من مصدر آخر.»

- **Success:** they insert words offered by the suggestion box (Tab, a click or a tap on «أدرج»), and can say which
  surah and ayah the inserted words come from.
- **Observe:** whether they notice the box at all, or type the whole verse from memory (record that as «not done:
  suggestion unnoticed», not as a failure of the participant); whether they understand it stops at a pause sign and
  that more can follow; what they do when an opening is shared by many verses and the box asks for another word;
  whether the box hides the line they are typing; whether they think a model wrote the suggestion.

#### Task 3 — Audit a long article

Card: «الصق الآن مقالك الأطول، واطلب من الأداة مراجعة الآيات فيه، ثم أخبرني بما وجدته.»

- **Success:** the audit finishes and the participant reaches the first item that needs their decision, and can say
  roughly how many items wait for them.
- **Record:** article length bucket (≤ 6,000 / 6,001–20,000 characters); **time to first useful result** (from pressing
  «دقّق الاقتباسات» to the moment they start reading the first decision card); the number of quotations they say the
  tool missed (ask at the end of the task: «هل في مقالك آية لم تظهر في القائمة؟», and compare with your count).
- **Observe:** whether the wait is understood; whether they read the summary line and the model-state line; whether
  they find the list of quotations; what they think «مطابق للمصحف» certifies.

#### Task 4 — Settle an uncertain quotation

Card: «ابحث عن موضع تقول الأداة إنها غير متأكدة منه، واحسمه بما تراه صحيحًا.»

Uses whichever appears: a boundary question («أين يبدأ الاقتباس؟» / «أين ينتهي الاقتباس؟»), a «possible» phrase
(«يحتاج تأكيدك», «هل قصدتَ هذه الآية؟»), or an optional phrase under «عبارات للتأكيد (اختياري)». If the participant's
article has none, use the backup sample «مثال: مقال بلا أقواس» and record the material.

- **Success:** the decision they make matches what they intend (ask: «ماذا قررتَ هنا، ولماذا؟»); a phrase that is not a
  quotation is not confirmed as one; a boundary is set where they meant it.
- **Record:** the number of «possible» or optional phrases the participant says are not quotations (unwanted «possible»).
- **Observe:** whether they understand that a «possible» phrase gets no replacement text until they confirm it;
  whether they read an optional phrase as an error; whether «أبقيتَه كما كتبتَ» is read as "the tool verified it".

#### Task 5 — Approve a correction, then undo it

Card: «اعتمد أحد التصحيحات المقترحة، ثم أعد النص كما كان قبل الاعتماد، كأنك غيّرت رأيك.»

If the participant's articles contain no wrong quotation, use the demonstration article and record the material.

- **Success:** one correction approved, then undone, and the article shows the original words again; the participant
  can say which words would have changed.
- **Record:** every proposed correction the participant or moderator judges wrong (it would change correct text, or
  replace it with something that is not the source's text, or point to the wrong verse). **Any wrong correction is
  severity 1**, whether or not it was approved.
- **Observe:** whether they read the struck words and the source text drawn above them; whether they find a way back
  (the approval button again, «تراجع», or «تراجع عنه» in the final review); whether they think the article was
  rewritten without their consent.

#### Task 6 — Inspect the final article

Card: «قبل أن تنقل المقال إلى موقعك، تحقّق مما سيُنقل بالضبط.»

- **Success:** they reach «المراجعة الأخيرة قبل النسخ» and can say which changes will be in the copied text and which
  quotations are still unsettled.
- **Observe:** whether they read the line that this is a check of the quotations found only, not a certificate for the
  whole article; whether «المقال المعدّل كاملًا (قبل وبعد)» is found or needed.

#### Task 7 — Copy it

Card: «انقل المقال المعدّل إلى [OWNER/moderator: البرنامج الذي يكتب فيه المشارك عادةً].»

- **Success:** the pasted text contains the approved changes and none of the rejected ones.
- **Observe:** whether they believe copying publishes the article or certifies it (treat either as a release issue, as
  in UX_REVIEW_PLAN.md); whether they find the printable review record and what they think it is for.

### Comprehension questions (after the tasks)

Ask exactly as written; do not rephrase into a yes/no question. Grade with the key; write the participant's words in
the notes only if they agreed to quotation.

**Q1 — the model's role**

```text
في رأيك، ما الذي يفعله النموذج اللغوي في هذه الأداة؟ وما الذي لا يفعله؟
```

- *Correct:* the model may only propose **where** quotations are (on the live service, for articles up to 6,000
  characters); it never writes verse text, references, verdicts or corrections; those come from the Hafs text of
  Quranpedia; suggestions while typing do not use a model; the writer decides every change.
- *Partial:* one of the two halves right (for example, "it does not write verses" but not what it does), or unsure.
- *Wrong:* believes the model writes, completes or corrects verses, judges correctness, or that the tool "uses AI to
  verify the Quran".

**Q2 — what happens to their text**

```text
حين ضغطتَ زر التدقيق، ماذا حدث لنص مقالك؟ وإلى أين ذهب؟
```

- *Correct:* it went to the tool's server, which does not keep it; an article up to 6,000 characters also went to the
  model provider (Groq) on the live service, a longer one did not; the browser keeps it only in the open tab until it is closed or cleared, longer only if they
  save a draft; there is no account. (For an instance with no model: it went only to the tool's server.)
- *Partial:* knows it leaves the device but not where, or misses the model provider, or the length rule.
- *Wrong:* believes the text stays on their device, or that the server stores it, or that it is published.

### Closing (Arabic)

```text
- ما الذي فاجأك في الأداة؟
- هل كان هناك شيء توقعتَ أن تجده ولم تجده؟
- لو استخدمتَ الأداة مرة أخرى في عملك، ما أول شيء ستفعله بطريقة مختلفة؟
شكرًا جزيلًا لوقتك. وأذكّرك بأنه يمكنك طلب حذف ملاحظاتك عبر [OWNER: وسيلة التواصل] قبل [OWNER: تاريخ إعداد التقرير].
```

After the participant leaves: clear the page («مسح»), delete any saved draft, close the private window, and check that
no article text is in the notes unless ticked.

---

## 5. Recording sheet

One row per participant per task, plus one row per comprehension question. Template:
[WRITER_PILOT_SHEET.csv](WRITER_PILOT_SHEET.csv) (header and one example row marked `EXAMPLE`, to be deleted). Never
put article text in the sheet unless the participant ticked that box; describe the screen state instead ("card 3 of
11, boundary question").

| Column | Values |
|---|---|
| `participant` | code `P1`–`P5` (Arabic in the consent record: م١–م٥); never a name |
| `session_date`, `build`, `service` | date; `build` from `/api/health`; `live` or `no-model` |
| `device`, `browser`, `viewport` | e.g. `laptop`, `Safari 19`, `1440x900` |
| `task` | `T1`–`T7`, `Q1`, `Q2` |
| `material` | `own_published`, `own_rights_cleared`, `unpublished_agreed`, `backup_demo`, `backup_sample3` |
| `article_chars_bucket` | `<=6000`, `6001-20000`, or empty |
| `completion` | `done`, `done_with_help`, `not_done` (T rows) |
| `task_seconds` | time on the task |
| `first_useful_result_seconds` | T3 only: from pressing «دقّق الاقتباسات» to reading the first decision card |
| `help_count` | number of hints given |
| `confusion_count`, `confusion_notes` | moments of hesitation or misreading; notes describe the control or sentence, not the article |
| `missed_quotations` | T3: quotations in the article that did not appear |
| `unwanted_possible` | T3/T4: «possible» or optional phrases the participant says are not quotations |
| `wrong_corrections` | any proposed correction judged wrong (**each one is S1**) |
| `wrong_approvals` | wrong corrections the participant approved |
| `understanding` | Q rows: `correct`, `partial`, `wrong` |
| `issue_refs` | issue numbers filed from this row |

---

## 6. Issues and severity

File each distinct problem once with [the issue template](../.github/ISSUE_TEMPLATE/pilot_observation.md), then add
each further participant who met it to the same issue. Do not paste article text, names or screenshots that show
article text unless the participant ticked those boxes.

| Severity | Meaning | Examples |
|---|---|---|
| **S1** | Wrong verse text or a wrong correction shown; or data exposure | a proposed correction that would make a correct quotation wrong; verse text that is not the source's; article text in a log, a URL or a place the privacy page does not name |
| **S2** | Task blocked, or a misquotation shown as matched | the participant cannot reach the copy step; a misquoted verse reads «مطابق للمصحف»; the copied text lacks an approved change |
| **S3** | Confusion the participant recovered from | took the wrong path first, then found the decision; misread a state, then corrected themselves |
| **S4** | Cosmetic | alignment, wording polish, spacing, with no effect on the task |

**Ranking.** Priority = severity weight × number of participants affected, with weights S1 = 4, S2 = 3, S3 = 2,
S4 = 1 (so an S3 met by all five ranks 10, above an S2 met by one, 3). Two overrides: **every S1 is fixed before any
release regardless of its score**, and an S2 met by two or more participants blocks the interface sign-off. Ties are
broken by the earlier task in the flow.

---

## 7. Analysis plan

- Report **counts**, per task and per participant: a table of `completion` (done / with help / not done) for T1–T7 ×
  P1–P5; the times per task as individual values (and their range), not a single average; `missed_quotations`,
  `unwanted_possible`, `wrong_corrections` and `wrong_approvals` per participant; Q1 and Q2 grades per participant.
- **Never a single satisfaction score**, no "usability index", no percentages presented as rates of the population.
  With five people, "3 of 5 could not undo a correction" is the finding; "60%" is not.
- Five participants find **usability problems**, not accuracy rates. Missed quotations and wrong corrections found here
  are filed as cases (and added to the evaluation sets only with the participant's permission and with rights to the
  text); they are not recall or precision figures.
- Report results on backup material separately from results on participants' own articles.
- List every S1 and S2 with its participant codes and the build; for each, the change made and whether it was
  re-checked with a new participant (a re-check with the same participant is weaker and is labelled as such).
- State what the study could not show (§1) and any deviation from this script (a changed build, a cold start, help given
  early, a task skipped).
- The study note goes in `docs/TEST_LOG.md` (and a summary in the CHANGELOG); it satisfies the Stage 4 interface
  sign-off gate only if five eligible participants completed sessions and every S1 is resolved.
