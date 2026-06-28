# X2-IMPL · 召回评分接入 query relevance（语义）

> 后端（Emerald-presence）。
> **前置**：X1 向量库（✓ 已落地，`vector_store.score_recall()` 是预留接管点，`query()` 返回距离）。**强依赖 X1**。
> **可并行**：与注入簇/梦境簇无冲突；但与 P3 的「语义召回偏好」共用 `vector_store.query`，建议同人做或先做 X2 定标。
> opus 早提过：召回评分缺 query relevance。

## 现状（已核对）

- `event_log.search`（`event_log.py:355+`）：`score = intensity × decay`（decay=1/(days_ago+1)），query 相关性只有 `relevance = hit/len(keywords)`（字符级关键词重叠），再 `score + relevance`，`MIN_SCORE` 过滤。
- episodic 召回类似，强度×衰减为主。
- 即 **query 相关性是弱的关键词命中率**，语义不相关也可能因强度高被召回。

## 目标

把 **query relevance 升为一等公民**：用 X1 的语义相似度参与打分，和强度×衰减融合。

## 改动点

### 1. 修 X1 留下的距离/相似度符号问题（先做）

`vector_store.query()` 返回 **distance（越小越近）**，而 `score_recall()` 按"越大越好"。统一：在 query 出口或 score_recall 入口把 distance 转 similarity（如 `sim = 1/(1+dist)` 或 `1 - dist/maxdist`），**全链统一用 similarity（越大越相关）**。

### 2. 融合公式（落进 `score_recall()`）

```python
final = w_sem*semantic_sim + w_kw*keyword_relevance + w_str*(intensity*decay)
```
- 权重从 config 读（`recall.weights: {sem, kw, strength}`，给默认值，便于你调）。
- `semantic_sim` 来自 `vector_store.query` 命中（转 similarity 后）；query 向量在 `pipeline.py:224` 召回处 `embed([content])` 算一次复用。
- 无 embedding（API 不可用）时 `w_sem` 项自动置 0、退回原 kw+strength（fail-open，X1 已保证 query 返回 []）。

### 3. 接入两路召回

- `event_log.search`：候选取 keyword 命中 ∪ 语义命中，统一过 `score_recall` 排序，`MIN_SCORE` 阈值按新量纲重标。
- episodic 召回同理接 `score_recall`。

## 验收

1. 语义相关但无关键词重叠的往事**能被召回**（旧关键词路径召不回的，现在召得回）。
2. 强度高但与本轮 query 无关的记忆**排名下降**（不再仅凭强度挤进来）。
3. 断网（embedding 不可用）→ 自动退回 kw+strength，召回不崩。
4. 调 `recall.weights` 能明显改变排序（证明可调）。

## 文档同步
新增/更新 `docs/vector-store.md` 或 `docs/memory.md` 的召回评分段，写清融合公式与权重配置。
