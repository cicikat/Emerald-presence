"""Read-only query support for persisted reality-side stimulus audit records."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from core.sandbox import get_paths

logger = logging.getLogger(__name__)


def query(*, source: str = "", gate_result: str = "", offset: int = 0, limit: int = 100) -> tuple[list[dict], int]:
    """Return newest-first stimulus audit records with optional exact filters.

    Audit data is forensic and may contain malformed historical lines. Those lines
    are skipped fail-open so observability never interrupts runtime behaviour.
    """
    entries: list[dict] = []
    try:
        root = get_paths()._p("event_log")
        for path in root.glob("*/trigger_audit.jsonl"):
            entries.extend(_read_records(path))
    except Exception:
        logger.warning("[perceive_event_audit] query failed", exc_info=True)
        return [], 0

    if source:
        entries = [entry for entry in entries if entry.get("source") == source]
    if gate_result:
        entries = [entry for entry in entries if entry.get("gate_result") == gate_result]
    entries.sort(key=lambda entry: float(entry.get("ts") or 0), reverse=True)
    total = len(entries)
    return entries[offset:offset + limit], total


def _read_records(path: Path) -> list[dict]:
    records: list[dict] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(record, dict):
                records.append(record)
    except Exception:
        logger.warning("[perceive_event_audit] cannot read %s", path, exc_info=True)
    return records
