"""Native Windows 'Save as' / 'Choose folder' / 'Open file' dialogs (tkinter.filedialog → the standard Windows dialogs).

The dialogs are shown by the local program (not by the browser), so files can be saved in any folder.
One dialog at a time; each call creates and destroys its own hidden, always-on-top Tk root in the calling thread.
For automated tests set SEMINAR_TOOL_DIALOG_STUB to a folder (the dialog is skipped and that folder is used)
or to "cancel" (behaves as if the user pressed Cancel).
"""
from __future__ import annotations

import logging
import os
import threading
from pathlib import Path
from typing import Callable

log = logging.getLogger("seminar_tool")
_LOCK = threading.Lock()


class DialogUnavailable(RuntimeError):
    """tkinter could not be used — the caller falls back to a browser download / typed path."""


def _stub() -> str | None:
    return os.environ.get("SEMINAR_TOOL_DIALOG_STUB")


def _run(fn: Callable) -> str:
    try:
        import tkinter as tk
        from tkinter import filedialog
    except Exception as exc:  # noqa: BLE001
        raise DialogUnavailable(str(exc)) from exc
    with _LOCK:
        try:
            root = tk.Tk()
        except Exception as exc:  # noqa: BLE001
            raise DialogUnavailable(str(exc)) from exc
        try:
            root.withdraw()
            root.attributes("-topmost", True)       # appear above the browser window
            root.update()
            return fn(root, filedialog) or ""
        finally:
            try:
                root.destroy()
            except Exception:  # noqa: BLE001
                pass


def _initial(folder: str | Path | None) -> str:
    return str(folder) if folder and Path(folder).is_dir() else str(Path.home())


def save_file(title: str, initial_dir: str | Path, filename: str, ext: str, type_label: str) -> Path | None:
    stub = _stub()
    if stub:
        return None if stub == "cancel" else Path(stub) / filename
    res = _run(lambda root, fd: fd.asksaveasfilename(
        parent=root, title=title, initialdir=_initial(initial_dir), initialfile=filename,
        defaultextension=ext, filetypes=[(type_label, "*" + ext), ("כל הקבצים", "*.*")], confirmoverwrite=True))
    return Path(res) if res else None


def choose_folder(title: str, initial_dir: str | Path) -> Path | None:
    stub = _stub()
    if stub:
        return None if stub == "cancel" else Path(stub)
    res = _run(lambda root, fd: fd.askdirectory(parent=root, title=title, initialdir=_initial(initial_dir), mustexist=False))
    return Path(res) if res else None


def open_file(title: str, initial_dir: str | Path, pattern: str, type_label: str) -> Path | None:
    stub = _stub()
    if stub:
        return None if stub == "cancel" else Path(stub)
    res = _run(lambda root, fd: fd.askopenfilename(
        parent=root, title=title, initialdir=_initial(initial_dir), filetypes=[(type_label, pattern), ("כל הקבצים", "*.*")]))
    return Path(res) if res else None
