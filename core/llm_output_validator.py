import logging
import time
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

_DEBUG_DIR = Path("data/debug/llm_output")
_KEEP_DAYS = 7


class FailureCounter:
    def __init__(self):
        self._state: dict[str, dict] = {}

    def _get(self, key: str) -> dict:
        if key not in self._state:
            self._state[key] = {"count": 0, "paused_until": 0.0}
        return self._state[key]

    def record_failure(self, key: str, raw_output: str, uid: str) -> None:
        entry = self._get(key)
        entry["count"] += 1
        count = entry["count"]

        self._save_debug(raw_output, uid)

        if count == 3:
            logger.error(
                f"[llm_validator] {key} 连续失败 3 次，raw_output 片段: {raw_output[:200]}"
            )
        if count >= 5:
            entry["paused_until"] = time.time() + 1800
            logger.error(
                f"[llm_validator] {key} 失败达 {count} 次，暂停 30 分钟"
            )

    def is_paused(self, key: str) -> bool:
        entry = self._get(key)
        return time.time() < entry["paused_until"]

    def reset(self, key: str) -> None:
        if key in self._state:
            self._state[key]["count"] = 0
            self._state[key]["paused_until"] = 0.0

    def _save_debug(self, raw_output: str, uid: str) -> None:
        try:
            _DEBUG_DIR.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            out_file = _DEBUG_DIR / f"{timestamp}_{uid}.txt"
            out_file.write_text(raw_output, encoding="utf-8")
            self._cleanup_old_files()
        except Exception as e:
            logger.warning(f"[llm_validator] 写入 debug 文件失败: {e}")

    def _cleanup_old_files(self) -> None:
        cutoff = datetime.now() - timedelta(days=_KEEP_DAYS)
        try:
            for f in _DEBUG_DIR.iterdir():
                if f.is_file() and datetime.fromtimestamp(f.stat().st_mtime) < cutoff:
                    f.unlink()
        except Exception as e:
            logger.warning(f"[llm_validator] 清理过期 debug 文件失败: {e}")


_counter = FailureCounter()


def record_failure(key: str, raw_output: str, uid: str) -> None:
    _counter.record_failure(key, raw_output, uid)


def is_paused(key: str) -> bool:
    return _counter.is_paused(key)


def reset(key: str) -> None:
    _counter.reset(key)
