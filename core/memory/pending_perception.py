"""
pending_perception — 两阶段提交
新写入 → build_prompt 原子抢占(rename) → post_process 成功后删除
cleanup_stale 兜底回收中途失败的文件
"""
import json
import os
import time
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def _pending_dir() -> Path:
    from core.sandbox import get_paths
    return get_paths().pending_perception_dir()


def _processing_dir() -> Path:
    d = _pending_dir() / "processing"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _list_pending() -> list[Path]:
    return sorted(_pending_dir().glob("*.json"))


def write(text: str, action: str = "", result: str = "") -> None:
    """pipeline 写入感知，替代原 _write_pending_perception"""
    p = _pending_dir() / f"{time.time()}.json"
    p.write_text(json.dumps({
        "ts": time.time(),
        "text": text,
        "action": action,
        "result": result,
        "consumed_at": None,
        "delivered_at": None,
    }, ensure_ascii=False), encoding="utf-8")


def read_and_mark() -> tuple[str, list[str]]:
    """
    build_prompt 调用，原子抢占未消费感知，标记 consumed，不删文件。
    用 os.rename 把文件移入 processing/ 子目录，同一文件系统保证原子性，
    并发调用时只有一个 task 能抢到同一文件，另一个得到 FileNotFoundError 后跳过。
    返回 (拼接文字, [processing 目录下的文件路径列表])
    """
    now = time.time()
    proc_dir = _processing_dir()
    parts = []
    paths = []
    for path in _list_pending():
        dst = proc_dir / (path.name + ".processing")
        try:
            os.rename(path, dst)
        except FileNotFoundError:
            continue
        try:
            data = json.loads(dst.read_text(encoding="utf-8"))
            elapsed = now - data.get("ts", now)
            if elapsed < 10:
                prefix = "[刚刚]"
            elif elapsed < 60:
                prefix = f"[{int(elapsed)}秒前]"
            else:
                prefix = f"[{int(elapsed / 60)}分钟前]"
            parts.append(f"{prefix} {data['text']}")
            data["consumed_at"] = now
            dst.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            paths.append(str(dst))
        except Exception:
            logger.exception("read_and_mark: failed to process %s", dst)
    return "；".join(parts), paths


def confirm_delivered(paths: list[str]) -> None:
    """post_process 成功后调用，删除 processing 目录下已交付文件"""
    for p in paths:
        try:
            Path(p).unlink(missing_ok=True)
        except Exception:
            pass


def cleanup_stale() -> None:
    """启动时调用，清理上次崩溃留下的脏数据"""
    now = time.time()
    # 根目录：超 24h 未被 rename 走（从未被消费）的文件
    for path in _list_pending():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if now - data.get("ts", 0) > 86400:
                path.unlink(missing_ok=True)
        except Exception:
            pass
    # processing 目录：consumed 超 1h 未 delivered，用 mtime 判断
    proc_dir = _pending_dir() / "processing"
    if proc_dir.exists():
        for path in proc_dir.glob("*.processing"):
            try:
                if now - path.stat().st_mtime > 3600:
                    path.unlink(missing_ok=True)
            except Exception:
                pass