"""Where things live — always relative to the program folder or chosen at runtime (no machine-specific paths).

Packaged layout (inside the ZIP):
    SeminarDataTool\\
        SeminarDataTool.exe      small launcher: checks that the ZIP was extracted, then starts app\\
        הפעלה.bat                same, without the launcher
        app\\SeminarDataToolApp.exe + app\\_internal\\   (Python runtime, libraries, web pages)
        data\\                    bundled study data (read-only)
        תוצרים\\                  created at first run: exports, downloads, log, settings

If the program folder is not writable (Program Files, read-only USB / network share, no permission),
outputs go to  Documents\\SeminarDataTool\\תוצרים  (or LocalAppData\\..., or TEMP\\... as a last resort).
"""
from __future__ import annotations

import json
import os
import sys
import threading
import uuid
from pathlib import Path
from typing import Any

APP_NAME = "SeminarDataTool"
VERSION = "1.1.0"
FROZEN = bool(getattr(sys, "frozen", False))
OUT_NAME = "תוצרים"

if FROZEN:
    APP_DIR = Path(sys.executable).resolve().parent          # ...\SeminarDataTool\app
    BUNDLE_DIR = Path(getattr(sys, "_MEIPASS", APP_DIR))
else:
    APP_DIR = Path(__file__).resolve().parents[2]            # ...\05_תוכנה (source checkout)
    BUNDLE_DIR = Path(__file__).resolve().parent

# the package root = the folder the user extracted (parent of app\ in the packaged layout)
ROOT_DIR = APP_DIR.parent if (APP_DIR.name.lower() == "app" and (APP_DIR.parent / "data").is_dir()) else APP_DIR
WEB_DIR = BUNDLE_DIR / "web"


def _find_data_dir() -> Path:
    for cand in (os.environ.get("SEMINAR_TOOL_DATA"), ROOT_DIR / "data", APP_DIR / "data", BUNDLE_DIR / "data"):
        if cand and (Path(cand) / "study_dataset_final.csv").exists():
            return Path(cand)
    return ROOT_DIR / "data"


DATA_DIR = _find_data_dir()


def writable(folder: Path) -> bool:
    """True if we can create the folder and write/delete a file in it."""
    try:
        folder.mkdir(parents=True, exist_ok=True)
        probe = folder / f".write_test_{os.getpid()}"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True
    except OSError:
        return False


def known_folder(guid: str) -> Path | None:
    """Real location of a Windows known folder (e.g. Documents redirected to OneDrive)."""
    try:
        import ctypes

        class GUID(ctypes.Structure):
            _fields_ = [("b", ctypes.c_ubyte * 16)]

        g = GUID.from_buffer_copy(uuid.UUID(guid).bytes_le)
        ptr = ctypes.c_wchar_p()
        if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(g), 0, None, ctypes.byref(ptr)) != 0:
            return None
        value = ptr.value
        ctypes.windll.ole32.CoTaskMemFree(ptr)
        return Path(value) if value else None
    except Exception:  # noqa: BLE001 - non-Windows or API missing
        return None


FOLDERID_DOCUMENTS = "FDD39AD0-238F-46AF-ADB4-6C85480369C7"
FOLDERID_LOCALAPPDATA = "F1B32785-6FBA-4FCF-9D55-7B8E7F157091"


def _find_output_dir() -> tuple[Path, bool, str]:
    """(folder, is_default, Hebrew explanation when a fallback is used)."""
    env = os.environ.get("SEMINAR_TOOL_OUTPUT")
    if env and writable(Path(env)):
        return Path(env), True, ""
    local = ROOT_DIR / OUT_NAME
    if writable(local):
        return local, True, ""
    reason = (f"לא ניתן לשמור קבצים בתיקיית התוכנה ({ROOT_DIR}) — למשל תיקייה מוגנת כמו Program Files, "
              "כונן או תיקיית רשת לקריאה בלבד, או תיקייה ללא הרשאת כתיבה. לכן הקבצים יישמרו בתיקייה החלופית שלהלן.")
    docs = known_folder(FOLDERID_DOCUMENTS) or (Path.home() / "Documents")
    lad = known_folder(FOLDERID_LOCALAPPDATA) or (Path(os.environ["LOCALAPPDATA"]) if os.environ.get("LOCALAPPDATA") else None)
    for base in (docs, lad, Path(os.environ.get("TEMP") or os.environ.get("TMP") or Path.home())):
        if base and base.exists():
            cand = base / APP_NAME / OUT_NAME
            if writable(cand):
                return cand, False, reason
    raise OSError("לא נמצאה אף תיקייה שאפשר לשמור בה קבצים (תיקיית התוכנה, המסמכים, AppData ו-TEMP חסומות).")


OUTPUT_DIR, OUTPUT_IS_DEFAULT, OUTPUT_REASON = _find_output_dir()
LOG_FILE = OUTPUT_DIR / "log.txt"
LOCK_FILE = OUTPUT_DIR / ".server.json"
SETTINGS_FILE = OUTPUT_DIR / "settings.json"

# ---------------------------------------------------------------- remembered choices (last save folder etc.)
_settings_lock = threading.Lock()


def load_settings() -> dict[str, Any]:
    try:
        return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def get_setting(key: str, default: Any = None) -> Any:
    return load_settings().get(key, default)


def set_setting(key: str, value: Any) -> None:
    with _settings_lock:
        s = load_settings()
        s[key] = value
        try:
            SETTINGS_FILE.write_text(json.dumps(s, ensure_ascii=False, indent=1), encoding="utf-8")
        except OSError:
            pass


def last_dir() -> Path:
    """Folder offered first in save dialogs: the last one the user chose, else תוצרים."""
    p = get_setting("last_dir")
    if p and Path(p).is_dir():
        return Path(p)
    return OUTPUT_DIR
