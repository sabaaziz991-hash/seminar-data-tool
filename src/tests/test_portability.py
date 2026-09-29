"""Portability ("any Windows 10/11 computer, any folder") tests of the packaged tool (dist\\SeminarDataTool).

* no machine-specific paths anywhere in the package (files, compressed Python archives, templates, JSON, guide)
* all DLLs are bundled or part of Windows (no VC++ redistributable / Python / .NET install needed except the
  .NET Framework 4 that ships with Windows 10/11 for the small launcher)
* runs from C:\\Users\\Public\\<Hebrew folder with spaces> and from another drive
* runs with a stripped environment (PATH = System32 only, other TEMP, no Python/conda/HF variables)
* read-only program folder -> outputs go to Documents\\SeminarDataTool\\תוצרים and the page says so
* opened from inside the ZIP (only the EXE / .bat extracted) -> Hebrew "extract first" message, no technical error
* no browser can be opened -> small window with the address; port chosen dynamically when 8765.. are taken
* the page works in Edge, Chrome and Firefox (headless, own temporary profiles)
"""
from __future__ import annotations

import os
import shutil
import socket
import subprocess
import time
import zlib
from pathlib import Path

import pytest

from winutil import (APP, EXTRACT_TEXT, heartbeat, kill_by_cmdline, IDCANCEL, IDOK, LAUNCHER, PKG, TITLE, clean_env, copy_package, find_window,
                     get_json, kill_tree, minimal_env, new_temp, ping, post, press, start_tool, stop_tool,
                     wait_pid_exit, window_texts)

pytestmark = pytest.mark.skipif(not (PKG / APP).exists(), reason="run build.py first")

# absolute paths / names of the build machine (relative provenance paths such as "03_ניתוח/..." are fine)
FORBIDDEN = ["\\sabaa", "/sabaa", "sabaa\\","סמינריון 2", "seminar2ענבל", r"AppData\Local\Temp\claude", "scratchpad",
             r".cache\huggingface", r"hf_raw\.cache", "\\Desktop\\", "/Desktop/"]


# ---------------------------------------------------------------- 1. no machine-specific paths
def _blobs() -> list[tuple[str, bytes]]:
    """Every file of the package, plus the decompressed contents of the Python archives inside the EXE."""
    from PyInstaller.archive.readers import CArchiveReader, ZlibArchiveReader

    out = []
    for p in PKG.rglob("*"):
        if p.is_file():
            out.append((str(p.relative_to(PKG)), p.read_bytes()))
    exe = PKG / APP
    car = CArchiveReader(str(exe))
    for name in car.toc:
        data = car.extract(name)
        if data is None:
            continue
        out.append((f"{APP}::{name}", data))
        if name.endswith(".pyz"):
            tmp = new_temp("sdt_pyz_") / name
            tmp.write_bytes(data)
            z = ZlibArchiveReader(str(tmp))
            for mod in z.toc:
                try:
                    out.append((f"{APP}::{name}::{mod}", z.extract(mod, raw=True) or b""))
                except TypeError:
                    out.append((f"{APP}::{name}::{mod}", repr(z.extract(mod)).encode()))
    base_lib = PKG / "app" / "_internal" / "base_library.zip"
    if base_lib.exists():
        import zipfile

        with zipfile.ZipFile(base_lib) as zf:
            for n in zf.namelist():
                out.append((f"base_library.zip::{n}", zf.read(n)))
    return out


def test_no_machine_specific_paths_in_package() -> None:
    needles = []
    for f in FORBIDDEN:
        needles += [f.encode("utf-8"), f.encode("utf-16-le"), f.lower().encode("utf-8")]
    hits = []
    blobs = _blobs()
    for name, data in blobs:
        variants = [data]
        if name.endswith(".pdf"):
            variants += [zlib.decompress(s) for s in _pdf_streams(data)]
        for v in variants:
            low = v.lower()
            for n in needles:
                if n in v or n.lower() in low:
                    hits.append((name, n.decode("utf-8", "ignore") if b"\x00" not in n else n.decode("utf-16-le")))
                    break
    assert len(blobs) > 1000
    assert not hits, hits[:20]


def _pdf_streams(pdf: bytes) -> list[bytes]:
    import re

    out = []
    for m in re.finditer(rb"stream\r?\n(.*?)\r?\nendstream", pdf, re.S):
        try:
            zlib.decompress(m.group(1))
            out.append(m.group(1))
        except zlib.error:
            pass
    return out


def test_spss_templates_have_no_path() -> None:
    for sps in (PKG / "data" / "spss").glob("*.sps"):
        txt = sps.read_text(encoding="utf-8")
        assert "FILE HANDLE root /NAME='{{SPSS_FOLDER}}'." in txt and ":/" not in txt.replace("http://", "")


# ---------------------------------------------------------------- 2. DLL dependencies
def test_all_dll_dependencies_are_bundled_or_windows() -> None:
    import pefile

    bundled = {}
    for p in PKG.rglob("*"):
        if p.suffix.lower() in (".dll", ".pyd", ".exe"):
            bundled.setdefault(p.name.lower(), p)
    for must in ("python313.dll", "vcruntime140.dll", "vcruntime140_1.dll", "ucrtbase.dll"):
        assert must in bundled, must
    assert any(n.startswith("msvcp140") for n in bundled), "msvcp140 (C++ runtime) must be bundled"
    assert any(n.startswith(("tcl86", "tk86")) for n in bundled), "Tcl/Tk (native dialogs) must be bundled"
    sys32 = Path(os.environ["SystemRoot"]) / "System32"
    windows_dlls, missing = set(), []
    for name, path in bundled.items():
        pe = pefile.PE(str(path), fast_load=True)
        pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"],
                                               pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_DELAY_IMPORT"]])
        for attr in ("DIRECTORY_ENTRY_IMPORT", "DIRECTORY_ENTRY_DELAY_IMPORT"):
            for imp in getattr(pe, attr, []) or []:
                dll = imp.dll.decode().lower()
                if dll in bundled or dll.startswith(("api-ms-win-", "ext-ms-")):
                    continue
                if (sys32 / dll).exists():
                    windows_dlls.add(dll)
                else:
                    missing.append((name, dll))
        pe.close()
    print("\nWindows system DLLs used:", sorted(windows_dlls))
    assert not missing, missing
    # only core Windows components (present on every Windows 10/11), no redistributables
    # (msvcrt.dll is the C runtime that is part of Windows itself; msvcr100/120.dll etc. would be redistributables)
    import re

    assert not {d for d in windows_dlls if re.match(r"(msvcp|vcruntime|msvcr\d|python|concrt|vcomp)", d)}


# ---------------------------------------------------------------- 3. other folders / drives
def _run_and_check(dest: Path, **kw) -> None:
    base, pid = start_tool(dest, **kw)
    try:
        info = get_json(base + "/api/info")
        assert Path(info["root_dir"]) == dest and Path(info["output_dir"]) == dest / "תוצרים"
        assert get_json(base + "/api/stats?source=study")["golden"]["all_ok"]
        assert get_json(base + "/api/case?id=HUGGINGFACE-00ab1bad61ad")["card"]["judgment"]["available"]
    finally:
        assert stop_tool(base, pid) == 0


def test_runs_from_public_hebrew_folder() -> None:
    parent = Path(os.environ.get("PUBLIC", r"C:\Users\Public")) / "בדיקה ניידות"
    if parent.exists():
        shutil.rmtree(parent, ignore_errors=True)
    try:
        _run_and_check(copy_package(parent))
    finally:
        shutil.rmtree(parent, ignore_errors=True)


def _other_drive() -> Path | None:
    import string

    here = Path(__file__).drive.upper()
    for letter in string.ascii_uppercase[2:]:
        d = Path(f"{letter}:\\")
        if f"{letter}:" != here and d.exists():
            try:
                t = d / "sdt_drive_probe.tmp"
                t.write_text("x")
                t.unlink()
                if shutil.disk_usage(d).free > 2_000_000_000:
                    return d
            except OSError:
                continue
    return None


def test_runs_from_another_drive() -> None:
    drive = _other_drive()
    if not drive:
        pytest.skip("no second writable drive")
    parent = drive / "sdt_portability_test" / "תיקייה עם רווח"
    try:
        _run_and_check(copy_package(parent))
    finally:
        shutil.rmtree(drive / "sdt_portability_test", ignore_errors=True)


def test_runs_with_stripped_environment() -> None:
    root = new_temp("sdt_env_")
    other_temp = root / "TEMP אחר"
    other_temp.mkdir()
    dest = copy_package(root / "pkg")
    save_to = root / "saved"
    save_to.mkdir()
    for how in ("launcher", "app"):
        env = minimal_env(other_temp, SEMINAR_TOOL_DIALOG_STUB=str(save_to))
        assert not any(k.upper().startswith(("PYTHON", "CONDA", "HF_", "VIRTUAL_ENV")) for k in env)
        base, pid = start_tool(dest, how, env=env)
        try:
            assert get_json(base + "/api/stats?source=study")["golden"]["all_ok"]
            res = post(base + "/api/save", {"kind": "study_xlsx"})
            assert Path(res["path"]).exists()
        finally:
            assert stop_tool(base, pid) == 0
    shutil.rmtree(root, ignore_errors=True)


# ---------------------------------------------------------------- 4. read-only program folder -> fallback
def test_read_only_folder_uses_documents_fallback() -> None:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from seminar_tool.paths import FOLDERID_DOCUMENTS, known_folder

    docs = known_folder(FOLDERID_DOCUMENTS) or Path.home() / "Documents"
    fallback_root = docs / "SeminarDataTool"
    existed = fallback_root.exists()
    root = new_temp("sdt_ro_") / "תיקייה לקריאה בלבד"
    dest = copy_package(root)
    user = subprocess.run(["whoami"], capture_output=True, text=True).stdout.strip()
    # deny creating/changing files and folders (like Program Files for a normal user); reading/running stays allowed
    subprocess.run(["icacls", str(dest), "/deny", f"{user}:(OI)(CI)(WD,AD,WEA,WA)"], check=True, capture_output=True)
    try:
        assert not os.access(dest, os.W_OK) or not _can_write(dest)
        base, pid = start_tool(dest, "launcher", out_dir=fallback_root / "תוצרים")
        try:
            info = get_json(base + "/api/info")
            assert info["output_is_default"] is False
            assert Path(info["output_dir"]) == fallback_root / "תוצרים"
            assert "לא ניתן לשמור קבצים בתיקיית התוכנה" in info["output_reason"]
            assert (fallback_root / "תוצרים" / "log.txt").exists()
            assert get_json(base + "/api/stats?source=study")["golden"]["all_ok"]
        finally:
            assert stop_tool(base, pid) == 0
        assert not (dest / "תוצרים").exists()
    finally:
        subprocess.run(["icacls", str(dest), "/remove:d", user], capture_output=True)
        shutil.rmtree(root.parent, ignore_errors=True)
        if not existed:
            shutil.rmtree(fallback_root, ignore_errors=True)


def _can_write(folder: Path) -> bool:
    try:
        (folder / "probe.tmp").write_text("x")
        (folder / "probe.tmp").unlink()
        return True
    except OSError:
        return False


# ---------------------------------------------------------------- 5. started from inside the ZIP
def _zip_temp_copy(files: list[str]) -> Path:
    """What Windows does when an EXE is double-clicked inside a ZIP: only that file lands in a Temp1_<zip> folder."""
    folder = new_temp("sdt_zip_") / "Temp1_SeminarDataTool.zip" / "SeminarDataTool"
    folder.mkdir(parents=True)
    for f in files:
        (folder / f).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(PKG / f, folder / f)
    return folder


def _expect_extract_message(proc: subprocess.Popen, title: str = TITLE) -> None:
    hwnd = find_window(title, 40)
    assert hwnd, "no message window appeared"
    text = " ".join(window_texts(hwnd))
    assert EXTRACT_TEXT in text, text
    assert "Traceback" not in text and "Error" not in text
    press(hwnd, IDOK)
    assert proc.wait(30) == 2


def test_launcher_inside_zip_shows_hebrew_message() -> None:
    folder = _zip_temp_copy([LAUNCHER])
    _expect_extract_message(subprocess.Popen([str(folder / LAUNCHER)], env=clean_env()))
    shutil.rmtree(folder.parents[1], ignore_errors=True)


def test_bat_inside_zip_shows_hebrew_message() -> None:
    folder = _zip_temp_copy(["הפעלה.bat"])
    _expect_extract_message(subprocess.Popen(["cmd", "/c", str(folder / "הפעלה.bat")], env=clean_env()))
    shutil.rmtree(folder.parents[1], ignore_errors=True)


def test_app_without_data_folder_shows_hebrew_message() -> None:
    folder = new_temp("sdt_nodata_") / "SeminarDataTool"
    shutil.copytree(PKG / "app", folder / "app")
    _expect_extract_message(subprocess.Popen([str(folder / APP)], env=clean_env()))
    shutil.rmtree(folder.parent, ignore_errors=True)


# ---------------------------------------------------------------- 6. browser / port
def test_no_browser_shows_address_window() -> None:
    root = new_temp("sdt_nobrowser_")
    dest = copy_package(root)
    base, pid = start_tool(dest, "launcher", args=[], env=clean_env(SEMINAR_TOOL_SIMULATE_NO_BROWSER="1"))
    try:
        hwnd = find_window(TITLE + " — כתובת התוכנה", 30)
        assert hwnd, "address window did not appear"
        text = " ".join(window_texts(hwnd))
        assert base in text, text
        time.sleep(1)
        assert ping(base), "the server must stay up while the address window is open"
        press(hwnd, IDCANCEL)                                   # "Cancel" = close the program
        assert wait_pid_exit(pid, 30) == 0
    finally:
        if ping(base):
            stop_tool(base, pid)
        shutil.rmtree(root, ignore_errors=True)


def test_port_chosen_dynamically_when_taken() -> None:
    root = new_temp("sdt_port_")
    dest = copy_package(root)
    blockers = []
    try:
        for port in range(8765, 8785):                          # occupy every preferred port
            s = socket.socket()
            try:
                s.bind(("127.0.0.1", port))
                s.listen(1)
                blockers.append(s)
            except OSError:
                s.close()
        base, pid = start_tool(dest, "launcher", fixed_port=False)
        port = int(base.rsplit(":", 1)[1])
        assert not 8765 <= port < 8785, port
        assert get_json(base + "/api/info")["n_cases"] == 497
        assert stop_tool(base, pid) == 0
    finally:
        for s in blockers:
            s.close()
        shutil.rmtree(root, ignore_errors=True)


BROWSERS = {
    "Edge": [r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe", r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"],
    "Chrome": [r"C:\Program Files\Google\Chrome\Application\chrome.exe", r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"],
    "Firefox": [r"C:\Program Files\Mozilla Firefox\firefox.exe", r"C:\Program Files (x86)\Mozilla Firefox\firefox.exe"],
}


@pytest.mark.parametrize("browser", list(BROWSERS))
def test_page_runs_in_browser(browser: str) -> None:
    exe = next((p for p in BROWSERS[browser] if Path(p).exists()), None)
    if not exe:
        pytest.skip(f"{browser} not installed")
    root = new_temp("sdt_br_")
    dest = copy_package(root / "pkg")
    profile = root / "profile"
    profile.mkdir()
    base, pid = start_tool(dest, "launcher")
    heartbeat(base, "test-keepalive")
    if browser == "Firefox":
        cmd = [exe, "-headless", "-no-remote", "-profile", str(profile), base + "/#stats"]
    else:
        cmd = [exe, "--headless=new", "--no-first-run", "--no-default-browser-check", "--disable-gpu",
               f"--user-data-dir={profile}", base + "/#stats"]
    br = subprocess.Popen(cmd)
    try:
        t0 = time.time()
        while time.time() - t0 < 60 and get_json(base + "/api/info")["clients"] < 2:
            time.sleep(1)
        assert get_json(base + "/api/info")["clients"] >= 2, f"{browser} did not run the page's script"
    finally:
        kill_tree(br.pid)
        kill_by_cmdline(str(profile))                       # all processes of this temporary browser profile
        stop_tool(base, pid)
        time.sleep(1)
        shutil.rmtree(root, ignore_errors=True)


@pytest.mark.skipif(not os.environ.get("SDT_INTERACTIVE"), reason="opens a tab in the real default browser (set SDT_INTERACTIVE=1)")
def test_default_browser_opens_page() -> None:
    root = new_temp("sdt_default_browser_")
    dest = copy_package(root)
    base, pid = start_tool(dest, "launcher", args=[])
    try:
        t0 = time.time()
        while time.time() - t0 < 60 and get_json(base + "/api/info")["clients"] < 1:
            time.sleep(1)
        assert get_json(base + "/api/info")["clients"] >= 1, "the default browser did not open the page"
    finally:
        stop_tool(base, pid)
        shutil.rmtree(root, ignore_errors=True)
