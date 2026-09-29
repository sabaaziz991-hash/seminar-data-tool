"""Local web server (127.0.0.1 only) that serves the Hebrew UI and a small JSON API.

The browser page sends a heartbeat every few seconds and a 'bye' beacon when the tab is closed;
the server stops itself when no page is open any more (or when the user presses 'סגירה').
"""
from __future__ import annotations

import json
import logging
import mimetypes
import os
import threading
import time
import traceback
import uuid
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pandas as pd

from . import dialogs, exports, paths, reimport_court, reimport_media, text_measures
from .data_access import StudyData
from .jobs import Job

log = logging.getLogger("seminar_tool")

HEARTBEAT_TIMEOUT = 180.0     # background tabs may be throttled to one timer per minute
BYE_GRACE = 10.0              # a page reload sends 'bye' and then a new heartbeat within a second
FIRST_CONNECT_TIMEOUT = 600.0
TOKEN_HEADER = "X-Requested-With"
TOKEN_VALUE = "SeminarDataTool"


XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
CSV = "text/csv; charset=utf-8"
# kind -> (GET path used for the browser-download fallback, Hebrew dialog title)
EXPORT_KINDS = {
    "study_xlsx": ("/api/study.xlsx", "שמירת נתוני המחקר"),
    "court_xlsx": ("/api/court/result.xlsx", "שמירת האוכלוסייה המשוחזרת"),
    "court_csv": ("/api/court/result.csv", "שמירת האוכלוסייה המשוחזרת"),
    "media_xlsx": ("/api/media/export.xlsx", "שמירת ידיעות Google News"),
    "media_csv": ("/api/media/export.csv", "שמירת ידיעות Google News"),
    "text_xlsx": ("/api/text/result.xlsx", "שמירת מדדי הטקסט"),
    "text_csv": ("/api/text/result.csv", "שמירת מדדי הטקסט"),
    "log_txt": ("/api/log.txt", "שמירת עותק של יומן התוכנה"),
}


def build_export(kind: str) -> tuple[bytes, str, str]:
    """(file bytes, suggested Hebrew file name, content type) for every export of the tool."""
    st = STATE
    assert st is not None
    if kind == "study_xlsx":
        return exports.frames_to_excel([("נתונים", st.sd.df)]), "נתוני_המחקר_497_תיקים.xlsx", XLSX
    if kind in ("text_xlsx", "text_csv"):
        res = st.text()
        if kind == "text_csv":
            return res["table"].to_csv(index=False).encode("utf-8-sig"), "מדדי_טקסט_497_פסקי_דין.csv", CSV
        cmp = pd.DataFrame(res["rows"]).rename(columns={"measure": "מדד", "equal": "זהה למחקר", "n": "פסקי דין",
                                                        "max_diff": "הפרש מרבי"})
        data = exports.frames_to_excel([("השוואה למחקר", cmp), ("מדדים לכל פסק דין", res["table"]),
                                        ("אזכורי תקשורת - שלב אוטומטי", res["candidates"])])
        return data, "מדדי_טקסט_497_פסקי_דין.xlsx", XLSX
    if kind in ("court_xlsx", "court_csv"):
        res = st.jobs["build"].result
        if not res:
            raise ValueError("עדיין לא נבנתה אוכלוסייה.")
        if kind == "court_csv":
            return res["table"].to_csv(index=False).encode("utf-8-sig"), "אוכלוסייה_משוחזרת.csv", CSV
        flow = pd.DataFrame(res["summary"]["flow"]).rename(columns={"step": "שלב", "count": "בשחזור", "paper": "בעבודה", "note": "הערה"})
        data = exports.frames_to_excel([("שלבי הסינון", flow), ("אוכלוסייה משוחזרת", res["table"]),
                                        ("תיק שסווג אחרת", res["missing"])])
        return data, "אוכלוסייה_משוחזרת.xlsx", XLSX
    if kind in ("media_xlsx", "media_csv"):
        df = reimport_media.export_rows(st.sd)
        if kind == "media_csv":
            return df.to_csv(index=False).encode("utf-8-sig"), "ידיעות_Google_News_ייבוא_מחדש.csv", CSV
        return exports.frames_to_excel([("ידיעות", df)]), "ידיעות_Google_News_ייבוא_מחדש.xlsx", XLSX
    if kind == "log_txt":
        raw = paths.LOG_FILE.read_bytes() if paths.LOG_FILE.exists() else b""
        return raw, "יומן_התוכנה_SeminarDataTool.txt", "text/plain; charset=utf-8"
    raise ValueError("סוג ייצוא לא מוכר")


def reveal(path: Path) -> None:
    """Open Explorer with the file selected (full path to explorer.exe: works with a minimal PATH)."""
    import subprocess

    windir = os.environ.get("SystemRoot") or os.environ.get("windir") or r"C:\Windows"
    if path.is_file():
        subprocess.Popen(f'"{Path(windir) / "explorer.exe"}" /select,"{path}"')
    else:
        os.startfile(str(path))  # noqa: S606


class AppState:
    def __init__(self) -> None:
        self.sd = StudyData()
        self.paper_flow = json.loads((self.sd.dir / "flow_reference.json").read_text(encoding="utf-8"))
        self._text_lock = threading.Lock()
        self.text_result: dict[str, Any] | None = None
        self.jobs = {"download": Job("download"), "build": Job("build"), "media": Job("media")}
        self.court_result: dict[str, Any] | None = None
        self.opened_dirs: set[str] = {str(paths.OUTPUT_DIR), str(paths.DATA_DIR)}
        self.saved: set[str] = set()          # files/folders written in this session (may be revealed in Explorer)
        # heartbeat bookkeeping
        self.clients: dict[str, float] = {}
        self.ever_connected = False
        self.last_bye = 0.0
        self.started = time.time()
        self.server: ThreadingHTTPServer | None = None
        self.stopping = False
        self.url_box_open = False              # the "open this address in a browser" window is showing
        self.run_id = uuid.uuid4().hex[:12]    # pages of an earlier run (old tabs) are told to reload

    # ---------------------------------------------------------------- text measures (step 3)
    def text(self) -> dict[str, Any]:
        with self._text_lock:
            if self.text_result is None:
                self.text_result = text_measures.compute(self.sd)
            return self.text_result

    # ---------------------------------------------------------------- lifetime
    def heartbeat(self, client: str) -> None:
        self.clients[client] = time.time()
        self.ever_connected = True

    def bye(self, client: str) -> None:
        self.clients.pop(client, None)
        self.last_bye = time.time()

    def shutdown(self, reason: str) -> None:
        if self.stopping:
            return
        self.stopping = True
        log.info("shutting down: %s", reason)
        for job in self.jobs.values():
            job.stop()
        if self.server:
            threading.Thread(target=self.server.shutdown, daemon=True).start()

    def watchdog(self) -> None:
        while not self.stopping:
            time.sleep(2)
            now = time.time()
            for c, t in list(self.clients.items()):
                if now - t > HEARTBEAT_TIMEOUT:
                    self.clients.pop(c, None)
            if not self.ever_connected:
                if now - self.started > FIRST_CONNECT_TIMEOUT and not self.url_box_open:
                    self.shutdown("no browser connected")
            elif not self.clients and now - max(self.last_bye, self.started) > BYE_GRACE:
                self.shutdown("browser tab closed")


STATE: AppState | None = None


def content_disposition(filename: str) -> str:
    """Hebrew file name for modern browsers (RFC 5987) + a plain ASCII fallback."""
    ascii_name = "SeminarDataTool_export" + Path(filename).suffix
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{urllib.parse.quote(filename)}"


class Handler(BaseHTTPRequestHandler):
    server_version = "SeminarDataTool"
    protocol_version = "HTTP/1.1"

    # ---------------------------------------------------------------- plumbing
    def log_message(self, fmt: str, *args: Any) -> None:  # route to the log file (no console in the EXE)
        if "/api/heartbeat" not in (args[0] if args else ""):
            log.debug("%s - %s", self.address_string(), fmt % args)

    def _send(self, code: int, body: bytes, ctype: str, extra: dict[str, str] | None = None) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def json(self, obj: Any, code: int = 200) -> None:
        self._send(code, json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8"), "application/json; charset=utf-8")

    def error(self, msg: str, code: int = 400) -> None:
        self.json({"ok": False, "error": msg}, code)

    def file_download(self, data: bytes, filename: str, ctype: str) -> None:
        self._send(200, data, ctype, {"Content-Disposition": content_disposition(filename)})

    def host_ok(self) -> bool:
        host = (self.headers.get("Host") or "").split(":")[0]
        return host in ("127.0.0.1", "localhost")

    def body(self) -> bytes:
        n = int(self.headers.get("Content-Length") or 0)
        if n > 60_000_000:
            raise ValueError("הקובץ גדול מדי (מעל 60MB).")
        return self.rfile.read(n) if n else b""

    def body_json(self) -> dict[str, Any]:
        raw = self.body()
        return json.loads(raw.decode("utf-8")) if raw else {}

    # ---------------------------------------------------------------- GET
    def do_GET(self) -> None:  # noqa: N802
        if not self.host_ok():
            return self.error("forbidden", 403)
        url = urllib.parse.urlparse(self.path)
        q = {k: v[0] for k, v in urllib.parse.parse_qs(url.query).items()}
        try:
            self.route_get(url.path, q)
        except Exception as exc:  # noqa: BLE001
            log.error("GET %s failed: %s", self.path, traceback.format_exc())
            self.error(str(exc) or "שגיאה פנימית", 500)

    do_HEAD = do_GET

    def route_get(self, path: str, q: dict[str, str]) -> None:
        st = STATE
        assert st is not None
        if path in ("/", "/index.html"):
            return self.static("index.html")
        if path.startswith("/static/"):
            return self.static(path[len("/static/"):])
        if path == "/api/ping":
            return self.json({"ok": True, "app": paths.APP_NAME, "version": paths.VERSION})
        if path == "/api/info":
            return self.json({"ok": True, "version": paths.VERSION, "data_dir": str(paths.DATA_DIR),
                              "output_dir": str(paths.OUTPUT_DIR), "output_is_default": paths.OUTPUT_IS_DEFAULT,
                              "output_reason": paths.OUTPUT_REASON, "root_dir": str(paths.ROOT_DIR),
                              "app_dir": str(paths.APP_DIR), "frozen": paths.FROZEN, "log_file": str(paths.LOG_FILE),
                              "last_dir": str(paths.last_dir()), "clients": len(st.clients), "run_id": st.run_id,
                              "n_cases": int(len(st.sd.df)), "n_main": int((st.sd.df.merits_appeal == 1).sum())})
        if path == "/api/cases":
            return self.json({"ok": True, "cases": st.sd.case_list()})
        if path == "/api/case":
            card = st.sd.case_card(q.get("id", ""))
            return self.json({"ok": True, "card": card}) if card else self.error("התיק לא נמצא", 404)
        if path == "/api/text/measures":
            res = st.text()
            return self.json({"ok": True, **{k: res[k] for k in ("rows", "mentions", "attempt", "all_ok", "n_cases")}})
        for kind, (get_path, _) in EXPORT_KINDS.items():
            if path == get_path:
                data, name, ctype = build_export(kind)
                return self.file_download(data, name, ctype)
        if path == "/api/court/status":
            return self.json({"ok": True, "local_copies": reimport_court.find_local_copies(),
                              "default_path": str(reimport_court.default_download_path()),
                              "download_dir": str(reimport_court.download_dir()), "url": reimport_court.HF_URL,
                              "page": reimport_court.HF_PAGE, "download": st.jobs["download"].status(),
                              "build": st.jobs["build"].status(),
                              "result": (st.jobs["build"].result or {}).get("summary") if st.jobs["build"].state == "done" else None})
        if path == "/api/media/cases":
            return self.json({"ok": True, "cases": st.sd.media_cases(), "max_cases": reimport_media.MAX_CASES,
                              "min_delay": reimport_media.MIN_DELAY, "default_delay": reimport_media.DEFAULT_DELAY})
        if path == "/api/media/status":
            ids = [x for x in q.get("ids", "").split(",") if x] or None
            return self.json({"ok": True, "job": st.jobs["media"].status(), "cases": reimport_media.summary(st.sd, ids),
                              "store": str(reimport_media.STORE)})
        return self.error("not found", 404)

    def static(self, rel: str) -> None:
        base = paths.WEB_DIR.resolve()
        target = (base / rel).resolve()
        if base not in target.parents or not target.is_file():
            return self.error("not found", 404)
        ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript",):
            ctype += "; charset=utf-8"
        self._send(200, target.read_bytes(), ctype)

    # ---------------------------------------------------------------- POST
    def do_POST(self) -> None:  # noqa: N802
        if not self.host_ok():
            return self.error("forbidden", 403)
        url = urllib.parse.urlparse(self.path)
        st = STATE
        assert st is not None
        try:
            if url.path == "/api/bye":                      # sent by navigator.sendBeacon (no custom headers)
                st.bye(self.body().decode("utf-8", "ignore")[:64])
                return self._send(204, b"", "text/plain")
            if self.headers.get(TOKEN_HEADER) != TOKEN_VALUE:
                return self.error("forbidden", 403)
            self.route_post(url.path)
        except Exception as exc:  # noqa: BLE001
            log.error("POST %s failed: %s", self.path, traceback.format_exc())
            self.error(str(exc) or "שגיאה פנימית", 500)

    def route_post(self, path: str) -> None:
        st = STATE
        assert st is not None
        if path == "/api/heartbeat":
            b = self.body_json()
            if b.get("run") != st.run_id:          # a tab left open from an earlier run of the program
                return self.json({"ok": False, "stale": True, "error": "stale page"}, 409)
            st.heartbeat(str(b.get("client", ""))[:64])
            return self.json({"ok": True, "jobs": {k: j.state for k, j in st.jobs.items()}})
        if path == "/api/shutdown":
            self.json({"ok": True})
            return st.shutdown("user pressed close")
        if path == "/api/save":                           # native "Save as" dialog, then write the file
            b = self.body_json()
            kind = b.get("kind", "")
            if kind not in EXPORT_KINDS:
                return self.error("סוג ייצוא לא מוכר")
            data, name, _ = build_export(kind)
            ext = Path(name).suffix
            label = {".xlsx": "קובץ Excel", ".csv": "קובץ CSV", ".txt": "קובץ טקסט"}.get(ext, "קובץ")
            try:
                target = dialogs.save_file(EXPORT_KINDS[kind][1], paths.last_dir(), name, ext, label)
            except dialogs.DialogUnavailable as exc:
                log.warning("save dialog unavailable: %s", exc)
                return self.json({"ok": False, "fallback": True, "href": EXPORT_KINDS[kind][0],
                                  "error": "חלון הבחירה של Windows אינו זמין — הקובץ יורד לתיקיית ההורדות של הדפדפן."})
            if target is None:
                return self.json({"ok": True, "cancelled": True})
            if not target.suffix:
                target = target.with_suffix(ext)
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
            except OSError as exc:
                return self.error(f"לא ניתן לשמור בתיקייה שנבחרה ({exc.strerror or exc}). בחרו תיקייה אחרת.")
            paths.set_setting("last_dir", str(target.parent))
            st.saved.update({str(target), str(target.parent)})
            return self.json({"ok": True, "path": str(target), "folder": str(target.parent)})
        if path == "/api/choose":                         # native folder / file chooser, returns the path only
            b = self.body_json()
            what = b.get("what", "")
            try:
                if what == "hf_folder":
                    res = dialogs.choose_folder("בחירת תיקייה להורדת מאגר פסקי הדין (כ-1.5 GB)", reimport_court.download_dir())
                elif what == "parquet_file":
                    res = dialogs.open_file("בחירת הקובץ cases_all.parquet", paths.get_setting("hf_dir") or Path.home(),
                                            "*.parquet", "קובץ Parquet")
                else:
                    return self.error("בחירה לא מוכרת")
            except dialogs.DialogUnavailable:
                return self.json({"ok": False, "fallback": True,
                                  "error": "חלון הבחירה של Windows אינו זמין — הקלידו את הנתיב בשדה."})
            if res is None:
                return self.json({"ok": True, "cancelled": True})
            if what == "hf_folder":
                if not paths.writable(res):
                    return self.error("לא ניתן לשמור בתיקייה שנבחרה. בחרו תיקייה אחרת.")
                paths.set_setting("hf_dir", str(res))
                st.opened_dirs.add(str(res))
                return self.json({"ok": True, "path": str(res), "download_path": str(reimport_court.default_download_path())})
            if what == "parquet_file":
                paths.set_setting("last_parquet", str(res))
            return self.json({"ok": True, "path": str(res)})
        if path == "/api/reveal":                         # open Explorer at a file/folder the tool wrote
            p = Path(self.body_json().get("path", ""))
            if str(p) not in st.saved and str(p) not in st.opened_dirs:
                return self.error("אפשר לפתוח רק קבצים ותיקיות שהכלי שמר.")
            if not p.exists():
                return self.error("הקובץ כבר אינו קיים.")
            reveal(p)
            return self.json({"ok": True})
        if path == "/api/open_folder":
            p = Path(self.body_json().get("path", ""))
            if str(p) not in st.opened_dirs or not p.is_dir():
                return self.error("אפשר לפתוח רק תיקיות שהכלי יצר.")
            os.startfile(str(p))  # noqa: S606 - local folder chosen by the tool itself
            return self.json({"ok": True})
        if path == "/api/court/download":
            dest = reimport_court.default_download_path()
            if not paths.writable(dest.parent):
                return self.error("לא ניתן לשמור בתיקיית ההורדה. בחרו תיקייה אחרת (כפתור „שינוי…”).")
            st.opened_dirs.add(str(dest.parent))
            if not st.jobs["download"].start(reimport_court.download, dest):
                return self.error("ההורדה כבר פועלת.")
            return self.json({"ok": True, "dest": str(dest)})
        if path == "/api/court/check":
            info = reimport_court.check_parquet(self.body_json().get("path", "").strip().strip('"'))
            return self.json({"ok": True, **info})
        if path == "/api/court/build":
            p = self.body_json().get("path", "").strip().strip('"')
            reimport_court.check_parquet(p)
            paths.set_setting("last_parquet", p)
            if not st.jobs["build"].start(reimport_court.build_population, p, st.sd.df, st.paper_flow):
                return self.error("הבנייה כבר פועלת.")
            st.opened_dirs.add(str(reimport_court.COURT_DIR))
            return self.json({"ok": True})
        if path == "/api/job/stop":
            name = self.body_json().get("job", "")
            if name in st.jobs:
                st.jobs[name].stop()
            return self.json({"ok": True})
        if path == "/api/media/start":
            b = self.body_json()
            ids = list(dict.fromkeys(b.get("case_ids") or []))
            if not ids:
                return self.error("לא נבחרו תיקים.")
            if len(ids) > reimport_media.MAX_CASES:
                return self.error(f"אפשר לבחור עד {reimport_media.MAX_CASES} תיקים בכל ריצה (כדי לא להעמיס על Google News).")
            cases = [c for c in st.sd.media_cases() if c["case_id"] in set(ids)]
            delay = max(reimport_media.MIN_DELAY, float(b.get("delay") or reimport_media.DEFAULT_DELAY))
            if not st.jobs["media"].start(reimport_media.run, cases, delay):
                return self.error("החיפוש כבר פועל.")
            st.opened_dirs.add(str(reimport_media.MEDIA_DIR))
            return self.json({"ok": True})
        if path == "/api/media/reset":
            if st.jobs["media"].running:
                return self.error("עצרו קודם את החיפוש.")
            reimport_media.reset()
            return self.json({"ok": True})
        return self.error("not found", 404)


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False

    def handle_error(self, request: Any, client_address: Any) -> None:
        """A browser that closes a connection early is normal; anything else goes to the log (no console in the EXE)."""
        import sys

        exc = sys.exc_info()[1]
        if isinstance(exc, (ConnectionResetError, ConnectionAbortedError, BrokenPipeError, TimeoutError)):
            log.debug("client disconnected: %s", exc)
            return
        log.error("request from %s failed: %s", client_address, traceback.format_exc())


def make_server(port: int) -> Server:
    global STATE
    STATE = AppState()
    srv = Server(("127.0.0.1", port), Handler)
    STATE.server = srv
    threading.Thread(target=STATE.watchdog, name="watchdog", daemon=True).start()
    return srv
