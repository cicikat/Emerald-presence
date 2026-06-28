# P3-IMPL · 用户画像单条化 + tag/时间戳 + recency 召回

> 后端（Emerald-presence）。
> **前置**：P1 骨架（✓ 已落地，层 5 在 `prompt_builder.py:653`）、X1 向量库（✓ 已落地，可选增强）。
> **可并行**：与 P2 / P5 / P4 / D3 互不冲突，可同时开。
> **改造档位：外科手术**——只动「画像条目模型」与「层 5 注入」，稳定字段保留平铺。

## 现状（已核对）

`core/memory/user_profile.py`：profile 是固定字段（`name/location/pets/interests/occupation`）+ `important_facts: list[str]`（>30 条触发 LLM 压缩）。层 5（`prompt_builder.py:655-676`）**全字段 100% 平铺注入**，无 tag、无时间、无 recency。你的痛点：像「喜欢听的歌」这种易变偏好和「职业」这种稳定事实被一视同仁、全量灌进去。

## 目标

画像引入**条目模型 + recency 召回**：偏好/易变类带 **tag + 时间戳**，注入时**按相关性单条召回**，默认只召最近；稳定事实（职业/地点）维持平铺，降风险。

## 改动点

### 1. 条目模型（最小侵入，不动稳定字段）

`important_facts` 的元素从 `str` 升级为**兼容 dict**：`{text, tag, ts}`（旧 str 视为 `{text, tag:"misc", ts:0}`，读时归一化，**不强制迁移历史**）。
- `tag` 取受控小集合：`pref.music`(喜欢听的歌) / `pref.food` / `pref.media` / `habit` / `health` / `misc` …（够用即可，后续可加）。「likesing」就是 `pref.music`。
- 写入侧（`update`/抽取 prompt `:198`）让 LLM 给新事实**打 tag + 写当前 ts**。压缩逻辑保留。

### 2. 层 5 注入改条件召回（核心）

`prompt_builder.py:655-676` 拆两段：
- **稳定段**（name/location/pets/occupation + tag 为稳定类的 important_facts）：维持平铺，照旧。
- **易变/偏好段**（`pref.*`、`habit` 等带 ts 的条目）：**默认只注入最近 window 内**（如 90 天）的条目；**除非**本轮 tag/语义命中该偏好（如用户问起音乐 → 注入 `pref.music` 不论新旧）。
  - recency：按 `ts` 倒序取 top-N；「明确提到几个月前喜欢的」= 当 query 命中该 tag 时放开时间窗。
  - 单条注入、各占一行，沿用 `_provenance{mode:"tagged"/"recency"}`。

### 3.（可选增强，依赖 X1）语义召回挑偏好

当本轮 query 与某偏好条目语义相关时召回：`vector_store.query(sources=["profile"], ...)`。需要先把 profile 偏好条目 `upsert(source="profile")`。**MVP 可不做**，先用 tag 命中 + recency；X2 落地后再接语义。

## 验收

1. 旧 `important_facts`（纯 str）仍能读、能注入（归一化兜底）。
2. 新增一条 `pref.music`（旧 ts）+ 一条近期 `habit`：平时只注入近期 habit；用户问「我喜欢听什么」→ `pref.music` 被召回。
3. 稳定字段（职业/地点）行为不变。
4. 层 5 总注入字数较改造前下降（不再全量平铺）。

## 文档同步
`docs/memory.md` 更新画像条目模型与层 5 召回规则。
