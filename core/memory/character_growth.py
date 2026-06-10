"""
Read-only legacy compatibility surface — character growth snapshot.

This module is read-only legacy compatibility surface.
Write path was retired in R8-E2; update() and should_update() have been deleted.
Do NOT reintroduce update() or should_update() — the active write chain is
consolidate_to_identity (identity.yaml) + trait_tracker_update slow_queue task.
load() is kept only for get_growth tool compatibility.

角色对每个用户维护一个"认知 Markdown 文件"（历史写入，不再自动更新）。

存储位置：
  data/character_growth/角色_{user_id}.md
"""

from pathlib import Path

from core.error_handler import log_error
from core.sandbox import get_paths


def _growth_root() -> Path:
    return get_paths().character_growth()


def _growth_file(character_name: str, user_id: str) -> Path:
    """返回认知文件路径，文件名格式：角色_{user_id}.md"""
    safe_char = "".join(c for c in character_name if c.isalnum() or c in "-_")
    safe_user = "".join(c for c in user_id if c.isalnum() or c in "-_")
    return _growth_root() / f"{safe_char}_{safe_user}.md"


def load(character_name: str, user_id: str) -> str:
    """
    Read legacy growth snapshot only; no mutation; not the current growth writer.

    读取角色对该用户的历史认知文件内容（只读兼容面）。
    文件不存在时返回空字符串，不报错。
    当前写入链为 consolidate_to_identity + trait_tracker_update，本函数不写任何数据。

    参数：
        character_name - 角色名（如"叶瑄"）
        user_id        - 用户 QQ 号

    返回：
        认知文件的文本内容，空则返回 ""
    """
    path = _growth_file(character_name, user_id)
    try:
        if path.exists():
            return path.read_text(encoding="utf-8").strip()
    except Exception as e:
        log_error("character_growth.load", e)
    return ""


class CharacterGrowth:
    """
    Read-only class wrapper; update() / should_update() retired in R8-E2.
    Use consolidate_to_identity + trait_tracker_update for writes.
    """

    def load(self, character_name: str, user_id: str) -> str:
        return load(character_name, user_id)
