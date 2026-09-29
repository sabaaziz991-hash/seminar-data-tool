"""Entry point: start the local server and open the default browser.

    SeminarDataToolApp.exe [--no-browser] [--port N]

* Only one copy runs at a time: a second start just opens the browser on the running copy.
* The program ends when the browser tab is closed (heartbeat) or when 'סגירה' is pressed.
* If no browser can be opened, a small window shows the address to type in a browser.
* Errors are written to תוצרים\\log.txt and shown in a Hebrew Windows message box (the EXE has no console).
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import socket
import sys
import threading
import time
import traceback
import urllib.request
import webbrowser

log = logging.getLogger("seminar_tool")
PREFERRED_PORTS = range(8765, 8785)
TITLE = "כלי נתוני הסמינריון"
EXTRACT_MSG = ("יש לחלץ את כל תוכן קובץ ה-ZIP לתיקייה (לחצן ימני ← חלץ הכל) ורק אז להפעיל.\n\n"
               "נראה שהתוכנה הופעלה מתוך קובץ ה-ZIP או שחסרים קבצים (התיקייה data).\n"
               "לאחר החילוץ: לחצו פעמיים על „הפעלה.bat” או על SeminarDataTool.exe שבתיקייה שחולצה.")
BROWSER_WAIT = 45.0

MB_OK, MB_RETRYCANCEL = 0x0, 0x5
MB_ICONERROR, MB_ICONWARNING, MB_ICONINFO = 0x10, 0x30, 0x40
MB_RIGHT, MB_RTLREADING, MB_TOPMOST, MB_SETFOREGROUND = 0x80000, 0x100000, 0x40000, 0x10000
IDRETRY = 4


class _NullWriter:
    def write(self, *_: object) -> int:
        return 0

    def flush(self) -> None:
        pass


def message_box(text: str, title: str = TITLE, flags: int = MB_ICONERROR) -> int:
    """Native Windows message box with right-to-left Hebrew layout. Returns the button id (0 if unavailable)."""
    try:
        import ctypes

        return ctypes.windll.user32.MessageBoxW(0, text, title, flags | MB_RIGHT | MB_RTLREADING | MB_TOPMOST | MB_SETFOREGROUND)
    except Exception:  # noqa: BLE001
        return 0


def setup_logging(paths) -> None:  # noqa: ANN001
    import warnings

    warnings.simplefilter("ignore")          # numerical warnings are not useful to the user
    if sys.stdout is None:        # windowed EXE: no console streams
        sys.stdout = _NullWriter()  # type: ignore[assignment]
    if sys.stderr is None:
        sys.stderr = _NullWriter()  # type: ignore[assignment]
    try:
        if paths.LOG_FILE.exists() and paths.LOG_FILE.stat().st_size > 2_000_000:
            paths.LOG_FILE.unlink()
    except OSError:
        pass
    logging.basicConfig(filename=str(paths.LOG_FILE), level=logging.INFO, encoding="utf-8",
                        format="%(asctime)s %(levelname)s %(message)s")


def running_instance(paths) -> str | None:  # noqa: ANN001
    """URL of an already running copy, if its lock file points to a live server."""
    try:
        info = json.loads(paths.LOCK_FILE.read_text(encoding="utf-8"))
        url = f"http://127.0.0.1:{int(info['port'])}/"
        with urllib.request.urlopen(url + "api/ping", timeout=2) as r:
            if json.loads(r.read().decode("utf-8")).get("app") == paths.APP_NAME:
                return url
    except Exception:  # noqa: BLE001
        return None
    return None


def free_port(requested: int | None) -> int:
    """The requested/preferred port if free, otherwise any free port chosen by Windows."""
    for port in ([requested] if requested else []) + list(PREFERRED_PORTS):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def open_browser(url: str) -> bool:
    if os.environ.get("SEMINAR_TOOL_SIMULATE_NO_BROWSER"):      # tests: behave as if no browser is available
        return False
    try:
        return bool(webbrowser.open(url))
    except Exception:  # noqa: BLE001
        return False


def browser_watch(url: str, state) -> None:  # noqa: ANN001
    """Open the default browser; if that fails (or no page connects), show the address in a small window."""
    opened = open_browser(url)
    log.info("default browser opened: %s", opened)
    if opened:
        t0 = time.time()
        while time.time() - t0 < BROWSER_WAIT and not state.ever_connected and not state.stopping:
            time.sleep(0.5)
    while not state.ever_connected and not state.stopping:
        state.url_box_open = True
        text = ("לא ניתן היה לפתוח את הדפדפן באופן אוטומטי.\n\n"
                "פתחו דפדפן (Edge, Chrome או Firefox) והקלידו בשורת הכתובת:\n\n"
                f"‎{url}‎\n\n"
                "(אפשר להעתיק את כל ההודעה הזו בלחיצה על Ctrl+C.)\n\n"
                "„ניסיון חוזר” — לנסות שוב לפתוח את הדפדפן ולהשאיר את התוכנה פועלת.\n"
                "„ביטול” — לסגור את התוכנה.")
        choice = message_box(text, TITLE + " — כתובת התוכנה", MB_RETRYCANCEL | MB_ICONINFO)
        state.url_box_open = False
        if choice == IDRETRY:
            open_browser(url)
            t0 = time.time()
            while time.time() - t0 < 20 and not state.ever_connected and not state.stopping:
                time.sleep(0.5)
            continue
        if not state.ever_connected:
            state.shutdown("user closed the address window without a browser")
        break


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="SeminarDataTool")
    ap.add_argument("--no-browser", action="store_true", help="do not open the browser (tests)")
    ap.add_argument("--port", type=int, default=None)
    args = ap.parse_args(argv)
    if os.environ.get("SEMINAR_TOOL_NO_BROWSER"):      # used by the automated tests of the .bat launcher
        args.no_browser = True

    from . import paths   # computes the data folder and a writable output folder (with fallback)

    setup_logging(paths)
    log.info("start %s %s frozen=%s root=%s data=%s out=%s default_out=%s", paths.APP_NAME, paths.VERSION, paths.FROZEN,
             paths.ROOT_DIR, paths.DATA_DIR, paths.OUTPUT_DIR, paths.OUTPUT_IS_DEFAULT)
    if not (paths.DATA_DIR / "study_dataset_final.csv").exists():
        log.warning("data folder missing: %s", paths.DATA_DIR)
        message_box(EXTRACT_MSG, TITLE, MB_ICONWARNING)
        return 2

    existing = running_instance(paths)
    if existing:
        log.info("already running at %s - opening browser", existing)
        if not args.no_browser and not open_browser(existing):
            message_box(f"התוכנה כבר פועלת. פתחו דפדפן והקלידו:\n‎{existing}‎", TITLE, MB_ICONINFO)
        return 0

    from .server import make_server  # heavy imports (pandas, scipy) only after the checks above

    port = free_port(args.port)
    try:
        srv = make_server(port)
    except OSError as exc:  # e.g. OneDrive "online-only" files that cannot be downloaded right now
        log.error("cannot read data: %s", traceback.format_exc())
        message_box("לא ניתן לקרוא את קובצי הנתונים של התוכנה.\n\n"
                    "אם התיקייה נמצאת ב-OneDrive: לחצו לחצן ימני על התיקייה ← „שמור תמיד במכשיר זה”, "
                    "או חלצו את קובץ ה-ZIP לתיקייה מקומית (למשל שולחן העבודה).\n\n"
                    f"פרטים: {exc}")
        return 3
    from . import server

    url = f"http://127.0.0.1:{port}/"
    paths.LOCK_FILE.write_text(json.dumps({"port": port, "pid": os.getpid()}), encoding="utf-8")
    log.info("serving on %s", url)
    if not args.no_browser:
        threading.Thread(target=browser_watch, args=(url, server.STATE), name="browser", daemon=True).start()
    try:
        srv.serve_forever(poll_interval=0.5)
    finally:
        srv.server_close()
        try:
            paths.LOCK_FILE.unlink()
        except OSError:
            pass
        log.info("stopped")
    return 0


def run() -> None:
    try:
        code = main()
    except Exception as exc:  # noqa: BLE001
        tb = traceback.format_exc()
        where = ""
        try:
            from . import paths

            log.error("fatal: %s", tb)
            where = "\n\nפרטים נשמרו בקובץ:\n‎" + str(paths.LOG_FILE) + "‎"
        except Exception:  # noqa: BLE001 - even the output folder is unavailable
            pass
        message_box(f"אירעה שגיאה והתוכנה נסגרה.\n\n{exc}{where}")
        code = 1
    sys.exit(code)


if __name__ == "__main__":
    run()
