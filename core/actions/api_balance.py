"""Read-only API balance adapters. They never submit payment requests."""
from __future__ import annotations
import logging
logger = logging.getLogger(__name__)

def _extract_balance(payload: object) -> float | None:
    if not isinstance(payload, dict): return None
    for key in ("balance", "available_balance", "remaining", "credit"):
        try: return float(payload[key])
        except (KeyError, TypeError, ValueError): pass
    data = payload.get("data")
    return _extract_balance(data) if isinstance(data, dict) else None

async def fetch_balance(provider: dict) -> float | None:
    base_url = str(provider.get("base_url") or "").rstrip("/")
    if not base_url: return None
    try:
        import aiohttp
        headers = {"Authorization": f"Bearer {provider['api_key']}"} if provider.get("api_key") else {}
        timeout = aiohttp.ClientTimeout(total=float(provider.get("timeout_s", 10)))
        endpoint = str(provider.get("balance_path") or "/balance")
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(base_url + endpoint, headers=headers) as response:
                if response.status >= 400: return None
                return _extract_balance(await response.json())
    except Exception as exc:
        logger.warning("[spend] balance lookup failed provider=%s: %s", provider.get("name"), exc)
        return None
