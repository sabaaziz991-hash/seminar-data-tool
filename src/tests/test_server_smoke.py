"""Smoke test: the local server starts and every API endpoint answers (no network calls to Google / Hugging Face)."""
from __future__ import annotations

import io
import json
import socket
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pandas as pd
import pytest

from seminar_tool import paths, server

TOKEN = {"X-Requested-With": "SeminarDataTool"}


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def base():
    port = free_port()
    srv = server.make_server(port)
    t = threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.2}, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{port}", srv, t
    server.STATE.shutdown("tests finished")
    t.join(5)


def get(url: str, headers: dict | None = None) -> tuple[int, bytes, dict]:
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, r.read(), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read(), dict(e.headers)


def post(url: str, body: dict | bytes, headers: dict | None = None) -> tuple[int, dict]:
    data = body if isinstance(body, bytes) else json.dumps(body).encode()
    h = {"Content-Type": "application/json", **(headers if headers is not None else TOKEN)}
    req = urllib.request.Request(url, data=data, headers=h, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read()
            return r.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def test_pages_and_static(base):
    b, _, _ = base
    code, body, hdr = get(b + "/")
    assert code == 200 and "כלי נתוני הסמינריון".encode() in body and "charset=utf-8" in hdr["Content-Type"]
    for f in ("app.js", "style.css", "icon.svg"):
        assert get(b + "/static/" + f)[0] == 200
    assert get(b + "/static/../server.py")[0] == 404


def test_info_cases_and_card(base):
    b, _, _ = base
    info = json.loads(get(b + "/api/info")[1])
    assert info["n_cases"] == 497 and info["n_main"] == 478 and Path(info["output_dir"]).exists()
    assert info["output_is_default"] is True and info["output_reason"] == "" and "clients" in info
    cases = json.loads(get(b + "/api/cases")[1])["cases"]
    assert len(cases) == 497
    card = json.loads(get(b + "/api/case?id=HUGGINGFACE-00ab1bad61ad")[1])["card"]
    assert card["google"] and card["queries"] and card["judgment"]["available"]
    assert any(s.get("ref") for s in card["judgment"]["segments"])
    assert get(b + "/api/case?id=nope")[0] == 404


def test_stats_and_exports(base):
    b, _, _ = base
    st = json.loads(get(b + "/api/stats?source=study")[1])
    assert st["golden"]["all_ok"], [i for i in st["golden"]["items"] if not i["ok"]]
    for path in ("/api/stats.xlsx?source=study", "/api/study.xlsx", "/api/template.xlsx"):
        code, body, hdr = get(b + path)
        assert code == 200 and body[:2] == b"PK" and "filename*=UTF-8''" in hdr["Content-Disposition"]


def test_save_dialog_flow(base, monkeypatch):
    """Every export goes through the (stubbed) native Save dialog, is written to the chosen folder, the folder is
    remembered for the next dialog, and the saved file may be revealed in Explorer."""
    b, _, _ = base
    target = Path(tempfile.mkdtemp(prefix="sdt_save_")) / "תיקייה שנבחרה"
    target.mkdir()
    monkeypatch.setenv("SEMINAR_TOOL_DIALOG_STUB", str(target))
    for kind in ("stats_xlsx", "study_xlsx", "template_xlsx", "media_xlsx", "media_csv", "log_txt"):
        code, res = post(b + "/api/save", {"kind": kind})
        assert code == 200 and res["ok"] and Path(res["path"]).exists(), (kind, res)
        assert Path(res["folder"]) == target
    assert json.loads(get(b + "/api/info")[1])["last_dir"] == str(target)           # remembered
    code, res = post(b + "/api/save", {"kind": "court_xlsx"})                       # nothing built yet
    assert code == 500 and "עדיין" in res["error"]
    code, res = post(b + "/api/choose", {"what": "spss_folder"})
    assert code == 200 and res["path"] == str(target)
    monkeypatch.setenv("SEMINAR_TOOL_DIALOG_STUB", "cancel")
    code, res = post(b + "/api/save", {"kind": "study_xlsx"})
    assert code == 200 and res.get("cancelled")
    assert post(b + "/api/reveal", {"path": "C:/Windows/notepad.exe"})[0] == 400    # only files the tool saved


def test_spss_export(base):
    b, _, _ = base
    folder = Path(tempfile.mkdtemp(prefix="sdt_spss_")) / "ייצוא SPSS"
    code, res = post(b + "/api/spss_export", {"folder": str(folder)})
    assert code == 200, res
    names = set(res["files"])
    assert {"study_dataset_final.csv", "01_import_and_labels.sps", "02_analysis.sps", "output"} <= names
    sps = (folder / "01_import_and_labels.sps").read_text(encoding="utf-8")
    assert f"FILE HANDLE root /NAME='{folder.as_posix()}'." in sps
    assert "root/study_dataset_final.csv" in sps and "02_נתונים" not in sps
    assert "root/output/" in (folder / "02_analysis.sps").read_text(encoding="utf-8")
    assert (folder / "study_dataset_final.csv").read_bytes() == (paths.DATA_DIR / "study_dataset_final.csv").read_bytes()


def test_upload_flow(base):
    b, _, _ = base
    buf = io.BytesIO()
    pd.read_csv(paths.DATA_DIR / "study_dataset_final.csv").to_excel(buf, index=False)
    code, res = post(b + "/api/upload", buf.getvalue(), {**TOKEN, "X-Filename": "my%20data.xlsx"})
    assert code == 200 and res["report"]["ok"], res
    up = json.loads(get(b + "/api/stats?source=upload")[1])
    assert up["golden"] is None and up["result"]["n_main"] == 478
    assert abs(up["result"]["values"]["main.chi2"] - 1.690) < 5e-4
    code, res = post(b + "/api/upload", b"a,b\n1,2\n", {**TOKEN, "X-Filename": "bad.csv"})
    assert code == 200 and not res["report"]["ok"]
    assert json.loads(get(b + "/api/stats?source=upload")[1])["ok"] is False


def test_reimport_endpoints_offline(base):
    b, _, _ = base
    st = json.loads(get(b + "/api/court/status")[1])
    assert st["url"].startswith("https://huggingface.co/datasets/LevMuchnik/SupremeCourtOfIsrael")
    code, res = post(b + "/api/court/check", {"path": "C:/no/such/file.parquet"})
    assert code == 500 and "לא נמצא" in res["error"]
    mc = json.loads(get(b + "/api/media/cases")[1])
    assert len(mc["cases"]) == 497 and mc["min_delay"] >= 3
    assert json.loads(get(b + "/api/media/status")[1])["ok"]
    assert get(b + "/api/media/export.xlsx")[0] == 200
    code, res = post(b + "/api/media/start", {"case_ids": [c["case_id"] for c in mc["cases"][:61]]})
    assert code == 400                                                       # more than the allowed 60 cases


def test_security_checks(base):
    b, _, _ = base
    assert post(b + "/api/shutdown", {}, headers={})[0] == 403               # no token -> refused (CSRF guard)
    assert get(b + "/api/ping", {"Host": "evil.example:80"})[0] == 403       # DNS-rebinding guard
    assert post(b + "/api/open_folder", {"path": "C:/Windows"})[0] == 400


def test_heartbeat_then_tab_closed_stops_server(base, monkeypatch):
    b, srv, t = base
    monkeypatch.setattr(server, "BYE_GRACE", 1.0)
    assert post(b + "/api/heartbeat", {"client": "old-tab"})[0] == 409          # page of an earlier run
    run = json.loads(get(b + "/api/info")[1])["run_id"]
    assert post(b + "/api/heartbeat", {"client": "t1", "run": run})[0] == 200
    req = urllib.request.Request(b + "/api/bye", data=b"t1", method="POST")  # what navigator.sendBeacon sends
    urllib.request.urlopen(req, timeout=5).read()
    t.join(15)
    assert not t.is_alive(), "server should stop after the last tab is closed"
