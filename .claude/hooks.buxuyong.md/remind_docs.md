#!/usr/bin/env python3
"""Stop hook: 改了代码但没同步文档时,阻塞 Stop 让 Claude 补上。"""
import json
import os
import sys
from pathlib import Path


# 全局兜底:改了这些路径的代码,默认都要判断 ARCHITECTURE + AGENTS 是否要更新
GLOBAL_CODE_PATTERNS = ["core/", "main.py", "admin/"]
GLOBAL_DOCS = [
    ("ARCHITECTURE.md", "系统全貌 / Pipeline 主流程 / 数据目录"),
    ("AGENTS.md", "任务-文档映射 / 关键文件速查 / 改代码前强制规则"),
]

# 专项规则:路径关键词 → 对应专项文档(在全局基础上追加)
SPECIFIC_RULES = [
    (
        ["core/memory/", "core/safe_write.py", "core/integrity_check.py",
         "core/llm_output_validator.py", "tools/extract_observations.py"],
        "docs/memory.md",
        "记忆子系统(short_term/event_log/episodic/growth/mood/mid_term/"
        "profile/locks/fixation_pipeline/trait_tracker/diary_context)",
    ),
    (
        ["core/prompt_builder.py", "core/tag_rules.py", "core/mood_text.py",
         "core/author_note_rotator.py", "core/lore_engine.py",
         "characters/", "data/jailbreak_entries.json"],
        "docs/prompt-layers.md",
        "Prompt 层结构 / tag 规则 / author note / 角色卡 / 世界书 / 破限",
    ),
    (
        ["core/tool_dispatcher.py", "core/tools/"],
        "docs/tools.md",
        "工具系统(info/desktop/memory/system 类) / 探针 / 桌面动作 / 意图解析",
    ),
    (
        ["core/scheduler/"],
        "docs/scheduler.md",
        "调度器主循环 / 触发器 / 冷却管理 / 优先级",
    ),
]

DOC_FILES = {
    "AGENTS.md", "ARCHITECTURE.md",
    "docs/memory.md", "docs/prompt-layers.md", "docs/tools.md",
    "docs/scheduler.md", "docs/known-issues.md",
}


def normalize(p, project_dir):
    try:
        rel = os.path.relpath(p, project_dir)
    except ValueError:
        rel = p
    return rel.replace("\\", "/")


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    # 防死循环:上一轮已经被 Stop hook 阻塞过,这一轮放行
    if payload.get("stop_hook_active"):
        sys.exit(0)

    project_dir = os.environ.get("CLAUDE_PROJECT_DIR", "")
    session_id = payload.get("session_id", "default")
    state_file = Path(project_dir) / ".claude" / ".cache" / f"edits_{session_id}.json"

    if not state_file.exists():
        sys.exit(0)

    try:
        edits = json.loads(state_file.read_text(encoding="utf-8"))
    except Exception:
        sys.exit(0)

    if not edits:
        sys.exit(0)

    edited_paths = {normalize(e["path"], project_dir) for e in edits}
    edited_docs = {p for p in edited_paths if p in DOC_FILES}
    edited_code = edited_paths - edited_docs

    if not edited_code:
        state_file.unlink(missing_ok=True)
        sys.exit(0)

    # 收集"应更新的文档 → 触发原因列表"
    suggested = {}

    # 全局兜底
    global_hit = [p for p in edited_code
                  if any(pat in p for pat in GLOBAL_CODE_PATTERNS)]
    if global_hit:
        for doc, reason in GLOBAL_DOCS:
            for p in global_hit:
                suggested.setdefault(doc, []).append(f"{p}  ({reason})")

    # 专项追加
    for code_path in edited_code:
        for patterns, doc, reason in SPECIFIC_RULES:
            if any(pat in code_path for pat in patterns):
                suggested.setdefault(doc, []).append(f"{code_path}  ({reason})")

    # 过滤掉本轮已更新的文档
    pending = {d: rs for d, rs in suggested.items() if d not in edited_docs}

    if not pending:
        state_file.unlink(missing_ok=True)
        sys.exit(0)

    # 组装提示:全局文档排前,专项靠后
    global_order = [d for d, _ in GLOBAL_DOCS]
    sorted_docs = sorted(
        pending.keys(),
        key=lambda d: (global_order.index(d) if d in global_order else 999, d),
    )

    lines = ["本轮你改动了代码,但下面这些相关文档尚未同步更新:", ""]
    for doc in sorted_docs:
        lines.append(f"- {doc}  ← 因为改了:")
        for r in sorted(set(pending[doc])):
            lines.append(f"    · {r}")

    lines += [
        "",
        "请根据实际改动选择:",
        "  (1) 若文档需要随代码更新(新增/删除字段、流程变化、新增层、新增工具、",
        "      改了行为约定、更新了关键文件速查等),现在补上。",
        "  (2) 若只是小 bug 修复、语法纠正、注释/日志调整、性能优化等不影响架构和速查表的改动,",
        "      明确说一句\"无需更新文档,理由:xxx\"再结束,本 hook 会放行。",
    ]

    print(json.dumps({"decision": "block", "reason": "\n".join(lines)},
                     ensure_ascii=False))
    sys.exit(0)


if __name__ == "__main__":
    main()
