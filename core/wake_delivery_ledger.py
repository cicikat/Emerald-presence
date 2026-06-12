"""Persistent at-most-once delivery ledger for desktop wake Path A."""

import json

from core.safe_write import safe_write_json
from core.sandbox import get_paths


class WakeDeliveryLedgerError(RuntimeError):
    pass


def load_delivered(uid: str) -> dict[str, float]:
    path = get_paths().wake_delivery_ledger(uid)
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        delivered = raw.get("wake_delivered", {})
        if not isinstance(delivered, dict):
            raise ValueError("wake_delivered must be an object")
        return {str(turn_id): float(ts) for turn_id, ts in delivered.items()}
    except Exception as exc:
        raise WakeDeliveryLedgerError("failed to read wake delivery ledger") from exc


def mark_delivered(uid: str, delivered: dict[str, float], turn_id: str, ts: float) -> None:
    delivered[str(turn_id)] = float(ts)
    if not safe_write_json(
        get_paths().wake_delivery_ledger(uid),
        {"wake_delivered": delivered},
    ):
        raise WakeDeliveryLedgerError("failed to persist wake delivery ledger")
