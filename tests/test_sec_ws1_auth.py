"""
tests/test_sec_ws1_auth.py — R9 / SEC-WS-1: WebSocket auth migration contract

Coverage:
  U1: extract_ws_token parses Authorization: Bearer header → (token, False)
  U2: extract_ws_token parses ?token= query fallback → (token, True)
  U3: extract_ws_token returns (None, False) when both header and query absent
  U4: extract_ws_token header takes priority over query when both present
  U5: extract_ws_token is header-case-insensitive

  A1: header Bearer token correct → WS accepted
  A2: header Bearer token wrong → WS rejected (code 1008)
  A3: no token at all → WS rejected (code 1008)
  A4: empty-string token → WS rejected (code 1008)
  A5: query token fallback correct → WS accepted (deprecated path)
  A6: query token fallback wrong → WS rejected (code 1008)

  C1: empty admin secret → authenticate_ws returns False regardless of token
  C2: token is not logged (header path) — no token value in log records
  C3: deprecated query path emits warning without token value
  C4: rejection log does not contain token value

  D1: deprecated query path calls authenticate_ws with is_deprecated=True
      and the warning text references SEC-WS-1 migration guidance
  D2: ws_desktop_endpoint no longer declares ?token= as an OpenAPI query param
      (schema does not document it)
"""

import logging
import pytest
from unittest.mock import MagicMock

from fastapi import FastAPI, WebSocket
from fastapi.testclient import TestClient
from starlette.datastructures import Headers, QueryParams
from starlette.websockets import WebSocketDisconnect

from admin.auth import authenticate_ws, extract_ws_token

# ── Minimal test app ──────────────────────────────────────────────────────────

_test_app = FastAPI()

@_test_app.websocket("/ws/desktop")
async def _ws_desktop(ws: WebSocket):
    if not authenticate_ws(ws):
        await ws.close(code=1008)
        return
    await ws.accept()
    await ws.send_text("connected")
    await ws.close()


VALID = "super-secret-r9"


@pytest.fixture(autouse=True)
def _patch_secret(monkeypatch):
    monkeypatch.setattr("admin.auth.get_admin_secret", lambda: VALID)


@pytest.fixture()
def client():
    return TestClient(_test_app, raise_server_exceptions=False)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _mock_ws(headers: dict | None = None, query_string: str = "") -> MagicMock:
    """Build a minimal mock that mimics WebSocket.headers / .query_params."""
    ws = MagicMock()
    ws.headers = Headers(headers or {})
    ws.query_params = QueryParams(query_string)
    return ws


def _assert_rejected(client, url, **kwargs):
    """Assert that websocket_connect raises WebSocketDisconnect with code 1008."""
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect(url, **kwargs) as ws:
            ws.receive_text()
    assert exc_info.value.code == 1008


# ═══════════════════════════════════════════════════════════════════════════════
# Unit: extract_ws_token
# ═══════════════════════════════════════════════════════════════════════════════

def test_U1_bearer_header_parsed():
    ws = _mock_ws({"authorization": f"Bearer {VALID}"})
    token, deprecated = extract_ws_token(ws)
    assert token == VALID
    assert deprecated is False


def test_U2_query_fallback_parsed():
    ws = _mock_ws(query_string=f"token={VALID}")
    token, deprecated = extract_ws_token(ws)
    assert token == VALID
    assert deprecated is True


def test_U3_no_token_returns_none():
    ws = _mock_ws()
    token, deprecated = extract_ws_token(ws)
    assert token is None
    assert deprecated is False


def test_U4_header_priority_over_query():
    other = "other-token"
    ws = _mock_ws(
        headers={"authorization": f"Bearer {VALID}"},
        query_string=f"token={other}",
    )
    token, deprecated = extract_ws_token(ws)
    assert token == VALID
    assert deprecated is False


def test_U5_bearer_prefix_case_insensitive():
    ws = _mock_ws({"authorization": f"BEARER {VALID}"})
    token, deprecated = extract_ws_token(ws)
    assert token == VALID
    assert deprecated is False


# ═══════════════════════════════════════════════════════════════════════════════
# Integration: WS endpoint accept / reject
# ═══════════════════════════════════════════════════════════════════════════════

def test_A1_header_token_accepted(client):
    with client.websocket_connect(
        "/ws/desktop",
        headers={"Authorization": f"Bearer {VALID}"},
    ) as ws:
        data = ws.receive_text()
    assert data == "connected"


def test_A2_header_wrong_token_rejected(client):
    _assert_rejected(
        client,
        "/ws/desktop",
        headers={"Authorization": "Bearer wrong-token"},
    )


def test_A3_no_token_rejected(client):
    _assert_rejected(client, "/ws/desktop")


def test_A4_empty_bearer_rejected(client):
    _assert_rejected(
        client,
        "/ws/desktop",
        headers={"Authorization": "Bearer "},
    )


def test_A5_query_fallback_accepted(client):
    """Deprecated ?token= path still works (backwards compat)."""
    with client.websocket_connect(f"/ws/desktop?token={VALID}") as ws:
        data = ws.receive_text()
    assert data == "connected"


def test_A6_query_fallback_wrong_rejected(client):
    _assert_rejected(client, "/ws/desktop?token=bad-token")


# ═══════════════════════════════════════════════════════════════════════════════
# Edge: config / corner cases
# ═══════════════════════════════════════════════════════════════════════════════

def test_C1_empty_secret_always_rejects(monkeypatch):
    monkeypatch.setattr("admin.auth.get_admin_secret", lambda: "")
    ws = _mock_ws({"authorization": f"Bearer {VALID}"})
    assert authenticate_ws(ws) is False


def test_C1b_empty_secret_rejects_query_token(monkeypatch):
    monkeypatch.setattr("admin.auth.get_admin_secret", lambda: "")
    ws = _mock_ws(query_string=f"token={VALID}")
    assert authenticate_ws(ws) is False


def test_C2_header_token_not_logged(caplog):
    """Token value must never appear in any log record on the header path."""
    ws = _mock_ws({"authorization": f"Bearer {VALID}"})
    with caplog.at_level(logging.DEBUG):
        authenticate_ws(ws)
    for record in caplog.records:
        assert VALID not in record.getMessage()


def test_C3_deprecated_query_emits_warning_without_token(caplog):
    """Deprecated query path warns and does NOT log the token value."""
    ws = _mock_ws(query_string=f"token={VALID}")
    with caplog.at_level(logging.WARNING, logger="admin.auth"):
        authenticate_ws(ws)
    warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert warnings, "expected at least one warning on deprecated path"
    for r in warnings:
        assert VALID not in r.getMessage()


def test_C4_rejection_log_no_token(caplog):
    """Failed auth must not leak the (wrong) token in any log message."""
    bad_token = "leaked-secret-123"
    ws = _mock_ws({"authorization": f"Bearer {bad_token}"})
    with caplog.at_level(logging.DEBUG):
        result = authenticate_ws(ws)
    assert result is False
    for record in caplog.records:
        assert bad_token not in record.getMessage()


# ═══════════════════════════════════════════════════════════════════════════════
# Deprecation contract
# ═══════════════════════════════════════════════════════════════════════════════

def test_D1_deprecated_path_warning_mentions_sec_ws1(caplog):
    """Warning on deprecated query path must reference migration guidance."""
    ws = _mock_ws(query_string=f"token={VALID}")
    with caplog.at_level(logging.WARNING, logger="admin.auth"):
        authenticate_ws(ws)
    msgs = " ".join(r.getMessage() for r in caplog.records)
    assert "SEC-WS-1" in msgs or "Authorization" in msgs, (
        "deprecated warning must mention SEC-WS-1 or Authorization header"
    )


def test_D2_ws_endpoint_no_query_param_in_openapi():
    """The /ws/desktop endpoint must not advertise ?token= in its OpenAPI schema."""
    from admin.admin_server import app as _app
    schema = _app.openapi()
    ws_path = schema.get("paths", {}).get("/ws/desktop", {})
    # OpenAPI for WS endpoints may be absent entirely — that is also acceptable.
    # If present, it must not list a 'token' query parameter.
    for method_data in ws_path.values():
        params = method_data.get("parameters", [])
        token_params = [p for p in params if p.get("name") == "token"]
        assert not token_params, (
            "/ws/desktop OpenAPI schema must not document the deprecated ?token= parameter"
        )
