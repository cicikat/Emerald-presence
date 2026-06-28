#!/usr/bin/env python3
"""PostToolUse hook: 把本 session 编辑过的文件追加到 cache 文件。"""
import json
import os
import sys
from pathlib import Path


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    if payload.get("tool_name") not in ("Edit", "Write", "MultiEdit"):
        sys.exit(0)

    tool_input = payload.get("tool_input") or {}
    file_path = tool_input.get("file_path")
    if not file_path:
        sys.exit(0)

    project_dir = os.environ.get("CLAUDE_PROJECT_DIR", "")
    session_id = payload.get("session_id", "default")
    cache_dir = Path(project_dir) / ".claude" / ".cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    state_file = cache_dir / f"edits_{session_id}.json"

    edits = []
    if state_file.exists():
        try:
            edits = json.loads(state_file.read_text(encoding="utf-8"))
        except Exception:
            edits = []

    edits.append({"path": file_path, "tool": payload.get("tool_name")})
    state_file.write_text(json.dumps(edits, ensure_ascii=False), encoding="utf-8")
    sys.exit(0)


if __name__ == "__main__":
    main()
