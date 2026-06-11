"""
管理面板鉴权
独立模块，避免 admin_server ↔ routers 的循环导入。
"""

import logging
import os

from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from core.config_loader import get_config

security = HTTPBearer(auto_error=False)

_logger = logging.getLogger(__name__)


def get_admin_secret() -> str:
    """获取管理面板 secret：env YEXUAN_ADMIN_SECRET 优先，否则读 config.admin.secret_key"""
    env_val = os.environ.get("YEXUAN_ADMIN_SECRET", "").strip()
    if env_val:
        return env_val
    return get_config().get("admin", {}).get("secret_key", "")


def verify_token(
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """简单的 Bearer Token 校验"""
    secret = get_admin_secret()
    if not secret:
        raise HTTPException(status_code=403, detail="admin secret not configured")
    if not credentials or credentials.credentials != secret:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return True


# ── WebSocket auth helpers ─────────────────────────────────────────────────────

def extract_ws_token(websocket) -> tuple[str | None, bool]:
    """Extract auth token from a WebSocket upgrade request.

    Returns (token_or_None, is_deprecated_query_fallback).

    Primary path  : Authorization: Bearer <token> header.
    Deprecated    : ?token= query param — still accepted for old clients but
                    logs a warning and must be removed from new clients.
    """
    auth = websocket.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip(), False

    # Query param fallback — deprecated, kept only for old client compat.
    token = websocket.query_params.get("token", "")
    if token:
        return token, True

    return None, False


def authenticate_ws(websocket) -> bool:
    """Authenticate a WebSocket upgrade. Returns True if authorized.

    Reads token via extract_ws_token(): Authorization header (primary) or
    ?token= query (deprecated fallback).  Token value is never logged.
    """
    secret = get_admin_secret()
    if not secret:
        return False
    token, is_deprecated = extract_ws_token(websocket)
    if token is None:
        return False
    if is_deprecated:
        _logger.warning(
            "[ws_auth] query token fallback used — client should migrate "
            "to Authorization: Bearer header (SEC-WS-1)"
        )
    return token == secret
