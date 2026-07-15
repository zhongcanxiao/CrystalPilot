"""Characterization tests for the EIC client's OAuth/auth path (HANDOFF item D).

``tests/test_eic_client_characterization.py`` pins the non-authenticated wire
path. The HANDOFF gates decomposition of ``core/eic/eic_client.py`` on also
characterizing the OAuth path — these tests are that second half. They pin, with
no network and no real credentials:

- ``EICClientAuthComm`` construction (pure attribute storage, no side effects),
- the bearer-header non-auth branch vs the OAuth2Session auth branch,
- lazy login via ``fetch_token`` and the relogin-on-``TokenExpiredError`` retry,
- ``should_verify`` (verify flag + localhost/load-balancer/proxy carve-outs),
- HTTP status → typed exception mapping (400/401/404/other),
- credentialed-token construction routing ``EICClient`` through the auth branch
  (inner_token/ipts_number stamping included),
- beamline → web-server URL derivation and the ``EIC_ENV`` prod/dev switch.

Like the sibling file, network seams are faked by monkeypatching attributes on
the shared ``requests`` / ``requests_oauthlib`` module objects, so the mocks
survive any future split of eic_client into submodules. A split must keep these
green.
"""

from __future__ import annotations

import base64
import os
import pickle
import zlib
from typing import Any

import oauthlib.oauth2
import pytest
import requests as _requests
from cryptography.fernet import Fernet
from oauthlib.oauth2.rfc6749.errors import InvalidClientError

from exphub.core.eic import eic_client as eic_mod
from exphub.core.eic.eic_client import (
    BadRequestError,
    EICClient,
    EICClientAuthComm,
    EICClientError,
    InvalidClientCredentialsError,
    NotFoundError,
    UnauthorizedError,
)

# Same hard-coded outer Fernet key as _deserialize_outer_data (and the sibling
# characterization file) — used to mint valid tokens with a known payload.
_OUTER_KEY = b"R-2xj4mOi7UxjC7fR119FD5aw_GCfN4IZYlGn41XUxU="

_BASE_URL = "https://fake-eic.test:8443"
_PING_FED_URL = "https://fake-idp.test/as/token.oauth2"


def _make_eic_token(outer_data: dict) -> str:
    """Inverse of _deserialize_outer_data: Fernet(base64(zlib(pickle(data))))."""
    plaintext = base64.b64encode(zlib.compress(pickle.dumps(outer_data)))
    return Fernet(_OUTER_KEY).encrypt(plaintext).decode("utf-8")


def _plain_response(status: int) -> _requests.models.Response:
    """Build a bare ``requests.Response`` with the given status code."""
    resp = _requests.models.Response()
    resp.status_code = status
    resp.reason = "canned"
    resp.url = _BASE_URL + "/whatever"
    resp._content = b"{}"
    return resp


def _eic_response(payload: dict, status: int = 200) -> _requests.models.Response:
    """Build a real ``requests.Response`` in EIC's ``response_json``/base64 format."""
    import json as _json

    b64 = base64.b64encode(_json.dumps(payload).encode("utf-8")).decode("utf-8")
    body = _json.dumps(f"response_json {b64}")
    resp = _requests.models.Response()
    resp.status_code = status
    resp.reason = "OK"
    resp._content = body.encode("utf-8")
    return resp


class _OAuthRecorder:
    """Shared state across fake OAuth2Session instances (login builds a new one)."""

    def __init__(self) -> None:
        self.constructed: list[dict[str, Any]] = []
        self.fetch_token_calls: list[dict[str, Any]] = []
        self.calls: list[dict[str, Any]] = []
        self.payload: dict = {"success": True}
        self.fetch_token_error: BaseException | None = None
        self.expire_first_call: bool = False
        self._expired_raised: bool = False


class _FakeOAuthSession:
    """Stands in for ``requests_oauthlib.OAuth2Session``; records every call."""

    def __init__(self, rec: _OAuthRecorder, **kwargs: Any) -> None:
        self._rec = rec
        rec.constructed.append(kwargs)

    def fetch_token(self, url: str, **kwargs: Any) -> dict:
        self._rec.fetch_token_calls.append({"url": url, **kwargs})
        if self._rec.fetch_token_error is not None:
            raise self._rec.fetch_token_error
        return {"access_token": "fake-access", "token_type": "Bearer"}

    def _verb(self, method: str, url: str, **kwargs: Any) -> _requests.models.Response:
        self._rec.calls.append({"method": method, "url": url, "json": kwargs.get("json")})
        if self._rec.expire_first_call and not self._rec._expired_raised:
            self._rec._expired_raised = True
            raise oauthlib.oauth2.TokenExpiredError()
        return _eic_response(self._rec.payload)

    def get(self, url: str, **kwargs: Any) -> _requests.models.Response:
        return self._verb("get", url, **kwargs)

    def put(self, url: str, **kwargs: Any) -> _requests.models.Response:
        return self._verb("put", url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> _requests.models.Response:
        return self._verb("post", url, **kwargs)

    def delete(self, url: str, **kwargs: Any) -> _requests.models.Response:
        return self._verb("delete", url, **kwargs)


@pytest.fixture
def oauth_rec(monkeypatch: pytest.MonkeyPatch) -> _OAuthRecorder:
    """Fake ``requests_oauthlib.OAuth2Session`` in the eic_client module; force dev env."""
    monkeypatch.setenv("EIC_ENV", "dev")
    rec = _OAuthRecorder()

    def _factory(**kwargs: Any) -> _FakeOAuthSession:
        return _FakeOAuthSession(rec, **kwargs)

    monkeypatch.setattr(eic_mod.requests_oauthlib, "OAuth2Session", _factory)
    return rec


def _auth_comm(**overrides: Any) -> EICClientAuthComm:
    kwargs: dict[str, Any] = {
        "eic_base_url": _BASE_URL,
        "ping_fed_url": _PING_FED_URL,
        "client_id": "cid",
        "client_secret": "sec",
        "scopes": ["EIC:write"],
        "verify": True,
    }
    kwargs.update(overrides)
    return EICClientAuthComm(**kwargs)


# --------------------------------------------------------------------- construction / token plumbing


def test_authcomm_construction_has_no_side_effects() -> None:
    # Pure attribute storage: no network, no lazy login at construction time.
    comm = _auth_comm()
    assert comm._token is None
    assert comm._oauth_client is None
    assert comm.eic_base_url() == _BASE_URL
    assert comm.ping_fed_url() == _PING_FED_URL


def test_authcomm_token_storage_defaults() -> None:
    comm = _auth_comm()
    comm.set_token({"access_token": "t"})
    assert comm.get_token() == {"access_token": "t"}


def test_authcomm_token_getter_setter_delegation() -> None:
    stored: list[Any] = []
    comm = _auth_comm(token_getter=lambda: "from-getter", token_setter=stored.append)
    comm.set_token("tok")
    assert stored == ["tok"]
    assert comm.get_token() == "from-getter"


# --------------------------------------------------------------------- should_verify


def test_should_verify_true_for_normal_url() -> None:
    assert _auth_comm(verify=True).should_verify() is True


@pytest.mark.parametrize("host", ["localhost", "load-balancer", "proxy"])
def test_should_verify_false_for_local_urls(host: str, monkeypatch: pytest.MonkeyPatch) -> None:
    # Local/dev deployments skip cert verification AND flip the oauthlib env switch.
    monkeypatch.delenv("OAUTHLIB_INSECURE_TRANSPORT", raising=False)
    comm = _auth_comm(eic_base_url=f"https://{host}:8443", verify=True)
    assert comm.should_verify() is False
    assert os.environ.get("OAUTHLIB_INSECURE_TRANSPORT") == "1"


def test_should_verify_false_when_disabled() -> None:
    assert _auth_comm(verify=False).should_verify() is False


# --------------------------------------------------------------------- non-auth branch (no client_id)


def test_non_auth_branch_sends_bearer_header(monkeypatch: pytest.MonkeyPatch) -> None:
    # Without a client_id the auth comm falls back to plain requests with a
    # bearer header (when an api_token is present) and verify=False.
    seen: list[dict[str, Any]] = []

    def _fake_get(url: str, **kwargs: Any) -> _requests.models.Response:
        seen.append({"url": url, **kwargs})
        return _eic_response({"success": True})

    monkeypatch.setattr(eic_mod.requests, "get", _fake_get)
    comm = _auth_comm(client_id=None, client_secret=None, api_token="api-tok")
    comm.get("ping")

    assert len(seen) == 1
    assert seen[0]["url"] == f"{_BASE_URL}/ping"
    assert seen[0]["headers"] == {"Authorization": "Bearer api-tok"}
    assert seen[0]["verify"] is False


@pytest.mark.parametrize(
    ("status", "exc"),
    [(400, BadRequestError), (401, UnauthorizedError), (404, NotFoundError), (500, EICClientError)],
)
def test_http_error_mapping(status: int, exc: type, monkeypatch: pytest.MonkeyPatch) -> None:
    # HTTP error statuses map to the typed EICClientError hierarchy.
    monkeypatch.setattr(eic_mod.requests, "get", lambda url, **kw: _plain_response(status))
    comm = _auth_comm(client_id=None, client_secret=None)
    with pytest.raises(exc):
        comm.get("ping")


# --------------------------------------------------------------------- auth branch (OAuth client-credentials)


def test_auth_branch_logs_in_lazily_and_uses_oauth_session(oauth_rec: _OAuthRecorder) -> None:
    comm = _auth_comm()
    response = comm.post("eic/actions", {"k": "v"})

    # One lazy client-credentials login against the ping-fed endpoint.
    assert len(oauth_rec.fetch_token_calls) == 1
    fetch = oauth_rec.fetch_token_calls[0]
    assert fetch["url"] == _PING_FED_URL
    assert fetch["client_id"] == "cid"
    assert fetch["client_secret"] == "sec"
    assert fetch["include_client_id"] is True

    # The OAuth2Session was built around a BackendApplicationClient with our id.
    assert len(oauth_rec.constructed) == 1
    assert oauth_rec.constructed[0]["client"].client_id == "cid"

    # The actual request went through the OAuth session, not plain requests.
    assert oauth_rec.calls == [{"method": "post", "url": f"{_BASE_URL}/eic/actions", "json": {"k": "v"}}]
    assert response.status_code == 200


def test_auth_branch_relogins_on_expired_token(oauth_rec: _OAuthRecorder) -> None:
    # First verb call raises TokenExpiredError -> login() again -> retry succeeds.
    oauth_rec.expire_first_call = True
    comm = _auth_comm()
    response = comm.get("status")

    assert len(oauth_rec.fetch_token_calls) == 2  # initial lazy login + relogin
    assert [c["method"] for c in oauth_rec.calls] == ["get", "get"]
    assert response.status_code == 200


def test_auth_branch_maps_invalid_client_credentials(oauth_rec: _OAuthRecorder) -> None:
    oauth_rec.fetch_token_error = InvalidClientError()
    comm = _auth_comm()
    with pytest.raises(InvalidClientCredentialsError):
        comm.get("status")


# --------------------------------------------------------------------- EICClient auth-path integration


def test_client_with_credentialed_token_uses_auth_path(oauth_rec: _OAuthRecorder) -> None:
    # A token whose payload carries client credentials routes EICClient through
    # the OAuth branch; do_auth stamps inner_token + ipts_number onto the body.
    token = _make_eic_token(
        {
            "client_id": "cid",
            "client_secret": "sec",
            "url_base": _BASE_URL,
            "inner_token": "inner-tok",
            "beamline": "bl12",
        }
    )
    oauth_rec.payload = {"success": True, "scan_id": 7, "eic_response_message": "queued"}
    client = EICClient(token, ipts_number="IPTS-1")

    assert client.client_id == "cid"
    assert client.client_secret == "sec"
    assert client.inner_token == "inner-tok"
    assert client.beamline == "bl12"
    assert client.url_base == _BASE_URL  # payload url_base wins over derivation

    success, scan_id, _ = client.submit_table_scan(
        parms={"run_mode": 0, "headers": ["Title"], "rows": [["r1"]]},
        desc="auth-path submission",
    )
    assert success is True
    assert scan_id == 7

    assert len(oauth_rec.calls) == 1
    call = oauth_rec.calls[0]
    assert call["method"] == "post"
    assert call["url"] == f"{_BASE_URL}/eic/actions"
    body = call["json"]
    assert body["command"] == "ControlScenario"
    assert body["parameters"]["control_scenario"] == "TableScan"
    assert body["inner_token"] == "inner-tok"
    assert body["ipts_number"] == "IPTS-1"


# --------------------------------------------------------------------- URL derivation / environment


def test_url_base_derivation_by_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EIC_ENV", "dev")
    client = EICClient(_make_eic_token({}), beamline="bl12")

    # Dev environment: fixed local url_base regardless of beamline.
    assert client.url_base == "http://127.0.0.1:5000"

    # Production branch (exercised directly): beamline table -> https://<dassrv>:<port>.
    client.is_production_environment = True
    assert client._get_url_base() == "https://bl12-dassrv1.sns.gov:8443"


def test_beamline_web_server_mapping(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EIC_ENV", "dev")
    client = EICClient(_make_eic_token({}), beamline="bl12")

    # Instrument names and beamline codes normalize to the same SNS web server.
    assert client._get_beamline_and_web_server("TOPAZ") == ("bl12", "bl12-dassrv1.sns.gov")
    assert client._get_beamline_and_web_server("bl-12") == ("bl12", "bl12-dassrv1.sns.gov")
    # Unknown names yield no web server (caller falls back to a placeholder URL).
    _, web_server = client._get_beamline_and_web_server("not-a-beamline")
    assert web_server is None


def test_is_production_environment_env_switch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EIC_ENV", "dev")
    assert EICClient._is_production_environment() is False
    monkeypatch.setenv("EIC_ENV", "prod")
    assert EICClient._is_production_environment() is True
    monkeypatch.delenv("EIC_ENV")
    assert EICClient._is_production_environment() is True  # unset presumes production
