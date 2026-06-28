# P2-IMPL · 工具结果选择性回写短期记忆（日记查重，时间不沉淀）

> 后端（Emerald-presence）。
> **前置**：G1 诊断（✓ 已结，日记链=用户日记原文经 `diary_inject` 进 `diary_context`，叶瑄读日记走 `read_toy_file`/diary 工具）。无代码前置。
> **可并行**：与 P3 / P5 / P4 / D 系列互不冲突。
> **硬规则**：改 short_term 写入**必须**走 `_sanitize_assistant_message`（`short_term.py:118`），严禁绕过——见 CLAUDE.md 规则 5。

## 现状（已核对）

- 工具结果注入在层 10（`prompt_builder.py:977`），**只进本轮 prompt，不沉淀进短期记忆**。
- short_term：`append()`（:395/509）写 history，`load_for_prompt`（:337）读，turn_id 去重（`seen_turn_ids`）。
- 日记读取 `diary_reader.read_recent`（按日期文件拼接）/ toy 文件读取——**无"读过哪篇"的记忆**，所以同一篇可能被反复触发、反复读、反复占上下文。

## 目标

工具结果**分类回写**短期记忆：**可沉淀类**（日记内容→写入短期记忆，叶瑄"记得读过"，并按文件指纹**去重**不二次触发同一篇）；**易失类**（时间/天气→只用本轮，不沉淀）。

## 改动点

### 1. 工具结果分类

给 `_TOOL_REGISTRY` 每个工具加一个字段 `persist: bool`（或一张白名单集合 `_PERSIST_TOOLS`）：
- **可沉淀**：日记读取、玩具文件读取等"内容型"。
- **易失**：`get_time`、天气、实时感知等"瞬时型"——`persist=False`。

### 2. 可沉淀结果回写短期记忆（带来源指纹去重）

post_process 链里（工具执行后、写 short_term 处）：
- 对 `persist=True` 的结果，生成**来源指纹** `source_fingerprint`（日记=文件名/日期；玩具=file_key + 内容 hash）。
- 维护一个**已读集合**（每 uid/char，存最近 K 个 fingerprint，可放 short_term 旁的小 json 或 mid_term 元区）。
- **命中指纹 → 不再二次注入/触发**该文件（工具层直接返回"刚读过这篇"，或 probe 阶段跳过）；未命中 → 正常注入 + 记 fingerprint + 把"叶瑄读了《X》"以**叶瑄视角一句**写进 short_term（经 `_sanitize_assistant_message`）。

### 3. 易失结果不沉淀

`persist=False` 的工具结果维持现状（只进层 10 本轮），不写 short_term、不记指纹。

## 验收

1. 连续两轮都想读同一篇日记 → 第二次被指纹挡下，不重复读、不重复注入。
2. 读不同日期日记 → 各自正常，指纹各记一条。
3. 时间类工具 → 不进 short_term（history 里查不到"叶瑄看了时间"这种沉淀）。
4. 回写的"读了《X》"一句确实经过 `_sanitize_assistant_message`（不破坏风格反馈）。

## 文档同步
`AGENTS.md` / `docs/memory.md` 工具系统段记 `persist` 字段与日记去重机制。
