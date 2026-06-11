"""
tests/test_no_hardcoded_qq_number.py — N6 回归测试（发布加固版）

仓库内所有会被 git track 的文本文件中，不得出现真实 QQ 号字面量 1043484516。
测试 fixture 允许使用明显假号（如 1234567890）。

扫描范围 = 全仓 tracked 候选目录（代码 + 文档 + 脚本 + 配置示例），
排除：本测试自身、data/、logs/、.git/、__pycache__、二进制后缀。
"""
from __future__ import annotations

from pathlib import Path

_ROOT = Path(__file__).parent.parent
_FORBIDDEN_NUMBER = "1043484516"

_SCAN_DIRS = ["core", "admin", "channels", "tools", "scripts", "docs", "tests", "characters", "content", "defaults"]
_SCAN_ROOT_GLOBS = ["*.py", "*.md", "*.bat", "*.yaml", "*.yml", "*.json", "*.example", "*.txt"]
_TEXT_SUFFIXES = {".py", ".md", ".bat", ".yaml", ".yml", ".json", ".example", ".txt", ".jsonl"}
_EXCLUDE_PARTS = {"__pycache__", ".git", "data", "logs", "test_sandbox", "node_modules"}
_SELF_NAME = "test_no_hardcoded_qq_number.py"
# config.yaml 是 gitignored 的私有运行配置，不进发布物，不在扫描范围
_EXCLUDE_FILES = {"config.yaml"}


def _iter_files():
    for d in _SCAN_DIRS:
        base = _ROOT / d
        if not base.exists():
            continue
        for p in base.rglob("*"):
            if p.is_file() and p.suffix.lower() in _TEXT_SUFFIXES:
                yield p
    for g in _SCAN_ROOT_GLOBS:
        yield from _ROOT.glob(g)


def test_no_hardcoded_qq_in_repo():
    violations: list[str] = []
    seen: set = set()
    for path in _iter_files():
        rp = path.resolve()
        if path.name == _SELF_NAME or path.name in _EXCLUDE_FILES or rp in seen:
            continue
        seen.add(rp)
        if _EXCLUDE_PARTS & set(path.parts):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if _FORBIDDEN_NUMBER in text:
            for i, line in enumerate(text.splitlines(), 1):
                if _FORBIDDEN_NUMBER in line:
                    violations.append(f"{path.relative_to(_ROOT)}:{i}: {line.strip()[:120]}")

    assert not violations, (
        f"仓库中发现硬编码 QQ 号 {_FORBIDDEN_NUMBER}:\n" + "\n".join(violations)
    )
