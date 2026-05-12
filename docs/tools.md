# docs/tools.md — 工具系统

---

## 工具触发的两条路径

工具有两条独立的触发路径，互不干扰：

```
路径A：探针（pipeline 之前）
  用户消息 → 极简 system prompt（get_probe_prompt）
           → LLM 判断是否调工具
           → 只判断 info + desktop 类
           → 结果写入 tool_result → perception_block

路径B：LLM 自主调用（正式对话中）
  完整 prompt → LLM 生成回复时自主触发 function calling
              → memory 类工具主要走此路径
              → 结果写入 tool_result → perception_block
```

**memory 类工具不走探针**，探针调用时明确过滤：
```python
get_tools_schema(categories=["info", "desktop"])
```

---

## 工具注册表

文件：`core/tool_dispatcher.py` → `_TOOL_REGISTRY`

### info 类（探针覆盖）

| 工具名 | 触发描述 | 实现位置 |
|---|---|---|
| `get_time` | 用户问"几点"/"现在时间" | `_get_current_time()` 内联 |
| `weather` | 用户问天气/温度/下雨 | `core/tools/weather.py` |
| `web_search` | 确认信息/帮用户找资料 | `core/tools/web_search.py`（DuckDuckGo）|
| `add_reminder` | "提醒我X点做Y"/"帮我记" | `core/tools/reminder.py` |

### desktop 类（探针覆盖）

| 工具名 | 触发描述 | 执行方式 |
|---|---|---|
| `desktop_minimize` | 最小化窗口 | 写 agent_actions.json 队列 |
| `desktop_open_url` | 打开网址 | 写 agent_actions.json 队列 |
| `desktop_play_pause` | 播放/暂停媒体 | 写 agent_actions.json 队列 |
| `desktop_notify` | 发系统通知 | 写 agent_actions.json 队列 |
| `play_song` | "放一首xx"/"我要听xx" | 网易云 API 搜索 song_id → 写队列 |

### memory 类（不走探针，LLM 自主调用）

| 工具名 | 用途 | 备注 |
|---|---|---|
| `read_diary` | 读用户日记 | Author's Note 强制要求叶瑄必须调 |
| `read_watch` | 读睡眠/心率/运动数据 | |
| `search_diary` | 按关键词搜索最近 30 天日记 | |
| `get_profile` | 获取用户画像 | fetch_context 已自动注入，此工具是第二路径 |
| `get_episodic` | 召回情景记忆 | fetch_context 已自动注入，此工具是第二路径 |
| `get_growth` | 获取叶瑄对用户的认知 | fetch_context 已自动注入，此工具是第二路径 |

> 注：`get_profile / get_episodic / get_growth` 在 `fetch_context` 里已经自动加载到 prompt，这三个工具是供叶瑄在对话中按需**主动再次召回**的第二路径，两者并存不冲突。

### 日记工具的三层分工

| 文件 | 职责 |
|---|---|
| `core/tools/diary_reader.py` | 底层读取，从 Obsidian 目录读 .md 文件 |
| `core/tools/diary_tool.py` | `read_diary` 工具实现，按日期读，读完调 `mark_diary_shared()` |
| `core/tools/diary_search.py` | `search_diary` 工具实现，按关键词搜最近30天 |
| `core/memory/diary_context.py` | 存储层，用户日记上下文单独存 txt，只进 prompt 层6d，不参与检索 |

### system 类（不走探针）

| 工具名 | 用途 | 备注 |
|---|---|---|
| `device_shutdown` | 关机 | `dangerous=True`，需用户确认，默认关闭 |
| `device_sleep` | 睡眠 | `dangerous=True`，需用户确认，默认关闭 |
| `exit_yandere` | 叶瑄从病娇状态平静 | 向 `Emerald-desktop` 项目写信号文件 |

---

## 探针规则（get_probe_prompt）

文件：`core/tool_dispatcher.py` → `get_probe_prompt()`

探针 prompt 现在从 `_TOOL_REGISTRY` 动态构建，不再硬编码规则列表。
每个 `info` / `desktop` 类工具注册时需提供 `examples` 和 `keywords` 字段：

- `examples`：2-4 条触发例句，拼入探针 prompt 供 LLM 判断
- `keywords`：关键词列表，命中时走快速路径直接调工具，跳过 LLM

**快速路径**（`_fast_path_match`，在 `main.py` 探针入口）：
关键词命中 → 直接构造 tool_calls，不调 LLM 探针。

**严禁推断**规则保留不变：消息里有"现在""今天""热""冷"等词，但没有明确问天气或时间，不调工具。

---

## 桌面动作执行机制（SubAgent）

### 流程

```
1. 工具调用或意图解析触发动作
2. _is_desktop_active()：检查 channel_queue.json 修改时间是否在 5 分钟内
   └─ 离线 → 直接返回失败，写入 pending_perception
3. _push_desktop_action()：动作追加到 agent_actions.json
4. 桌宠端轮询 agent_actions.json，执行后清空
5. 执行失败：最多重试 2 次，间隔 0.5s
6. 仍失败：_write_pending_perception() → 下轮注入 perception_block
```

### pending_perception 机制

失败感知文件目录：`data/pending_perception/`
- 文件名为时间戳（防止多次失败覆盖）
- 两阶段提交，消除并发竞态：
  1. `read_and_mark()`：`os.rename` 原子抢占，把文件移到 `processing/` 子目录
     并发时只有一个 task 能成功，FileNotFoundError 说明被抢走，直接跳过
  2. `confirm_delivered()`：删除 `processing/` 下的文件
  3. `cleanup_stale()`：根目录扫超24h文件；processing 目录扫 mtime 超1h的文件
- 时间前缀自动计算：`[刚刚]` / `[N秒前]` / `[N分钟前]`

### send_notification 防误触发

二次校验：叶瑄回复必须包含以下关键词之一才真正触发通知：
```
"提醒你" / "通知你" / "告诉你记得" / "帮你记" / "记得提醒"
```

---

## 意图解析（_parse_and_execute_intent）

在 `post_process` 里异步执行。不同于探针（在用户消息上判断），意图解析是在**叶瑄的回复**上判断：

叶瑄说"我去把游戏关掉" → 真的执行 `minimize_window`

支持的意图类型：
- `minimize_window`：最小化窗口
- `play_song`：播放歌曲
- `open_url`：打开网址
- `play_pause`：播放/暂停
- `send_notification`：发通知（有额外关键词校验）

---

## 工具开关

`config.yaml` 的 `tools:` 节点，危险工具默认关闭：

```yaml
tools:
  device_shutdown:
    enabled: false
  device_sleep:
    enabled: false
  weather:
    enabled: true
  # 其他工具默认 enabled: true
```

---

## 新增工具的规范

1. 在 `core/tools/` 下创建独立实现文件
2. 在 `tool_dispatcher.py` 顶部写 wrapper 函数（async）
3. 在 `_TOOL_REGISTRY` 里注册，填写 `func / description / dangerous / category / parameters`
4. 如果需要探针覆盖（info/desktop 类），在注册条目里补充 `examples`（触发例句）和 `keywords`（快速路径关键词），`get_probe_prompt()` 会自动同步，无需手动改探针规则
5. 如果是高危工具，设 `dangerous: True`，并在 `execute()` 的确认逻辑里补充描述文案
6. 在 `config.yaml` 的 `tools:` 节点决定默认开关状态
7. 在此文档的注册表里补充说明

---

## 已注册但未生效的代码

`_desktop_launch_netease_wrapper` 和 `_desktop_play_netease_wrapper` 有实现但未加入 `_TOOL_REGISTRY`，被 `play_song`（搜索+播放一体）取代，属于死代码。
