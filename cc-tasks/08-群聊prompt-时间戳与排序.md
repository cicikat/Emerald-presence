# CC 任务：群聊 prompt 注入 — 时间戳 + 排序 + 注释（低优先）

> 给 Claude Code 执行。开工前读 `AGENTS.md` 的 stage / channels 条目。
> 改动 2 文件：`core/memory/group_context.py`、`core/prompt_builder.py`（4_group_context 层）。小改、独立。

---

## 背景（现状已确认，2026-06-29 实读）

茶茶反馈：群聊语义一片混乱、牛头不对马嘴。根因在群聊上下文的存储与注入：

1. **存储丢日期**：`group_context.py:55` `append()` 存 `timestamp = datetime.now().strftime("%H:%M")` —— **只有时分，跨天即无法判断先后**。
2. **不排序**：`get_recent()`（:65）直接 `return _load_raw()`，按写入顺序返回，无显式时间排序。
3. **注入缺锚**：`prompt_builder.py:636-651` 的 4_group_context 层，按 `sender_name + content` 拼行（:638-645），**没把时间戳带进注入文本**，也没有「按时间排序 / 这是历史回顾、非对你提问」的注释 → 模型读到一堆无时序、无身份锚的消息，自然错乱、牛头不对马嘴。

---

## 实现

### 1. `group_context.py::append`（:39）存完整时间戳

```python
"ts": time.time(),                               # 新增：用于排序的绝对时间
"timestamp": datetime.now().strftime("%m-%d %H:%M"),  # 显示用：带日期
```
保留向后兼容：`_load_raw` 读到旧条目（只有 `"%H:%M"`、无 `ts`）时不报错；缺 `ts` 的按 0 处理或用文件顺序兜底。

### 2. `get_recent`（:65）按时间排序

```python
def get_recent(group_id):
    if not group_id:
        return []
    msgs = _load_raw(group_id)
    msgs.sort(key=lambda m: float(m.get("ts") or 0))   # 升序：旧→新
    return msgs
```

### 3. `prompt_builder.py` 4_group_context 注入（:636-651）带时间戳 + 注释

每行改成带时间戳：
```python
for msg in group_context:
    sender = msg.get("sender_name", "群友")
    ts_label = msg.get("timestamp", "")
    content = msg.get("content", "")
    ctx_lines.append(f"[{ts_label}] {sender}：{content}")
```
层头注释明确语境（:650 的 content 前缀）：
```python
"content": (
    "<群聊上下文>\n"
    "【群聊上下文（最近群内动态，按时间先后排列，仅供理解语境，"
    "不是对你的直接提问；只在被 @ 或明显需要回应时才接话）】\n"
    + "\n".join(ctx_lines) + "\n</群聊上下文>"
),
```

---

## 验收标准

1. 群聊注入文本里每行带 `[MM-DD HH:MM] 发言人：内容`，且**按时间升序**。
2. 跨天的群消息先后正确（不再因只有时分而错乱）。
3. 层头注释让模型把这些当**历史语境**而非逐条提问 → 不再牛头不对马嘴地逐条回应。
4. 旧 group_context 文件（无 `ts`）不报错，平滑兼容。
5. 私聊（group_id=None）仍返回空、不注入该层。

---

## 备注

- 低优先、独立小改，可随时插队做。
- 若群聊体感仍乱，下一步可考虑限制注入条数（`config.memory.group_context_lines`）与「仅保留与当前话题/被@相关」的过滤——本单先把时序和语境注释补上。
