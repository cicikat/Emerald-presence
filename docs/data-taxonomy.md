# Data Taxonomy

本文件记录 `data/` 分层迁移的目标结构和边界。当前阶段只建立路径规划，现有 loader 仍按旧路径工作，不搬文件，不改变运行行为。

## 目标根目录

未来 `data/` 顶层按用途分为：

| 目录 | 定位 |
|---|---|
| `runtime/` | 运行时队列、临时动作、短生命周期通道文件 |
| `memory/` | 会进入现实对话记忆链路的用户记忆 |
| `generated/` | 媒体缓存、上传解析产物、LLM 生成但非核心状态的内容 |
| `state/` | 调度器、presence、花园、活动状态等可重建或可继续运行的状态 |
| `archive/` | 人工归档和历史保留，默认不进入现实 prompt |
| `dreams/` | Dream Session 专用边界，默认不进入现实 prompt |
| `config/` | 可由管理面板维护的配置型数据 |
| `debug/` | 调试输出、异常样本、观测日志 |
| `personas/` | 多角色 persona 元数据和按 persona 分区的角色状态 |

`core/paths.py` 提供这些未来根路径 helper，但现阶段不替换 `core/sandbox.get_paths()`，不接入 prompt、scheduler、memory loader。

## Runtime / Debug 待接入项

低风险 `runtime/` 与 `debug/` 项应等客户端轮询路径同步、且路径入口具备 sandbox-aware 兼容后再接入。当前运行代码仍保持旧行为。

| 当前旧路径 | 规划新路径 | 未来读策略 | 未来写策略 |
|---|---|---|---|
| `data/channel_queue.json` | `data/runtime/channel_queue.json` | 优先读新路径；新路径不存在时读旧路径 | 写新路径 |
| `data/mobile_queue.json` | `data/runtime/mobile_queue.json` | 优先读新路径；新路径不存在时读旧路径 | 写新路径 |
| `data/agent_actions.json` | `data/runtime/agent_actions.json` | 优先读新路径；新路径不存在时读旧路径 | 写新路径 |
| `data/debug/llm_output/` | `data/debug/llm_output/` | cleanup 优先处理新路径；新路径不存在时兼容旧路径 | 写新路径 |

接入时不自动移动旧文件，也不删除旧文件。如果需要保留旧队列或旧 debug 样本，由人工在停机窗口复制到新路径，并确认客户端读取位置已经同步。

## Personas 规划

规划结构：

```text
data/personas/
├── active.json
├── registry.json
└── p001/
    ├── profile/
    ├── inner_state/
    ├── relationship/
    └── growth/
```

persona 的稳定目录名必须使用 ASCII id，例如 `p001`、`p002`。不要用 `叶瑄` 这类中文显示名做路径。中文名、展示名、角色卡文件名应放在 `registry.json` 里映射到稳定 id。

当前 `personas/` 只是规划目录。现实 loader 不会读取 `data/personas/active.json`、`registry.json` 或 `p001/` 下任何文件。

## 会进入现实 Prompt / Retrieve 的数据

当前现实对话会读取这些旧路径，并可能注入 prompt 或影响 retrieve：

| 旧路径 | 当前用途 |
|---|---|
| `data/history/{uid}.json` | 层 9 短期历史 |
| `data/event_log/{uid}/{date}.md` | 层 6b 事件搜索 |
| `data/mid_term/{uid}.json` | `mid_term` 层 |
| `data/episodic_memory/{uid}.json` | 层 6c / 9.5 情景记忆 |
| `data/user_identity/{uid}.yaml` | 层 6a 用户稳定行为模式 |
| `data/profiles/{uid}.json` | 层 5 画像，3.5/3.6/3.7 传感数据 |
| `data/diary_context/{uid}.txt` | 层 6d 用户近期日记 |
| `data/reminders/{uid}.json` | 层 5.2 待办备忘 |
| `data/group_context/{gid}.json` | 层 4 群聊上下文 |
| `data/relations.yaml` | 层 3 用户关系 |
| `data/lorebook.yaml` | 层 5.5 世界书 |
| `data/jailbreak_entries.json` | 层 0 / 2 / 11 破限条目 |
| `data/activity_snapshot.json` | 层 3.8 桌面活动快照 |
| `data/yexuan_inner/mood_state.json` | 层 1 情绪软提示 |
| `data/yexuan_inner/presence.json` | 层 2.55 上次说话时间、2.6 活动注入判断 |
| `data/yexuan_inner/diary/{date}.md` | 层 6e 角色日记 |
| `data/yexuan_inner/observations.jsonl` | 层 11 style hint |
| `data/yexuan_inner/activity_pool.yaml` / `activity_state.json` | 层 2.6 角色当前活动 |
| `characters/yexuan_author_notes.json` + `data/yexuan_inner/trait_state.json` | 层 11 author note 轮换 |

`data/character_growth/` 当前不由主 prompt 自动注入，但仍是 legacy/兼容路径：`get_growth` 工具和旧 DLQ / 手动 `consolidate_to_growth` 仍可能读取或写入。

## Never Prompt Load

以下目录或文件默认不应进入现实 prompt/retrieve：

| 路径 | 说明 |
|---|---|
| `data/debug/` | LLM 异常输出和调试样本 |
| `data/logs/` | fixation、gating、trigger、dry-run 观测日志 |
| `data/dead_letter_queue/` | 慢任务失败重试记录，只能由重试/管理逻辑读取 |
| `data/archive/` | 人工归档，默认不参与现实 loader |
| `data/dreams/archive/` | Dream Session 归档，默认不参与现实 loader |
| `data/dreams/summaries/` | Dream Session 摘要，默认不参与现实 loader |
| `data/personas/` | 当前未接入 loader，默认不参与现实 prompt |
| `data/inbox/` | 上传文件落盘，只有解析后的用户消息进入对话 |
| `data/image_cache/` | 图片描述缓存，不作为主动记忆源 |

当前现实 loader 没有全量扫描 `data/` 的逻辑。`dreams/archive`、`dreams/summaries`、`personas` 默认不会被 `history`、`event_log`、`mid_term`、`episodic_memory`、`user_identity` 等现实记忆读取。

注意：`core/tools/diary_reader.py` 会对配置的日记根目录执行按文件名的递归查找。迁移时不要把它的根目录指向整个 `data/`，否则同名 `YYYY-MM-DD.md` 可能被误读成用户日记。

## 迁移顺序

建议按风险从低到高迁移：

1. `runtime/` 与 `debug/`：通道队列、动作队列、调试输出、观测日志。先迁这些，验证路径入口和客户端 `data_prefix` 协议。
2. `generated/` 与 `state/`：`inbox/`、`image_cache/`、花园、presence、activity、scheduler state 等。它们影响体验，但通常不是长期人格记忆主干。
3. `config/`：`relations.yaml`、`blacklist.yaml`、`lorebook.yaml`、`jailbreak_entries.json`、`yexuan_traits.yaml`、activity pool 等。必须成对迁移 admin 写入端和 core 读取端。
4. `memory/`：`history`、`event_log`、`mid_term`、`episodic_memory`、`user_identity`、`profiles`、`fixation_state`。这是现实 prompt 和固化链路主干，最后分批迁。
5. `personas/`：等 registry、active persona、旧 `characters/`、`yexuan_inner/`、`character_growth/` 的映射边界明确后再接入。不要直接把中文角色名作为目录名。

任何一步都应保持“先双读观测或只读影子验证，再切写入，再清理旧路径”的节奏；本阶段只记录目标，不启用迁移。
