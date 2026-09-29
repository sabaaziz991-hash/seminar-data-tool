"""Build the portable Windows package:  python build.py [--refresh-data] [--skip-tests] [--skip-exe-test] [--package-only]

1. (optional) rebuild 05_תוכנה\\data from the project files (prepare_data.py)
2. unit + server smoke tests (pytest)
3. PyInstaller (onedir, no console)            -> 05_תוכנה\\build\\pyi_dist\\SeminarDataToolApp
4. launcher SeminarDataTool.exe (C#, csc.exe of the .NET Framework that ships with Windows 10/11)
5. assemble 05_תוכנה\\dist\\SeminarDataTool:  SeminarDataTool.exe, הפעלה.bat, app\\, data\\, guide, read-me
6. packaged-EXE + portability tests
7. ZIP -> 05_תוכנה\\SeminarDataTool_<date>.zip
"""
from __future__ import annotations

import argparse
import base64
import datetime as dt
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

SRC = Path(__file__).resolve().parent
TOOL = SRC.parent                      # 05_תוכנה
DIST = TOOL / "dist"
BUILD = TOOL / "build"
PYI_DIST = BUILD / "pyi_dist"
PKG = DIST / "SeminarDataTool"
CSC = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "Microsoft.NET" / "Framework64" / "v4.0.30319" / "csc.exe"

TITLE = "כלי נתוני הסמינריון"
EXTRACT_MSG = ("יש לחלץ את כל תוכן קובץ ה-ZIP לתיקייה (לחצן ימני ← חלץ הכל) ורק אז להפעיל.\n\n"
               "לאחר החילוץ: לחצו פעמיים על „הפעלה.bat” או על SeminarDataTool.exe שבתיקייה שחולצה.")


def ps_message_command() -> str:
    """PowerShell that shows the Hebrew 'extract first' message; encoded so the .bat file stays pure ASCII."""
    q = lambda t: t.replace("'", "''")  # noqa: E731
    script = ("Add-Type -AssemblyName System.Windows.Forms; "
              f"[void][System.Windows.Forms.MessageBox]::Show('{q(EXTRACT_MSG)}', '{q(TITLE)}', 'OK', 'Warning', "
              "'Button1', 'RtlReading, RightAlign')")
    return base64.b64encode(script.encode("utf-16-le")).decode("ascii")


def launcher_bat() -> str:
    return "\r\n".join([
        "@echo off",
        "rem Starts the seminar data tool. No installation needed; works from any folder.",
        "rem The default web browser opens automatically; closing the browser tab stops the tool.",
        'if not exist "%~dp0app\\SeminarDataToolApp.exe" goto notextracted',
        'if not exist "%~dp0data\\study_dataset_final.csv" goto notextracted',
        'start "" "%~dp0app\\SeminarDataToolApp.exe" %*',
        "exit /b 0",
        ":notextracted",
        "rem The ZIP was not extracted (e.g. this file was opened from inside the ZIP): show a Hebrew message.",
        '"%SystemRoot%\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" -NoProfile -NonInteractive -WindowStyle Hidden '
        f"-EncodedCommand {ps_message_command()} >nul 2>&1",
        "if errorlevel 1 (",
        "  echo.",
        "  echo Please extract the whole ZIP file first ^(right-click - Extract All^), then run this file again.",
        "  echo.",
        "  pause",
        ")",
        "exit /b 2",
        "",
    ])


README_TXT = (
    "כלי נתוני הסמינריון — הפעלה\r\n"
    "==========================\r\n"
    "הכלי עובד בכל מחשב Windows 10 / 11 (‏64 סיביות), מכל תיקייה, ללא התקנה וללא Python.\r\n\r\n"
    "1. חלצו קודם את כל קובץ ה-ZIP לתיקייה (לחצן ימני ← „חלץ הכל” / Extract All). אין להפעיל מתוך ה-ZIP עצמו.\r\n"
    "2. בתיקייה שחולצה לחצו פעמיים על \"הפעלה.bat\" או על SeminarDataTool.exe. הדפדפן ייפתח עם מסך הבית.\r\n"
    "3. בפעם הראשונה Windows עשוי להציג \"Windows protected your PC\": לחצו \"More info\" ואז \"Run anyway\".\r\n"
    "4. לסגירה: לחצו \"סגירה\" בראש המסך, או פשוט סגרו את לשונית הדפדפן.\r\n\r\n"
    "שמירת קבצים: בכל ייצוא נפתח חלון \"שמירה בשם\" של Windows ואפשר לבחור כל תיקייה. החלון זוכר את התיקייה האחרונה;\r\n"
    "ברירת המחדל היא התיקייה \"תוצרים\" שנוצרת ליד התוכנה.\r\n"
    "אם אי אפשר לכתוב בתיקיית התוכנה (למשל Program Files, כונן או תיקיית רשת לקריאה בלבד), הקבצים יישמרו ב:\r\n"
    "  מסמכים\\SeminarDataTool\\תוצרים   (ואם אין תיקיית מסמכים: AppData\\Local\\SeminarDataTool\\תוצרים)\r\n"
    "והתוכנה תציג הודעה על כך במסך הבית.\r\n\r\n"
    "אם הדפדפן לא נפתח: ייפתח חלון קטן עם הכתובת להקלדה בדפדפן (Edge / Chrome / Firefox).\r\n"
    "נתוני המחקר: בתיקייה data.   מדריך מלא: מדריך_למשתמש.pdf\r\n"
)


def run(cmd: list[str], **kw) -> None:
    print(">", " ".join(str(c) for c in cmd), flush=True)
    subprocess.run([str(c) for c in cmd], check=True, **kw)


def compile_launcher(out: Path) -> None:
    if not CSC.exists():
        raise SystemExit(f"csc.exe not found at {CSC} (part of the .NET Framework 4 that ships with Windows)")
    run([CSC, "/nologo", "/target:winexe", "/optimize+", "/codepage:65001", f"/win32icon:{SRC / 'app.ico'}",
         f"/out:{out}", "/r:System.Windows.Forms.dll", SRC / "launcher" / "Launcher.cs"])


def assemble() -> None:
    if PKG.exists():
        shutil.rmtree(PKG)
    PKG.mkdir(parents=True)
    shutil.copytree(PYI_DIST / "SeminarDataToolApp", PKG / "app")
    shutil.copytree(TOOL / "data", PKG / "data")
    compile_launcher(PKG / "SeminarDataTool.exe")
    (PKG / "הפעלה.bat").write_bytes(launcher_bat().encode("ascii"))
    (PKG / "קרא_אותי.txt").write_text(README_TXT, encoding="utf-8-sig")
    guide = next((TOOL / g for g in ("מדריך_למשתמש.pdf", "מדריך_למשתמש.docx") if (TOOL / g).exists()), None)
    if guide:
        shutil.copyfile(guide, PKG / guide.name)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh-data", action="store_true")
    ap.add_argument("--skip-tests", action="store_true")
    ap.add_argument("--skip-exe-test", action="store_true")
    ap.add_argument("--package-only", action="store_true", help="skip PyInstaller; re-assemble and re-zip")
    args = ap.parse_args()
    py = sys.executable

    if args.refresh_data:
        run([py, str(SRC / "prepare_data.py")])
    if not args.skip_tests and not args.package_only:
        run([py, "-m", "pytest", "tests/test_stats_golden.py", "tests/test_server_smoke.py", "-q", "-p", "no:cacheprovider"], cwd=SRC)
    if not args.package_only:
        run([py, "-m", "PyInstaller", "SeminarDataTool.spec", "--noconfirm", "--clean",
             "--distpath", str(PYI_DIST), "--workpath", str(BUILD / "pyi_work")], cwd=SRC)
    assemble()

    if not args.skip_exe_test:
        run([py, "-m", "pytest", "tests/test_packaged_exe.py", "tests/test_portability.py", "-q", "-p", "no:cacheprovider", "-rs"], cwd=SRC)
        shutil.rmtree(PKG / "תוצרים", ignore_errors=True)

    # zip (UTF-8 file names; Windows Explorer extracts Hebrew names correctly)
    out = TOOL / f"SeminarDataTool_{dt.date.today().isoformat()}.zip"
    tmp = out.with_suffix(".zip.tmp")
    with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for p in sorted(PKG.rglob("*")):
            if p.is_file():
                z.write(p, Path("SeminarDataTool") / p.relative_to(PKG))
    tmp.replace(out)
    size = out.stat().st_size / 1e6
    folder = sum(p.stat().st_size for p in PKG.rglob("*") if p.is_file()) / 1e6
    print(f"\nPackage folder: {PKG}  ({folder:.1f} MB)\nZIP: {out}  ({size:.1f} MB)")


if __name__ == "__main__":
    main()
