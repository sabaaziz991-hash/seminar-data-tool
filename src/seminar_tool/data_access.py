"""Read-only access to the bundled study data (case table, case card, inputs of the method screens)."""
from __future__ import annotations

import math
import threading
import urllib.parse
from pathlib import Path
from typing import Any

import pandas as pd

from . import paths

RELIEF_LABELS = {0: "ללא שינוי", 1: "הקלה בעונש", 2: "המרה לעבירה קלה", 3: "זיכוי", 4: "החזרה לערכאה", 5: "החמרה בעונש"}
DIRECTION_LABELS = {-1: "החמרה עם הנאשם", 0: "ללא שינוי לטובת הנאשם", 1: "הקלה עם הנאשם"}
WINDOW_LABELS = {
    "district_verdict_stage_media": "שלב הערכאה הדיונית (7 ימים לפני הכרעת הדין ועד 30 יום אחריה)",
    "appeal_stage_pre_decision_media": "שלב הערעור (עד יום לפני פסק הדין בעליון)",
}
WINDOW_SHORT = {"district_verdict_stage_media": "שלב הערכאה הדיונית", "appeal_stage_pre_decision_media": "שלב הערעור"}
STATUS_LABELS = {
    "included": "נכלל",
    "excluded_wrong_case": "הוחרג — תיק אחר / שם זהה",
    "excluded_after_window": "הוחרג — מחוץ לחלון הזמן",
    "excluded_false_positive": "הוחרג — תוצאה שגויה",
}
REF_LABELS = {"A": "סיקור התיק / ראיון (A)", "B": "התקשורת כמקור מידע (B)", "C": "טענה להשפעת התקשורת (C)"}
METHOD_LABELS = {"heading_discussion_decision": "כותרת \"דיון והכרעה\"", "heading_discussion_numbered": "כותרת \"דיון\" ממוספרת",
                 "court_turn_phrase": "ביטוי מעבר (\"לאחר שעיינתי...\")", "whole_judgment": "לא נמצא סימן — כל פסק הדין"}


def _clean(v: Any) -> Any:
    if v is None:
        return None
    if isinstance(v, float) and math.isnan(v):
        return None
    if hasattr(v, "item"):
        v = v.item()
    return v


def records(df: pd.DataFrame) -> list[dict[str, Any]]:
    return [{k: _clean(v) for k, v in row.items()} for row in df.to_dict(orient="records")]


def google_news_search_link(query: str, start: str, end: str) -> str:
    """A human-readable Google News search for the same query and window (opens in the browser)."""
    import datetime as dt

    before = (dt.date.fromisoformat(end) + dt.timedelta(days=1)).isoformat()
    q = f"{query} after:{start} before:{before}"
    return "https://news.google.com/search?" + urllib.parse.urlencode({"q": q, "hl": "iw", "gl": "IL", "ceid": "IL:he"})


class StudyData:
    def __init__(self, data_dir: Path | None = None) -> None:
        self.dir = Path(data_dir or paths.DATA_DIR)
        rd = lambda name: pd.read_csv(self.dir / name, encoding="utf-8-sig")  # noqa: E731
        self.df = rd("study_dataset_final.csv")
        self.extra = rd("cases_extra.csv").set_index("case_id")
        self.google = rd("media_google.csv")
        self.queries = rd("queries_google.csv")
        self.primo = rd("media_primo.csv")
        self.refs = rd("media_refs_verified.csv")
        self.outcome_review = rd("outcome_manual_review.csv") if (self.dir / "outcome_manual_review.csv").exists() else None
        self._judgments: pd.DataFrame | None = None
        self._lock = threading.Lock()

    # ---------------------------------------------------------------- text inputs
    def mention_reference(self) -> pd.DataFrame:
        """The study's automatic stage of the media dictionary (every match and its automatic exclusion)."""
        return pd.read_csv(self.dir / "mention_candidates_reference.csv", encoding="utf-8-sig")

    def judgments(self) -> pd.DataFrame:
        with self._lock:
            if self._judgments is None:
                self._judgments = pd.read_parquet(self.dir / "judgments.parquet").set_index("case_id")
            return self._judgments

    # ---------------------------------------------------------------- case table
    def case_list(self) -> list[dict[str, Any]]:
        d = self.df
        out = pd.DataFrame({
            "case_id": d.case_id,
            "case_number": d.case_number,
            "decision_date": d.decision_date,
            "year": d.year,
            "offence": d.homicide_murder.map({1: "רצח או ניסיון לרצח", 0: "המתה אחרת"}),
            "merits": d.merits_appeal,
            "non_merits_reason": d.non_merits_reason.fillna(""),
            "media_any": d.media_any,
            "media_count": d.media_count,
            "intervention": d.intervention,
            "relief": d.relief_type.map(RELIEF_LABELS),
            "media_ref_any": d.media_ref_any,
        })
        return records(out)

    # ---------------------------------------------------------------- case card
    def case_card(self, case_id: str) -> dict[str, Any] | None:
        rows = self.df[self.df.case_id == case_id]
        if rows.empty:
            return None
        r = {k: _clean(v) for k, v in rows.iloc[0].to_dict().items()}
        ex = {k: _clean(v) for k, v in self.extra.loc[case_id].to_dict().items()} if case_id in self.extra.index else {}
        card: dict[str, Any] = {"row": r}
        card["summary"] = [
            ["מספר הליך", r["case_number"]],
            ["תאריך פסק הדין בעליון", r["decision_date"]],
            ["סוג העבירה", "רצח או ניסיון לרצח" if r["homicide_murder"] == 1 else "המתה אחרת"],
            ["הרכב", f"{r['panel_size']} שופטים" + (f" ({ex.get('panel_judges')})" if ex.get("panel_judges") else "")],
            ["התערבות בית המשפט העליון", "כן" if r["intervention"] == 1 else "לא"],
            ["סוג התוצאה", RELIEF_LABELS.get(r["relief_type"], str(r["relief_type"]))],
            ["כיוון התוצאה מבחינת הנאשם", DIRECTION_LABELS.get(r["outcome_direction"], str(r["outcome_direction"]))],
            ["אופן קידוד התוצאה", self._outcome_coding(case_id, r)],
            ["תאריך הכרעת הדין בערכאה הדיונית (חולץ מהטקסט)", ex.get("district_verdict_date") or "לא אותר"],
            ["ציר זמן ודאי", "כן" if r["timeline_clean"] == 1 else "לא — מסומן לבדיקה"],
        ]
        if r["merits_appeal"] == 1:
            card["inclusion"] = {"included": True, "text": "נכלל במדגם הניתוח (N=478): ערעור של הנאשם על הכרעת דין או גזר דין "
                                 "בעבירת המתה, פסק דין סופי בשנים 2010–2020."}
        else:
            card["inclusion"] = {"included": False, "text": f"הוחרג ממדגם הניתוח (נשאר בקורפוס המלא, N=497): {r['non_merits_reason']}."}
        card["media_summary"] = [
            ["בולטות מוקדמת (חלון מרכזי)", "כן" if r["media_any"] == 1 else "לא"],
            ["מספר ידיעות שנכללו (ערכאה דיונית + ערעור)", r["media_count"]],
            ["ידיעות לפי שלב", f"שלב הערכאה הדיונית: {r['media_district_count']} · שלב הערעור: {r['media_appeal_count']}"],
            ["רשומות במאגר העיתונות (Primo)", "כן" if r["media_primo_any"] == 1 else "לא"],
        ]
        g = self.google[self.google.case_id == case_id].copy()
        g["window_label"] = g.window_type.map(WINDOW_SHORT)
        g["status_label"] = g.curation_status.map(STATUS_LABELS).fillna(g.curation_status)
        g["_order"] = (g.curation_status != "included").astype(int)      # included items first
        g = g.sort_values(["_order", "published_date"])
        card["google"] = records(g[["title", "source", "published_date", "url", "curation_status", "status_label", "window_label"]])
        q = self.queries[self.queries.case_id == case_id].copy()
        q["window_label"] = q.window_type.map(WINDOW_LABELS)
        q["search_link"] = [google_news_search_link(a, b, c) for a, b, c in zip(q.query_text, q.window_start, q.window_end)]
        card["queries"] = records(q[["query_text", "window_label", "window_start", "window_end", "search_link"]])
        p = self.primo[self.primo.case_id == case_id].copy()
        p["status_label"] = p.curation_status.map(STATUS_LABELS).fillna(p.curation_status)
        card["primo"] = records(p[["title", "newspaper_source", "published_date", "status_label", "query_text"]])
        card["text_measures"] = [
            ["אורך פסק הדין (מילים)", r.get("words")],
            ["אורך פרק ההנמקה (מילים)", r.get("r_words")],
            ["אופן חילוץ פרק ההנמקה", METHOD_LABELS.get(r.get("reasoning_method"), r.get("reasoning_method"))],
            ["אורך משפט ממוצע בהנמקה", r.get("r_sentence_len")],
            ["אזכורי תקשורת מאומתים בפסק הדין", r.get("media_ref_count")],
        ]
        card["judgment"] = self._judgment_segments(case_id)
        return card

    def _outcome_coding(self, case_id: str, r: dict[str, Any]) -> str:
        o = self.outcome_review
        if o is not None and case_id in set(o.case_id):
            row = o[o.case_id == case_id].iloc[0]
            ex = str(row.outcome_evidence_excerpt if isinstance(row.outcome_evidence_excerpt, str) else "").strip()
            return "נבדק ידנית" + (f" — „{ex[:220]}{'…' if len(ex) > 220 else ''}”" if ex else "")
        if r.get("relief_type") == 5:
            return "סווג אוטומטית ונבדק ידנית (תוצאת החמרה)"
        return "סווג אוטומטית לפי כללי הקידוד"

    def _judgment_segments(self, case_id: str) -> dict[str, Any]:
        j = self.judgments()
        if case_id not in j.index:
            return {"available": False, "segments": [], "refs": []}
        row = j.loc[case_id]
        text: str = row.body_text or ""
        rstart = int(row.reasoning_start) if pd.notna(row.reasoning_start) else 0
        refs = self.refs[self.refs.case_id == case_id].sort_values("position")
        cuts: list[tuple[int, int, dict[str, Any] | None]] = []
        for _, rf in refs.iterrows():
            s, e = int(rf.position), int(rf.position) + len(str(rf.match))
            cuts.append((s, e, {"reason": rf.manual_reason, "label": REF_LABELS.get(rf.manual_reason, rf.manual_reason),
                                "in_reasoning": int(rf.in_reasoning)}))
        segments: list[dict[str, Any]] = []
        pos = 0
        marker_done = rstart <= 0
        for s, e, info in cuts:
            if s < pos:
                continue
            if not marker_done and rstart <= s:
                segments.append({"t": text[pos:rstart]})
                segments.append({"marker": "תחילת פרק ההנמקה"})
                pos, marker_done = rstart, True
            segments.append({"t": text[pos:s]})
            segments.append({"t": text[s:e], "ref": info})
            pos = e
        if not marker_done and rstart < len(text):
            segments.append({"t": text[pos:rstart]})
            segments.append({"marker": "תחילת פרק ההנמקה"})
            pos = rstart
        segments.append({"t": text[pos:]})
        ref_list = [{"label": REF_LABELS.get(rf.manual_reason, rf.manual_reason), "match": rf.match,
                     "in_reasoning": int(rf.in_reasoning), "context": rf.context} for _, rf in refs.iterrows()]
        return {"available": True, "doc_date": row.doc_verdict_date, "chars": len(text),
                "reasoning_label": METHOD_LABELS.get(row.reasoning_method, row.reasoning_method),
                "segments": [s for s in segments if s.get("t") or s.get("marker")], "refs": ref_list}

    # ---------------------------------------------------------------- media re-import helpers
    def media_cases(self) -> list[dict[str, Any]]:
        """Study cases with the name (for the exact-name query) and the stored search windows."""
        from .court_rules import primo_case_party_name, quote_phrase

        out = []
        inc = self.google[self.google.curation_status == "included"].groupby("case_id").size()
        for _, r in self.df.iterrows():
            ex = self.extra.loc[r.case_id] if r.case_id in self.extra.index else None
            name = str(ex.case_name) if ex is not None and pd.notna(ex.case_name) else ""
            person = primo_case_party_name(name)
            q = self.queries[self.queries.case_id == r.case_id]
            windows = [{"window_type": w.window_type, "label": WINDOW_LABELS.get(w.window_type, w.window_type),
                        "start": w.window_start, "end": w.window_end, "original_query": w.query_text}
                       for w in q.itertuples()]
            out.append({"case_id": r.case_id, "case_number": r.case_number, "year": int(r.year),
                        "decision_date": r.decision_date, "query": quote_phrase(person) if person else "",
                        "windows": windows, "original_included": int(inc.get(r.case_id, 0)),
                        "merits": int(r.merits_appeal)})
        return out
