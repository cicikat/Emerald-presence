import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def safe_write_text(path: Path, content: str, encoding: str = "utf-8") -> bool:
    path = Path(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(content, encoding=encoding)
        tmp.replace(path)
        return True
    except Exception as e:
        logger.error(f"[safe_write] 写入失败 {path}: {e}")
        try:
            if tmp.exists():
                tmp.unlink()
        except Exception:
            pass
        return False


def safe_write_bytes(path: Path, content: bytes) -> bool:
    path = Path(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_bytes(content)
        tmp.replace(path)
        return True
    except Exception as e:
        logger.error(f"[safe_write] 写入失败 {path}: {e}")
        try:
            if tmp.exists():
                tmp.unlink()
        except Exception:
            pass
        return False


def safe_write_json(path: Path, data: dict | list) -> bool:
    return safe_write_text(Path(path), json.dumps(data, ensure_ascii=False, indent=2))


def safe_append_jsonl(path: Path, record: dict) -> bool:
    """追加一行 JSON 到 .jsonl 文件（asyncio 单线程安全，进程级原子性）。"""
    path = Path(path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record, ensure_ascii=False) + "\n"
        with open(path, "a", encoding="utf-8") as f:
            f.write(line)
        return True
    except Exception as e:
        logger.error(f"[safe_write] jsonl 追加失败 {path}: {e}")
        return False
