/* Seminar data tool — single-page UI (Hebrew, RTL). No external libraries; talks to the local server. */
"use strict";

// ------------------------------------------------------------------ helpers
// replaceChildren() that skips null/false (optional parts of a screen) and flattens arrays
const _replaceChildren = Element.prototype.replaceChildren;
Element.prototype.replaceChildren = function (...kids) {
  return _replaceChildren.apply(this, kids.flat(Infinity).filter((k) => k !== null && k !== undefined && k !== false));
};
const $ = (sel, root = document) => root.querySelector(sel);
const view = () => $("#view");

/** Create a DOM element: h("div", {class: "x", onclick: fn}, child, "text", [children]) — text is never parsed as HTML. */
function h(tag, attrs, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k.startsWith("on") && typeof v === "function") el.addEventListener(k.slice(2), v);
    else if (k === "class") el.className = v;
    else if (k === "html") el.innerHTML = v;            // only used with static strings written in this file
    else if (v === true) el.setAttribute(k, "");
    else el.setAttribute(k, v);
  }
  for (const c of children.flat(Infinity)) {
    if (c === null || c === undefined || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return el;
}
const fmtInt = (n) => (n === null || n === undefined ? "—" : Number(n).toLocaleString("he-IL"));
const yesNo = (v, yes = "כן", no = "לא") => h("span", { class: "badge " + (v == 1 ? "yes" : "no") }, v == 1 ? yes : no);

async function api(path) {
  const r = await fetch(path, { cache: "no-store" });
  const data = await r.json().catch(() => ({ ok: false, error: "תשובה לא תקינה מהשרת" }));
  if (!r.ok || data.ok === false) throw new Error(data.error || ("שגיאה " + r.status));
  return data;
}
async function post(path, body, raw) {
  const headers = { "X-Requested-With": "SeminarDataTool" };
  let payload = raw;
  if (!raw) { headers["Content-Type"] = "application/json"; payload = JSON.stringify(body || {}); }
  else if (body && body.filename) headers["X-Filename"] = encodeURIComponent(body.filename);
  const r = await fetch(path, { method: "POST", headers, body: payload });
  const data = await r.json().catch(() => ({ ok: false, error: "תשובה לא תקינה מהשרת" }));
  if (!r.ok || data.ok === false) throw new Error(data.error || ("שגיאה " + r.status));
  return data;
}
function helpLine(text) {
  return h("div", { class: "help" }, h("strong", {}, "מה רואים כאן? "), text);
}
function errorBox(err) {
  return h("div", { class: "banner bad" }, "⚠ ", String(err && err.message ? err.message : err));
}
function download(href) {           // browser download (goes to the user's Downloads folder)
  const a = h("a", { href, download: "" });
  document.body.append(a); a.click(); a.remove();
}
function table(columns, rows, opts = {}) {
  const thead = h("thead", {}, h("tr", {}, columns.map((c) => h("th", {}, c))));
  const tbody = h("tbody", {}, rows.map((r) => h("tr", {}, r.map((c) => h("td", { class: typeof c === "number" ? "num" : "" }, c)))));
  return h("div", { class: "table-wrap" }, h("table", { class: opts.cls || "" }, opts.caption ? h("caption", {}, opts.caption) : null, thead, tbody));
}
function kv(pairs) {
  return h("dl", { class: "kv" }, pairs.map(([k, v]) => [h("dt", {}, k), h("dd", {}, v === null || v === undefined || v === "" ? "—" : v)]));
}
function progressBar(p) {
  const bar = h("div", { class: "progress" + (p < 0 ? " indeterminate" : "") }, h("div", {}));
  bar.firstChild.style.width = Math.max(0, Math.min(1, p)) * 100 + "%";
  return bar;
}
function pathEl(p) {             // Windows path with Hebrew folder names: isolate each segment so it reads correctly
  const el = h("span", { class: "path", dir: "ltr" });
  String(p || "").split("\\").forEach((seg, i) => { if (i) el.append("\\"); el.append(h("bdi", { dir: "ltr" }, seg)); });
  return el;
}
let INFO = null;
let timers = [];
function clearTimers() { timers.forEach(clearInterval); timers = []; }

// ------------------------------------------------------------------ heartbeat + close
const CLIENT_ID = Math.random().toString(36).slice(2) + Date.now().toString(36);
let hbFailures = 0;
let hbTimer = null;
async function heartbeat() {
  try {
    const r = await fetch("/api/heartbeat", { method: "POST", headers: { "X-Requested-With": "SeminarDataTool", "Content-Type": "application/json" },
      body: JSON.stringify({ client: CLIENT_ID, run: INFO && INFO.run_id }) });
    if (r.status === 409) {
      showOverlay("התוכנה הופעלה מחדש", "לשונית זו שייכת להפעלה קודמת של התוכנה. טענו מחדש את הדף (F5) או עברו ללשונית החדשה.");
      return;
    }
    if (!r.ok) throw new Error("heartbeat " + r.status);
    hbFailures = 0;
  } catch (e) {
    if (++hbFailures >= 3) showOverlay("התוכנה אינה פועלת", "החיבור לתוכנה נותק. אם סגרתם אותה — אפשר לסגור את הלשונית. כדי לפתוח שוב: לחצו פעמיים על „הפעלה.bat”.");
  }
}
function showOverlay(title, text) {
  // this page is finished: stop the heartbeat so an old tab never keeps a later run of the program alive
  if (hbTimer) { clearInterval(hbTimer); hbTimer = null; }
  $("#overlayTitle").textContent = title;
  $("#overlayText").textContent = text;
  $("#overlay").hidden = false;
}
window.addEventListener("pagehide", () => { try { navigator.sendBeacon("/api/bye", CLIENT_ID); } catch (e) { /* ignore */ } });
$("#closeApp").addEventListener("click", async () => {
  if (!confirm("לסגור את התוכנה? (פעולות שרצות ברקע, כמו הורדה, ייעצרו)")) return;
  try { await post("/api/shutdown", {}); } catch (e) { /* already closed */ }
  showOverlay("התוכנה נסגרה", "אפשר לסגור את הלשונית הזו. כדי לפתוח שוב — לחצו פעמיים על „הפעלה.bat”.");
  setTimeout(() => window.close(), 400);
});

// ------------------------------------------------------------------ router
const ROUTES = { home: viewHome, cases: viewCases, case: viewCase, stats: viewStats, "stats-upload": viewStats, reimport: viewReimport, upload: viewUpload };
async function route() {
  clearTimers();
  const hash = location.hash.replace(/^#/, "") || "home";
  const [name, ...rest] = hash.split("/");
  const fn = ROUTES[name] || viewHome;
  document.querySelectorAll(".nav a").forEach((a) => a.classList.toggle("active", a.dataset.nav === (name === "case" ? "cases" : name.replace("-upload", ""))));
  view().replaceChildren(h("p", { class: "loading" }, "טוען…"));
  try {
    await fn(decodeURIComponent(rest.join("/")), name);
  } catch (e) {
    view().replaceChildren(errorBox(e));
  }
  view().focus({ preventScroll: true });
}
window.addEventListener("hashchange", () => { route(); window.scrollTo(0, 0); });

// ------------------------------------------------------------------ footer
function renderFooter() {
  $("#footer").replaceChildren(
    h("span", {}, "נתוני המחקר: ", pathEl(INFO.data_dir)),
    h("span", {}, "קבצים שהכלי יוצר: ", pathEl(INFO.output_dir)),
    h("span", {}, "גרסה " + INFO.version),
  );
}
async function openFolder(path) {
  try { await post("/api/open_folder", { path }); } catch (e) { alert(e.message); }
}
async function reveal(path) {
  try { await post("/api/reveal", { path }); } catch (e) { alert(e.message); }
}
/** Where-saved line: full path + "open folder" button. */
function savedLine(path, isFolder) {
  return h("div", { class: "saved" }, h("span", { class: "badge yes" }, "✓ נשמר"), " ", pathEl(path), " ",
    h("button", { class: "btn btn-light btn-small", onclick: () => reveal(path) }, isFolder ? "פתיחת התיקייה" : "הצגה בתיקייה"));
}
/** Save an export: the program opens the Windows "Save as" dialog (it starts in the last folder used, by default
 *  תוצרים), writes the file, and the status line shows the full path. Without the dialog: browser download. */
async function saveFileOrDownload(kind, statusEl, source) {
  try {
    const r = await fetch("/api/save", { method: "POST", headers: { "X-Requested-With": "SeminarDataTool", "Content-Type": "application/json" },
      body: JSON.stringify({ kind, source: source || "study" }) }).then((x) => x.json());
    if (r.fallback) { download(r.href); statusEl.replaceChildren(h("span", { class: "muted" }, r.error)); return; }
    if (!r.ok) throw new Error(r.error);
    if (r.cancelled) { statusEl.replaceChildren(h("span", { class: "muted" }, "השמירה בוטלה.")); return; }
    statusEl.replaceChildren(savedLine(r.path, false));
    INFO.last_dir = r.folder;
  } catch (e) { statusEl.replaceChildren(errorBox(e)); }
}
/** Button + status line pair for an export. */
function saveButton(label, kind, opts = {}) {
  const status = opts.status || h("div", { class: "save-status" });
  const btn = h("button", { class: "btn " + (opts.light ? "btn-light" : ""), title: "בחירת מיקום השמירה בחלון של Windows",
    onclick: () => { status.replaceChildren(h("span", { class: "loading" }, "נפתח חלון „שמירה בשם” של Windows…")); saveFileOrDownload(kind, status, opts.source); } }, label);
  return opts.status ? btn : [btn, status];
}

// ------------------------------------------------------------------ א. home
async function viewHome() {
  const tile = (letter, title, text, href, online) =>
    h("a", { class: "home-tile", href },
      h("div", { class: "row" }, h("span", { class: "letter" }, letter), h("span", { class: "spacer" }),
        h("span", { class: "tag " + (online ? "online" : "offline") }, online ? "דורש אינטרנט" : "עובד ללא אינטרנט")),
      h("h2", {}, title), h("p", {}, text));
  view().replaceChildren(
    h("h1", {}, "ברוכים הבאים"),
    h("p", {}, "הכלי מציג את נתוני העבודה הסמינריונית: ערעורים פליליים (ע\"פ) של נאשמים בעבירות רצח והמתה שהוכרעו בבית המשפט העליון בשנים 2010–2020 ",
      `(${fmtInt(INFO.n_main)} ערעורים במדגם הניתוח, ${fmtInt(INFO.n_cases)} בקורפוס המלא). `,
      "המשתנה הבלתי תלוי: האם התפרסמה ידיעה ב-Google News לפני פסק הדין; המשתנה התלוי: האם בית המשפט העליון שינה את תוצאת בית המשפט המחוזי."),
    helpLine("ארבע אפשרויות עבודה. בחרו אחת מהן — אפשר לחזור לכאן בכל רגע דרך „בית” בסרגל העליון."),
    h("div", { class: "home-grid" },
      tile("א", "צפייה בנתוני המחקר", "טבלת כל התיקים עם סינון, וכרטיס מלא לכל תיק: תוצאה, ידיעות, שאילתות וטקסט פסק הדין.", "#cases", false),
      tile("ב", "שחזור הניתוח הסטטיסטי", "לחיצה אחת מריצה את כל טבלאות העבודה ובודקת שהן זהות למספרים שבעבודה. ייצוא ל-Excel ול-SPSS.", "#stats", false),
      tile("ג", "ייבוא הנתונים מחדש מהמקורות", "הורדת מאגר פסקי הדין ובניית האוכלוסייה מחדש, וחיפוש חוזר של ידיעות ב-Google News לתיקים נבחרים.", "#reimport", true),
      tile("ד", "ייבוא קובץ נתונים משלך", "הורדת תבנית Excel, העלאת קובץ משלכם, בדיקת תקינות והרצת אותם ניתוחים על הנתונים שלכם.", "#upload", false),
    ),
    INFO.output_is_default ? null : h("div", { class: "banner warn", id: "fallbackNotice" }, "⚠ ", INFO.output_reason, " ",
      h("strong", {}, "התיקייה החלופית: "), pathEl(INFO.output_dir)),
    h("div", { class: "card" },
      h("h3", {}, "איפה הנתונים נשמרים?"),
      kv([
        ["נתוני המחקר (לקריאה בלבד)", pathEl(INFO.data_dir)],
        ["תיקיית ברירת המחדל לקבצים שהכלי יוצר", pathEl(INFO.output_dir)],
        ["יומן התוכנה", pathEl(INFO.log_file)],
      ]),
      h("p", { class: "small" }, "בכל שמירה נפתח חלון „שמירה בשם” של Windows ואפשר לבחור כל תיקייה (גם כונן USB או תיקיית רשת). ",
        "החלון נפתח בתיקייה האחרונה שבחרתם; בפעם הראשונה — בתיקיית ברירת המחדל שלמעלה."),
      h("div", { class: "row" },
        h("button", { class: "btn btn-light", onclick: () => openFolder(INFO.output_dir) }, "פתיחת תיקיית ברירת המחדל"),
        saveButton("שמירת עותק של יומן התוכנה…", "log_txt", { light: true })),
      h("p", { class: "muted small" }, "התוכנה נסגרת אוטומטית כשסוגרים את הלשונית, או בלחיצה על „סגירה” למעלה."),
    ),
  );
}

// ------------------------------------------------------------------ א. case table
let CASES = null;
const FILTERS = { q: "", year: "", offence: "", media: "", intervention: "", sample: "merits" };
let SORT = { key: "decision_date", dir: 1 };
async function viewCases() {
  if (!CASES) CASES = (await api("/api/cases")).cases;
  const years = [...new Set(CASES.map((c) => c.year))].sort();
  const sel = (key, label, options) => h("label", { class: "field" }, label,
    h("select", { onchange: (e) => { FILTERS[key] = e.target.value; renderRows(); } },
      options.map(([v, t]) => h("option", { value: v, selected: FILTERS[key] === v }, t))));
  const countEl = h("span", { class: "muted" });
  const casesSaveStatus = h("div", { class: "save-status" });
  const tbody = h("tbody");
  const cols = [["case_number", "מספר הליך"], ["decision_date", "תאריך פסק הדין"], ["offence", "עבירה"],
    ["media_count", "בולטות (ידיעות)"], ["intervention", "התערבות"], ["relief", "תוצאה"], ["merits", "מדגם"]];
  const thead = h("thead", {}, h("tr", {}, cols.map(([k, t]) => h("th", { class: "sortable", onclick: () => { SORT = { key: k, dir: SORT.key === k ? -SORT.dir : 1 }; renderRows(); } }, t))));
  function renderRows() {
    const q = FILTERS.q.trim();
    let rows = CASES.filter((c) =>
      (!q || c.case_number.replace(/["״]/g, "").includes(q.replace(/["״]/g, ""))) &&
      (!FILTERS.year || String(c.year) === FILTERS.year) &&
      (!FILTERS.offence || c.offence === FILTERS.offence) &&
      (!FILTERS.media || String(c.media_any) === FILTERS.media) &&
      (!FILTERS.intervention || String(c.intervention) === FILTERS.intervention) &&
      (FILTERS.sample === "all" || (FILTERS.sample === "merits" ? c.merits == 1 : c.merits == 0)));
    rows = rows.slice().sort((a, b) => (a[SORT.key] > b[SORT.key] ? 1 : a[SORT.key] < b[SORT.key] ? -1 : 0) * SORT.dir);
    countEl.textContent = `מוצגים ${fmtInt(rows.length)} מתוך ${fmtInt(CASES.length)} תיקים`;
    tbody.replaceChildren(...rows.map((c) => h("tr", { class: "clickable", tabindex: "0", title: "לחצו לפתיחת כרטיס התיק",
      onclick: () => { location.hash = "#case/" + encodeURIComponent(c.case_id); },
      onkeydown: (e) => { if (e.key === "Enter") location.hash = "#case/" + encodeURIComponent(c.case_id); } },
      h("td", {}, h("strong", {}, c.case_number)), h("td", { class: "num" }, c.decision_date), h("td", {}, c.offence),
      h("td", {}, c.media_any == 1 ? h("span", { class: "badge yes" }, `כן (${c.media_count})`) : h("span", { class: "badge no" }, "לא")),
      h("td", {}, yesNo(c.intervention)), h("td", {}, c.relief),
      h("td", {}, c.merits == 1 ? "ערעור לגופו" : h("span", { class: "badge warn", title: c.non_merits_reason }, "הוחרג")))));
    if (!rows.length) tbody.replaceChildren(h("tr", {}, h("td", { colspan: cols.length, class: "muted" }, "אין תיקים שמתאימים לסינון.")));
  }
  view().replaceChildren(
    h("h1", {}, "צפייה בנתוני המחקר"),
    helpLine("כל תיקי המחקר. אפשר לסנן לפי שנה, סוג עבירה, בולטות תקשורתית, התערבות ומדגם, או לחפש מספר הליך. לחיצה על שורה פותחת את כרטיס התיק."),
    h("div", { class: "card" },
      h("div", { class: "filters" },
        h("label", { class: "field" }, "חיפוש מספר הליך",
          h("input", { type: "text", placeholder: "לדוגמה 8800/08", value: FILTERS.q, oninput: (e) => { FILTERS.q = e.target.value; renderRows(); } })),
        sel("year", "שנת ההכרעה", [["", "כל השנים"], ...years.map((y) => [String(y), String(y)])]),
        sel("offence", "סוג העבירה", [["", "הכול"], ["רצח או ניסיון לרצח", "רצח או ניסיון לרצח"], ["המתה אחרת", "המתה אחרת"]]),
        sel("media", "בולטות תקשורתית", [["", "הכול"], ["1", "עם ידיעות"], ["0", "ללא ידיעות"]]),
        sel("intervention", "התערבות העליון", [["", "הכול"], ["1", "התערב"], ["0", "לא התערב"]]),
        sel("sample", "מדגם", [["merits", "מדגם הניתוח (478)"], ["excluded", "הליכים שהוחרגו (19)"], ["all", "כל הקורפוס (497)"]]),
      ),
      h("div", { class: "row", style: "margin-top:.7rem" }, countEl, h("span", { class: "spacer" }),
        h("button", { class: "btn btn-light", onclick: () => { Object.assign(FILTERS, { q: "", year: "", offence: "", media: "", intervention: "", sample: "merits" }); route(); } }, "ניקוי הסינון"),
        saveButton("שמירת כל הנתונים ל-Excel…", "study_xlsx", { light: true, status: casesSaveStatus })),
      casesSaveStatus,
    ),
    h("div", { class: "table-wrap" }, h("table", {}, thead, tbody)),
  );
  renderRows();
}

// ------------------------------------------------------------------ א. case card
async function viewCase(caseId) {
  const card = (await api("/api/case?id=" + encodeURIComponent(caseId))).card;
  const r = card.row;
  const g = card.google;
  const statusBadge = (s, label) => h("span", { class: "badge " + (s === "included" ? "yes" : "no") }, label);
  const mediaTable = g.length ? h("div", { class: "table-wrap" }, h("table", {},
    h("thead", {}, h("tr", {}, ["כותרת", "כלי תקשורת", "תאריך", "חלון", "סטטוס"].map((t) => h("th", {}, t)))),
    h("tbody", {}, g.map((it) => h("tr", {},
      h("td", {}, it.url ? h("a", { href: it.url, target: "_blank", rel: "noopener noreferrer", title: "פתיחת הידיעה (דורש אינטרנט)" }, it.title) : it.title),
      h("td", {}, it.source), h("td", { class: "num" }, it.published_date), h("td", { class: "small" }, it.window_label),
      h("td", {}, statusBadge(it.curation_status, it.status_label)))))))
    : h("p", { class: "muted" }, "לא נמצאו ידיעות Google News לתיק הזה בחלונות הזמן שנבדקו.");
  const j = card.judgment;
  let judgment = h("p", { class: "muted" }, "טקסט פסק הדין אינו זמין.");
  if (j.available) {
    const textEl = h("div", { class: "judgment-text" });
    for (const s of j.segments) {
      if (s.marker) textEl.append(h("span", { class: "reasoning-marker" }, "▼ " + s.marker));
      else if (s.ref) textEl.append(h("mark", { class: "ref ref-" + s.ref.reason, title: s.ref.label + (s.ref.in_reasoning ? " · בתוך פרק ההנמקה" : "") }, s.t));
      else textEl.append(document.createTextNode(s.t));
    }
    judgment = h("details", { class: "judgment" },
      h("summary", {}, `טקסט פסק הדין (${fmtInt(j.chars)} תווים) — לחצו לפתיחה`),
      h("p", { class: "muted small" }, `פסק הדין מתאריך ${j.doc_date}. זיהוי פרק ההנמקה: ${j.reasoning_label}. מסומנים רק אזכורי תקשורת שאומתו ידנית בהקשרם.`),
      h("div", { class: "legend" }, h("span", { class: "la" }, "סיקור התיק / ראיון (A)"), h("span", { class: "lb" }, "התקשורת כמקור מידע (B)"), h("span", { class: "lc" }, "טענה להשפעת התקשורת (C)")),
      textEl);
  }
  view().replaceChildren(
    h("p", {}, h("a", { href: "#cases" }, "→ חזרה לרשימת התיקים")),
    h("div", { class: "case-head" }, h("h1", {}, card.summary[0][1]), h("span", { class: "muted" }, "פסק דין מיום " + r.decision_date)),
    helpLine("כל המידע שנאסף על התיק: פרטי ההליך והתוצאה, מדוע נכלל במחקר, הידיעות שנמצאו והשאילתות שהופעלו, וטקסט פסק הדין עם אזכורי התקשורת המסומנים."),
    h("div", { class: "banner " + (card.inclusion.included ? "ok" : "warn") }, card.inclusion.included ? "✓ " : "⚠ ", card.inclusion.text),
    h("div", { class: "grid2" },
      h("div", { class: "card" }, h("h2", {}, "פרטי ההליך והתוצאה"), kv(card.summary.slice(1))),
      h("div", { class: "card" }, h("h2", {}, "בולטות תקשורתית"), kv(card.media_summary),
        h("h3", {}, "מדדי טקסט"), kv(card.text_measures.map(([k, v]) => [k, typeof v === "number" ? fmtInt(Math.round(v * 100) / 100) : v])))),
    h("div", { class: "card" }, h("h2", {}, `ידיעות Google News שנמצאו (${g.length})`),
      h("p", { class: "muted small" }, "„נכלל” = ידיעה על התיק שפורסמה בתוך חלון הזמן ונספרה במשתנה הבולטות. ידיעות שהוחרגו מוצגות לשקיפות. ",
        "שלב הערכאה הדיונית = מ-7 ימים לפני הכרעת הדין בבית המשפט המחוזי ועד 30 יום אחריה; שלב הערעור = מהכרעת הדין ועד יום לפני פסק הדין בעליון."),
      mediaTable),
    h("div", { class: "card" }, h("h2", {}, "השאילתות המדויקות שהופעלו"),
      card.queries.length ? table(["שאילתה", "חלון", "מתאריך", "עד תאריך", ""], card.queries.map((q) => [
        h("span", { class: "q" }, q.query_text), q.window_label, q.window_start, q.window_end,
        h("a", { href: q.search_link, target: "_blank", rel: "noopener noreferrer", title: "פותח את אותו חיפוש ב-Google News (דורש אינטרנט; התוצאות משתנות עם הזמן)" }, "פתיחת החיפוש ↗")]))
        : h("p", { class: "muted" }, "אין שאילתות שמורות לתיק."),
      card.primo.length ? [h("h3", {}, `רשומות ממאגר העיתונות Primo (${card.primo.length})`),
        table(["כותרת", "עיתון", "תאריך", "סטטוס"], card.primo.map((p) => [p.title, p.newspaper_source, p.published_date, p.status_label]))] : null),
    h("div", { class: "card" }, h("h2", {}, `פסק הדין ואזכורי תקשורת מאומתים (${j.refs ? j.refs.length : 0})`),
      j.refs && j.refs.length ? table(["סוג האזכור", "המילה", "בפרק ההנמקה?", "הקשר"], j.refs.map((x) => [x.label, x.match, x.in_reasoning ? "כן" : "לא", h("span", { class: "small" }, "…" + x.context + "…")])) : h("p", { class: "muted" }, "לא נמצאו בפסק הדין אזכורי תקשורת מאומתים."),
      judgment),
  );
}

// ------------------------------------------------------------------ ב. statistics
const SECTION_OF = { desc: "desc", balance: "desc", main: "main", logit: "logit", rob: "robust", attempt: "robust", dose: "dose", ref: "refs", cx: "complexity", mw: "complexity", holm: "holm", power: "power", quality: "quality" };
async function viewStats(_arg, name) {
  const source = name === "stats-upload" ? "upload" : "study";
  view().replaceChildren(h("h1", {}, source === "study" ? "שחזור הניתוח הסטטיסטי" : "ניתוח הקובץ שהעליתם"),
    h("p", { class: "loading" }, "מחשב את כל הניתוחים… (כמה שניות)"));
  const data = await api("/api/stats?source=" + source);
  const res = data.result, gold = data.golden;
  const bySection = {};
  if (gold) for (const it of gold.items) {
    const s = SECTION_OF[it.key.split(".")[0]] || "other";
    (bySection[s] = bySection[s] || []).push(it);
  }
  const goldBanner = gold ? h("div", { class: "banner " + (gold.all_ok ? "ok" : "bad") },
    h("span", { class: "check" }, gold.all_ok ? "✓" : "✗"),
    h("span", { class: "big" }, gold.all_ok ? "זהה לנתוני העבודה" : "יש הבדלים מנתוני העבודה"),
    h("span", {}, `${gold.matched} מתוך ${gold.checked} ערכים זהים לגיליון המספרים המאושר של העבודה (פלט SPSS 27).`),
    h("span", { class: "spacer" }),
    h("button", { class: "btn btn-light", onclick: () => $("#goldTable").classList.toggle("hidden") }, "הצגת ההשוואה המלאה"))
    : h("div", { class: "banner info" }, "ℹ הניתוח הורץ על הקובץ שהעליתם (", data.source_label, "). אין השוואה לנתוני העבודה כי אלה נתונים אחרים.");
  const goldTable = gold ? h("div", { id: "goldTable", class: "hidden" },
    table(["ערך", "בעבודה (SPSS)", "חושב עכשיו", "זהה?"], gold.items.map((i) => [i.label, i.expected, i.got, i.ok ? "✓" : "✗"]))) : null;
  const statsSaveStatus = h("div", { class: "save-status" });
  const spssPanel = h("div", { class: "card hidden", id: "spssPanel" },
    h("h3", {}, "ייצוא ל-SPSS"),
    h("p", {}, "הכלי שומר בתיקייה שתבחרו את קובץ הנתונים (CSV) ואת שני קובצי התחביר של העבודה (‎.sps), כשהנתיבים בתוכם כבר מותאמים לתיקייה. אחר כך פותחים ב-SPSS את 01_import_and_labels.sps ומריצים Run > All, ואז את 02_analysis.sps."),
    h("label", { class: "field" }, "תיקיית היעד",
      h("div", { class: "row" }, h("input", { type: "text", class: "wide grow", dir: "ltr", id: "spssFolder", value: INFO.spss_default }),
        h("button", { class: "btn btn-light", onclick: chooseSpssFolder }, "בחירת תיקייה…"))),
    h("div", { class: "row", style: "margin-top:.6rem" },
      h("button", { class: "btn btn-green", onclick: doSpss }, "שמירת הקבצים לתיקייה"), h("span", { id: "spssMsg" })));
  async function chooseSpssFolder() {
    const msg = $("#spssMsg");
    msg.replaceChildren(h("span", { class: "loading" }, "נפתח חלון בחירת תיקייה של Windows…"));
    try {
      const r = await post("/api/choose", { what: "spss_folder" });
      if (r.fallback) { msg.replaceChildren(h("span", { class: "muted" }, r.error)); return; }
      if (r.cancelled) { msg.replaceChildren(h("span", { class: "muted" }, "הבחירה בוטלה.")); return; }
      $("#spssFolder").value = r.path;
      msg.replaceChildren(h("span", { class: "muted" }, "נבחרה תיקייה. לחצו „שמירת הקבצים לתיקייה”."));
    } catch (e) { msg.replaceChildren(errorBox(e)); }
  }
  async function doSpss() {
    const msg = $("#spssMsg");
    msg.replaceChildren(h("span", { class: "loading" }, "שומר…"));
    try {
      const r = await post("/api/spss_export", { folder: $("#spssFolder").value, source });
      msg.replaceChildren(savedLine(r.folder, true), h("div", { class: "muted small" }, "קבצים: " + r.files.join(", ")));
    } catch (e) { msg.replaceChildren(errorBox(e)); }
  }
  const toc = h("div", { class: "toc" }, res.sections.map((s) => h("a", { href: "#", onclick: (e) => { e.preventDefault(); document.getElementById("sec-" + s.id).scrollIntoView({ behavior: "smooth" }); } }, s.title)));
  const sections = res.sections.map((s) => {
    const items = bySection[s.id] || [];
    const ok = items.filter((i) => i.ok).length;
    const badge = items.length ? h("span", { class: "sec-badge " + (ok === items.length ? "ok" : "bad") },
      ok === items.length ? `✓ זהה לנתוני העבודה (${ok}/${items.length})` : `✗ ${items.length - ok} ערכים שונים`) : null;
    return h("section", { class: "card", id: "sec-" + s.id },
      h("div", { class: "row" }, h("h2", {}, s.title), h("span", { class: "spacer" }), badge),
      helpLine(s.help),
      s.blocks.map((b) => b.type === "note" ? h("div", { class: "note " + (b.kind === "warn" ? "warn" : "") }, b.text)
        : table(b.columns, b.rows, { caption: b.caption, cls: "stats" })));
  });
  view().replaceChildren(
    h("h1", {}, source === "study" ? "שחזור הניתוח הסטטיסטי" : "ניתוח הקובץ שהעליתם"),
    helpLine(source === "study"
      ? `כל הטבלאות של פרק הממצאים, מחושבות עכשיו מקובץ הנתונים (מדגם ניתוח N=${res.n_main}, קורפוס מלא N=${res.n_full}). הסימון הירוק מאשר שכל מספר זהה למספר שבעבודה.`
      : `אותם ניתוחים של העבודה, על הקובץ שהעליתם (${res.n_main} שורות במדגם הניתוח, ${res.n_full} בסך הכול).`),
    goldBanner, goldTable,
    h("div", { class: "row" },
      saveButton("ייצוא התוצאות ל-Excel…", "stats_xlsx", { source, status: statsSaveStatus }),
      h("button", { class: "btn btn-light", onclick: () => $("#spssPanel").classList.toggle("hidden") }, "ייצוא ל-SPSS"),
      source === "upload" ? h("a", { class: "btn btn-light", href: "#upload" }, "חזרה להעלאת קובץ") : null),
    statsSaveStatus, spssPanel, toc, ...sections);
}

// ------------------------------------------------------------------ ג. re-import wizard
let WIZ_STEP = 1;
async function viewReimport() {
  const steps = h("div", { class: "steps" },
    [[1, "שלב 1 · נתוני בית המשפט"], [2, "שלב 2 · ידיעות Google News"], [3, "שלב 3 · ייצוא"]].map(([n, t]) =>
      h("button", { class: WIZ_STEP === n ? "active" : "", onclick: () => { WIZ_STEP = n; route(); } }, t)));
  const body = h("div");
  view().replaceChildren(h("h1", {}, "ייבוא הנתונים מחדש מהמקורות"),
    helpLine("שחזור איסוף הנתונים מהמקור: בניית רשימת התיקים מתוך מאגר פסקי הדין, וחיפוש חוזר של ידיעות. מסך זה דורש חיבור לאינטרנט (חוץ מבנייה מעותק מקומי)."),
    steps, body);
  if (WIZ_STEP === 1) await wizCourt(body);
  else if (WIZ_STEP === 2) await wizMedia(body);
  else await wizExport(body);
}

function jobPanel(job, stopName) {
  if (!job || job.state === "idle") return h("div");
  const stateLabel = { running: "פועל…", done: "הסתיים ✓", error: "שגיאה", stopped: "נעצר" }[job.state] || job.state;
  return h("div", { class: "card" },
    h("div", { class: "row" }, h("strong", {}, stateLabel), h("span", { class: "muted" }, job.message), h("span", { class: "spacer" }),
      job.state === "running" ? h("button", { class: "btn btn-danger", onclick: async () => { await post("/api/job/stop", { job: stopName }); } }, "עצירה") : null),
    job.state === "running" ? progressBar(job.progress) : null,
    job.error ? errorBox(job.error) : null,
    job.log && job.log.length ? h("details", {}, h("summary", { class: "small muted" }, "יומן פעולות"), h("div", { class: "logbox" }, job.log.join("\n"))) : null);
}

async function wizCourt(body) {
  let st = await api("/api/court/status");
  const pathInput = h("input", { type: "text", class: "wide grow", dir: "ltr", value: st.local_copies[0] || st.default_path });
  const dlDirEl = h("span", {}, pathEl(st.download_dir));
  const checkMsg = h("div");
  const jobsEl = h("div");
  const resultEl = h("div");
  const render = () => {
    jobsEl.replaceChildren(jobPanel(st.download, "download"), jobPanel(st.build, "build"));
    resultEl.replaceChildren(st.result ? courtResult(st.result) : h("div"));
  };
  body.replaceChildren(
    h("div", { class: "card" },
      h("h2", {}, "מקור הנתונים"),
      h("p", {}, "פסקי הדין נלקחים ממאגר הנתונים הפתוח ", h("strong", {}, "LevMuchnik/SupremeCourtOfIsrael"),
        " באתר Hugging Face — אוסף של כ-751 אלף פסקי דין והחלטות של בית המשפט העליון, יחד עם פרטי התיק. זהו ", h("strong", {}, "מאגר נתונים (dataset) ולא מודל בינה מלאכותית"), "."),
      kv([["קובץ", "cases_all.parquet (קובץ אחד)"], ["גודל", "כ-1.5 GB"], ["זמן הורדה", "כ-5 עד 30 דקות, לפי מהירות החיבור (אפשר לעצור ולהמשיך)"],
        ["זמן בניית האוכלוסייה", "כחצי דקה עד כמה דקות (ללא אינטרנט)"], ["דף המאגר", h("a", { href: st.page, target: "_blank", rel: "noopener noreferrer" }, st.page)]])),
    h("div", { class: "card" },
      h("h2", {}, "א. בחירת הקובץ"),
      h("p", {}, st.local_copies.length ? "נמצא עותק מקומי של המאגר — אין צורך להוריד שוב." : "לא נמצא עותק מקומי. אפשר להוריד את הקובץ, או להדביק נתיב לעותק קיים."),
      h("label", { class: "field" }, "נתיב לקובץ cases_all.parquet",
        h("div", { class: "row" }, pathInput, h("button", { class: "btn btn-light", onclick: async () => {
          try { const r = await post("/api/choose", { what: "parquet_file" }); if (r.path) pathInput.value = r.path; else if (r.fallback) alert(r.error); }
          catch (e) { alert(e.message); } } }, "עיון…"))),
      h("div", { class: "row small", style: "margin-top:.5rem" }, "תיקיית ההורדה: ", dlDirEl,
        h("button", { class: "btn btn-light btn-small", onclick: async () => {
          try {
            const r = await post("/api/choose", { what: "hf_folder" });
            if (r.fallback) return alert(r.error);
            if (r.path) { st.download_dir = r.path; st.default_path = r.download_path; dlDirEl.replaceChildren(pathEl(r.path)); }
          } catch (e) { alert(e.message); } } }, "שינוי…")),
      h("div", { class: "row", style: "margin-top:.6rem" },
        h("button", { class: "btn btn-light", onclick: async () => {
          checkMsg.replaceChildren(h("span", { class: "loading" }, "בודק…"));
          try { const r = await post("/api/court/check", { path: pathInput.value }); checkMsg.replaceChildren(h("span", { class: "badge yes" }, `✓ קובץ תקין: ${fmtInt(r.rows)} מסמכים, ${(r.bytes / 1e9).toFixed(2)} GB`)); }
          catch (e) { checkMsg.replaceChildren(errorBox(e)); } } }, "בדיקת הקובץ"),
        h("button", { class: "btn", onclick: async () => {
          if (!confirm(`להוריד כעת כ-1.5 GB מ-Hugging Face?\nהקובץ יישמר ב:\n${st.default_path}\n\nאל תסגרו את הלשונית בזמן ההורדה.`)) return;
          try { const r = await post("/api/court/download", {}); pathInput.value = r.dest; poll(); } catch (e) { alert(e.message); } } }, "הורדת הקובץ (כ-1.5 GB)"),
        checkMsg)),
    h("div", { class: "card" },
      h("h2", {}, "ב. בניית אוכלוסיית התיקים"),
      h("p", {}, "אותם סינונים של העבודה: ע\"פ בלבד → פסק דין סופי לא טכני בשנים 2010–2020 → סיווג עבירת המתה → הנאשם הוא המערער → שם מערער גלוי. ",
        "הסיווג משתמש בכללים של תוכנת האיסוף המקורית. בסוף מוצגת השוואה לרשימת 497 התיקים של המחקר."),
      h("button", { class: "btn btn-green btn-big", onclick: async () => {
        try { await post("/api/court/build", { path: pathInput.value }); poll(); } catch (e) { alert(e.message); } } }, "בניית האוכלוסייה")),
    jobsEl, resultEl);
  render();
  async function poll() {
    clearTimers();
    const t = setInterval(async () => {
      try { st = await api("/api/court/status"); render(); if (st.download.state !== "running" && st.build.state !== "running") clearInterval(t); }
      catch (e) { clearInterval(t); }
    }, 1000);
    timers.push(t);
  }
  if (st.download.state === "running" || st.build.state === "running") poll();
}

function courtResult(res) {
  const courtSave = h("div", { class: "save-status" });
  const rows = res.flow.map((f) => [f.step, fmtInt(f.count), f.paper === null || f.paper === undefined ? "—" : fmtInt(f.paper),
    f.paper === null || f.paper === undefined ? "" : (f.paper === f.count ? h("span", { class: "badge yes" }, "✓ זהה") : h("span", { class: "badge warn" }, "שונה")), f.note || ""]);
  const named = (res.flow.find((f) => f.step.startsWith("ערעורים עם שם מערער גלוי")) || {}).count;
  return h("div", { class: "card" },
    h("h2", {}, "תוצאה: שלבי הסינון"),
    h("div", { class: "banner ok" }, h("span", { class: "big" }, `${fmtInt(named)} ערעורים עם שם מערער גלוי`),
      h("span", {}, `· ${res.found} מהם ברשימת המחקר · ${res.extra} מחוץ לקורפוס המחקר`)),
    table(["שלב", "בשחזור עכשיו", "בעבודה", "", "הערה"], rows),
    h("p", { class: "muted small" }, `קורפוס המחקר (${res.study_n}) = ${res.found} התיקים שזוהו בכללים האוטומטיים` +
      (res.missing_list.length ? ` + ${res.missing_list.map((m) => m.case_number).join(", ")} (ראו להלן)` : "") +
      ". ההחרגה של 19 הליכים שאינם ערעור לגופו נעשית בשלב הניתוח (מדגם 478)."),
    res.missing_list.length ? [h("h3", {}, "תיק מחקר שסווג אחרת בכללים האוטומטיים"), table(["מספר הליך", "הערה"], res.missing_list.map((m) => [m.case_number, m.reason]))] : null,
    res.extra_list.length ? [h("h3", {}, "ערעורים עם שם גלוי שאינם בקורפוס המחקר"), table(["מספר הליך", "שם", "תאריך פסק הדין", "הערה"], res.extra_list.map((m) => [m.case_number, m.case_name, m.verdict_date, m.note || ""]))] : null,
    h("div", { class: "row" },
      saveButton("ייצוא ל-Excel…", "court_xlsx", { status: courtSave }),
      saveButton("ייצוא ל-CSV…", "court_csv", { light: true, status: courtSave }),
      h("span", { class: "muted small" }, "עותק CSV נשמר גם ב: ", pathEl(res.csv_path))),
    courtSave);
}

let MEDIA_SEL = new Set();
let MEDIA_YEAR = "2015";
async function wizMedia(body) {
  const mc = await api("/api/media/cases");
  const cases = mc.cases.filter((c) => c.merits == 1);
  const years = [...new Set(cases.map((c) => String(c.year)))].sort();
  const listEl = h("div", { class: "table-wrap case-pick" });
  const selInfo = h("span", { class: "muted" });
  const delayInput = h("input", { type: "number", min: String(mc.min_delay), step: "1", value: String(mc.default_delay), style: "width:5rem" });
  const statusEl = h("div");
  const resultsEl = h("div");
  function updateSel() {
    const n = MEDIA_SEL.size;
    const q = cases.filter((c) => MEDIA_SEL.has(c.case_id)).reduce((s, c) => s + c.windows.length, 0);
    const secs = q * (Number(delayInput.value || mc.default_delay) + 1.5);
    selInfo.textContent = `נבחרו ${n} תיקים · ${q} שאילתות · זמן משוער כ-${Math.max(1, Math.round(secs / 60))} דקות` + (n > mc.max_cases ? ` · אפשר עד ${mc.max_cases} תיקים בריצה` : "");
  }
  function renderList() {
    const shown = cases.filter((c) => !MEDIA_YEAR || String(c.year) === MEDIA_YEAR);
    listEl.replaceChildren(h("table", {},
      h("thead", {}, h("tr", {}, ["", "מספר הליך", "תאריך פסק הדין", "שאילתה (שם מדויק)", "חלונות", "ידיעות במחקר"].map((t) => h("th", {}, t)))),
      h("tbody", {}, shown.map((c) => h("tr", {},
        h("td", {}, h("input", { type: "checkbox", checked: MEDIA_SEL.has(c.case_id), onchange: (e) => { e.target.checked ? MEDIA_SEL.add(c.case_id) : MEDIA_SEL.delete(c.case_id); updateSel(); } })),
        h("td", {}, c.case_number), h("td", { class: "num" }, c.decision_date), h("td", { class: "q" }, c.query), h("td", { class: "num" }, c.windows.length), h("td", { class: "num" }, c.original_included))))));
    updateSel();
  }
  async function refresh() {
    const st = await api("/api/media/status");
    statusEl.replaceChildren(jobPanel(st.job, "media"));
    resultsEl.replaceChildren(...[].concat(mediaResults(st.cases)));
    return st;
  }
  body.replaceChildren(
    h("div", { class: "banner warn" }, "⚠ ", "תוצאות Google News משתנות עם הזמן (ידיעות נמחקות, מתווספות או מקבלות תאריך אחר), והרשימה שמתקבלת כאן לא עברה את הסינון הידני של המחקר (למשל אדם אחר עם אותו שם). ",
      h("strong", {}, "תמונת המצב המקורית של המחקר היא נקודת הייחוס"), " — החיפוש כאן נועד לבדיקה מדגמית בלבד, ואינו משנה את נתוני המחקר."),
    h("div", { class: "card" },
      h("h2", {}, "בחירת תיקים"),
      h("p", {}, "לכל תיק מופעלת אותה שאילתת „שם מדויק” של העבודה, בשני חלונות הזמן (שלב הערכאה הדיונית ושלב הערעור). נשמרות רק ידיעות שתאריכן בתוך החלון. ",
        "כדי לא להעמיס על Google, הבקשות נשלחות אחת-אחת עם השהיה, והריצה נעצרת אם Google מבקש להאט. מומלץ להתחיל בשנה אחת או בכמה תיקים."),
      h("div", { class: "row" },
        h("label", { class: "field" }, "שנה", h("select", { onchange: (e) => { MEDIA_YEAR = e.target.value; renderList(); } },
          h("option", { value: "" }, "כל השנים"), years.map((y) => h("option", { value: y, selected: y === MEDIA_YEAR }, y)))),
        h("button", { class: "btn btn-light", onclick: () => { cases.filter((c) => !MEDIA_YEAR || String(c.year) === MEDIA_YEAR).slice(0, mc.max_cases).forEach((c) => MEDIA_SEL.add(c.case_id)); renderList(); } }, "בחירת כל התיקים המוצגים"),
        h("button", { class: "btn btn-light", onclick: () => { MEDIA_SEL.clear(); renderList(); } }, "ניקוי הבחירה"),
        h("label", { class: "field" }, "השהיה בין בקשות (שניות, מינימום " + mc.min_delay + ")", delayInput)),
      listEl,
      h("div", { class: "row", style: "margin-top:.6rem" }, selInfo, h("span", { class: "spacer" }),
        h("button", { class: "btn btn-green btn-big", onclick: async () => {
          if (!MEDIA_SEL.size) return alert("בחרו לפחות תיק אחד.");
          if (!confirm(`להתחיל חיפוש ב-Google News עבור ${MEDIA_SEL.size} תיקים?\n${selInfo.textContent}\nאל תסגרו את הלשונית בזמן החיפוש.`)) return;
          try { await post("/api/media/start", { case_ids: [...MEDIA_SEL], delay: Number(delayInput.value) }); poll(); } catch (e) { alert(e.message); } } }, "התחלת החיפוש"))),
    statusEl,
    h("div", { class: "card" }, h("div", { class: "row" }, h("h2", {}, "תוצאות"), h("span", { class: "spacer" }),
      h("button", { class: "btn btn-light", onclick: async () => { if (confirm("למחוק את תוצאות החיפוש החוזר שנשמרו? (נתוני המחקר לא ישתנו)")) { try { await post("/api/media/reset", {}); refresh(); } catch (e) { alert(e.message); } } } }, "ניקוי תוצאות")),
      resultsEl),
    h("div", { class: "card" }, h("h2", {}, "מאגר העיתונות Primo"),
      h("p", {}, "חיפוש במאגר העיתונות של הספרייה (Primo) דורש כניסה עם שם המשתמש של הספרייה, ולכן ", h("strong", {}, "אינו מבוצע אוטומטית בכלי הזה"),
        ". הרשומות שנאספו במחקר מוצגות בכרטיס כל תיק (מסך א), והשאילתה ששימשה מופיעה שם.")));
  delayInput.addEventListener("input", updateSel);
  renderList();
  const st = await refresh();
  function poll() {
    clearTimers();
    const t = setInterval(async () => { try { const s = await refresh(); if (s.job.state !== "running") clearInterval(t); } catch (e) { clearInterval(t); } }, 2000);
    timers.push(t);
  }
  if (st.job.state === "running") poll();
}

function mediaResults(list) {
  if (!list.length) return h("p", { class: "muted" }, "עדיין אין תוצאות. בחרו תיקים ולחצו „התחלת החיפוש”.");
  const itemLi = (it, badge) => h("li", {}, it.published_date, " · ", it.url ? h("a", { href: it.url, target: "_blank", rel: "noopener noreferrer" }, it.title) : it.title,
    it.source ? h("span", { class: "muted" }, " (" + it.source + ")") : null, badge ? [" ", badge] : null);
  return list.map((c) => h("details", { class: "card" },
    h("summary", {}, h("strong", {}, c.case_number), " · ", h("span", { class: "q" }, c.query), " · ",
      `עכשיו בחלון: ${c.now_count} (מתוכן ${c.overlap} גם במקור) · במחקר המקורי: ${c.original_count}`,
      c.errors.length ? h("span", { class: "badge bad" }, " שגיאות: " + c.errors.length) : null),
    h("div", { class: "compare" },
      h("div", {}, h("h3", {}, "נמצא עכשיו (בתוך החלון)"), c.now_items.length ? h("ul", {}, c.now_items.map((it) => itemLi(it, it.also_in_original ? h("span", { class: "badge yes" }, "גם במקור") : null))) : h("p", { class: "muted" }, "לא נמצאו ידיעות.")),
      h("div", {}, h("h3", {}, "תמונת המצב המקורית (נכללו)"), c.original_items.length ? h("ul", {}, c.original_items.map((it) => itemLi(it))) : h("p", { class: "muted" }, "אין ידיעות במקור.")))));
}

async function wizExport(body) {
  const exportStatus1 = h("div", { class: "save-status" });
  const exportStatus2 = h("div", { class: "save-status" });
  const court = await api("/api/court/status");
  const media = await api("/api/media/status");
  body.replaceChildren(
    h("div", { class: "card" }, h("h2", {}, "ייצוא הנתונים שיובאו מחדש"),
      helpLine("שמירת תוצאות השלבים הקודמים לקובצי Excel או CSV. בכל שמירה נפתח חלון של Windows לבחירת המיקום."),
      h("h3", {}, "אוכלוסיית התיקים (שלב 1)"),
      court.result ? h("div", { class: "row" },
        saveButton("Excel…", "court_xlsx", { status: exportStatus1 }), saveButton("CSV…", "court_csv", { light: true, status: exportStatus1 }),
        h("span", { class: "muted" }, `${court.result.found} מתוך ${court.result.study_n} תיקי מחקר שוחזרו`), exportStatus1)
        : h("p", { class: "muted" }, "עדיין לא נבנתה אוכלוסייה בהפעלה הנוכחית — חזרו לשלב 1."),
      h("h3", {}, "ידיעות Google News (שלב 2)"),
      media.cases.length ? h("div", { class: "row" },
        saveButton("Excel…", "media_xlsx", { status: exportStatus2 }), saveButton("CSV…", "media_csv", { light: true, status: exportStatus2 }),
        h("span", { class: "muted" }, `${media.cases.length} תיקים נבדקו`), exportStatus2)
        : h("p", { class: "muted" }, "עדיין אין תוצאות חיפוש — חזרו לשלב 2."),
      h("h3", {}, "תיקיית ברירת המחדל"),
      h("div", { class: "row" }, pathEl(INFO.output_dir), h("button", { class: "btn btn-light", onclick: () => openFolder(INFO.output_dir) }, "פתיחה"))));
}

// ------------------------------------------------------------------ ד. upload your own file
async function viewUpload() {
  const tplStatus = h("div", { class: "save-status" });
  const st = await api("/api/upload/status");
  const reportEl = h("div");
  const fileInput = h("input", { type: "file", accept: ".xlsx,.xls,.csv", id: "fileInput" });
  function renderReport(name, rep) {
    if (!rep) { reportEl.replaceChildren(); return; }
    reportEl.replaceChildren(h("div", { class: "card" },
      h("h2", {}, "בדיקת הקובץ: ", name),
      rep.ok ? h("div", { class: "banner ok" }, h("span", { class: "check" }, "✓"), h("span", { class: "big" }, "הקובץ תקין"),
        h("span", {}, `${fmtInt(rep.n_rows)} שורות, מתוכן ${fmtInt(rep.n_main)} במדגם הניתוח.`))
        : h("div", { class: "banner bad" }, h("span", { class: "check" }, "✗"), h("span", { class: "big" }, "יש לתקן את הקובץ לפני הניתוח")),
      rep.errors && rep.errors.length ? h("ul", { class: "errors" }, rep.errors.map((e) => h("li", {}, e))) : null,
      rep.warnings && rep.warnings.length ? [h("h3", {}, "הערות"), h("ul", { class: "warnings" }, rep.warnings.map((e) => h("li", {}, e)))] : null,
      rep.ok ? h("a", { class: "btn btn-green btn-big", href: "#stats-upload" }, "הרצת הניתוחים על הקובץ") : null));
  }
  view().replaceChildren(
    h("h1", {}, "ייבוא קובץ נתונים משלך"),
    helpLine("אפשר להריץ את אותם ניתוחים של העבודה על נתונים אחרים — למשל אחרי תיקון קידוד ידני. מורידים תבנית, ממלאים, מעלים, והכלי בודק שהקובץ תקין."),
    h("div", { class: "card" }, h("h2", {}, "1. תבנית"),
      h("p", {}, "שורה לכל תיק; שמות העמודות בשורה הראשונה חייבים להישאר כמו בתבנית. חובה: media_any (בולטות 0/1) ו-intervention (התערבות 0/1). הסבר לכל עמודה נמצא בגיליון „הסבר העמודות”."),
      h("div", { class: "row" },
        saveButton("שמירת תבנית Excel…", "template_xlsx", { status: tplStatus }),
        saveButton("שמירת נתוני המחקר כדוגמה מלאה…", "study_xlsx", { light: true, status: tplStatus })),
      tplStatus),
    h("div", { class: "card" }, h("h2", {}, "2. העלאת הקובץ"),
      h("p", {}, "קובץ Excel ‏(‎.xlsx‏) או CSV. הקובץ נשאר במחשב — הוא נקרא על ידי התוכנה המקומית בלבד."),
      h("div", { class: "row" }, fileInput,
        h("button", { class: "btn btn-green", onclick: async () => {
          const f = fileInput.files[0];
          if (!f) return alert("בחרו קובץ.");
          reportEl.replaceChildren(h("p", { class: "loading" }, "בודק את הקובץ…"));
          try { const r = await post("/api/upload", { filename: f.name }, await f.arrayBuffer()); renderReport(f.name, r.report); }
          catch (e) { reportEl.replaceChildren(errorBox(e)); } } }, "העלאה ובדיקה"))),
    reportEl);
  if (st.report) renderReport(st.name, st.report);
}

// ------------------------------------------------------------------ start
(async function start() {
  try {
    INFO = await api("/api/info");
    renderFooter();
  } catch (e) {
    view().replaceChildren(errorBox("לא ניתן להתחבר לתוכנה המקומית. הפעילו אותה מחדש דרך „הפעלה.bat”."));
    return;
  }
  heartbeat();
  hbTimer = setInterval(heartbeat, 5000);
  route();
})();
