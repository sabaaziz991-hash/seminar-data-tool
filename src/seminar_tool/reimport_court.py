"""Screen ג, step 1: court data.

(a) download cases_all.parquet from the Hugging Face *dataset* LevMuchnik/SupremeCourtOfIsrael (≈1.5 GB,
    resumable), or use an existing local copy;
(b) rebuild the case population with the same filters as 03_ניתוח/build_flow.py and the classification
    rules of the original pipeline (court_rules.py), showing the count after every step and comparing
    the result with the study list (497 cases).
Memory-friendly: metadata columns are read first; the large `text` column is streamed in batches and only
the ~12k candidate judgments are kept.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import pandas as pd

from . import paths
from .court_rules import (classify_appellant_type, classify_offense, classify_outcome, is_anonymous_name,
                          is_institutional_party_name)
from .jobs import Job

HF_DATASET = "LevMuchnik/SupremeCourtOfIsrael"
HF_URL = f"https://huggingface.co/datasets/{HF_DATASET}/resolve/main/cases_all.parquet"
HF_PAGE = f"https://huggingface.co/datasets/{HF_DATASET}"
EXPECTED_BYTES = 1_523_770_663          # size of the file used in the study (for the progress bar only)
USER_AGENT = f"{paths.APP_NAME}/{paths.VERSION} (academic seminar replication tool)"
AP_RE = r'^\s*ע"פ\s'
# anonymised appellants: whole-word פלוני / פלונית / אלמוני / אלמונית anywhere in the case name
# (same pattern as ANONYMOUS_PARTY_RE in the original search_case_media.py)
ANON_RE = re.compile(r"(?<![\w֐-׿])(?:פלוני|פלונית|"
                     r"אלמוני|אלמונית)(?![\w֐-׿])")
COURT_DIR = paths.OUTPUT_DIR / "ייבוא_נתוני_בית_המשפט"
# party block of a judgment: "המערער: <name>", "המערערים: 1. <name>", "המערער בע"פ 9817/16: <name>" (not "בשם המערער:")
PARTY_RE = re.compile(r'(?<!בשם )(?<!ב)(?:המערער|המערערת|המערערים|המערערות)(?:\s+(?:ו?ה?משיב\S*\s+)?ב?ע"פ\s*[\d/]+)*\s*:\s*(?=(.{0,60}))')
INSTITUTIONS = ("מדינת ישראל", "היועץ המשפטי", "פרקליטות", "עו\"ד")
NOTE_4908 = "סווג אוטומטית כערעור מדינה; באימות ידני נמצא ערעור נאשם"
NOTE_EXTRA = "לא נאספו לגביהם נתוני סיקור"


def appellant_from_text(text: str) -> str:
    """The appellant as written in the party block of the judgment (first party that is not the State or a lawyer)."""
    flat = re.sub(r"\s+", " ", text[:6000])
    for m in PARTY_RE.finditer(flat):
        cand = re.sub(r"^\d+\.\s*", "", m.group(1)).strip(" .,:;")
        cand = re.split(r"\s+(?:נ ג ד|נגד|נ\.)\s+|\s+\d+\.\s+", cand)[0].strip()
        if cand and not cand.startswith(INSTITUTIONS):
            return cand
    return ""


def is_anonymous(name: str) -> bool:
    return (bool(ANON_RE.search(name)) or is_anonymous_name(name)) if name.strip() else False


def defendant_side(case_name: str) -> str:
    """Appellant side of 'X נ. Y' ('' when the appellant is the State or another institution)."""
    left = re.split(r"\s+(?:נ\.|נ'|נ׳|נגד)\s+", case_name.strip(), maxsplit=1)[0].strip()
    return "" if (not left or is_institutional_party_name(left)) else left


def case_names(meta: pd.DataFrame, ids: set[int]) -> pd.Series:
    """Per case: the appellant's name taken from CaseName across ALL the case's documents - the most frequent
    non-empty CaseName whose appellant side is a person (joint judgments may carry another docket's name)."""
    d = meta[meta.CaseId.isin(ids)][["CaseId", "CaseName"]].copy()
    d["CaseName"] = d.CaseName.fillna("").astype(str).str.strip()
    d = d[d.CaseName.map(defendant_side) != ""]
    return d.groupby("CaseId").CaseName.agg(lambda x: x.value_counts().index[0])


def study_id(case_id: int) -> str:
    """Study case_id = 'HUGGINGFACE-' + first 12 hex chars of sha1(str(CaseId))."""
    return "HUGGINGFACE-" + hashlib.sha1(str(case_id).encode()).hexdigest()[:12]


def download_dir() -> Path:
    """Folder for the ~1.5 GB download: the user's last choice, else the default folder under the outputs."""
    p = paths.get_setting("hf_dir")
    return Path(p) if p and Path(p).is_dir() else COURT_DIR


def default_download_path() -> Path:
    return download_dir() / "cases_all.parquet"


def find_local_copies() -> list[str]:
    """Existing copies of cases_all.parquet (no network): the last file the user chose, the download folder,
    the program folder and up to three folders above it (e.g. a project folder with 02_נתונים/hf_raw), and Downloads."""
    cands = [Path(p) for p in (paths.get_setting("last_parquet"),) if p]
    cands += [default_download_path(), COURT_DIR / "cases_all.parquet", paths.ROOT_DIR / "cases_all.parquet"]
    for up in list(paths.ROOT_DIR.parents)[:3]:
        cands += [up / "02_נתונים" / "hf_raw" / "cases_all.parquet", up / "cases_all.parquet"]
    cands.append(Path.home() / "Downloads" / "cases_all.parquet")
    seen, out = set(), []
    for c in cands:
        try:
            if c.exists() and c.stat().st_size > 100_000_000 and str(c.resolve()) not in seen:
                seen.add(str(c.resolve()))
                out.append(str(c))
        except OSError:
            pass
    return out


def check_parquet(path: str | Path) -> dict[str, Any]:
    import pyarrow.parquet as pq

    p = Path(path)
    if not p.exists():
        raise ValueError("הקובץ לא נמצא בנתיב שצוין.")
    meta = pq.ParquetFile(p).metadata
    names = set(meta.schema.names)
    need = {"CaseId", "CaseDesc", "CaseName", "Type", "Technical", "VerdictDt", "text"}
    if not need <= names:
        raise ValueError("זה אינו קובץ המאגר הנכון — חסרות עמודות: " + ", ".join(sorted(need - names)))
    return {"path": str(p), "rows": meta.num_rows, "bytes": p.stat().st_size}


# ---------------------------------------------------------------- download
def download(job: Job, dest: Path) -> dict[str, Any]:
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    have = part.stat().st_size if part.exists() else 0
    headers = {"User-Agent": USER_AGENT}
    if have:
        headers["Range"] = f"bytes={have}-"
    job.update(0.0, "מתחבר ל-Hugging Face...", f"הורדה אל {dest}" + (f" (ממשיך מ-{have/1e6:,.0f} MB)" if have else ""))
    req = urllib.request.Request(HF_URL, headers=headers)
    with urllib.request.urlopen(req, timeout=60) as resp:
        if have and resp.status != 206:           # server ignored the range: start over
            have = 0
        length = int(resp.headers.get("Content-Length") or 0)
        total = (have + length) if length else EXPECTED_BYTES
        mode = "ab" if have else "wb"
        done, t0, last = have, time.time(), 0.0
        with open(part, mode) as f:
            while True:
                chunk = resp.read(1 << 20)
                if not chunk:
                    break
                f.write(chunk)
                done += len(chunk)
                now = time.time()
                if now - last > 0.5:
                    last = now
                    speed = (done - have) / max(now - t0, 1e-6)
                    eta = (total - done) / speed if speed > 0 else 0
                    job.update(done / total, f"הורדו {done/1e9:.2f} מתוך {total/1e9:.2f} GB · {speed/1e6:.1f} MB לשנייה · "
                                             f"נותרו כ-{eta/60:.0f} דקות")
    if part.stat().st_size < total:
        raise RuntimeError("ההורדה נקטעה. לחצו שוב על 'הורדה' כדי להמשיך מאותה נקודה.")
    part.replace(dest)
    job.update(1.0, "בודק את הקובץ שהורד...")
    info = check_parquet(dest)
    job.update(1.0, f"ההורדה הושלמה: {info['rows']:,} מסמכים.", "ההורדה הושלמה")
    return info


# ---------------------------------------------------------------- population rebuild
def build_population(job: Job, parquet_path: str, study: pd.DataFrame, paper: dict[str, Any]) -> dict[str, Any]:
    import pyarrow as pa
    import pyarrow.parquet as pq

    check_parquet(parquet_path)
    pf = pq.ParquetFile(parquet_path)
    flow: list[dict[str, Any]] = []

    def step(label: str, count: int, paper_value: Any = None, note: str = "") -> None:
        flow.append({"step": label, "count": int(count), "paper": paper_value, "note": note})
        job.update(log_line=f"{label}: {count:,}")

    job.update(0.02, "קורא את עמודות המטא-דאטה (ללא הטקסט)...")
    meta = pf.read(columns=["CaseId", "CaseDesc", "CaseName", "Type", "Technical", "VerdictDt"]).to_pandas()
    meta["Technical"] = meta["Technical"].astype("boolean").fillna(False).astype(bool)
    meta["vd"] = pd.to_datetime(meta.VerdictDt)
    if getattr(meta["vd"].dt, "tz", None) is not None:
        meta["vd"] = meta["vd"].dt.tz_localize(None)
    step("מסמכים במאגר Hugging Face", len(meta), paper.get("hf_documents"))
    step("תיקים (CaseId) במאגר", meta.CaseId.nunique(), paper.get("hf_cases"))

    is_ap = meta.CaseDesc.fillna("").str.match(AP_RE)
    fa = meta[is_ap]
    step('תיקי ע"פ (כל השנים)', fa.CaseId.nunique(), paper.get("criminal_appeal_cases_any_year"))
    final = fa[(fa.Type == "פסק-דין") & (~fa.Technical)]
    final = final[(final.vd >= "2010-01-01") & (final.vd <= "2020-12-31")]
    final = final.sort_values("vd").groupby("CaseId").tail(1)          # latest final judgment per case
    step('תיקי ע"פ עם פסק דין סופי (לא טכני) 2010–2020', len(final), paper.get("criminal_appeal_cases_with_final_judgment_2010_2020"))

    # stream the text column; keep only non-technical judgments of the selected cases
    ids = set(final.CaseId)
    cand_mask = (meta.CaseId.isin(ids) & (meta.Type == "פסק-דין") & (~meta.Technical)).to_numpy()
    kept: dict[int, str] = {}
    offset, n = 0, len(meta)
    job.update(0.05, "קורא את טקסט פסקי הדין (בקטעים)...")
    for batch in pf.iter_batches(batch_size=20_000, columns=["text"]):
        rows = batch.num_rows
        idx = cand_mask[offset:offset + rows].nonzero()[0]
        if len(idx):
            texts = batch.column(0).take(pa.array(idx)).to_pylist()
            for i, t in zip(idx, texts):
                if t is not None:
                    kept[offset + int(i)] = t
        offset += rows
        job.update(0.05 + 0.25 * offset / n, f"קורא טקסט: {offset:,} / {n:,} מסמכים")
    txt = meta.loc[list(kept)].assign(text=pd.Series(kept))
    txt = txt.sort_values("vd").groupby("CaseId").tail(1).set_index("CaseId")

    # classification with the original rules
    names = case_names(meta, ids)
    rows = []
    total = len(final)
    for k, r in enumerate(final.itertuples(index=False), start=1):
        text = txt.text.get(r.CaseId, "") or ""
        off = classify_offense(text)
        name = r.CaseName if isinstance(r.CaseName, str) else ""
        appellant = classify_appellant_type(name, text[:4000])          # as in 03_ניתוח/build_flow.py
        party = names.get(r.CaseId, "")
        if party:        # anonymity is decided by the case name (across the case's documents) when there is one ...
            anonymous, source, shown = is_anonymous(defendant_side(party)), "CaseName", party
        else:            # ... otherwise by the appellant written in the party block of the judgment
            shown = appellant_from_text(text)
            anonymous, source = is_anonymous(shown), "טקסט פסק הדין"
        rows.append({
            "CaseId": int(r.CaseId), "case_id": study_id(r.CaseId), "case_number": r.CaseDesc,
            "case_name": shown, "name_source": source,
            "verdict_date": r.vd.date().isoformat() if pd.notna(r.vd) else "",
            "offense_group": off.get("offense_group", ""), "murder_or_homicide": int(off.get("murder_or_homicide") or 0),
            "appellant_type": appellant, "name_anonymous": int(anonymous),
            "_text": text,
        })
        if k % 50 == 0 or k == total:
            job.update(0.30 + 0.65 * k / total, f"מסווג פסקי דין לפי כללי המחקר: {k:,} / {total:,}")
    df = pd.DataFrame(rows)
    hom = df[df.murder_or_homicide == 1].copy()
    step("סווגו כעבירות המתה (רצח / המתה אחרת)", len(hom), paper.get("homicide_cases"))
    defe = hom[hom.appellant_type == "defendant"].copy()
    step("הנאשם הוא המערער", len(defe), paper.get("homicide_defendant_appeals"))
    anon = defe[defe.name_anonymous == 1]
    by_src = anon.name_source.value_counts()
    step("הוחרגו: זהות המערער חסויה (\"פלוני\")", len(anon), paper.get("homicide_defendant_appeals_anonymous_excluded"),
         f"לפי שם התיק {int(by_src.get('CaseName', 0))}; לפי שורת הצדדים בפסק הדין (שם התיק ריק במאגר) {int(by_src.get('טקסט פסק הדין', 0))}")
    named = defe[defe.name_anonymous == 0]
    step("ערעורים עם שם מערער גלוי", len(named), paper.get("homicide_defendant_appeals_named"))

    # outcome classification of the rebuilt population (information only)
    job.update(0.96, "מסווג תוצאות ערעור...")
    outcome = [classify_outcome(t, "defendant") for t in named._text]
    named = named.assign(relief_type_rule=[o.get("relief_type", "") for o in outcome])

    # comparison with the study list
    study_ids = set(study.case_id)
    in_named = named.case_id.isin(study_ids)
    found = int(in_named.sum())
    extra = named[~in_named]
    step(f"מתוכם — תיקים מרשימת המחקר ({len(study)})", found, paper.get("study_corpus_found_in_reconstruction"))
    step("ערעורים עם שם גלוי שאינם בקורפוס המחקר", len(extra), paper.get("named_not_in_study_corpus"), NOTE_EXTRA)
    missing = study[~study.case_id.isin(set(named.case_id))][["case_id", "case_number"]].copy()
    by_id = df.set_index("case_id")

    def why(cid: str) -> str:
        if cid not in by_id.index:
            return "לא נמצא פסק דין סופי לא טכני של ע\"פ בשנים 2010–2020 במאגר"
        r = by_id.loc[cid]
        if r.murder_or_homicide != 1:
            return f"הכללים לא סיווגו כעבירת המתה ({r.offense_group})"
        if r.appellant_type == "state":
            return NOTE_4908
        if r.appellant_type != "defendant":
            who = {"both": "שני הצדדים", "unknown": "לא ידוע"}.get(r.appellant_type, r.appellant_type)
            return f"סיווג אוטומטי של המערער: {who}"
        if r.name_anonymous:
            return "זהות המערער חסויה במאגר"
        return "אחר"
    missing["reason"] = missing.case_id.map(why)

    merits = study.set_index("case_id").merits_appeal
    out = named.drop(columns=["_text"]).assign(
        in_study=in_named.astype(int).values,
        study_merits_appeal=named.case_id.map(merits).fillna(-1).astype(int).values)
    COURT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y-%m-%d_%H%M")
    csv_path = COURT_DIR / f"population_rebuilt_{stamp}.csv"
    out.to_csv(csv_path, index=False, encoding="utf-8-sig")
    summary = {"flow": flow, "found": found, "study_n": len(study), "extra": len(extra), "missing": len(missing),
               "extra_list": extra[["case_number", "case_name", "verdict_date"]].assign(note=NOTE_EXTRA).to_dict(orient="records"),
               "missing_list": missing[["case_number", "reason"]].to_dict(orient="records"),
               "csv_path": str(csv_path), "parquet": str(parquet_path),
               "built_at": dt.datetime.now().isoformat(timespec="seconds")}
    (COURT_DIR / "last_result.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    job.update(1.0, f"הסתיים: {len(named)} ערעורים עם שם גלוי; {found} מתוך {len(study)} תיקי המחקר זוהו בכללים האוטומטיים.", "הסתיים")
    return {"summary": summary, "table": out, "missing": missing}
