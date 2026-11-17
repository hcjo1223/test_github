"""The API end to end, in demo mode: every route, success and failure."""

from conftest import MANDATE


# ---- settings & catalog -----------------------------------------------------

def test_health_and_default_mode_is_demo_without_keys(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok" and body["mode"] == "demo"
    assert body["aihf_version"] == "2.7.2"


def test_live_mode_is_refused_without_a_data_key(client):
    response = client.put("/api/settings", json={"mode": "live"})
    assert response.status_code == 400
    assert "FINANCIAL_DATASETS_API_KEY" in response.json()["detail"]
    assert client.get("/api/settings").json()["live_ready"] is False


def test_saving_a_key_masks_it_and_unlocks_live(client, home):
    secret = "fd-test-0123456789abcdef"
    body = client.put("/api/settings/credentials",
                      json={"env_var": "FINANCIAL_DATASETS_API_KEY", "value": secret}).json()
    saved = next(c for c in body["credentials"] if c["env_var"] == "FINANCIAL_DATASETS_API_KEY")
    assert saved["set"] is True and secret not in str(body)
    assert secret in (home / ".env").read_text()
    assert client.put("/api/settings", json={"mode": "live"}).json()["mode"] == "live"


def test_only_known_credential_names_can_be_written(client):
    response = client.put("/api/settings/credentials", json={"env_var": "PATH", "value": "x"})
    assert response.status_code == 400


def test_unknown_model_is_refused(client):
    assert client.put("/api/settings", json={"model": "not-a-model"}).status_code == 400


def test_catalog_lists_analysts_and_library_strategies(client):
    body = client.get("/api/catalog").json()
    analysts = {a["name"]: a for a in body["analysts"]}
    assert analysts["pead"]["kind"] == "quant" and analysts["buffett"]["kind"] == "llm"
    assert {s["name"] for s in body["strategies"]} >= {"deep-value", "earnings-drift"}
    assert body["models"] and body["universe_presets"]


# ---- mandates ---------------------------------------------------------------

def test_a_new_workspace_has_the_example_mandate(client):
    names = [m["name"] for m in client.get("/api/mandates").json()]
    assert names == ["example-fund"]
    assert client.get("/api/mandates/example-fund").json()["benchmark"] == "SPY"


def test_create_get_delete_mandate(client, mandate):
    assert client.get("/api/mandates/test-fund").json()["capital"] == 100000
    assert client.post("/api/mandates", json=MANDATE).status_code == 409
    assert client.delete("/api/mandates/test-fund").status_code == 204
    assert client.get("/api/mandates/test-fund").status_code == 404


def test_invalid_mandates_are_rejected_with_the_field(client):
    unknown = {**MANDATE, "name": "bad", "strategies": [
        {"name": "x", "blend": {"mode": "long_only"}, "models": [{"name": "nobody"}]}]}
    response = client.post("/api/mandates", json=unknown)
    assert response.status_code == 422 and "nobody" in response.json()["detail"]

    assert client.post("/api/mandates", json={**MANDATE, "name": "../escape"}).status_code == 422
    minute = {**MANDATE, "name": "fast", "rebalance": "minute"}
    assert client.post("/api/mandates", json=minute).status_code == 422


def test_path_traversal_names_are_refused(client):
    assert client.get("/api/mandates/..%2F..%2Fetc").status_code in (404, 422)
    assert client.get("/api/backtests/..").status_code in (404, 422)


# ---- backtests --------------------------------------------------------------

def run_backtest(client, wait_job, **overrides):
    body = {"mandate": "test-fund", "universe": ["aapl", "MSFT", "NVDA"],
            "start": "2026-03-02", "end": "2026-06-30", **overrides}
    response = client.post("/api/backtests", json=body)
    assert response.status_code == 202, response.text
    return wait_job(response.json()["job_id"])


def test_backtest_runs_and_reports(client, mandate, wait_job):
    job = run_backtest(client, wait_job)
    assert job["status"] == "succeeded", job["error"]
    assert job["progress"]["done"] == job["progress"]["total"] > 50
    assert len(job["partial"]["nav"]) == job["progress"]["total"]

    backtest_id = job["result"]["backtest_id"]
    listed = client.get("/api/backtests").json()
    assert [row["id"] for row in listed] == [backtest_id]
    assert listed[0]["universe"] == ["AAPL", "MSFT", "NVDA"]

    report = client.get(f"/api/backtests/{backtest_id}").json()
    assert report["mode"] == "demo" and report["llm_model"] == "demo-heuristic"
    assert len(report["dates"]) == len(report["nav"]) == len(report["benchmark_nav"]) == len(report["drawdown"])
    assert report["nav"][0] == 100000 and max(report["drawdown"]) == 0
    assert report["metrics"]["n_cycles"] > 0
    assert min(report["drawdown"]) == -report["metrics"]["max_drawdown_pct"]
    assert {a["name"] for a in report["scorecard"]["analysts"]} == {"graham", "buffett", "pead"}

    # The mandate list now carries the score.
    row = next(m for m in client.get("/api/mandates").json() if m["name"] == "test-fund")
    assert row["last_backtest"]["id"] == backtest_id

    # Drill into the first rebalance: theses are there, the mandate copy is not.
    decided = next(s for s in report["sessions"] if s["decided"])
    detail = client.get(f"/api/backtests/{backtest_id}/sessions/{decided['session']}").json()
    signals = [sig for strategy in detail["decision"]["strategies"] for sig in strategy["signals"]]
    assert any(sig["reasoning"] and sig["reasoning"].startswith("[demo]") for sig in signals)
    assert "spec" not in detail["decision"]
    executed = next(s for s in report["sessions"] if s["executed"])
    cycle = client.get(f"/api/backtests/{backtest_id}/sessions/{executed['session']}").json()["executed"]
    assert len(cycle["orders"]) == len(cycle["fills"]) == executed["executed"]["n_orders"]

    assert client.get(f"/api/backtests/{backtest_id}/sessions/1999-01-01").status_code == 404
    assert client.delete(f"/api/backtests/{backtest_id}").status_code == 204
    assert client.get(f"/api/backtests/{backtest_id}").status_code == 404


def test_backtest_result_is_the_engines_own_format(client, mandate, wait_job, home):
    from hedge_fund.backtesting import FundBacktestResult

    backtest_id = run_backtest(client, wait_job)["result"]["backtest_id"]
    saved = home / "web-demo" / "research" / f"{backtest_id}.json"
    result = FundBacktestResult.model_validate_json(saved.read_text())
    assert result.fund == "test-fund" and result.records[0].hash == result.records[0].compute_hash()


def test_backtest_input_errors(client, mandate, wait_job):
    assert client.post("/api/backtests", json={"mandate": "nope", "universe": ["AAPL"]}).status_code == 404
    assert client.post("/api/backtests", json={"mandate": "test-fund", "universe": []}).status_code == 422
    assert client.post("/api/backtests", json={"mandate": "test-fund", "universe": ["A B"]}).status_code == 422
    backwards = {"mandate": "test-fund", "universe": ["AAPL"], "start": "2026-06-01", "end": "2026-01-01"}
    assert client.post("/api/backtests", json=backwards).status_code == 400
    assert client.get("/api/jobs/missing").status_code == 404


# ---- paper funds ------------------------------------------------------------

def tick(client, wait_job, count=1):
    response = client.post("/api/funds/alpha/tick", json={"count": count})
    assert response.status_code == 202
    return wait_job(response.json()["job_id"])


def test_paper_fund_lifecycle(client, mandate, wait_job):
    created = client.post("/api/funds", json={"name": "alpha", "mandate": "test-fund", "universe": ["AAPL", "MSFT"]})
    assert created.status_code == 201, created.text
    assert created.json()["n_sessions"] == 0 and created.json()["nav"] == 100000
    assert client.post("/api/funds", json={"name": "alpha", "mandate": "test-fund", "universe": ["AAPL"]}).status_code == 409
    assert client.get("/api/funds/alpha/scorecard").status_code == 404

    # The preview names the session a run would record; a demo fund starts in the past.
    preview = client.get("/api/funds/alpha/preview").json()
    assert preview["due"] and preview["rebalance"] is True and preview["pending"] is None

    first = tick(client, wait_job)
    assert first["status"] == "succeeded", first["error"]
    assert first["result"]["sessions"] == [preview["due"]]

    detail = client.get("/api/funds/alpha").json()
    assert detail["n_sessions"] == 1 and detail["pending"] is not None, "the first session decides"
    assert detail["positions"] == [], "and nothing trades until the next close"

    # The pending decision is what the next session executes.
    preview = client.get("/api/funds/alpha/preview").json()
    assert preview["pending"]["final_weights"] == detail["pending"]["final_weights"]
    more = tick(client, wait_job, count=6)
    assert more["status"] == "succeeded", more["error"]
    assert len(more["result"]["sessions"]) == 6 and more["result"]["sessions"][0] == preview["due"]

    detail = client.get("/api/funds/alpha").json()
    assert detail["n_sessions"] == 7 and len(detail["nav_series"]) == 7
    assert detail["dates"] == sorted(detail["dates"])
    assert detail["positions"], "the first decision was executed"
    assert abs(sum(p["value"] for p in detail["positions"]) + detail["cash"] - detail["nav"]) < 0.01
    assert any(event["kind"] == "tick" for event in detail["events"])

    session = client.get(f"/api/funds/alpha/sessions/{detail['dates'][1]}").json()
    assert session["executed"]["orders"], "session two filled the first decision"
    assert client.get("/api/funds/alpha/scorecard").json()["fund"] == "test-fund", "records carry the mandate name"
    assert client.get("/api/funds").json()[0]["n_sessions"] == 7


def test_kill_switch_blocks_and_resume_restores(client, mandate, wait_job):
    client.post("/api/funds", json={"name": "alpha", "mandate": "test-fund", "universe": ["AAPL"]})
    assert client.post("/api/funds/alpha/halt", json={"reason": " "}).status_code == 400
    assert client.post("/api/funds/alpha/halt", json={"reason": "점검"}).json()["halted"] == "점검"
    assert "점검" in client.get("/api/funds/alpha/preview").json()["reason"]

    job = tick(client, wait_job)
    assert job["status"] == "failed" and "halted" in job["error"]
    assert client.get("/api/funds/alpha").json()["n_sessions"] == 0

    assert client.post("/api/funds/alpha/resume").json()["halted"] is None
    assert tick(client, wait_job)["status"] == "succeeded"


def test_catching_up_stops_when_nothing_more_is_due(client, mandate, wait_job):
    client.post("/api/funds", json={"name": "alpha", "mandate": "test-fund", "universe": ["AAPL"]})
    ran = 0
    for _ in range(4):  # a demo fund starts about 60 sessions back
        job = tick(client, wait_job, count=30)
        if job["status"] == "failed":
            break
        ran += len(job["result"]["sessions"])
        if job["result"]["stopped_reason"]:
            break
    assert 50 <= ran <= 70
    again = tick(client, wait_job)
    assert again["status"] == "failed" and "no completed" in again["error"]
    assert client.get("/api/funds/alpha/preview").json()["due"] is None


def test_unknown_fund_is_404(client):
    assert client.get("/api/funds/ghost").status_code == 404
    assert client.post("/api/funds/ghost/tick", json={"count": 1}).status_code == 404
    assert client.post("/api/funds", json={"name": "x", "mandate": "ghost", "universe": ["AAPL"]}).status_code == 404


def test_demo_and_live_workspaces_are_separate(client, mandate, home):
    assert (home / "web-demo" / "mandates" / "test-fund.yaml").is_file()
    assert not (home / "mandates" / "test-fund.yaml").exists()


def test_first_requests_can_arrive_together(client):
    """A page fires several requests at once into a home that does not exist yet."""
    from concurrent.futures import ThreadPoolExecutor

    paths = ["/api/mandates", "/api/backtests", "/api/funds"] * 8
    with ThreadPoolExecutor(max_workers=12) as pool:
        statuses = list(pool.map(lambda path: client.get(path).status_code, paths))
    assert set(statuses) == {200}
