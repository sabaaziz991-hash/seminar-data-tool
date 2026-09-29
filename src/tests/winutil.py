"""Helpers for the packaged-EXE / portability tests: start the tool, find and press Windows dialogs, wait for PIDs."""
from __future__ import annotations

import ctypes
import json
import os
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from ctypes import wintypes
from pathlib import Path

PKG = Path(__file__).resolve().parents[2] / "dist" / "SeminarDataTool"
LAUNCHER = "SeminarDataTool.exe"
APP = Path("app") / "SeminarDataToolApp.exe"
TOKEN = {"X-Requested-With": "SeminarDataTool", "Content-Type": "application/json"}
TITLE = "כלי נתוני הסמינריון"
EXTRACT_TEXT = "יש לחלץ את כל תוכן קובץ ה-ZIP לתיקייה"

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
user32.FindWindowW.restype = wintypes.HWND
user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetDlgCtrlID.argtypes = [wintypes.HWND]
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
WM_COMMAND, WM_CLOSE = 0x0111, 0x0010
IDOK, IDCANCEL = 1, 2


# ---------------------------------------------------------------- windows
def find_window(title: str, timeout: float = 30, cls: str | None = "#32770") -> int:
    """A visible top-level window with this exact title; by default only dialog boxes (class #32770), so that
    e.g. a browser tab with the same title (taskbar proxy window) is not picked up."""
    t0 = time.time()
    while time.time() - t0 < timeout:
        h = user32.FindWindowW(cls, title)
        if h and user32.IsWindowVisible(h):
            return h
        time.sleep(0.25)
    return 0


def window_texts(hwnd: int) -> list[str]:
    texts: list[str] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(h, _):
        n = user32.GetWindowTextLengthW(h)
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(h, buf, n + 1)
        if buf.value:
            texts.append(buf.value)
        return True

    user32.EnumChildWindows(hwnd, cb, 0)
    return texts


def is_topmost(hwnd: int) -> bool:
    return bool(user32.GetWindowLongW(hwnd, -20) & 0x8)       # GWL_EXSTYLE & WS_EX_TOPMOST


def buttons(hwnd: int) -> list[tuple[int, int, str]]:
    """(control id, hwnd, caption) of the push buttons of a dialog."""
    out: list[tuple[int, int, str]] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(h, _):
        cls = ctypes.create_unicode_buffer(32)
        user32.GetClassNameW(h, cls, 32)
        if cls.value == "Button":
            txt = ctypes.create_unicode_buffer(64)
            user32.GetWindowTextW(h, txt, 64)
            out.append((user32.GetDlgCtrlID(h), h, txt.value))
        return True

    user32.EnumChildWindows(hwnd, cb, 0)
    return out


def press(hwnd: int, button: int) -> None:
    """Click a dialog button by its id (IDOK / IDCANCEL / IDRETRY ...). A message box with a single OK button
    gives it the id IDCANCEL, so for IDOK the only button is clicked whatever its id is."""
    btns = buttons(hwnd)
    match = [b for b in btns if b[0] == button] or (btns if button == IDOK and len(btns) == 1 else [])
    if match:
        cid, bh, _ = match[0]
        user32.PostMessageW(hwnd, WM_COMMAND, cid, bh)          # BN_CLICKED (high word 0) from that button
    else:
        user32.PostMessageW(hwnd, WM_COMMAND, button, 0)


# ---------------------------------------------------------------- processes
def wait_pid_exit(pid: int, timeout: float) -> int | None:
    """Exit code of `pid` once it ends (None if it is still running after `timeout`)."""
    h = kernel32.OpenProcess(0x00100000 | 0x1000, False, pid)   # SYNCHRONIZE | PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return 0                                                  # already gone
    try:
        if kernel32.WaitForSingleObject(h, int(timeout * 1000)) != 0:
            return None
        code = wintypes.DWORD()
        kernel32.GetExitCodeProcess(h, ctypes.byref(code))
        return code.value
    finally:
        kernel32.CloseHandle(h)


def kill_tree(pid: int) -> None:
    subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True)


def kill_by_cmdline(fragment: str) -> None:
    """Stop every process whose command line contains `fragment` (e.g. a unique temporary browser profile):
    Chromium browsers re-launch themselves, so the PID returned by Popen is not the browser's main process."""
    ps = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    frag = fragment.replace("'", "''")
    subprocess.run([str(ps), "-NoProfile", "-NonInteractive", "-Command",
                    f"Get-CimInstance Win32_Process | Where-Object {{ $_.CommandLine -like '*{frag}*' }} | "
                    "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"],
                   capture_output=True, timeout=60)


# ---------------------------------------------------------------- HTTP
def get_json(url: str, timeout: float = 120) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read())


def get_bytes(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=120) as r:
        return r.read()


def post(url: str, body: dict | bytes, headers: dict | None = None, timeout: float = 120) -> dict:
    data = body if isinstance(body, bytes) else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers=TOKEN if headers is None else headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
        return json.loads(raw) if raw else {}


def heartbeat(base: str, client: str) -> dict:
    return post(base + "/api/heartbeat", {"client": client, "run": get_json(base + "/api/info")["run_id"]})


def ping(base: str) -> bool:
    try:
        return bool(get_json(base + "/api/ping", timeout=3).get("ok"))
    except (urllib.error.URLError, OSError, ValueError):
        return False


# ---------------------------------------------------------------- package copies and runs
def copy_package(parent: Path, name: str = "SeminarDataTool") -> Path:
    parent.mkdir(parents=True, exist_ok=True)
    dest = parent / name
    shutil.copytree(PKG, dest, ignore=shutil.ignore_patterns("תוצרים"))
    return dest


def clean_env(**extra: str) -> dict:
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith("SEMINAR_TOOL_")}
    env.update(extra)
    return env


def minimal_env(temp_dir: Path, **extra: str) -> dict:
    """What a fresh Windows account looks like: no Python/conda/HF variables, PATH = System32 only, own TEMP."""
    keep = ("SystemRoot", "windir", "SystemDrive", "USERPROFILE", "USERNAME", "USERDOMAIN", "HOMEDRIVE", "HOMEPATH",
            "APPDATA", "LOCALAPPDATA", "ComSpec", "PATHEXT", "OS", "PROCESSOR_ARCHITECTURE", "NUMBER_OF_PROCESSORS",
            "ProgramData", "ProgramFiles", "ProgramFiles(x86)", "PUBLIC", "ALLUSERSPROFILE", "COMPUTERNAME")
    low = {k.lower(): k for k in os.environ}
    env = {low[k.lower()]: os.environ[low[k.lower()]] for k in keep if k.lower() in low}
    env["PATH"] = str(Path(env.get("SystemRoot", r"C:\Windows")) / "System32")
    env["TEMP"] = env["TMP"] = str(temp_dir)
    env.update(extra)
    return env


def start_tool(root: Path, how: str = "launcher", args: list[str] | None = None, env: dict | None = None,
               out_dir: Path | None = None, timeout: float = 90, fixed_port: bool = True) -> tuple[str, int]:
    """Start the tool from an extracted package and wait for its lock file. Returns (base URL, PID)."""
    out_dir = out_dir or (root / "תוצרים")
    lock = out_dir / ".server.json"
    if lock.exists():
        lock.unlink()
    args = ["--no-browser"] if args is None else args
    if "--port" not in args and fixed_port:     # own port: old browser tabs on 8765 must not interfere
        args = [*args, "--port", str(free_port())]
    env = env or clean_env()
    if how == "launcher":
        subprocess.Popen([str(root / LAUNCHER), *args], env=env)
    elif how == "app":
        subprocess.Popen([str(root / APP), *args], env=env)
    elif how == "bat":
        subprocess.run(["cmd", "/c", str(root / "הפעלה.bat"), *args], env=env, check=True, timeout=30)
    t0 = time.time()
    while not lock.exists() and time.time() - t0 < timeout:
        time.sleep(0.3)
    assert lock.exists(), f"the tool did not start ({how}) - no lock file in {out_dir}"
    info = json.loads(lock.read_text(encoding="utf-8"))
    base = f"http://127.0.0.1:{info['port']}"
    while not ping(base) and time.time() - t0 < timeout:
        time.sleep(0.3)
    assert ping(base), "server not answering"
    return base, int(info["pid"])


def stop_tool(base: str, pid: int) -> int | None:
    try:
        post(base + "/api/shutdown", {})
    except (urllib.error.URLError, OSError):
        pass
    code = wait_pid_exit(pid, 30)
    if code is None:
        kill_tree(pid)
    return code


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def new_temp(prefix: str) -> Path:
    return Path(tempfile.mkdtemp(prefix=prefix))
