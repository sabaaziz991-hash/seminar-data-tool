"""Screen ג step 1 on the real court dataset: the flow counts must equal the paper
(586 defendant appeals -> 85 anonymous -> 501 named; 496 of the 497 study cases; 5 named appeals outside the corpus).
Skipped when cases_all.parquet is not available next to the project (…\\02_נתונים\\hf_raw)."""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from seminar_tool import reimport_court
from seminar_tool.data_access import StudyData
from seminar_tool.jobs import Job

SRC = Path(__file__).resolve().parents[1]
PARQUET = SRC.parents[1] / "02_נתונים" / "hf_raw" / "cases_all.parquet"
pytestmark = pytest.mark.skipif(not PARQUET.exists(), reason="cases_all.parquet not available")


def test_population_counts_match_paper() -> None:
    sd = StudyData(SRC.parent / "data")
    paper = json.loads((sd.dir / "flow_reference.json").read_text(encoding="utf-8"))
    job = Job("build")
    job.start(reimport_court.build_population, str(PARQUET), sd.df, paper)
    t0 = time.time()
    while job.running and time.time() - t0 < 600:
        time.sleep(1)
    assert job.state == "done", job.error
    s = job.result["summary"]
    counts = [f["count"] for f in s["flow"]]
    assert counts[:6] == [751194, 233718, 16747, 5768, 617, 586]
    anon = next(f for f in s["flow"] if f["step"].startswith("הוחרגו"))
    named = next(f for f in s["flow"] if f["step"].startswith("ערעורים עם שם מערער גלוי"))
    assert anon["count"] == 85 and named["count"] == 501
    assert "82" in anon["note"] and "3" in anon["note"]               # 82 by case name + 3 by the party block
    assert all(f["paper"] in (None, f["count"]) for f in s["flow"]), s["flow"]
    assert s["found"] == 496 and s["extra"] == 5
    assert [m["case_number"] for m in s["missing_list"]] == ['ע"פ 4908/18']
    assert s["missing_list"][0]["reason"] == reimport_court.NOTE_4908
    extra = {m["case_number"] for m in s["extra_list"]}
    assert extra == {'ע"פ 370/10', 'ע"פ 105/17', 'ע"פ 8328/17', 'ע"פ 2255/15', 'ע"פ 5855/15'}
    assert all(m["note"] == reimport_court.NOTE_EXTRA for m in s["extra_list"])


def test_party_block_parser() -> None:
    f = reimport_court.appellant_from_text
    assert f("המערער: פלוני נ ג ד המשיבה: מדינת ישראל") == "פלוני"
    assert f("המערערים: 1. תאופיק אגבריה 2. סעיד אגבריה נ ג ד") == "תאופיק אגבריה"
    assert f('המערערת בע"פ 9816/16 והמשיבה בע"פ 9817/16: מדינת ישראל נ ג ד המשיב בע"פ 9816/16 והמערער בע"פ 9817/16: פלוני') == "פלוני"
    assert reimport_court.is_anonymous("פלונית") and not reimport_court.is_anonymous("דוד-ישראל לוגסי")
