"""The method screens must apply exactly the rules of the study and reproduce its automatic results.

Run from 05_תוכנה\\src:   python -m pytest tests -q
"""
from __future__ import annotations

import importlib.util
import inspect
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SRC))

from seminar_tool import reimport_media, text_measures  # noqa: E402
from seminar_tool.data_access import StudyData  # noqa: E402

DATA = SRC.parent / "data"
PROJECT = SRC.parents[1] / "03_ניתוח"


@pytest.fixture(scope="module")
def sd() -> StudyData:
    return StudyData(DATA)


@pytest.fixture(scope="module")
def measures(sd: StudyData) -> dict:
    return text_measures.compute(sd)


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_text_rules_are_the_papers() -> None:
    """The text rules were copied unchanged from 03_ניתוח (skipped when the project folder is absent)."""
    if not (PROJECT / "text_measures.py").exists():
        pytest.skip("project folder not available")
    tm = _load("paper_text_measures", PROJECT / "text_measures.py")
    att = _load("paper_attempt_only", PROJECT / "attempt_only.py")
    for name in ("MEDIA_TERMS", "AUTO_EXCLUDE", "REASONING_MARKERS", "PFX", "END"):
        assert getattr(tm, name) == getattr(text_measures, name), name
    assert tm.HEB_WORD.pattern == text_measures.HEB_WORD.pattern
    for fn in ("reasoning_start", "sentence_lengths", "complexity"):
        assert inspect.getsource(getattr(tm, fn)) == inspect.getsource(getattr(text_measures, fn)), fn
    assert att.ATTEMPT.pattern == text_measures.ATTEMPT.pattern and att.DEATH.pattern == text_measures.DEATH.pattern


def test_text_measures_match_the_study(measures: dict) -> None:
    assert measures["n_cases"] == 497
    bad = [r for r in measures["rows"] if r["equal"] != r["n"]]
    assert not bad, bad
    m = measures["mentions"]
    assert m["found_now"] == m["found_study"] == m["identical"] == 2050
    assert m["auto_excluded_now"] == m["auto_excluded_study"] == 1628
    assert m["checked_now"] == m["checked_study"] == 412          # "412 המופעים שנבדקו" in the paper
    assert measures["attempt"] == {"now": 31, "study": 31, "now_all": 34, "study_all": 34}
    assert measures["all_ok"]


def test_exact_name_queries_are_regenerated(sd: StudyData) -> None:
    cases = sd.media_cases()
    assert len(cases) == 497
    mism = [c["case_number"] for c in cases for w in c["windows"] if w["original_query"] != c["query"]]
    assert not mism, mism[:10]


def test_article_rules() -> None:
    xml = """<rss><channel>
<item><title>בית המשפט העליון דחה ערעור ברצח - ynet</title><link>https://www.ynet.co.il/a?utm_source=x</link>
<pubDate>Mon, 05 Jul 2010 10:00:00 GMT</pubDate><description>&lt;b&gt;ערעור&lt;/b&gt; נדחה</description><source url="https://www.ynet.co.il">ynet</source></item>
<item><title>בית המשפט העליון דחה ערעור ברצח - ynet</title><link>https://www.ynet.co.il/a</link>
<pubDate>Mon, 05 Jul 2010 10:00:00 GMT</pubDate><source>ynet</source></item>
<item><title>שחקן כדורגל חדש</title><link>https://sport5.co.il/b</link><pubDate>Tue, 06 Jul 2010 10:00:00 GMT</pubDate><source>sport5</source></item>
<item><title>חנות נפתחה</title><link>https://x.co.il/c</link><pubDate>Tue, 06 Jul 2010 10:00:00 GMT</pubDate><source>x</source></item>
<item><title>ידיעה מאוחרת</title><link>https://x.co.il/d</link><pubDate>Tue, 20 Jul 2010 10:00:00 GMT</pubDate><source>x</source></item>
</channel></rss>"""
    items = reimport_media.parse_rss(xml, "2010-07-01", "2010-07-10")
    assert [i["in_window"] for i in items] == [True, True, True, True, False]
    assert items[0]["snippet"] == "ערעור נדחה"
    got = [i["auto_status"] for i in reimport_media.classify([i for i in items if i["in_window"]])]
    assert got == ["included", "excluded_duplicate", "excluded_wrong_case", "pending_review"]
