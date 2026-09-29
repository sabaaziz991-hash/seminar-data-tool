"""The packaged tool (dist\\SeminarDataTool) must start from a path with Hebrew letters and spaces and from a plain
ASCII path — through the launcher, the app EXE and הפעלה.bat — serve the UI, reproduce the paper's numbers, save
files where the user chooses, and stop cleanly (button or closed tab).
Run after build.py:  python -m pytest tests/test_packaged_exe.py -q
"""
from __future__ import annotations

import json
import shutil
import threading
import time
import urllib.request
from pathlib import Path

import pytest

from winutil import (APP, PKG, heartbeat, copy_package, find_window, get_bytes, get_json, is_topmost, new_temp, ping, post,
                     press, start_tool, stop_tool, wait_pid_exit, window_texts, IDCANCEL, clean_env)

pytestmark = pytest.mark.skipif(not (PKG / APP).exists(), reason="run build.py first")


@pytest.mark.parametrize("folder_name,how", [("בדיקה עברית עם רווח", "launcher"), ("sdt_ascii_test", "app")])
def test_exe_starts_serves_and_stops(folder_name: str, how: str) -> None:
    root = new_temp("sdt_exe_") / folder_name
    dest = copy_package(root)
    try:
        base, pid = start_tool(dest, how)
        info = get_json(base + "/api/info")
        assert info["frozen"] is True
        assert Path(info["data_dir"]) == dest / "data" and Path(info["output_dir"]) == dest / "תוצרים"
        assert info["output_is_default"] is True
        with urllib.request.urlopen(base + "/", timeout=30) as r:
            assert "כלי נתוני הסמינריון" in r.read().decode("utf-8")
        stats = get_json(base + "/api/stats?source=study")
        assert stats["golden"]["all_ok"], [i for i in stats["golden"]["items"] if not i["ok"]][:5]
        card = get_json(base + "/api/case?id=HUGGINGFACE-00ab1bad61ad")["card"]
        assert card["judgment"]["available"]                              # parquet (pyarrow) works in the EXE
        assert get_bytes(base + "/api/stats.xlsx?source=study")[:2] == b"PK"   # openpyxl works in the EXE
        assert stop_tool(base, pid) == 0
        assert (dest / "תוצרים" / "log.txt").exists()
        log = (dest / "תוצרים" / "log.txt").read_text(encoding="utf-8")
        assert "ERROR" not in log and "Traceback" not in log, log[-2000:]
    finally:
        shutil.rmtree(root.parent, ignore_errors=True)


def test_bat_launcher_from_hebrew_path_and_tab_close() -> None:
    """Double-click equivalent: `cmd /c הפעלה.bat`; then a heartbeat + 'bye' (tab closed) must stop the program."""
    root = new_temp("sdt_bat_") / "סמינריון בדיקה"
    dest = copy_package(root)
    try:
        base, pid = start_tool(dest, "bat", env=clean_env(SEMINAR_TOOL_NO_BROWSER="1"), args=[])
        heartbeat(base, "tab1")
        post(base + "/api/bye", b"tab1", headers={})                   # what the browser sends when the tab closes
        assert wait_pid_exit(pid, 40) == 0, "program kept running after the tab was closed"
        time.sleep(0.5)
        assert not (dest / "תוצרים" / ".server.json").exists(), "lock file should be removed on exit"
    finally:
        shutil.rmtree(root.parent, ignore_errors=True)


def test_save_anywhere_in_frozen_app() -> None:
    """Exports are written to the folder chosen in the (stubbed) dialog — here a folder outside the package."""
    root = new_temp("sdt_save_") / "חבילה"
    dest = copy_package(root)
    target = root.parent / "שמירה במקום אחר"
    target.mkdir()
    try:
        base, pid = start_tool(dest, "launcher", env=clean_env(SEMINAR_TOOL_DIALOG_STUB=str(target)))
        for kind in ("stats_xlsx", "study_xlsx", "template_xlsx", "media_csv", "log_txt"):
            res = post(base + "/api/save", {"kind": kind})
            assert res["ok"] and Path(res["path"]).parent == target and Path(res["path"]).stat().st_size > 0, res
        res = post(base + "/api/spss_export", {"folder": str(target / "SPSS")})
        assert (target / "SPSS" / "01_import_and_labels.sps").exists()
        assert get_json(base + "/api/info")["last_dir"] == str(target / "SPSS")      # remembered for the next dialog
        assert json.loads((dest / "תוצרים" / "settings.json").read_text(encoding="utf-8"))["last_dir"] == str(target / "SPSS")
        assert stop_tool(base, pid) == 0
    finally:
        shutil.rmtree(root.parent, ignore_errors=True)


def test_real_native_dialogs_open_on_top_and_cancel() -> None:
    """The real Windows 'Save as' and folder dialogs (tkinter) open above other windows, twice in a row from
    different request threads, and Cancel is reported back to the page."""
    root = new_temp("sdt_dlg_") / "dialogs"
    dest = copy_package(root)
    try:
        base, pid = start_tool(dest, "launcher")
        for kind, title, what in (("template_xlsx", "שמירת תבנית קובץ הנתונים", None),
                                  ("study_xlsx", "שמירת נתוני המחקר", None),
                                  (None, "בחירת תיקייה לקובצי SPSS", "spss_folder")):
            result: dict = {}

            def call() -> None:
                if kind:
                    result.update(post(base + "/api/save", {"kind": kind}, timeout=120))
                else:
                    result.update(post(base + "/api/choose", {"what": what}, timeout=120))

            t = threading.Thread(target=call)
            t.start()
            hwnd = find_window(title, 30)
            assert hwnd, f"dialog '{title}' did not appear"
            assert is_topmost(hwnd) or is_topmost(int(ctypes_parent(hwnd))), "dialog should be on top of the browser"
            press(hwnd, IDCANCEL)
            t.join(30)
            assert result.get("cancelled") is True, result
        assert stop_tool(base, pid) == 0
    finally:
        shutil.rmtree(root.parent, ignore_errors=True)


def ctypes_parent(hwnd: int) -> int:
    import ctypes

    return ctypes.windll.user32.GetWindow(hwnd, 4) or 0          # GW_OWNER
