"""Owner login for a deployed instance.

One password, set by the operator in AIHF_PASSWORD (a platform secret, never
committed). A correct login sets a signed, HTTP-only cookie. The signing key
is derived from the password, so changing the password signs everyone out.

With no password set, login is off: that is the local development default.
AIHF_REQUIRE_AUTH=1 (set in the Docker image) makes a missing password a
startup error instead, so a deployment cannot go live unprotected by mistake.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import time

COOKIE = "aihf_session"
TTL_SECONDS = 14 * 24 * 3600
MIN_PASSWORD_LENGTH = 12
FAILED_LOGIN_DELAY = 0.5  # seconds; slows down password guessing


class Auth:
    def __init__(self, password: str | None, secure_cookie: bool) -> None:
        self._password = password or None
        self.secure_cookie = secure_cookie
        self._key = (
            hashlib.sha256(f"aihf-session|{password}".encode()).digest() if password else b""
        )

    @property
    def required(self) -> bool:
        return self._password is not None

    def check_password(self, given: str) -> bool:
        return self.required and hmac.compare_digest(given.encode(), self._password.encode())

    def issue(self) -> str:
        body = f"v1.{int(time.time()) + TTL_SECONDS}"
        return f"{body}.{self._sign(body)}"

    def valid(self, token: str | None) -> bool:
        if not self.required:
            return True
        if not token:
            return False
        try:
            version, expires, signature = token.split(".")
            if version != "v1" or int(expires) < time.time():
                return False
        except ValueError:
            return False
        return hmac.compare_digest(signature, self._sign(f"v1.{expires}"))

    def _sign(self, body: str) -> str:
        return hmac.new(self._key, body.encode(), hashlib.sha256).hexdigest()


def from_env() -> Auth:
    password = os.environ.get("AIHF_PASSWORD") or None
    if os.environ.get("AIHF_REQUIRE_AUTH") == "1" and password is None:
        raise RuntimeError("AIHF_REQUIRE_AUTH=1 이지만 AIHF_PASSWORD가 설정되지 않았습니다.")
    if password is not None and len(password) < MIN_PASSWORD_LENGTH:
        raise RuntimeError(f"AIHF_PASSWORD는 {MIN_PASSWORD_LENGTH}자 이상이어야 합니다.")
    return Auth(password, secure_cookie=os.environ.get("AIHF_COOKIE_SECURE") == "1")
