"""
Group Dream shared transcript storage — Brief 100 §1.

Physically separate from `core.stage.store` (reality transcript.json): the
in-dream transcript lives in an append-only jsonl file
(`tmp/current_dream.jsonl`), never in the reality group's transcript.json, so
dream turns can never leak into reality history rendering or projection.

Every persisted record carries the dream artifact sentinel
(never_retrieve / not_memory_source / reality_boundary=dream_only).
"""
from __future__ import annotations

import json
import logging
import time

from core.dream.dream_state import apply_dream_artifact_sentinel
from core.safe_write import safe_append_jsonl, safe_write_json
from core.sandbox import get_paths
from core.stage.models import TranscriptEntry

logger = logging.getLogger(__name__)


def load_dream_transcript(group_id: str) -> list[TranscriptEntry]:
    path = get_paths().dream_group_tmp_path(group_id=group_id)
    if not path.exists():
        return []
    entries: list[TranscriptEntry] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                entries.append(TranscriptEntry.from_dict(json.loads(line)))
            except Exception:
                logger.warning("[stage.dream_store] skipping malformed transcript line group=%s", group_id)
    except Exception as exc:
        logger.error("[stage.dream_store] load transcript failed group=%s: %s", group_id, exc)
        return []
    return entries


def append_dream_transcript(group_id: str, entry: TranscriptEntry) -> bool:
    path = get_paths().dream_group_tmp_path(group_id=group_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    record = apply_dream_artifact_sentinel(entry.to_dict())
    return safe_append_jsonl(path, record)


def archive_dream_transcript(group_id: str, dream_id: str) -> None:
    """Move the current tmp transcript into archive/dream_{id}.jsonl and clear tmp.

    Best-effort — a failure here must never block hard_exit (Invariant D).
    """
    try:
        tmp_path = get_paths().dream_group_tmp_path(group_id=group_id)
        if not tmp_path.exists():
            return
        archive_dir = get_paths().dream_group_archive_dir(group_id=group_id)
        archive_dir.mkdir(parents=True, exist_ok=True)
        safe_id = "".join(c for c in dream_id if c.isalnum() or c in "_-") or f"dream_{int(time.time())}"
        archive_path = archive_dir / f"{safe_id}.jsonl"
        archive_path.write_text(tmp_path.read_text(encoding="utf-8"), encoding="utf-8")
        tmp_path.unlink()
    except Exception as exc:
        logger.error("[stage.dream_store] archive failed group=%s dream_id=%s: %s", group_id, dream_id, exc)


def clear_dream_transcript(group_id: str) -> None:
    try:
        tmp_path = get_paths().dream_group_tmp_path(group_id=group_id)
        if tmp_path.exists():
            tmp_path.unlink()
    except Exception as exc:
        logger.warning("[stage.dream_store] clear tmp transcript failed group=%s: %s", group_id, exc)
