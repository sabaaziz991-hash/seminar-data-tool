"""Screen ב, step 3: the automatic text measures of the judgments, recomputed and compared with the study.

The rules are COPIED VERBATIM from the study code (03_ניתוח/text_measures.py and 03_ניתוח/attempt_only.py):
* the start of the court's reasoning ('דיון והכרעה' heading and fallbacks);
* the six components of the textual-complexity index and the length of the judgment and of the reasoning;
* the dictionary of media terms and the automatic exclusions (the manual decisions that followed are not automatic);
* the attempted-murder-only flag.
The measures are computed from the judgment texts bundled with the tool (the main judgment of every case, taken from
the open dataset) and every value is compared with the study data.
"""
from __future__ import annotations

import re
from typing import Any

import pandas as pd

# ---------------------------------------------------------------- copied from 03_ניתוח/text_measures.py
PFX = r"(?<![֐-׿A-Za-z])[והבלמשכ]{0,3}"
END = r"(?![֐-׿])"
MEDIA_TERMS = {
    "תקשורת": PFX + r"תקשורת(?:י|ית|יים|יות)?" + END,
    "עיתונות": PFX + r"עיתונ(?:ות|אי|אים|אית|איות|ים|י)?" + END,
    "סיקור": PFX + r"(?:סיקור|מסוקר|מסוקרת|מסוקרים)" + END,
    "כתבות": PFX + r"(?:כתבות|כתבה\s+(?:ב|ש)?(?:עיתון|אתר|טלוויזיה|תקשורת|חדשות))" + END,
    "חדשות": r"(?:(?:מהדורת|מהדורות|אתר|אתרי|כתב|כתבת|כתבי|ערוץ|שידורי|שידור)\s+ה?חדשות|(?<![֐-׿])ו?בחדשות)" + END,
    "טלוויזיה": PFX + r"(?:טלוויזי(?:ה|וני|ונית|וניים))" + END,
    "רדיו": PFX + r"רדיו" + END,
    # media interviews and publications
    "ראיון": PFX + r"(?:ראיון|ריאיון|ראיונות|ריאיונות|התראיין|התראיינה|התראיינו|מתראיין|מתראיינת)" + END,
    "פרסום": PFX + r"(?:פרסום|פרסומים|פרסומי|פורסם|פורסמה|פורסמו|פרסמה|פרסמו)" + END,
}
# Non-media senses of "תקשורת" that are common in homicide judgments (phones, cell sites, interpersonal).
AUTO_EXCLUDE = [
    r"נתוני\s+ה?תקשורת", r"מחקר(?:י)?\s+ה?תקשורת", r"תקשורת\s+(?:סלולרית|טלפונית|אלחוטית|בין|עם|מחשבים|לקויה|בינאישית)",
    r"ב?תקשורת\s+עם", r"פלט(?:י)?\s+ה?תקשורת", r"חבר(?:ת|ות)\s+ה?תקשורת", r"אנטנ(?:ה|ות)", r"מכשיר(?:י)?\s+ה?תקשורת",
    r"קו(?:וי)?\s+ה?תקשורת", r"מערכ(?:ת|ות)\s+ה?תקשורת", r"חוק\s+ה?תקשורת", r"ניתוח\s+ה?תקשורת", r"אמצעי\s+תקשורת\s+(?:אלקטרוני|סלולרי)",
    r"כושר\s+ה?תקשורת", r"יכולת\s+ה?תקשורת", r"תקשורת\s+(?:מילולית|רגשית|תקינה|טובה|קשה)", r"צור(?:ת|ות)\s+ה?תקשורת",
    r"(?:סים|כרטיס)\S*\s+תקשורת", r"תקשורת\s+נתונים",
    r"מכשיר(?:י)?\s+(?:ה)?(?:טלוויזיה|רדיו|קשר)", r"(?:צפה|צפו|צופה|צפתה|צפייה|צפיה|צופים)\s+ב?(?:ה)?טלוויזיה", r"מסך\s+ה?טלוויזיה",
    r"טלוויזי\S*\s+(?:ב)?מעגל\s+סגור", r"(?:ה)?טלוויזיה\s+ב(?:חדר|סלון)", r"קשר\s+(?:ה)?רדיו", r"רדיו\s+(?:ה)?משטרתי", r"(?:ב|ה)?רדיו\s+(?:ב|של\s+)?(?:ה)?רכב",
    # legal senses of "פרסום": gag orders, publication of rulings/laws, citation formulas
    r"איסור\s+(?:ה)?פרסום", r"צו\s+(?:ה)?איסור", r"(?:לא|טרם)\s+(?:ה)?(?:פורסם|פורסמ\S*)", r"(?:פורסם|פורסמ\S*)\s+ב(?:נבו|מאגר|מאגרים|פדאור|תקדין|דינים|רשומות|ילקוט|אתר)",
    r"(?:מותר|אסור|הותר)\S*\s+(?:ב|ל)?פרסום", r"פרסום\s+(?:פסק|גזר|החלטה|הכרעת|ה?תקנות|ה?חוק|שמו?ת?|פרטי\S*\s+מזה)",
    r"ברשומות", r"פרסום\s+(?:ה)?(?:ראיות|חומר\s+ה?חקירה)", r"פרסום\s+(?:ה)?(?:דיבה|לשון\s+הרע)",
    r"ראיון\s+(?:ה)?(?:משטרתי|במשטרה|עבודה|קבלה|פסיכיאטרי|קליני)", r"ראיונות?\s+(?:עם\s+)?(?:ה)?(?:פסיכיאטר|פסיכולוג|עובדת\s+סוציאלית|קצינת\s+מבחן|שירות\s+המבחן)",
]

HEB_WORD = re.compile(r"[א-תA-Za-z]+(?:[\"'׳״][א-ת]+)?")

REASONING_MARKERS = [
    ("heading_discussion_decision", r"(?:ה)?דיון\s+ו(?:ה)?הכרעה"),
    ("heading_discussion_numbered", r"\d+\.\s*דיון(?![א-ת])|(?<![א-ת])דיון(?![א-ת])\s+\d+\."),
    ("court_turn_phrase", r"לאחר\s+ש(?:עיינתי|עיינו|שקלתי|שקלנו|בחנתי|בחנו)"),
]


def reasoning_start(body: str) -> tuple[int, str]:
    """Offset where the court's own discussion begins ('דיון והכרעה' heading and fallbacks).
    Markers in the first 5% of the text are ignored (they tend to be summaries, not headings)."""
    floor = int(len(body) * 0.05)
    for name, pat in REASONING_MARKERS:
        for m in re.finditer(pat, body):
            if m.start() >= floor:
                return m.start(), name
    return 0, "whole_judgment"


def sentence_lengths(t: str) -> list[int]:
    # sentence boundaries: . ! ? : ; followed by space, but not paragraph numbers like "12. "
    parts = re.split(r"(?<!\b\d)(?<!\b\d\d)[.!?;:](?=\s)", t)
    return [len(HEB_WORD.findall(s)) for s in parts if HEB_WORD.search(s)]


def complexity(t: str) -> dict[str, float]:
    """The six components of the textual-complexity index."""
    words = HEB_WORD.findall(t)
    n = len(words)
    lens = sentence_lengths(t) or [n]
    letters = [len(re.sub(r"[\"'׳״]", "", w)) for w in words]
    s = pd.Series(lens, dtype=float)
    return {
        "r_words": n,
        "r_sentences": len(lens),
        "r_sentence_len": float(s.mean()),
        "r_sentence_len_p90": float(s.quantile(0.9)),
        "r_word_len": sum(letters) / n if n else float("nan"),
        "r_long_words_pct": 100 * sum(L > 6 for L in letters) / n if n else float("nan"),
        "r_very_long_words_pct": 100 * sum(L > 8 for L in letters) / n if n else float("nan"),
        "r_paren_per_1000": 1000 * t.count("(") / n if n else float("nan"),
    }


# ---------------------------------------------------------------- copied from 03_ניתוח/attempt_only.py
ATTEMPT = re.compile(r"ניסיון (?:ל)?רצח|ניסיון לרצוח|לנסות לרצוח")
# whole words only (an optional one- or two-letter prefix such as ו/ש/ה/ב/ל/מ/כ is allowed), so that
# "הלימותו של" or "התרשמותו של" are not read as "מותו של"
DEATH = re.compile(r"(?<![א-ת])[ובהלמשכ]{0,2}(?:"
                   r"המנוח|המנוחה|המנוחים|המנוחות|נרצח|נרצחה|נרצחו|נהרג|נהרגה|נהרגו|קיפח את חייו|קיפחה את חייה|"
                   r"גרם למותו|גרם למותה|גרם למותם|מותו של|מותה של|מותם של|הרוג|הקורבן שנפטר|נפטר|נפטרה|"
                   r"גופת|גופתו|גופתה|המתה)")


# ---------------------------------------------------------------- recomputation and comparison
MEASURES = [  # (column in the study data, Hebrew label, decimals kept in the study data)
    ("words", "אורך פסק הדין (מילים)", 0),
    ("r_words", "אורך פרק ההנמקה (מילים)", 0),
    ("r_sentence_len", "אורך משפט ממוצע (מילים)", 3),
    ("r_sentence_len_p90", "אורך משפט באחוזון ה-90", 3),
    ("r_word_len", "אורך מילה ממוצע (אותיות)", 3),
    ("r_long_words_pct", "שיעור המילים בנות 7 אותיות ומעלה", 3),
    ("r_very_long_words_pct", "שיעור המילים בנות 9 אותיות ומעלה", 3),
    ("r_paren_per_1000", "סוגריים ל-1,000 מילים", 3),
]


def media_candidates(case_id: str, body: str, rstart: int) -> list[dict[str, Any]]:
    """Every match of the media dictionary in one judgment, with the automatic exclusion (same rule as the study)."""
    rows = []
    for term, pat in MEDIA_TERMS.items():
        for m in re.finditer(pat, body):
            s, e = max(0, m.start() - 160), min(len(body), m.end() + 160)
            local = body[max(0, m.start() - 40): m.end() + 40]
            rows.append({"case_id": case_id, "term": term, "match": m.group(0), "position": m.start(),
                         "auto_excluded": int(any(re.search(p, local) for p in AUTO_EXCLUDE)),
                         "in_reasoning": int(m.start() >= rstart), "context": body[s:e]})
    return rows


def _same(a: Any, b: Any, decimals: int) -> bool:
    if pd.isna(a) and pd.isna(b):
        return True
    if pd.isna(a) or pd.isna(b):
        return False
    # same rounding as the study data (pandas .round), which can differ from Python's round() on a tie
    return float(pd.Series([float(a)]).round(decimals)[0]) == float(pd.Series([float(b)]).round(decimals)[0])


def compute(sd: Any) -> dict[str, Any]:
    """Recompute every automatic text measure from the bundled judgments and compare with the study data."""
    j = sd.judgments()
    study = sd.df.set_index("case_id")
    ref = sd.mention_reference()
    per_case, cands = [], []
    for cid, row in j.iterrows():
        body = row.body_text or ""
        rstart, method = reasoning_start(body)
        m = complexity(body[rstart:])
        per_case.append({"case_id": cid, "reasoning_start": rstart, "reasoning_method": method,
                         "words": len(HEB_WORD.findall(body)), **{k: m[k] for k, _, _ in MEASURES if k in m},
                         "attempt_only": int(bool(ATTEMPT.search(body)) and not DEATH.search(body))})
        cands += media_candidates(cid, body, rstart)
    now = pd.DataFrame(per_case).set_index("case_id")
    cand = pd.DataFrame(cands)
    both = now.join(study[[k for k, _, _ in MEASURES] + ["reasoning_method", "attempt_only", "case_number", "merits_appeal"]],
                    rsuffix="_study", how="left")

    rows = []
    for key, label, dec in MEASURES:
        eq = [_same(a, b, dec) for a, b in zip(both[key], both[key + "_study"])]
        diff = (both[key].astype(float).round(dec) - both[key + "_study"].astype(float)).abs().max()
        rows.append({"measure": label, "equal": int(sum(eq)), "n": len(eq), "max_diff": float(diff) if pd.notna(diff) else 0.0})
    eq_m = (both.reasoning_method == both.reasoning_method_study)
    rows.insert(0, {"measure": "זיהוי תחילת פרק ההנמקה (השיטה שנמצאה)", "equal": int(eq_m.sum()), "n": len(eq_m), "max_diff": None})
    eq_a = (both.attempt_only == both.attempt_only_study)
    rows.append({"measure": "סימון „ניסיון לרצח בלבד” (אין אזכור של מוות)", "equal": int(eq_a.sum()), "n": len(eq_a), "max_diff": None})

    # media dictionary: the automatic stage (matches + automatic exclusions), compared match by match
    key = ["case_id", "position", "term"]
    merged = cand.merge(ref, on=key, how="outer", suffixes=("", "_study"), indicator=True)
    same_rows = merged[(merged._merge == "both") & (merged.auto_excluded == merged.auto_excluded_study)
                       & (merged.in_reasoning == merged.in_reasoning_study)]
    merits = set(study.index[study.merits_appeal == 1])
    checked = cand[(cand.auto_excluded == 0) & cand.case_id.isin(merits)]
    mentions = {
        "found_now": int(len(cand)), "found_study": int(len(ref)), "identical": int(len(same_rows)),
        "auto_excluded_now": int(cand.auto_excluded.sum()), "auto_excluded_study": int(ref.auto_excluded.sum()),
        "checked_now": int(len(checked)),
        "checked_study": int(((ref.auto_excluded == 0) & ref.case_id.isin(merits)).sum()),
    }
    attempt = {"now": int(both.loc[both.merits_appeal == 1, "attempt_only"].sum()),
               "study": int(both.loc[both.merits_appeal == 1, "attempt_only_study"].sum()),
               "now_all": int(both.attempt_only.sum()), "study_all": int(both.attempt_only_study.sum())}
    table = both.reset_index()[["case_id", "case_number", "merits_appeal", "reasoning_method", "reasoning_start", "words"]
                               + [k for k, _, _ in MEASURES if k != "words"] + ["attempt_only"]]
    all_ok = all(r["equal"] == r["n"] for r in rows) and mentions["identical"] == mentions["found_now"] == mentions["found_study"]
    return {"rows": rows, "mentions": mentions, "attempt": attempt, "all_ok": bool(all_ok), "n_cases": int(len(now)),
            "table": table, "candidates": cand.drop(columns=["context"]).merge(
                study[["case_number"]], left_on="case_id", right_index=True, how="left")}
