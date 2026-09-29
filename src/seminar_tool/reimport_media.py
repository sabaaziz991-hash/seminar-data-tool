"""Screen ג, step 2: re-run the exact-name Google News RSS queries for a small, user-selected set of cases.

Polite by design: one request at a time, >= 3 s (default 5 s) + random jitter between requests,
exponential back-off on 429/5xx, the job stops after repeated errors, and a stop button.
Results are saved after every query, so a stopped run resumes where it left off.
Only items dated inside the case's pre-decision window are kept. Google News results change over time,
so the curated snapshot of the study remains the reference.
"""
from __future__ import annotations

import datetime as dt
import json
import random
import re
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import pandas as pd

from . import paths
from .court_rules import google_news_date_operators, parse_rfc822_date
from .jobs import Job

MIN_DELAY = 3.0
DEFAULT_DELAY = 5.0
MAX_CASES = 60
USER_AGENT = f"{paths.APP_NAME}/{paths.VERSION} (academic seminar replication; low-rate)"
MEDIA_DIR = paths.OUTPUT_DIR / "ייבוא_מחדש_Google_News"
STORE = MEDIA_DIR / "results.json"


def rss_url(query: str, start: str, end: str) -> str:
    """Same URL as the original search_case_media.google_news_rss_url (hl=iw, gl=IL, ceid=IL:he)."""
    after, before = google_news_date_operators(dt.date.fromisoformat(start), dt.date.fromisoformat(end))
    q = f"{query} after:{after} before:{before}"
    return "https://news.google.com/rss/search?" + urllib.parse.urlencode({"q": q, "hl": "iw", "gl": "IL", "ceid": "IL:he"})


def norm_title(t: str) -> str:
    t = re.sub(r"\s+[-|–]\s+[^-|–]{1,40}$", "", str(t or ""))          # drop " - outlet" suffix
    t = re.sub(r"[^\w֐-׿]+", " ", t).casefold()
    return re.sub(r"\s+", " ", t).strip()


def parse_rss(xml_text: str, start: str, end: str) -> list[dict[str, Any]]:
    root = ET.fromstring(xml_text)
    s, e = dt.date.fromisoformat(start), dt.date.fromisoformat(end)
    out = []
    for item in root.findall(".//item"):
        pub = (item.findtext("pubDate") or "").strip()
        try:
            date = parse_rfc822_date(pub) if pub else ""
        except (TypeError, ValueError, IndexError):
            date = ""
        src = item.find("source")
        out.append({"title": (item.findtext("title") or "").strip(), "url": (item.findtext("link") or "").strip(),
                    "source": (src.text or "").strip() if src is not None else "", "published_date": date,
                    "in_window": bool(date) and s <= dt.date.fromisoformat(date) <= e})
    return out


def load_store() -> dict[str, Any]:
    try:
        return json.loads(STORE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_store(store: dict[str, Any]) -> None:
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = STORE.with_suffix(".tmp")
    tmp.write_text(json.dumps(store, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(STORE)


def fetch(url: str, timeout: int = 30) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT,
                                               "Accept": "application/rss+xml, application/xml;q=0.9, */*;q=0.8"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode(resp.headers.get_content_charset() or "utf-8", errors="replace")


def run(job: Job, cases: list[dict[str, Any]], delay: float) -> dict[str, Any]:
    delay = max(MIN_DELAY, float(delay or DEFAULT_DELAY))
    store = load_store()
    tasks = [(c, w) for c in cases for w in c["windows"] if c.get("query")]
    todo = [(c, w) for c, w in tasks if store.get(f"{c['case_id']}|{w['window_type']}", {}).get("status") != "ok"]
    job.update(0.0, f"{len(tasks)} שאילתות, מתוכן {len(tasks) - len(todo)} כבר בוצעו (ממשיך מאותה נקודה).",
               f"התחלה: {len(todo)} שאילתות להרצה, השהיה {delay:.0f} שניות בין בקשות")
    errors_in_row = 0
    for i, (c, w) in enumerate(todo, start=1):
        key = f"{c['case_id']}|{w['window_type']}"
        url = rss_url(c["query"], w["start"], w["end"])
        job.update((i - 1) / max(len(todo), 1), f"שאילתה {i} מתוך {len(todo)}: {c['case_number']} — {w['label']}")
        attempt = 0
        while True:
            try:
                items = parse_rss(fetch(url), w["start"], w["end"])
                store[key] = {"status": "ok", "case_id": c["case_id"], "case_number": c["case_number"], "query": c["query"],
                              "window_type": w["window_type"], "window_label": w["label"], "start": w["start"], "end": w["end"],
                              "rss_url": url, "fetched_at": dt.datetime.now().isoformat(timespec="seconds"),
                              "n_returned": len(items), "items": [x for x in items if x["in_window"]]}
                save_store(store)
                errors_in_row = 0
                job.update(log_line=f"{c['case_number']} ({w['label'][:12]}…): {len(items)} תוצאות, "
                                    f"{sum(x['in_window'] for x in items)} בתוך החלון")
                break
            except urllib.error.HTTPError as exc:
                if exc.code in (429, 500, 502, 503, 504) and attempt < 3:
                    wait = 30 * (2 ** attempt)
                    attempt += 1
                    job.update(message=f"Google ביקש להאט (קוד {exc.code}). ממתין {wait} שניות ומנסה שוב...",
                               log_line=f"קוד {exc.code} — המתנה {wait} שניות")
                    job.sleep(wait)
                    continue
                errors_in_row += 1
                store[key] = {"status": "error", "error": f"HTTP {exc.code}", "case_number": c["case_number"]}
                save_store(store)
                job.update(log_line=f"שגיאה {exc.code} בתיק {c['case_number']}")
                if exc.code == 429 or errors_in_row >= 3:
                    raise RuntimeError("Google News מגביל כרגע את קצב הבקשות. הריצה נעצרה כדי לא להעמיס; "
                                       "נסו שוב בעוד כשעה — התוצאות שכבר התקבלו נשמרו.") from exc
                break
            except (urllib.error.URLError, TimeoutError, ET.ParseError, OSError) as exc:
                errors_in_row += 1
                store[key] = {"status": "error", "error": str(exc), "case_number": c["case_number"]}
                save_store(store)
                job.update(log_line=f"שגיאת רשת בתיק {c['case_number']}: {exc}")
                if errors_in_row >= 3:
                    raise RuntimeError("שלוש שגיאות רשת ברצף — בדקו את החיבור לאינטרנט ונסו שוב.") from exc
                break
        if i < len(todo):
            job.sleep(delay + random.uniform(0, 1.5))
    job.update(1.0, f"הסתיים: {len(todo)} שאילתות בוצעו.", "הסתיים")
    return {"done": len(todo)}


def summary(sd: Any, case_ids: list[str] | None = None) -> list[dict[str, Any]]:
    """Per-case comparison: items found now (inside the window) vs. the curated items of the study."""
    store = load_store()
    by_case: dict[str, list[dict[str, Any]]] = {}
    for key, rec in store.items():
        cid = key.split("|")[0]
        if case_ids and cid not in case_ids:
            continue
        by_case.setdefault(cid, []).append(rec)
    out = []
    orig = sd.google
    for cid, recs in by_case.items():
        o = orig[(orig.case_id == cid) & (orig.curation_status == "included")]
        otitles = {norm_title(t) for t in o.title}
        now_items, seen = [], set()
        for rec in recs:
            for it in rec.get("items", []):
                if it["url"] in seen:
                    continue
                seen.add(it["url"])
                now_items.append({**it, "window_label": rec.get("window_label", ""),
                                  "also_in_original": norm_title(it["title"]) in otitles})
        errors = [r.get("error") for r in recs if r.get("status") == "error"]
        out.append({"case_id": cid, "case_number": recs[0].get("case_number", ""), "query": recs[0].get("query", ""),
                    "queries_done": sum(r.get("status") == "ok" for r in recs), "errors": errors,
                    "now_count": len(now_items), "overlap": sum(i["also_in_original"] for i in now_items),
                    "original_count": len(o), "now_items": sorted(now_items, key=lambda x: x["published_date"]),
                    "original_items": o[["title", "source", "published_date", "url"]].sort_values("published_date").to_dict(orient="records")})
    return sorted(out, key=lambda r: r["case_number"])


def export_rows(sd: Any) -> pd.DataFrame:
    rows = []
    for c in summary(sd):
        for it in c["now_items"]:
            rows.append({"מספר הליך": c["case_number"], "case_id": c["case_id"], "שאילתה": c["query"], "חלון": it["window_label"],
                         "כותרת": it["title"], "כלי תקשורת": it["source"], "תאריך פרסום": it["published_date"], "קישור": it["url"],
                         "נמצא גם בתמונת המצב המקורית": "כן" if it["also_in_original"] else "לא"})
        if not c["now_items"]:
            rows.append({"מספר הליך": c["case_number"], "case_id": c["case_id"], "שאילתה": c["query"],
                         "כותרת": "(לא נמצאו ידיעות בתוך החלון)"})
    return pd.DataFrame(rows)


def reset() -> None:
    if STORE.exists():
        STORE.unlink()
