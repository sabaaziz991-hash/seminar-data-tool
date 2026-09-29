"""Screenshots for the user guide.

Runs a copy of the packaged tool from a neutral folder (C:\\Users\\Public\\SeminarDataTool, so no personal paths
appear in the pictures), prepares the screens (population rebuild from a local cases_all.parquet, one Google News
re-query with the automatic classification, the text measures) and captures them with Playwright's Chromium.

    python src/guide/take_screenshots.py [path\\to\\cases_all.parquet]
"""
from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "tests"))
from winutil import PKG, clean_env, copy_package, get_json, heartbeat, post, start_tool, stop_tool  # noqa: E402

OUT = HERE / "screens"
CASE = "HUGGINGFACE-00ab1bad61ad"
MEDIA_CASE = "HUGGINGFACE-c0f5ef125985"   # a case whose live results are all about the case itself
PUBLIC = Path(r"C:\Users\Public")
SAVE_DIR = PUBLIC / "Documents" / "SeminarDataTool"


def prepare(base: str, parquet: str | None) -> None:
    heartbeat(base, "screenshots")
    if parquet:
        post(base + "/api/court/build", {"path": parquet})
        while get_json(base + "/api/court/status")["build"]["state"] == "running":
            time.sleep(2)
    post(base + "/api/media/start", {"case_ids": [MEDIA_CASE], "delay": 5})
    while get_json(base + "/api/media/status")["job"]["state"] == "running":
        time.sleep(2)


def shoot(base: str) -> None:
    from playwright.sync_api import sync_playwright

    OUT.mkdir(exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 760}, device_scale_factor=1.25, locale="he-IL")

        def shot(name: str) -> None:
            page.wait_for_timeout(700)
            page.screenshot(path=str(OUT / f"{name}.png"))
            print("saved", name)

        page.goto(base + "/#home")
        page.wait_for_selector(".home-tile")
        shot("01_home")
        page.goto(base + "/#cases")
        page.wait_for_selector("tr.clickable")
        page.select_option("select >> nth=2", "1")
        shot("02_cases")
        page.goto(base + "/#case/" + CASE)
        page.wait_for_selector(".case-head")
        shot("03_case_top")
        page.evaluate("document.querySelector('details.judgment').open = true")
        page.wait_for_timeout(300)
        page.evaluate("document.querySelector('mark.ref').scrollIntoView({block: 'center'})")
        page.evaluate("window.scrollBy(0, -120)")
        shot("04_case_judgment")
        page.goto(base + "/#reimport")
        page.wait_for_selector("text=מקור הנתונים")
        if page.locator("text=תוצאה: שלבי הסינון").count():
            page.evaluate("[...document.querySelectorAll('h2')].find(x => x.textContent.includes('תוצאה')).scrollIntoView()")
            page.evaluate("window.scrollBy(0, -70)")
            shot("09_reimport_flow")
        page.click("text=שלב 2 · Google News וסיווג הכתבות")
        page.wait_for_selector("text=בחירת תיקים")
        page.evaluate("const d = document.querySelector('details.card'); d.open = true; d.scrollIntoView()")
        page.evaluate("window.scrollBy(0, -70)")
        shot("10_reimport_media")
        page.click("text=שלב 3 · מדדי הטקסט")
        page.click("text=חישוב המדדים והשוואה למחקר")
        page.wait_for_selector(".banner.ok", timeout=120000)
        page.evaluate("document.querySelector('.banner.ok').scrollIntoView()")
        page.evaluate("window.scrollBy(0, -70)")
        shot("11_reimport_text")
        browser.close()


def main() -> None:
    parquet = sys.argv[1] if len(sys.argv) > 1 else None
    dest = PUBLIC / "SeminarDataTool"
    if dest.exists():
        raise SystemExit(f"{dest} already exists - not touching it")
    SAVE_DIR.mkdir(parents=True, exist_ok=True)
    copy_package(PUBLIC, "SeminarDataTool")
    base, pid = start_tool(dest, "launcher", env=clean_env(SEMINAR_TOOL_DIALOG_STUB=str(SAVE_DIR)))
    try:
        prepare(base, parquet)
        shoot(base)
    finally:
        stop_tool(base, pid)
        shutil.rmtree(dest, ignore_errors=True)
        shutil.rmtree(SAVE_DIR, ignore_errors=True)


if __name__ == "__main__":
    main()
