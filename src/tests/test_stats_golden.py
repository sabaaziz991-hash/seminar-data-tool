"""The statistics module must reproduce every number of the paper (golden values from results_master.md).

Run from 05_תוכנה\\src:   python -m pytest tests -q
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

SRC = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SRC))

from seminar_tool import analysis_core, exports, study_stats  # noqa: E402
from seminar_tool.data_access import StudyData  # noqa: E402

DATA = SRC.parent / "data"
PAPER_CORE = SRC.parents[1] / "03_ניתוח" / "analysis_core.py"


@pytest.fixture(scope="module")
def sd() -> StudyData:
    return StudyData(DATA)


@pytest.fixture(scope="module")
def report(sd: StudyData) -> dict:
    return study_stats.run_all(sd.df, sd.extras())


def test_all_golden_values_match(report: dict) -> None:
    g = study_stats.compare_golden(report["values"], DATA / "golden_values.json")
    bad = [f"{i['key']}: paper {i['expected']} vs {i['got']}" for i in g["items"] if not i["ok"]]
    assert not bad, "\n".join(bad)
    assert g["checked"] >= 250


@pytest.mark.parametrize("key,expected,tol", [
    ("main.chi2", 1.690, 5e-4), ("main.p_chi2", 0.194, 5e-4), ("main.fisher2", 0.192, 5e-4),
    ("main.or", 1.387, 5e-4), ("main.or_lo", 0.846, 5e-4), ("main.or_hi", 2.274, 5e-4),
    ("logit.adj.or", 1.289, 5e-4), ("logit.adj.p", 0.322, 5e-4), ("ref.any.chi2", 24.27, 5e-3),
    ("ref.reas.chi2", 26.12, 5e-3), ("cx.t", 3.96, 5e-3), ("cx.mean1", 0.346, 5e-4), ("cx.mean0", -0.092, 5e-4),
])
def test_key_numbers(report: dict, key: str, expected: float, tol: float) -> None:
    assert abs(report["values"][key] - expected) <= tol


def test_complexity_weights_match_spss(sd: StudyData) -> None:
    main = sd.df[sd.df.merits_appeal == 1]
    cx = study_stats.complexity_index(main)
    assert [round(w, 3) for w in cx["weights"]] == [0.339, 0.372, 0.202, 0.304, 0.233, 0.164]


def test_bundled_core_is_the_papers_core() -> None:
    """analysis_core.py was copied unchanged from 03_ניתוח (skipped when the project folder is absent)."""
    if not PAPER_CORE.exists():
        pytest.skip("project folder not available")
    assert Path(analysis_core.__file__).read_bytes().replace(b"\r\n", b"\n") == PAPER_CORE.read_bytes().replace(b"\r\n", b"\n")


def test_exact_name_queries_are_regenerated(sd: StudyData) -> None:
    cases = sd.media_cases()
    assert len(cases) == 497
    mism = [c["case_number"] for c in cases for w in c["windows"] if w["original_query"] != c["query"]]
    assert not mism, mism[:10]


def test_rounding_rule() -> None:
    assert not study_stats.matches(1.2746511, 1.28, 2)   # single rounding only: 1.2747 -> 1.27, not 1.28
    assert study_stats.matches(1.2746511, 1.27, 2)
    assert not study_stats.matches(1.26, 1.28, 2)


def test_upload_validation_messages() -> None:
    ok = exports.validate_upload(pd.DataFrame({"media_any": [0, 1, 0, 1], "intervention": [1, 0, 0, 1]}))
    assert ok["ok"] and any("merits_appeal" in w for w in ok["warnings"])
    bad = exports.validate_upload(pd.DataFrame({"media_any": [0, 2, "x"], "other": [1, 2, 3]}))
    assert not bad["ok"]
    text = " ".join(bad["errors"])
    assert "intervention" in text and "0 או 1" in text and "אינם מספרים" in text


def test_analyses_survive_awkward_user_data() -> None:
    d = pd.DataFrame({"media_any": [1, 1, 0, 0, 1, 0], "intervention": [1, 1, 0, 0, 1, 0],
                      "year_c": [0, 1, 2, 3, 4, 5], "homicide_murder": [1, 0, 1, 0, 1, 0]})
    res = study_stats.run_all(d)
    assert res["n_main"] == 6 and len(res["sections"]) >= 5


# golden values that are more precise than the text of results_master.md (SPSS 3-decimal output quoted in the task),
# or that deliberately use the single-rounded exact value (pre-137 upper limit: exact 2.1148, SPSS 2.115)
MORE_PRECISE_THAN_TEXT = {"main.or", "main.or_lo", "main.or_hi", "logit.adj.or", "ref.any.phi", "cx.mean1", "cx.mean0",
                          "mw.words.U"}


def test_golden_values_are_the_numbers_of_results_master() -> None:
    """Every expected value appears in the bundled copy of 03_ניתוח/results_master.md (same numbers as the paper)."""
    import json
    import re

    txt = (DATA / "results_master.md").read_text(encoding="utf-8").replace("−", "-").replace(",", "")
    spec = json.loads((DATA / "golden_values.json").read_text(encoding="utf-8"))
    missing = []
    for it in spec["items"]:
        e, d = it["expected"], it["decimals"]
        if isinstance(e, str) or it["key"] in MORE_PRECISE_THAN_TEXT:
            continue
        s = f"{e:.{d}f}"
        cands = {s, s.rstrip("0").rstrip(".") if "." in s else s}
        cands |= {c[1:] for c in cands if c.startswith("0.")} | {"-" + c[2:] for c in cands if c.startswith("-0.")}
        if not any(re.search(r"(?<![\d.])" + re.escape(c) + r"(?!\d)", txt) for c in cands):
            missing.append((it["key"], s))
    assert not missing, missing
    if PAPER_CORE.exists():   # the bundled copy is the project's current file
        assert (DATA / "results_master.md").read_bytes() == (PAPER_CORE.parent / "results_master.md").read_bytes()
