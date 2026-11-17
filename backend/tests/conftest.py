"""Every test runs in demo mode against a throwaway home directory."""

import time

import pytest
from fastapi.testclient import TestClient

from hedge_fund.llm import PROVIDER_ENV_VARS
from hedge_fund.tui import keys

CREDENTIAL_VARS = ["FINANCIAL_DATASETS_API_KEY", "X402_WALLET_PRIVATE_KEY", *PROVIDER_ENV_VARS.values()]


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("AIHF_WEB_HOME", str(tmp_path))
    monkeypatch.setattr(keys, "ENV_PATH", tmp_path / ".env")
    for name in CREDENTIAL_VARS:
        monkeypatch.delenv(name, raising=False)
    return tmp_path


@pytest.fixture
def client(home):
    from app.main import create_app

    return TestClient(create_app())


@pytest.fixture
def wait_job(client):
    def wait(job_id: str, timeout: float = 120.0) -> dict:
        deadline = time.time() + timeout
        while time.time() < deadline:
            job = client.get(f"/api/jobs/{job_id}").json()
            if job["status"] in ("succeeded", "failed"):
                return job
            time.sleep(0.05)
        raise AssertionError(f"job {job_id} did not finish in {timeout}s")

    return wait


MANDATE = {
    "name": "test-fund",
    "strategies": [
        {"name": "deep-value", "blend": {"mode": "long_only"}, "weight": 0.6,
         "models": [{"name": "graham", "weight": 2.0}, {"name": "buffett"}]},
        {"name": "earnings-drift", "blend": {"mode": "long_short"}, "weight": 0.4,
         "models": [{"name": "pead"}]},
    ],
    "risk": {"max_position_pct": 0.25, "max_gross_exposure": 1.0},
    "capital": 100000,
    "rebalance": "weekly",
    "benchmark": "SPY",
}


@pytest.fixture
def mandate(client):
    response = client.post("/api/mandates", json=MANDATE)
    assert response.status_code == 201, response.text
    return MANDATE
