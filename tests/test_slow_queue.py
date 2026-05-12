"""
DLQ 落盘测试

验证项：
- handler 被调用 3 次（首次 + 重试 2 次）
- data/dead_letter_queue/ 下生成 1 个文件
- 文件名格式：{ms_ts}_always_fail.json
- 文件内容：task.task_type、task.payload.marker、error("boom")、failed_at
"""

import json
import pytest


async def test_dlq_written_and_handler_retried_3_times(sandbox):
    import core.post_process.slow_queue as sq

    call_log: list[str] = []

    async def always_fail(payload):
        call_log.append("call")
        raise RuntimeError("boom")

    sq.register_handler("always_fail", always_fail)
    sq.start_worker()
    sq.enqueue("always_fail", {"marker": "test_dlq"})

    await sq.drain()

    # ── DLQ 文件存在确认 ─────────────────────────────────────────────────────
    dlq_dir = sandbox.dead_letter_queue()
    files = list(dlq_dir.glob("*.json"))
    assert len(files) == 1, f"DLQ 文件应恰好 1 个，实际: {len(files)}"

    fname = files[0].name
    assert fname.endswith("_always_fail.json"), f"文件名格式错误: {fname}"
    prefix = fname.replace("_always_fail.json", "")
    assert prefix.isdigit(), f"时间戳前缀不是纯数字: {prefix}"

    # ── 文件内容验证 ──────────────────────────────────────────────────────────
    data = json.loads(files[0].read_text(encoding="utf-8"))
    assert data["task"]["task_type"] == "always_fail"
    assert data["task"]["payload"]["marker"] == "test_dlq"
    assert "boom" in data["error"], f"error 字段缺少 'boom': {data['error'][:200]}"
    assert isinstance(data["failed_at"], float), "failed_at 应为 float 时间戳"

    # ── 重试次数验证（3 次调用 = 首次 + 重试 2 次）────────────────────────────
    assert len(call_log) == 3, f"handler 调用次数应为 3，实际: {len(call_log)}"
