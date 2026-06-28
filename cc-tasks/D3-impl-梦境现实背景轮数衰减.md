# D3-IMPL · 梦境现实背景注入：轮数后衰减为概括

> 后端（Emerald-presence）。**小改**。
> **前置**：无硬前置（P1 骨架的"轮数后降级"思路可参照，但 D3 在梦境侧独立实现）。
> **可并行**：与 D2 改不同文件，可并行。
> 用户需求：梦境里**逐字的现实初始背景**在一定轮数后**停止注入**（防止把现实语感带进梦），但**保留概括的一句**（"你记得入梦前在做 xxx"）。

## 现状（已核对）

- 入梦时 `dream_context.build_snapshot` 冻结一份快照，含 `recent_reality_context`（`_summarize_recent` 最近几轮现实对话）。
- 注入在 `dream_prompt.py:319` 的 **D4·入梦前背景（冻结快照，只读）**，:547 把 `recent_reality_context` 作为"近期互动背景"注入。
- **问题**：这份逐字背景**每个梦境轮都原样注入、不随轮数变化**——越往后越容易把现实语感带歪梦境。

## 改动点

### 1. 拿到梦境轮数

dream 管线有梦内轮次计数（`dream_pipeline` / `dream_state` 里递增的 turn index）。D3 需要在构建 D4 时读到**当前是第几梦境轮**。若现成没有暴露，给 dream_prompt 构建处传入 `dream_turn: int`。

### 2. 两段式注入 `recent_reality_context`

在 `dream_prompt.py:547` 处按 `dream_turn` 分叉：
- **前 N 轮**（如 N=3）：注入**完整** `recent_reality_context`（现状行为）。
- **N 轮之后**：**不再注入逐字背景**，改注入**一句概括**：`（你记得入梦前你们在{gist}）`，其中 `gist` 是 `recent_reality_context` 的一句话浓缩（入梦时顺手在 snapshot 里存一个 `recent_reality_gist` 字段，或注入时即时截一句）。
- N 可配置（`dream.reality_context_full_turns`，默认 3）。

### 3. gist 来源

在 `build_snapshot`（`dream_context.py:79`）算 `recent_reality_context` 时，**顺手生成一句 gist** 存进 snapshot（如取 `_summarize_recent` 的首句，或一次轻量浓缩）。避免梦中再调 LLM——snapshot 是冻结只读的，gist 也应在入梦时一次算好冻结。

## 验收

1. 梦境前 N 轮：D4 含完整入梦前背景。
2. 第 N+1 轮起：逐字背景消失，只剩"你记得入梦前在做 xxx"一句。
3. 梦境语感在后段不再被现实对话原文带偏（人工读几轮确认）。
4. gist 在入梦时冻结，梦中不二次调 LLM。

## 文档同步
`docs/` 梦境文档记 D4 的轮数衰减规则与 `dream.reality_context_full_turns` 配置。
