import json

import pytest

from hub import fakes, http, webhook
from hub.auth import TokenClient
from hub.mapping import ValidationError, map_task
from hub.sync import run


@pytest.fixture
def world_server():
    servers = []

    def make(**kw):
        w = fakes.World(kw.pop("tasks", fakes.make_tasks()), **kw)
        s, url = fakes.start(w)
        servers.append(s)
        return w, url
    yield make
    for s in servers:
        s.shutdown()


def _run(url, tmp, tok=None, **kw):
    tok = tok or TokenClient(url + "/token", "id", "secret")
    return run(url, url, tok, tok, str(tmp / "state.json"), str(tmp / "dead.jsonl"), sleep=lambda s: None, **kw)


def test_token_is_cached_and_refreshed_after_expiry(world_server):
    w, url = world_server()
    now = [0.0]
    t = TokenClient(url + "/token", "id", "secret", clock=lambda: now[0])
    assert t.get() == t.get() and t.fetches == 1
    now[0] = 1000
    t.get()
    assert t.fetches == 2


def test_retries_a_503_and_then_succeeds(world_server, tmp_path):
    w, url = world_server(fail_first=2, tasks=fakes.make_tasks(5, 0))
    out = _run(url, tmp_path)
    assert out["created"] == 5 and w.target_calls == 5 + 2


def test_429_waits_for_retry_after(world_server):
    w, url = world_server(throttle_first=1)
    waits = []
    tok = TokenClient(url + "/token", "id", "secret")
    http.call("POST", url + "/cost-lines", tok, body={"external_id": "X", "amount_ore": 1}, sleep=waits.append)
    assert waits == [0.01]


def test_401_triggers_one_token_refresh_then_works(world_server):
    w, url = world_server()
    tok = TokenClient(url + "/token", "id", "secret")
    tok.get()
    w.revoke_all_next = True
    http.call("POST", url + "/cost-lines", tok, body={"external_id": "Y", "amount_ore": 1})
    assert tok.fetches == 2


def test_bad_records_go_to_dead_letter_with_a_reason(world_server, tmp_path):
    w, url = world_server()
    out = _run(url, tmp_path)
    reasons = [json.loads(l)["reason"] for l in open(tmp_path / "dead.jsonl")]
    assert out["dead_letter"] == 6 and out["created"] == 114
    assert any("unknown wbs" in r for r in reasons) and any("unsupported currency" in r for r in reasons)
    assert any("bad date" in r for r in reasons) and any("missing wbs" in r for r in reasons)


def test_rerun_creates_no_duplicates_and_makes_no_calls(world_server, tmp_path):
    w, url = world_server(tasks=fakes.make_tasks(60, 0))
    tok = TokenClient(url + "/token", "id", "secret")
    _run(url, tmp_path, tok)
    calls = w.target_calls
    second = _run(url, tmp_path, tok)
    assert second["unchanged"] == 60 and second["created"] == 0 and w.target_calls == calls
    assert len(w.lines) == 60


def test_changed_task_is_updated_not_duplicated(world_server, tmp_path):
    w, url = world_server(tasks=fakes.make_tasks(10, 0))
    tok = TokenClient(url + "/token", "id", "secret")
    _run(url, tmp_path, tok)
    w.tasks[3]["amount_ore"] += 5000
    out = _run(url, tmp_path, tok)
    assert out["updated"] == 1 and len(w.lines) == 10 and out["reconciled"]


def test_reconciliation_totals_match(world_server, tmp_path):
    w, url = world_server()
    out = _run(url, tmp_path)
    assert out["reconciled"] and out["source_total_ore"] == out["target_total_ore"] > 0


def test_pages_are_all_fetched(world_server, tmp_path):
    w, url = world_server(tasks=fakes.make_tasks(130, 0))
    assert _run(url, tmp_path)["created"] == 130


def test_mapping_rejects_bad_input():
    with pytest.raises(ValidationError):
        map_task({"id": "1", "wbs": "A-100", "amount_ore": 1.5, "currency": "DKK", "booked_on": "2026-10-01"})


def test_webhook_signature_checks():
    body, ts = b'{"event":"task.updated"}', 1_800_000_000
    sig = webhook.sign("s3cret", body, ts)
    assert webhook.verify("s3cret", body, ts, sig, now=ts + 10)
    assert not webhook.verify("s3cret", body + b" ", ts, sig, now=ts + 10)
    assert not webhook.verify("s3cret", body, ts, sig, now=ts + 4000)
    assert not webhook.verify("other", body, ts, sig, now=ts + 10)
