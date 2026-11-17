"""Owner login: off locally, mandatory when a password is set."""

import pytest
from fastapi.testclient import TestClient

from app.auth import COOKIE, Auth, from_env

PASSWORD = "correct horse battery"


@pytest.fixture
def secured(home, monkeypatch):
    monkeypatch.setenv("AIHF_PASSWORD", PASSWORD)
    from app.main import create_app

    return TestClient(create_app())


@pytest.fixture(autouse=True)
def no_ambient_password(monkeypatch):
    monkeypatch.delenv("AIHF_PASSWORD", raising=False)
    monkeypatch.delenv("AIHF_REQUIRE_AUTH", raising=False)


def test_login_is_off_without_a_password(home):
    from app.main import create_app

    client = TestClient(create_app())
    assert client.get("/api/mandates").status_code == 200
    assert client.get("/api/auth/status").json() == {"required": False, "authenticated": True}


def test_everything_under_api_needs_a_session(secured):
    assert secured.get("/api/mandates").status_code == 401
    assert secured.get("/api/settings").status_code == 401
    assert secured.post("/api/backtests", json={}).status_code == 401
    assert secured.get("/api/health").status_code == 200, "health stays open for the platform"
    assert secured.get("/api/auth/status").json() == {"required": True, "authenticated": False}


def test_a_wrong_password_is_refused(secured):
    response = secured.post("/api/auth/login", json={"password": "not the password"})
    assert response.status_code == 401
    assert COOKIE not in response.cookies


def test_the_right_password_opens_the_api_until_logout(secured):
    response = secured.post("/api/auth/login", json={"password": PASSWORD})
    assert response.status_code == 200 and COOKIE in response.cookies
    assert secured.get("/api/mandates").status_code == 200
    assert secured.get("/api/auth/status").json()["authenticated"] is True

    secured.post("/api/auth/logout")
    secured.cookies.clear()
    assert secured.get("/api/mandates").status_code == 401


def test_a_forged_or_tampered_cookie_is_refused(secured):
    for forged in ("v1.9999999999.deadbeef", "v1.1.x", "garbage", "v2.9999999999.abc"):
        secured.cookies.set(COOKIE, forged)
        assert secured.get("/api/mandates").status_code == 401, forged


def test_changing_the_password_signs_everyone_out(home, monkeypatch):
    from app.main import create_app

    monkeypatch.setenv("AIHF_PASSWORD", PASSWORD)
    first = TestClient(create_app())
    first.post("/api/auth/login", json={"password": PASSWORD})
    token = first.cookies.get(COOKIE)

    monkeypatch.setenv("AIHF_PASSWORD", "a brand new long password")
    second = TestClient(create_app())
    second.cookies.set(COOKIE, token)
    assert second.get("/api/mandates").status_code == 401


def test_require_auth_without_a_password_refuses_to_start(monkeypatch):
    monkeypatch.setenv("AIHF_REQUIRE_AUTH", "1")
    with pytest.raises(RuntimeError, match="AIHF_PASSWORD"):
        from_env()


def test_a_short_password_is_refused(monkeypatch):
    monkeypatch.setenv("AIHF_PASSWORD", "short")
    with pytest.raises(RuntimeError, match="12자"):
        from_env()


def test_the_cookie_is_marked_secure_when_configured(monkeypatch):
    monkeypatch.setenv("AIHF_PASSWORD", PASSWORD)
    monkeypatch.setenv("AIHF_COOKIE_SECURE", "1")
    assert from_env().secure_cookie is True
    assert Auth(None, secure_cookie=False).required is False
