"""Build the bundled data folder (05_תוכנה/data) from the project's read-only inputs.

Run once before packaging:  python src/prepare_data.py
Only reads from 02_נתונים / 03_ניתוח; writes only into 05_תוכנה/data.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import shutil
import sys
from pathlib import Path

import pandas as pd

TOOL = Path(__file__).resolve().parents[1]          # ...\05_תוכנה
ROOT = TOOL.parent                                   # project root
DATA_IN = ROOT / "02_נתונים"
EXPORT = DATA_IN / "FINAL_STUDY_DATA_2010_2020_PRIMO_MANUAL_REVIEW_2026-05-27_113917" / "01_final_dataset"
ANALYSIS = ROOT / "03_ניתוח"
OUT = TOOL / "data"


# Articles that the manual review found unrelated to the case (mostly a namesake) stay in the data with their status,
# so every count is complete, but their title, link and note are not published.
HIDDEN_TITLE = "(הכותרת הוסתרה: הכתבה אינה עוסקת בתיק)"
HIDDEN_NOTE = "הוחרג בבדיקה ידנית: הכתבה אינה עוסקת בתיק (אדם אחר בעל אותו שם או עניין אחר)"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    OUT.mkdir(parents=True, exist_ok=True)
    sources: dict[str, str] = {}

    # 1. final study data (byte-for-byte copy)
    src = DATA_IN / "study_dataset_final.csv"
    shutil.copyfile(src, OUT / "study_dataset_final.csv")
    sources["study_dataset_final.csv"] = str(src.relative_to(ROOT))

    # 2. per-case extra fields (names are needed only to rebuild the exact-name media queries)
    fav = pd.read_csv(EXPORT / "final_analysis_variables_2010_2020_primo_manual_review.csv")
    extra = fav[["case_id", "case_number", "case_name", "offense_group", "appellant_type", "relief_type",
                 "panel_judges", "district_verdict_date", "offense_date", "media_window_start", "media_window_end",
                 "timeline_needs_review"]].rename(columns={"relief_type": "relief_type_text"})
    extra.to_csv(OUT / "cases_extra.csv", index=False, encoding="utf-8-sig")
    sources["cases_extra.csv"] = str((EXPORT / "final_analysis_variables_2010_2020_primo_manual_review.csv").relative_to(ROOT))

    # 3. Google News items (district + appeal windows, with curation status) and the exact queries
    g = pd.read_csv(EXPORT / "selected_google_articles_district_plus_appeal_and_appeal_only.csv")
    g = g[["article_id", "case_id", "window_type", "window_start", "window_end", "query_text", "title", "source",
           "published_date", "url", "curation_status", "curator_note"]].copy()
    hide = g.curation_status == "excluded_wrong_case"
    g.loc[hide, ["title", "url", "curator_note"]] = [HIDDEN_TITLE, "", HIDDEN_NOTE]
    g.to_csv(OUT / "media_google.csv", index=False, encoding="utf-8-sig")
    sources["media_google.csv"] = str((EXPORT / "selected_google_articles_district_plus_appeal_and_appeal_only.csv").relative_to(ROOT))
    q = pd.read_csv(EXPORT / "selected_google_queries_district_plus_appeal_and_appeal_only.csv")
    q = q[["query_id", "case_id", "query_text", "query_type", "window_type", "window_start", "window_end"]]
    q.to_csv(OUT / "queries_google.csv", index=False, encoding="utf-8-sig")
    sources["queries_google.csv"] = str((EXPORT / "selected_google_queries_district_plus_appeal_and_appeal_only.csv").relative_to(ROOT))

    # 4. Primo newspaper records (robustness source)
    p = pd.read_csv(EXPORT / "primo_advanced_api_articles_2010_2020_manual_reviewed.csv")
    p = p[["article_id", "case_id", "query_text", "window_start", "window_end", "title", "newspaper_source",
           "published_date", "source_collection", "curation_status", "curator_note"]].copy()
    hide = p.curation_status.isin(["excluded_wrong_case", "excluded_false_positive"])
    p.loc[hide, ["title", "curator_note"]] = [HIDDEN_TITLE, HIDDEN_NOTE]
    p.to_csv(OUT / "media_primo.csv", index=False, encoding="utf-8-sig")
    sources["media_primo.csv"] = str((EXPORT / "primo_advanced_api_articles_2010_2020_manual_reviewed.csv").relative_to(ROOT))

    # 5. judgment text (operative Supreme Court judgment, body only) + verified media references
    j = pd.read_parquet(DATA_IN / "main_judgments_497.parquet", columns=["case_id", "doc_verdict_date", "reasoning_start", "reasoning_method", "body_text"])
    j.to_parquet(OUT / "judgments.parquet", index=False, compression="zstd", compression_level=15)
    sources["judgments.parquet"] = str((DATA_IN / "main_judgments_497.parquet").relative_to(ROOT))
    c = pd.read_csv(DATA_IN / "media_mention_candidates.csv")
    c = c[c.manual_decision == "include"][["case_id", "term", "match", "position", "in_reasoning", "manual_reason", "context"]]
    c.to_csv(OUT / "media_refs_verified.csv", index=False, encoding="utf-8-sig")
    sources["media_refs_verified.csv"] = str((DATA_IN / "media_mention_candidates.csv").relative_to(ROOT))
    # the automatic stage of the media dictionary (every match + automatic exclusion), for the comparison in step 3
    c_all = pd.read_csv(DATA_IN / "media_mention_candidates.csv")
    c_all[["case_id", "position", "term", "auto_excluded", "in_reasoning"]].to_csv(
        OUT / "mention_candidates_reference.csv", index=False, encoding="utf-8-sig")
    sources["mention_candidates_reference.csv"] = str((DATA_IN / "media_mention_candidates.csv").relative_to(ROOT))

    # 5b. manual review of the outcome coding (117 cases; how each outcome was coded is shown on the case card)
    o = pd.read_csv(DATA_IN / "outcome_manual_review_117.csv")
    o = o[["case_id", "reviewed_at", "appeal_outcome_raw", "relief_type", "outcome_evidence_excerpt"]]
    o.to_csv(OUT / "outcome_manual_review.csv", index=False, encoding="utf-8-sig")
    sources["outcome_manual_review.csv"] = str((DATA_IN / "outcome_manual_review_117.csv").relative_to(ROOT))

    # 6. flow counts of the paper (for comparison in the re-import wizard)
    flow = json.loads((ANALYSIS / "flow_counts.json").read_text(encoding="utf-8"))
    flow["paper_table"] = {"anonymous_excluded": 85, "study_corpus": 497, "non_merits_excluded": 19, "analysis_sample": 478}
    (OUT / "flow_reference.json").write_text(json.dumps(flow, ensure_ascii=False, indent=2), encoding="utf-8")
    sources["flow_reference.json"] = str((ANALYSIS / "flow_counts.json").relative_to(ROOT)) + " + results_master.md"

    manifest = {"built_at": dt.datetime.now().isoformat(timespec="seconds"), "files": {}}
    for rel, origin in sources.items():
        path = OUT / rel
        manifest["files"][rel] = {"source": origin, "bytes": path.stat().st_size, "sha256": sha256(path)}
    (OUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    for rel, info in manifest["files"].items():
        print(f"{rel:32s} {info['bytes']:>10,d}  <- {info['source']}")


if __name__ == "__main__":
    main()
