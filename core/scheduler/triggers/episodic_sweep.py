"""
episodic_sweep 触发器 — 扫描所有 uid 的 mid_term，
找出 age > 11h 且 promoted_to_episodic_id 为 null 的条目，批量触发 reflect_to_episodic。
冷却 30 分钟，触发类型 "sweep"。
"""

import logging
import time

from core.error_handler import log_error
from core.sandbox import get_paths

logger = logging.getLogger(__name__)


async def _check_episodic_sweep() -> None:
    from core.scheduler.loop import _is_ready, _mark

    if not _is_ready("episodic_sweep"):
        return

    _mark("episodic_sweep")

    mid_term_dir = get_paths().mid_term()
    if not mid_term_dir.exists():
        return

    uid_files = list(mid_term_dir.glob("*.json"))
    if not uid_files:
        return

    logger.debug(f"[scheduler.episodic_sweep] 扫描 {len(uid_files)} 个 uid")

    for uid_file in uid_files:
        uid = uid_file.stem
        try:
            await _sweep_uid(uid)
        except Exception as e:
            log_error(f"scheduler.episodic_sweep.sweep_uid.{uid}", e)


async def _sweep_uid(uid: str) -> None:
    from core.memory import mid_term as _mt
    from core.post_process import slow_queue

    events = _mt.load(uid)
    now = time.time()

    aged_ids = [
        e["mid_id"]
        for e in events
        if e.get("mid_id")
        and (now - e.get("ts", 0)) > 11 * 3600
        and not e.get("promoted_to_episodic_id")
    ]

    if not aged_ids:
        return

    slow_queue.enqueue("reflect_to_episodic", {
        "uid": uid,
        "mid_ids": aged_ids,
        "trigger": "sweep",
    })
    logger.info(
        f"[scheduler.episodic_sweep] uid={uid} 入队 reflect_to_episodic sweep "
        f"mid_ids={aged_ids}"
    )
