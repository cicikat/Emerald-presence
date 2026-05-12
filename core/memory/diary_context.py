"""
日记上下文独立存储
日记内容不写入 event_log，单独存储，只注入 prompt 不参与检索。
"""
from pathlib import Path
from core.error_handler import log_error
from core.sandbox import get_paths


def save(user_id: str, text: str):
    d = get_paths().diary_context()
    d.mkdir(parents=True, exist_ok=True)
    try:
        (d / f"{user_id}.txt").write_text(text, encoding="utf-8")
    except Exception as e:
        log_error("diary_context.save", e)


def load(user_id: str) -> str:
    try:
        p = get_paths().diary_context() / f"{user_id}.txt"
        if p.exists():
            return p.read_text(encoding="utf-8").strip()
    except Exception as e:
        log_error("diary_context.load", e)
    return ""