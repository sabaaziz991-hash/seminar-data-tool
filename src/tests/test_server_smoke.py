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


def test_text_measures_and_exports(base):
    b, _, _ = base
    tm = json.loads(get(b + "/api/text/measures")[1])
    assert tm["all_ok"] and tm["n_cases"] == 497, tm["rows"]
    assert tm["mentions"]["checked_now"] == 412 and tm["attempt"]["now"] == 31
    for path in ("/api/study.xlsx", "/api/text/result.xlsx"):
        code, body, hdr = get(b + path)
        assert code == 200 and body[:2] == b"PK" and "filename*=UTF-8''" in hdr["Content-Disposition"]
    code, body, _ = get(b + "/api/text/result.csv")
    assert code == 200 and body.startswith(b"\xef\xbb\xbf") and body.count(b"\n") == 498
    for gone in ("/api/stats", "/api/stats.xlsx", "/api/template.xlsx", "/api/upload/status"):
        assert get(b + gone)[0] == 404                                      # the statistics screens were removed


def test_save_dialog_flow(base, monkeypatch):
    """Every export goes through the (stubbed) native Save dialog, is written to the chosen folder, the folder is
    remembered for the next dialog, and the saved file may be revealed in Explorer."""
    b, _, _ = base
    target = Path(tempfile.mkdtemp(prefix="sdt_save_")) / "תיקייה שנבחרה"
    target.mkdir()
    monkeypatch.setenv("SEMINAR_TOOL_DIALOG_STUB", str(target))
    for kind in ("study_xlsx", "text_xlsx", "text_csv", "media_xlsx", "media_csv", "log_txt"):
        code, res = post(b + "/api/save", {"kind": kind})
        assert code == 200 and res["ok"] and Path(res["path"]).exists(), (kind, res)
        assert Path(res["folder"]) == target
    assert json.loads(get(b + "/api/info")[1])["last_dir"] == str(target)           # remembered
    code, res = post(b + "/api/save", {"kind": "court_xlsx"})                       # nothing built yet
    assert code == 500 and "עדיין" in res["error"]
    code, res = post(b + "/api/choose", {"what": "hf_folder"})
    assert code == 200 and res["path"] == str(target)
    monkeypatch.setenv("SEMINAR_TOOL_DIALOG_STUB", "cancel")
    code, res = post(b + "/api/save", {"kind": "study_xlsx"})
    assert code == 200 and res.get("cancelled")
    assert post(b + "/api/reveal", {"path": "C:/Windows/notepad.exe"})[0] == 400    # only files the tool saved


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
